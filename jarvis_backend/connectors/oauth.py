"""OAuth2 token management for connector integrations (Gmail, Outlook, ...).

Design (spec §7/#8/#19/#20/#21):
  * The OAuth *protocol* (authorize URL + HMAC-bound state + code exchange +
    refresh) is general and driven by ``JARVIS_OAUTH_CLIENTS`` (registered in
    ``start_all.ps1``), so Gmail, Outlook, GitHub etc. all flow through one,
    audited path.
  * Tokens are encrypted at rest with the platform's Fernet vault
    (``connectors.crypto``) and persisted in the SQL KV store under the
    ``oauth_tokens`` collection, keyed per ``(connector kind, user id)``.
  * Only the backend ever holds a plaintext token.  The API exposes
    connection metadata only — never the access token, never the refresh
    token, never an access token in any log line.

This is the shared helper; the Gmail/Outlook ``Connector`` subclasses call
:func:`access_token` to get a (refreshed) bearer, then call the provider REST
API directly.  Silverwing/JARVIS never receives a credential.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx

from .crypto import ConnectorCryptoError, decrypt_secret, encrypt_secret
from ..core import get_store, now_iso

# A captured authorization-code exchange is short-lived; the state that binds
# authorize->callback is valid for this long (seconds).
STATE_TTL = 600  # 10 minutes

# Per-user key so a single install can hold tokens for several accounts.
def _key(kind: str, user_id: str) -> str:
    return f"{kind}:{user_id}"


class OAuthError(Exception):
    """Raised on any OAuth protocol failure (state mismatch, bad code, ...)."""


def _state_secret() -> bytes:
    key = os.environ.get("JARVIS_SECRET_KEY", "")
    if not key:
        raise OAuthError("JARVIS_SECRET_KEY must be configured before enabling OAuth")
    return key.encode("utf-8")


# --------------------------------------------------------------------------- #
# State: binds an authorize request to its callback (CSRF + replay defence).
# --------------------------------------------------------------------------- #
def make_state(kind: str, user_id: str) -> str:
    """Opaque, signed state token binding ``kind``+``user_id``+timestamp."""
    payload = base64.urlsafe_b64encode(
        json.dumps({"k": kind, "u": user_id, "t": int(time.time())}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    sig = hmac.new(_state_secret(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_state(state: str, ttl: int = STATE_TTL) -> Tuple[str, str]:
    """Validate a state token, returning ``(kind, user_id)`` or raising OAuthError."""
    payload, _, sig = state.partition(".")
    if not payload or not sig:
        raise OAuthError("malformed state")
    expected = hmac.new(_state_secret(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise OAuthError("invalid state signature")
    pad = "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
    except Exception as exc:  # noqa: BLE001
        raise OAuthError("invalid state payload") from exc
    if int(time.time()) - int(data.get("t", 0)) > ttl:
        raise OAuthError("state expired")
    return data["k"], data["u"]


# --------------------------------------------------------------------------- #
# Client config (read from JARVIS_OAUTH_CLIENTS, populated by start_all.ps1).
# --------------------------------------------------------------------------- #
def client_config(kind: str) -> Optional[Dict[str, Any]]:
    """Return the OAuth client config for ``kind`` from ``JARVIS_OAUTH_CLIENTS``."""
    raw = os.environ.get("JARVIS_OAUTH_CLIENTS")
    if not raw:
        return None
    try:
        clients = json.loads(raw)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None
    cfg = clients.get(kind)
    if not isinstance(cfg, dict) or not cfg.get("client_id"):
        return None
    return cfg


def _backend_base() -> str:
    return os.environ.get("NEXT_PUBLIC_API_URL", "http://127.0.0.1:8000").rstrip("/")


def authorize_url(kind: str, user_id: str, scope: Optional[str] = None) -> str:
    """Build the provider's authorize URL for ``kind`` (HMAC-signed state)."""
    cfg = client_config(kind)
    if not cfg:
        raise OAuthError(f"no OAuth client configured for '{kind}'")
    state = make_state(kind, user_id)
    redirect_uri = f"{_backend_base()}/api/v1/connectors/oauth/callback/{kind}"
    params: Dict[str, Any] = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    # Google/Microsoft both want an explicit offline access prompt for refresh.
    if cfg.get("is_google", False) or cfg.get("is_microsoft", False):
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    sc = scope or cfg.get("scope")
    if sc:
        params["scope"] = sc
    sep = "&" if "?" in cfg["authorize_url"] else "?"
    return f"{cfg['authorize_url']}{sep}{urlencode(params)}"


# --------------------------------------------------------------------------- #
# Secure storage (encrypted at rest; server-side only).
# --------------------------------------------------------------------------- #
def save_tokens(kind: str, user_id: str, tokens: Dict[str, Any]) -> None:
    """Persist an encrypted token set for ``(kind, user_id)``."""
    s = get_store("oauth_tokens").load()
    def _enc(v: Optional[str]) -> Optional[str]:
        return encrypt_secret(v) if v else None
    s[_key(kind, user_id)] = {
        "access_token": _enc(tokens.get("access_token")),
        "refresh_token": _enc(tokens.get("refresh_token")),
        "access_expires_at": tokens.get("expires_at"),
        "account": tokens.get("account"),
        "scope": tokens.get("scope") or tokens.get("granted_scope"),
        "provider": tokens.get("provider") or kind,
        "updated_at": now_iso(),
    }
    get_store("oauth_tokens").save()


