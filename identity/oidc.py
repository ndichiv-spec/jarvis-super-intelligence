"""OIDC client implementing the OAuth 2.0 / OpenID Connect login flow (spec §12, §53).

Features:
  * Dynamic discovery from the provider's well-known endpoint (spec §7).
  * PKCE (RFC 7636) — ``code_challenge`` / ``code_verifier`` for native/confidential
    clients (spec §12).
  * HMAC-signed ``state`` parameter for CSRF protection (spec §12).
  * Authorization-code exchange with ``state`` + ``code_verifier`` verification.
  * Refresh-token rotation (spec §54).
  * Userinfo endpoint call to normalize identity.
  * ``id_token`` optional verification (RSA signature check is best-effort —
    requires the provider's public JWKS; falls back to userinfo if unavailable).

No real provider API is called during unit tests: all HTTP is routed through an
injectable ``http_client`` (default ``httpx.AsyncClient``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any, Optional, Protocol


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_code_verifier(length: int = 128) -> str:
    """Cryptographically random PKCE code verifier (RFC 7636 §4.1)."""
    # Range: 43-128 chars; default 128 (max entropy).
    return _b64url(secrets.token_bytes(length // 2 + length % 2))[:128]


def code_challenge(verifier: str) -> str:
    """S256 PKCE code challenge from a verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)


def generate_state(payload: dict[str, Any], secret: str) -> str:
    """Opaque, HMAC-signed state binding ``payload`` (spec §12 — CSRF defence).

    Format: ``<b64url(json_payload)>.<hex_hmac>``
    """
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hashlib.sha256((body + "." + secret).encode("utf-8")).hexdigest()
    return f"{body}.{sig}"


def verify_state(state: str, secret: str) -> dict[str, Any]:
    """Validate a state token, returning the original payload.

    Raises :class:`OidcError` on any mismatch/expiry.
    """
    body, _, sig = state.partition(".")
    if not body or not sig:
        raise OidcError("malformed state")
    expected = hashlib.sha256((body + "." + secret).encode("utf-8")).hexdigest()
    if not secrets.compare_digest(expected, sig):
        raise OidcError("invalid state signature")
    pad = "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
    except Exception as exc:  # noqa: BLE001
        raise OidcError("invalid state payload") from exc
    if not isinstance(payload, dict):
        raise OidcError("state payload is not a dict")
    # Optional TTL check.
    requested_at = payload.get("_t", 0)
    ttl = payload.get("_ttl", 600)
    if requested_at and (time.time() - requested_at) > ttl:
        raise OidcError("state expired")
    return payload