def load_tokens(kind: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Load + decrypt a token set (server-side only). Returns plaintext access/refresh."""
    s = get_store("oauth_tokens").load()
    raw = s.get(_key(kind, user_id))
    if not raw:
        return None
    out = dict(raw)
    for f in ("access_token", "refresh_token"):
        v = out.get(f)
        if isinstance(v, str) and v.startswith("fernet:"):
            try:
                out[f] = decrypt_secret(v)
            except ConnectorCryptoError:
                out[f] = None  # unrecoverable -> surface honestly
    return out


def delete_tokens(kind: str, user_id: str) -> bool:
    s = get_store("oauth_tokens").load()
    k = _key(kind, user_id)
    if k in s:
        del s[k]
        get_store("oauth_tokens").save()
        return True
    return False


def token_expired(tok: Dict[str, Any]) -> bool:
    exp = tok.get("access_expires_at")
    # Opaque OAuth tokens from providers such as GitHub OAuth Apps and API keys
    # often have no advertised expiry. Treat absent expiry as non-expiring;
    # providers that do expire tokens must supply an explicit expiry timestamp.
    if exp is None:
        return False
    try:
        return float(exp) <= time.time() + 30
    except (TypeError, ValueError):
        return True


def connection_metadata(kind: str, user_id: str) -> Dict[str, Any]:
    """Safe-to-return profile for the frontend (spec §20): no tokens, ever.

    status enum (spec §38/§21): Authorization required | Expired | Connected | Revoked.
    """
    tok = load_tokens(kind, user_id)
    if not tok:
        return {"connected": False, "status": "Authorization required"}
    has_token = bool(tok.get("access_token") or tok.get("refresh_token"))
    if not has_token:
        return {"connected": False, "status": "Authorization required"}
    expired_acc = token_expired(tok) if tok.get("access_token") else False
    if expired_acc and not tok.get("refresh_token"):
        return {"connected": False, "status": "Expired",
                "account": tok.get("account"), "token_expires_at": tok.get("access_expires_at")}
    status = "Expired" if (expired_acc and tok.get("refresh_token")) else "Connected"
    return {
        "connected": True,
        "status": status,
        "account": tok.get("account") or tok.get("provider"),
        "scope": tok.get("scope"),
        "token_expires_at": tok.get("access_expires_at"),
        "expired": expired_acc,
        "updated_at": tok.get("updated_at"),
    }


# --------------------------------------------------------------------------- #
# Token acquisition (with lazy refresh).
# --------------------------------------------------------------------------- #
def _refresh(cfg: Dict[str, Any], refresh_token: str) -> Optional[Dict[str, Any]]:
    try:
        r = httpx.post(cfg["token_url"], data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }, timeout=15)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    d = r.json()
    return {
        "access_token": d.get("access_token"),
        "refresh_token": d.get("refresh_token") or refresh_token,
        "expires_at": time.time() + int(d.get("expires_in", 0)),
    }


def access_token(kind: str, user_id: str, cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return a valid access token for ``kind``, refreshing the stored refresh token server-side."""
    tok = load_tokens(kind, user_id)
    if not tok:
        return None
    if tok.get("access_token") and not token_expired(tok):
        return tok["access_token"]
    if not tok.get("refresh_token"):
        return None
    cfg = cfg or client_config(kind)
    if not cfg:
        return None
    refreshed = _refresh(cfg, tok["refresh_token"])
    if refreshed is None:
        return None
    refreshed["account"] = tok.get("account")
    refreshed["scope"] = tok.get("scope") or tok.get("provider")
    refreshed["provider"] = tok.get("provider") or kind
    save_tokens(kind, user_id, refreshed)
    return refreshed.get("access_token")


# --------------------------------------------------------------------------- #
# Authorization-code exchange (called from the callback route).
# --------------------------------------------------------------------------- #
def _extract_account(kind: str, token_resp: Dict[str, Any]) -> str:
    """Best-effort account (email) from the token response without an extra API call."""
    id_token = token_resp.get("id_token")
    if id_token and isinstance(id_token, str) and id_token.count(".") >= 1:
        try:
            body = id_token.split(".")[1]
            body += "=" * (-len(body) % 4)
            payload = json.loads(base64.urlsafe_b64decode(body))
            if isinstance(payload, dict):
                return payload.get("email") or payload.get("preferred_username") or ""
        except Exception:  # noqa: BLE001
            pass
    return ""


def exchange_code(kind: str, code: str, state: str, user_id: str) -> Dict[str, Any]:
    """Validate state + exchange an auth code for tokens. Raises OAuthError on failure."""
    k, uid = verify_state(state)
    if k != kind or uid != user_id:
        raise OAuthError("state does not match the original request")
    cfg = client_config(kind)
    if not cfg:
        raise OAuthError(f"no OAuth client configured for '{kind}'")
    redirect_uri = f"{_backend_base()}/api/v1/connectors/oauth/callback/{kind}"
    r = httpx.post(cfg["token_url"], data={
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "scope": cfg.get("scope", ""),
    }, timeout=15)
    if r.status_code != 200:
        raise OAuthError(f"token exchange failed: HTTP {r.status_code}")
    d = r.json()
    tokens = {
        "access_token": d.get("access_token"),
        "refresh_token": d.get("refresh_token"),
        "expires_at": time.time() + int(d.get("expires_in", 0)),
        "account": _extract_account(kind, d),
        "scope": d.get("scope") or cfg.get("scope"),
        "provider": kind,
    }
    save_tokens(kind, user_id, tokens)
    return tokens


def audit_record(actor: str, kind: str, operation: str, ok: bool,
                 user_id: Optional[str] = None, detail: Optional[str] = None) -> None:
    """Append an OAuth/connection audit record (spec §27 shape). Never logs tokens."""
    from . import registry
    registry.audit({
        "ts": now_iso(),
        "actor": actor,
        "user_id": user_id,
        "kind": kind,
        "operation": operation,
        "ok": bool(ok),
        "detail": detail or "",
    })