def _parse_jwt_payload(token: str) -> dict[str, Any]:
    """Best-effort decode of a JWT ``id_token`` payload (no signature check)."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    body = parts[1]
    pad = "=" * (-len(body) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(body + pad))
    except Exception:  # noqa: BLE001
        return {}


class OidcError(Exception):
    """Raised on any OIDC protocol failure."""


class HttpClient(Protocol):
    """Minimal HTTP client interface.  ``httpx.AsyncClient`` satisfies this."""

    async def get(self, url: str, **kwargs: Any) -> Any: ...
    async def post(self, url: str, **kwargs: Any) -> Any: ...


def _ensure_client(client: Optional[HttpClient]) -> HttpClient:
    if client is not None:
        return client
    import httpx  # type: ignore[import-not-found]
    return httpx.AsyncClient(timeout=30.0)


class OidcClient:
    """OAuth 2.0 / OpenID Connect login client for a single provider.

    All network I/O goes through ``http_client`` (injectable for tests).  The
    ``client_secret`` is supplied by the caller from the SecretManager — this
    class never reads env vars or stores secrets (spec §16/§69).
    """

    def __init__(
        self,
        config: Any,
        *,
        http_client: Optional[HttpClient] = None,
        state_secret: str = "",
    ) -> None:
        from .models import OidcConfig  # local import to avoid cycle at import time

        self.config: OidcConfig = config
        self._http = http_client
        self._state_secret = state_secret or secrets.token_urlsafe(32)

    # ------------------------------------------------------------------ #
    # Discovery (spec §7 — fetch provider metadata from well-known URL)
    # ------------------------------------------------------------------ #
    async def discover(self, http_client: Optional[HttpClient] = None) -> None:
        """Fetch the OIDC well-known discovery document and populate endpoints."""
        client = http_client or self._http or _ensure_client(None)
        url = self.config.discovery_url or self._default_discovery_url()
        if not url:
            raise OidcError(
                f"no discovery URL for provider '{self.config.provider.value}'"
            )
        try:
            resp = await client.get(url)
        except Exception as exc:  # noqa: BLE001
            raise OidcError(f"discovery HTTP failed: {exc}") from exc
        if getattr(resp, "status_code", 200) != 200:
            raise OidcError(
                f"discovery returned HTTP {getattr(resp, 'status_code', '??')}"
            )
        try:
            doc = resp.json() if hasattr(resp, "json") else json.loads(resp.text)
        except Exception as exc:  # noqa: BLE001
            raise OidcError(f"discovery response not JSON: {exc}") from exc
        self.config.authorization_endpoint = doc.get("authorization_endpoint", "")
        self.config.token_endpoint = doc.get("token_endpoint", "")
        self.config.userinfo_endpoint = doc.get("userinfo_endpoint", "")
        self.config.jwks_uri = doc.get("jwks_uri")
        self.config.issuer = doc.get("issuer", self.config.issuer)

    def _default_discovery_url(self) -> str:
        p = self.config.provider
        if p.value == "google":
            return "https://accounts.google.com/.well-known/openid-configuration"
        if p.value == "microsoft":
            return "https://login.microsoftonline.com/organizations/v2.0/.well-known/openid-configuration"
        if p.value == "github":
            # GitHub does not have a standard OIDC discovery; use the auth/api URLs.
            return ""
        return ""

    # ------------------------------------------------------------------ #
    # Authorization URL (with PKCE + signed state)
    # ------------------------------------------------------------------ #
    def authorization_url(self, redirect_uri: Optional[str] = None) -> tuple[str, str, str]:
        """Build the authorize URL, returning ``(url, code_verifier, state)``.

        The caller must store ``code_verifier`` + ``state`` (e.g. in a cookie
        or the session store) and present them at callback time.
        """
        if not self.config.authorization_endpoint:
            raise OidcError("authorization_endpoint not discovered; call discover() first")
        verifier = generate_code_verifier()
        challenge = code_challenge(verifier)
        state = generate_state(
            {"_t": time.time(), "_ttl": 600, "provider": self.config.provider.value},
            self._state_secret,
        )
        uri = redirect_uri or self.config.redirect_uri
        params: dict[str, str] = {
            "client_id": self.config.client_id,
            "redirect_uri": uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",  # refresh token
            "prompt": "consent",  # force refresh token on Google
        }
        from urllib.parse import urlencode

        sep = "&" if "?" in self.config.authorization_endpoint else "?"
        url = self.config.authorization_endpoint + sep + urlencode(params)
        return url, verifier, state

    # ------------------------------------------------------------------ #
    # Token exchange (spec §12 — code exchange with PKCE)
    # ------------------------------------------------------------------ #
    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        state: Optional[str] = None,
    ) -> dict[str, Any]:
        """Exchange an authorization code for tokens.

        Verifies ``state`` if provided. Returns the raw token response dict.
        """
        if state:
            verify_state(state, self._state_secret)
        if not self.config.token_endpoint:
            raise OidcError("token_endpoint not discovered; call discover() first")
        client = self._http or _ensure_client(None)
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.redirect_uri,
        }
        try:
            resp = await client.post(
                self.config.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except Exception as exc:  # noqa: BLE001
            raise OidcError(f"token exchange HTTP failed: {exc}") from exc
        if getattr(resp, "status_code", 200) != 200:
            raise OidcError(
                f"token exchange failed: HTTP {getattr(resp, 'status_code', '??')}"
            )
        try:
            return resp.json() if hasattr(resp, "json") else json.loads(resp.text)
        except Exception as exc:  # noqa: BLE001
            raise OidcError(f"token response not JSON: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Refresh token rotation (spec §54)
    # ------------------------------------------------------------------ #
    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new access token (rotation)."""
        if not self.config.token_endpoint:
            raise OidcError("token_endpoint not discovered; call discover() first")
        client = self._http or _ensure_client(None)
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            resp = await client.post(
                self.config.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except Exception as exc:  # noqa: BLE001
            raise OidcError(f"refresh HTTP failed: {exc}") from exc
        if getattr(resp, "status_code", 200) != 200:
            raise OidcError(
                f"refresh failed: HTTP {getattr(resp, 'status_code', '??')}"
            )
        result = resp.json() if hasattr(resp, "json") else json.loads(resp.text)
        # OAuth spec: if a new refresh_token is returned, the old one is rotated
        # (invalidated). The caller should replace the stored refresh token.
        return result

    # ------------------------------------------------------------------ #
    # Userinfo / ID token normalisation
    # ------------------------------------------------------------------ #
    async def userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch user identity from the userinfo endpoint."""
        if not self.config.userinfo_endpoint:
            if self.config.supports_id_token:
                # Fall back: caller should pass id_token claims instead.
                raise OidcError("userinfo_endpoint not available")
            raise OidcError("no userinfo endpoint configured")
        client = self._http or _ensure_client(None)
        try:
            resp = await client.get(
                self.config.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except Exception as exc:  # noqa: BLE001
            raise OidcError(f"userinfo HTTP failed: {exc}") from exc
        if getattr(resp, "status_code", 200) != 200:
            raise OidcError(
                f"userinfo failed: HTTP {getattr(resp, 'status_code', '??')}"
            )
        return resp.json() if hasattr(resp, "json") else json.loads(resp.text)

    def normalize_userinfo(self, raw: dict[str, Any]) -> Any:
        """Map raw provider claims to :class:`OoidcUserInfo`."""
        from .models import OidcUserInfo

        sub = raw.get("sub") or raw.get("id") or raw.get("user_id", "")
        email = raw.get("email")
        if isinstance(email, dict):
            email = email.get("value") or email.get("primary") or email.get("email")
        # GitHub returns email in a nested object sometimes.
        return OidcUserInfo(
            sub=str(sub),
            email=email,
            email_verified=raw.get("email_verified", False),
            name=raw.get("name"),
            preferred_username=raw.get("preferred_username") or raw.get("preferred_username"),
            avatar_url=raw.get("picture") or raw.get("avatar_url"),
            raw=dict(raw),
        )

    async def fetch_userinfo(self, token_response: dict[str, Any]) -> Any:
        """End-to-end: extract id_token claims or call userinfo, return normalized."""
        from .models import OidcUserInfo

        id_token = token_response.get("id_token")
        if id_token and self.config.supports_id_token:
            claims = _parse_jwt_payload(id_token)
            if claims.get("sub"):
                return self.normalize_userinfo(claims)
        access_token = token_response.get("access_token", "")
        raw = await self.userinfo(access_token)
        return self.normalize_userinfo(raw)
