"""Tests for the JARVIS unified identity layer (spec §12, §15, §53, §54).

Covers:
  * OIDC PKCE + signed-state helpers
  * OidcClient (discovery, authorize URL, code exchange, refresh, userinfo)
  * SessionManager (lifecycle, CSRF, rate-limiting / anomaly detection)
  * AccountLinker (link, find, unlink, resolve-or-create)
  * PermissionEngine (RBAC: role perms, scopes, wildcards, escalation guard)
  * ProviderConnectionManager (connection status, test, disconnect — no secrets)
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

import pytest

from identity.linking import AccountLinker
from identity.models import (
    AccountLink,
    ConnectionStatus,
    IdentityProvider,
    IdentitySession,
    OidcConfig,
    OidcUserInfo,
    ProviderConnection,
)
from identity.oidc import (
    OidcClient,
    OidcError,
    code_challenge,
    generate_code_verifier,
    generate_state,
    verify_state,
)
from identity.provider_center import ProviderConnectionManager
from identity.rbac import CANONICAL_ROLES, PermissionEngine
from identity.session import LoginAttemptTracker, MemorySessionStore, SessionManager


# --------------------------------------------------------------------------- #
# Fake HTTP client for OidcClient tests
# --------------------------------------------------------------------------- #
@dataclass
class FakeResponse:
    status_code: int = 200
    _json: dict[str, Any] = None  # type: ignore[assignment]
    text: str = ""

    def __post_init__(self) -> None:
        if self._json is None:
            self._json = {}

    def json(self) -> dict[str, Any]:
        return self._json


class FakeOidcHTTP:
    """Records calls and returns canned responses for OIDC endpoints."""

    def __init__(self) -> None:
        self.responses: dict[str, FakeResponse] = {}
        self.calls: list[tuple[str, str]] = []

    def set_discovery(self, doc: dict) -> "FakeOidcHTTP":
        self.responses["discovery"] = FakeResponse(200, doc, json.dumps(doc))
        return self

    def set_token(self, doc: dict) -> "FakeOidcHTTP":
        self.responses["token"] = FakeResponse(200, doc, json.dumps(doc))
        return self

    def set_userinfo(self, doc: dict) -> "FakeOidcHTTP":
        self.responses["userinfo"] = FakeResponse(200, doc, json.dumps(doc))
        return self

    def set_error(self, status: int, detail: str = "error") -> "FakeOidcHTTP":
        self.responses["error"] = FakeResponse(status, {}, detail)
        return self

    async def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append(("GET", url))
        if "discovery" in self.responses and ("well-known" in url or "openid-configuration" in url):
            return self.responses["discovery"]
        if "userinfo" in self.responses:
            return self.responses["userinfo"]
        if "error" in self.responses:
            return self.responses["error"]
        return FakeResponse(404, {}, "not found")

    async def post(self, url: str, **kwargs: Any) -> Any:
        self.calls.append(("POST", url))
        if "token" in self.responses:
            return self.responses["token"]
        if "error" in self.responses:
            return self.responses["error"]
        return FakeResponse(404, {}, "not found")


# --------------------------------------------------------------------------- #
# PKCE + state helpers
# --------------------------------------------------------------------------- #
class TestPKCEAndState:
    def test_code_verifier_length_in_range(self):
        v = generate_code_verifier()
        assert 43 <= len(v) <= 128

    def test_code_verifier_is_random(self):
        v1 = generate_code_verifier()
        v2 = generate_code_verifier()
        assert v1 != v2

    def test_code_challenge_is_base64url_s256(self):
        v = generate_code_verifier()
        c = code_challenge(v)
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(v.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        assert c == expected

    def test_state_round_trip(self):
        payload = {"provider": "google", "_t": time.time(), "_ttl": 600}
        state = generate_state(payload, "secret-key")
        decoded = verify_state(state, "secret-key")
        assert decoded["provider"] == "google"

    def test_state_rejects_tampered_signature(self):
        state = generate_state({"provider": "google", "_t": time.time(), "_ttl": 600}, "secret")
        with pytest.raises(OidcError):
            verify_state(state, "wrong-secret")

    def test_state_rejects_expired(self):
        payload = {"_t": time.time() - 9999, "_ttl": 600}
        state = generate_state(payload, "secret")
        with pytest.raises(OidcError):
            verify_state(state, "secret")

    def test_state_rejects_malformed(self):
        with pytest.raises(OidcError):
            verify_state("garbage", "secret")


# --------------------------------------------------------------------------- #
# OidcClient
# --------------------------------------------------------------------------- #
def _make_config(provider="google", client_id="cid", client_secret="sec"):
    return OidcConfig(
        provider=IdentityProvider(provider),
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8000/api/v1/identity/callback/google",
        scopes=["openid", "email", "profile"],
        discovery_url="https://example.com/.well-known/openid-configuration",
    )


class TestOidcClient:
    @pytest.mark.asyncio
    async def test_discover_populates_endpoints(self):
        cfg = _make_config()
        fake = FakeOidcHTTP().set_discovery({
            "authorization_endpoint": "https://accounts.example.com/o/oauth2/auth",
            "token_endpoint": "https://accounts.example.com/o/oauth2/token",
            "userinfo_endpoint": "https://accounts.example.com/o/oauth2/userinfo",
            "jwks_uri": "https://accounts.example.com/.well-known/jwks",
            "issuer": "https://accounts.example.com",
        })
        client = OidcClient(cfg, http_client=fake)
        await client.discover()
        assert cfg.authorization_endpoint == "https://accounts.example.com/o/oauth2/auth"
        assert cfg.token_endpoint == "https://accounts.example.com/o/oauth2/token"
        assert cfg.userinfo_endpoint == "https://accounts.example.com/o/oauth2/userinfo"
        assert cfg.jwks_uri == "https://accounts.example.com/.well-known/jwks"

    @pytest.mark.asyncio
    async def test_discover_http_failure_raises(self):
        cfg = _make_config()
        fake = FakeOidcHTTP().set_error(500)
        client = OidcClient(cfg, http_client=fake)
        with pytest.raises(OidcError):
            await client.discover()

    def test_authorization_url_contains_pkce_and_state(self):
        cfg = _make_config()
        cfg.authorization_endpoint = "https://accounts.example.com/o/oauth2/auth"
        client = OidcClient(cfg)
        url, verifier, state = client.authorization_url()
        assert "client_id=cid" in url
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        assert "state=" in url
        assert "response_type=code" in url
        assert len(verifier) >= 43
        assert state.count(".") == 1  # HMAC signature separator

    def test_authorization_url_raises_when_not_discovered(self):
        cfg = _make_config()
        client = OidcClient(cfg)
        with pytest.raises(OidcError):
            client.authorization_url()

    @pytest.mark.asyncio
    async def test_exchange_code_success(self):
        cfg = _make_config()
        cfg.token_endpoint = "https://accounts.example.com/o/oauth2/token"
        fake = FakeOidcHTTP().set_token({
            "access_token": "at-123",
            "id_token": "header.body.sig",
            "refresh_token": "rt-123",
            "expires_in": 3600,
        })
        client = OidcClient(cfg, http_client=fake)
        payload = {"test": True, "_t": time.time(), "_ttl": 600, "provider": "google"}
        state = generate_state(payload, client._state_secret)
        code_verifier = generate_code_verifier()
        tokens = await client.exchange_code("auth-code", code_verifier, state=state)
        assert tokens["access_token"] == "at-123"
        assert tokens["refresh_token"] == "rt-123"
        assert "POST" in str(fake.calls[0])

    @pytest.mark.asyncio
    async def test_exchange_code_rejects_bad_state(self):
        cfg = _make_config()
        cfg.token_endpoint = "https://accounts.example.com/o/oauth2/token"
        fake = FakeOidcHTTP().set_token({"access_token": "ok"})
        client = OidcClient(cfg, http_client=fake)
        bad_state = generate_state({"_t": time.time(), "_ttl": 600}, "wrong-secret")
        with pytest.raises(OidcError):
            await client.exchange_code("code", generate_code_verifier(), state=bad_state)

    @pytest.mark.asyncio
    async def test_exchange_code_http_failure(self):
        cfg = _make_config()
        cfg.token_endpoint = "https://accounts.example.com/o/oauth2/token"
        fake = FakeOidcHTTP().set_error(400)
        client = OidcClient(cfg, http_client=fake)
        state = generate_state({"_t": time.time(), "_ttl": 600}, client._state_secret)
        with pytest.raises(OidcError):
            await client.exchange_code("code", generate_code_verifier(), state=state)

    @pytest.mark.asyncio
    async def test_refresh_returns_new_tokens(self):
        cfg = _make_config()
        cfg.token_endpoint = "https://accounts.example.com/o/oauth2/token"
        fake = FakeOidcHTTP().set_token({
            "access_token": "at-new",
            "refresh_token": "rt-new",
            "expires_in": 3600,
        })
        client = OidcClient(cfg, http_client=fake)
        result = await client.refresh("old-refresh-token")
        assert result["access_token"] == "at-new"
        # Verify the refresh_token grant was sent.
        assert any("POST" in str(c) for c in fake.calls)

    @pytest.mark.asyncio
    async def test_fetch_userinfo_from_endpoint(self):
        cfg = _make_config()
        cfg.userinfo_endpoint = "https://accounts.example.com/o/oauth2/userinfo"
        fake = FakeOidcHTTP().set_userinfo({
            "sub": "user123",
            "email": "user@example.com",
            "name": "Test User",
        })
        client = OidcClient(cfg, http_client=fake)
        info = await client.fetch_userinfo({"access_token": "at-123"})
        assert info.sub == "user123"
        assert info.email == "user@example.com"
        assert info.name == "Test User"

    def test_normalize_userinfo_github_email_dict(self):
        cfg = _make_config()
        client = OidcClient(cfg)
        raw = {"sub": "42", "email": {"value": "gh@user.com", "primary": True}}
        info = client.normalize_userinfo(raw)
        assert info.email == "gh@user.com"

    @pytest.mark.asyncio
    async def test_fetch_userinfo_uses_id_token_when_present(self):
        cfg = _make_config()
        client = OidcClient(cfg)
        # Build a fake id_token.
        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(json.dumps({
            "sub": "idt-123", "email": "idt@test.com", "name": "IDT User",
        }).encode()).rstrip(b"=").decode()
        id_token = f"{header}.{body}.sig"
        info = await client.fetch_userinfo({"id_token": id_token, "access_token": "at"})
        assert info.sub == "idt-123"
        assert info.email == "idt@test.com"


# --------------------------------------------------------------------------- #
# SessionManager
# --------------------------------------------------------------------------- #
class TestSessionManager:
    def test_create_session(self):
        sm = SessionManager(store=MemorySessionStore())
        s = sm.create_session("user-1", ip="10.0.0.1", auth_method="password")
        assert s.user_id == "user-1"
        assert s.ip == "10.0.0.1"
        assert s.auth_method == "password"
        assert s.csrf_token is not None
        assert not s.revoked

    def test_get_session_valid(self):
        sm = SessionManager(store=MemorySessionStore())
        s = sm.create_session("user-1")
        assert sm.get_session(s.id) is not None
        assert sm.get_session(s.id).user_id == "user-1"

    def test_get_session_unknown_returns_none(self):
        sm = SessionManager(store=MemorySessionStore())
        assert sm.get_session("nonexistent") is None

    def test_get_session_revoked_returns_none(self):
        sm = SessionManager(store=MemorySessionStore())
        s = sm.create_session("user-1")
        sm.destroy_session(s.id)
        assert sm.get_session(s.id) is None

    def test_get_session_expired_returns_none(self):
        sm = SessionManager(store=MemorySessionStore(), access_ttl=1)
        s = sm.create_session("user-1")
        assert sm.get_session(s.id) is not None
        time.sleep(1.2)
        assert sm.get_session(s.id) is None

    def test_touch_updates_last_seen(self):
        sm = SessionManager(store=MemorySessionStore())
        s = sm.create_session("user-1")
        old = s.last_seen_at
        time.sleep(0.01)
        assert sm.touch(s.id)
        updated = sm.get_session(s.id)
        assert updated.last_seen_at > old

    def test_destroy_session(self):
        sm = SessionManager(store=MemorySessionStore())
        s = sm.create_session("user-1")
        assert sm.destroy_session(s.id)
        assert sm.get_session(s.id) is None
        assert not sm.destroy_session(s.id)  # already gone

    def test_csrf_token_verification(self):
        sm = SessionManager(store=MemorySessionStore())
        s = sm.create_session("user-1")
        assert sm.verify_csrf_token(s.id, s.csrf_token)
        assert not sm.verify_csrf_token(s.id, "bogus.token")
        assert not sm.verify_csrf_token(s.id, "")

    def test_csrf_token_bound_to_session(self):
        """CSRF token from session A must not validate for session B."""
        sm = SessionManager(store=MemorySessionStore())
        a = sm.create_session("user-1")
        b = sm.create_session("user-2")
        assert not sm.verify_csrf_token(b.id, a.csrf_token)
        assert not sm.verify_csrf_token(a.id, b.csrf_token)

    def test_rotate_session(self):
        sm = SessionManager(store=MemorySessionStore())
        old = sm.create_session("user-1", auth_method="password")
        new = sm.rotate_session(old.id)
        assert new is not None
        assert new.id != old.id
        assert new.user_id == old.user_id
        # Old session must be invalid.
        assert sm.get_session(old.id) is None
        assert sm.get_session(new.id) is not None

    def test_session_cookie_attrs_are_httponly(self):
        sm = SessionManager(store=MemorySessionStore())
        attrs = sm.session_cookie_attrs(secure=True)
        assert attrs["httponly"] == "true"
        assert attrs["secure"] == "true"
        assert attrs["samesite"] == "strict"

    def test_rate_limiting(self):
        sm = SessionManager(
            store=MemorySessionStore(),
            tracker=LoginAttemptTracker(max_attempts=3, window_seconds=60),
        )
        ip = "1.2.3.4"
        assert not sm.is_rate_limited(ip)
        for _ in range(3):
            sm.record_login_attempt(ip, success=False)
        assert sm.is_rate_limited(ip)

    def test_rate_limit_reset_on_success(self):
        sm = SessionManager(
            store=MemorySessionStore(),
            tracker=LoginAttemptTracker(max_attempts=3, window_seconds=60),
        )
        ip = "5.6.7.8"
        for _ in range(2):
            sm.record_login_attempt(ip, success=False)
        assert not sm.is_rate_limited(ip)
        sm.record_login_attempt(ip, success=True)
        assert not sm.is_rate_limited(ip)
        # Failures start fresh after reset.
        for _ in range(3):
            sm.record_login_attempt(ip, success=False)
        assert sm.is_rate_limited(ip)

    def test_login_anomaly_detection(self):
        sm = SessionManager(store=MemorySessionStore())
        known_ips = ["1.1.1.1", "2.2.2.2"]
        assert sm.login_anomaly("3.3.3.3", known_ips)
        assert not sm.login_anomaly("1.1.1.1", known_ips)


# --------------------------------------------------------------------------- #
# AccountLinker
# --------------------------------------------------------------------------- #
class _MemStore:
    """Reusable in-memory store with load()/save() for tests."""

    def __init__(self) -> None:
        self._d: dict[str, dict] = {}

    def load(self) -> dict[str, dict]:
        return self._d

    def save(self) -> None:
        pass


class TestAccountLinker:
    def _linker(self):
        return AccountLinker(_MemStore())

    def test_link_and_find(self):
        linker = self._linker()
        rec = linker.link("user-1", "google", "sub-123", email="a@b.c", token_vault_ref="vault:google:sub-123")
        found = linker.find_by_provider("google", "sub-123")
        assert found is not None
        assert found["jarvis_user_id"] == "user-1"
        assert found["access_token_ref"] == "vault:google:sub-123"

    def test_find_unknown_returns_none(self):
        assert self._linker().find_by_provider("google", "nope") is None

    def test_unlink_removes_link_not_user(self):
        linker = self._linker()
        linker.link("user-1", "google", "sub-123")
        assert linker.find_by_provider("google", "sub-123") is not None
        assert linker.unlink("google", "sub-123")
        assert linker.find_by_provider("google", "sub-123") is None

    def test_links_for_user(self):
        linker = self._linker()
        linker.link("user-1", "google", "g-1", email="a@b.c")
        linker.link("user-1", "github", "gh-1", email="a@b.c")
        links = linker.links_for_user("user-1")
        assert len(links) == 2
        # Links must be safe — no token references.
        for l in links:
            assert "access_token_ref" not in l
            assert l["connected"]

    def test_links_for_user_filters_correctly(self):
        linker = self._linker()
        linker.link("user-1", "google", "g-1")
        linker.link("user-2", "google", "g-2")
        assert len(linker.links_for_user("user-1")) == 1
        assert len(linker.links_for_user("user-2")) == 1

    def test_resolve_or_create_first_login(self):
        linker = self._linker()
        user_store = _MemStore()

        def create_user(email, name, provider):
            return {
                "id": "new-user-id",
                "email": email,
                "username": name,
                "roles": ["user"],
            }

        ui = OidcUserInfo(sub="google-sub-1", email="user@example.com", name="Test User")
        user, created = linker.resolve_or_create("google", ui, user_store, create_user)
        assert created
        assert user["id"] == "new-user-id"
        assert user["email"] == "user@example.com"
        assert user_store.load()["new-user-id"]["email"] == "user@example.com"
        # A link should now exist.
        link = linker.find_by_provider("google", "google-sub-1")
        assert link is not None
        assert link["jarvis_user_id"] == "new-user-id"

    def test_resolve_or_create_second_login_finds_existing(self):
        linker = self._linker()
        user_store = _MemStore()

        def create_user(email, name, provider):
            return {"id": "u1", "email": email, "username": name, "roles": ["user"]}

        ui = OidcUserInfo(sub="google-sub-1", email="user@example.com", name="Test User")
        user, created = linker.resolve_or_create("google", ui, user_store, create_user)
        assert created
        # Second login with the same (provider, sub)
        user2, created2 = linker.resolve_or_create("google", ui, user_store, create_user)
        assert not created2
        assert user2["id"] == "u1"

    def test_resolve_or_create_email_match_links(self):
        """User exists locally; OIDC login with matching email links, not dupes."""
        linker = self._linker()
        user_store = _MemStore()
        # Pre-seed a local user.
        user_store.load()["existing-id"] = {
            "id": "existing-id",
            "email": "existing@example.com",
            "username": "existing",
            "roles": ["user"],
        }

        ui = OidcUserInfo(sub="google-sub-2", email="existing@example.com", name="Existing User")
        user, created = linker.resolve_or_create("google", ui, user_store, lambda *a, **kw: {"id": "x"})
        assert not created  # should have found by email, not created
        assert user["id"] == "existing-id"
        # And a link should now exist.
        assert linker.find_by_provider("google", "google-sub-2") is not None

    def test_resolve_or_create_no_match_no_callback_raises(self):
        linker = self._linker()
        user_store = _MemStore()
        ui = OidcUserInfo(sub="orphan-sub", email="noone@nowhere.com")
        with pytest.raises(ValueError, match="no existing"):
            linker.resolve_or_create("google", ui, user_store)


# --------------------------------------------------------------------------- #
# PermissionEngine (RBAC)
# --------------------------------------------------------------------------- #
class _RoleStore:
    def __init__(self, roles=None):
        self._roles = roles or CANONICAL_ROLES

    def load(self):
        return dict(self._roles)


class TestPermissionEngine:
    def _engine(self):
        return PermissionEngine(_RoleStore())

    def test_owner_has_all(self):
        pe = self._engine()
        assert pe.has_permission({"roles": ["owner"]}, "identity:manage")
        assert pe.has_permission({"roles": ["owner"]}, "system:manage")
        assert pe.has_permission({"roles": ["admin"]}, "provider:rotate")

    def test_role_permissions_resolved(self):
        pe = self._engine()
        user = {"roles": ["viewer"]}
        assert pe.has_permission(user, "system:read")
        assert pe.has_permission(user, "monitoring:read")
        assert pe.has_permission(user, "agent:read")
        assert not pe.has_permission(user, "system:manage")
        assert not pe.has_permission(user, "identity:manage")

    def test_api_key_scopes_grant_permissions(self):
        """API-key principals derive authority from scopes, not owner roles."""
        pe = self._engine()
        key_principal = {"roles": [], "scopes": ["provider:read", "provider:rotate"]}
        assert pe.has_permission(key_principal, "provider:read")
        assert pe.has_permission(key_principal, "provider:rotate")
        assert not pe.has_permission(key_principal, "provider:manage")

    def test_principals_without_roles_have_no_permissions(self):
        """A bare principal (no roles, no scopes) has no permissions.

        In the real backend, API-key principals are constructed with only
        scopes (never the owner's roles), preventing privilege escalation
        (spec §8).  Here we verify the engine returns no permissions for a
        principal with no authority sources.
        """
        pe = self._engine()
        bare = {"roles": [], "scopes": []}
        assert not pe.has_permission(bare, "identity:manage")
        assert not pe.has_permission(bare, "system:read")
        assert not pe.has_permission(None, "anything")

    def test_scopes_augment_role_permissions(self):
        """A user with roles + scopes gets the union."""
        pe = self._engine()
        user = {"roles": ["viewer"], "scopes": ["training:create"]}
        assert pe.has_permission(user, "system:read")      # from viewer
        assert pe.has_permission(user, "training:create")   # from scope
        assert not pe.has_permission(user, "system:manage")  # neither grants it

    def test_wildcard_action(self):
        pe = self._engine()
        user = {"roles": ["user"]}  # user role has "read", "chat", etc.
        # Grant resource:* via a custom role.
        custom_roles = {"myrole": {"permissions": ["memory:*"]}}
        pe2 = PermissionEngine(_RoleStore(custom_roles))
        user2 = {"roles": ["myrole"]}
        assert pe2.has_permission(user2, "memory:write")
        assert pe2.has_permission(user2, "memory:delete")
        assert pe2.has_permission(user2, "memory:read")
        assert not pe2.has_permission(user2, "identity:read")

    def test_require_raises(self):
        pe = self._engine()
        user = {"roles": ["viewer"]}
        pe.require(user, "system:read")
        with pytest.raises(PermissionError):
            pe.require(user, "system:manage")

    def test_none_user_has_no_permissions(self):
        pe = self._engine()
        assert not pe.has_permission(None, "anything")

    def test_has_any(self):
        pe = self._engine()
        user = {"roles": ["viewer"]}
        assert pe.has_any(user, ["system:read", "identity:manage"])
        assert not pe.has_any(user, ["identity:manage", "provider:manage"])


# --------------------------------------------------------------------------- #
# ProviderConnectionManager
# --------------------------------------------------------------------------- #
class _FakeSecrets:
    """Minimal SecretManager stand-in for provider center tests."""

    def __init__(self, env=None):
        self._env = env or {}
        self._overrides: dict[str, str] = {}

    def get(self, name, default=None):
        if name in self._overrides:
            val = self._overrides[name]
            return val if val else default
        val = self._env.get(name) or self._env.get(name.upper())
        return val or default


class _FakeAdapter:
    """Minimal adapter stand-in for ProviderConnectionManager."""

    def __init__(self, provider_id, configured=True, capabilities=None, models=None, health_status="healthy"):
        self.provider_id = provider_id
        self._configured = configured
        self._capabilities = capabilities or set()
        self._models = models or []
        self._health_status = health_status

    @property
    def configured(self):
        return self._configured

    @property
    def declared_capabilities(self):
        return self._capabilities

    @property
    def models(self):
        return self._models

    def health(self, force=False):
        from providers.health import ProviderHealth, HealthStatus

        status = {
            "healthy": HealthStatus.HEALTHY,
            "unconfigured": HealthStatus.UNCONFIGURED,
            "unknown": HealthStatus.UNKNOWN,
        }.get(self._health_status, HealthStatus.UNKNOWN)
        return ProviderHealth(provider=self.provider_id, status=status, detail=self._health_status)


class _FakeRegistry:
    def __init__(self, adapters=None):
        self._adapters = {a.provider_id: a for a in (adapters or [])}

    def get(self, provider_id):
        return self._adapters.get(provider_id)


class _MemLinkStore:
    def __init__(self):
        self._d = {}

    def load(self):
        return self._d

    def save(self):
        pass


class TestProviderConnectionManager:
    def test_not_connected_when_no_credential(self):
        from providers.capabilities import Capability

        secrets = _FakeSecrets({"OPENAI_API_KEY": ""})
        center = ProviderConnectionManager(secrets=secrets)
        conn = center.status("openai")
        assert conn.status is ConnectionStatus.NOT_CONNECTED
        assert not conn.connected
        assert not conn.configured

    def test_connected_with_credential_and_healthy_adapter(self):
        from providers.capabilities import Capability
        secrets = _FakeSecrets({"JARVIS_OPENAI_API_KEY": "sk-test"})
        adapter = _FakeAdapter(
            "openai", configured=True,
            capabilities={Capability.CHAT, Capability.REASONING},
            health_status="healthy",
        )
        reg = _FakeRegistry([adapter])
        center = ProviderConnectionManager(secrets=secrets, registry=reg)
        conn = center.status("openai")
        assert conn.status is ConnectionStatus.CONNECTED
        assert conn.connected
        assert conn.configured
        assert "chat" in conn.capabilities

    def test_error_status_when_unhealthy(self):
        secrets = _FakeSecrets({"JARVIS_NVIDIA_API_KEY": "nv-key"})
        adapter = _FakeAdapter("nvidia", configured=True, health_status="unknown")
        reg = _FakeRegistry([adapter])
        center = ProviderConnectionManager(secrets=secrets, registry=reg)
        conn = center.status("nvidia")
        assert conn.status is ConnectionStatus.ERROR

    def test_all_status_no_secrets(self):
        """The status view must never contain raw secret values (spec §16)."""
        secrets = _FakeSecrets({
            "JARVIS_OPENAI_API_KEY": "sk-secret-key-12345",
            "JARVIS_HF_TOKEN": "hf_very-secret-token",
        })
        center = ProviderConnectionManager(secrets=secrets)
        serialized = str(center.all_status_safe())
        assert "sk-secret-key-12345" not in serialized
        assert "hf_very-secret-token" not in serialized

    def test_test_runs_probe_and_returns_result(self):
        secrets = _FakeSecrets({"JARVIS_OPENAI_API_KEY": "sk-test"})
        adapter = _FakeAdapter("openai", configured=True, health_status="healthy")
        reg = _FakeRegistry([adapter])
        center = ProviderConnectionManager(secrets=secrets, registry=reg)
        result = center.test("openai")
        assert result["provider"] == "openai"
        assert result["status"] == "connected"
        assert "testing" not in result["status"]  # testing flag cleared after

    def test_disconnect_clears_credential(self):
        secrets = _FakeSecrets({"JARVIS_OPENAI_API_KEY": "sk-test"})
        center = ProviderConnectionManager(secrets=secrets)
        result = center.disconnect("openai")
        assert result["ok"] is True
        assert not secrets.get("JARVIS_OPENAI_API_KEY")

    def test_disconnect_unknown_provider(self):
        center = ProviderConnectionManager(secrets=_FakeSecrets({}))
        result = center.disconnect("nonexistent")
        assert not result["ok"]

    def test_rotate_returns_vault_key(self):
        secrets = _FakeSecrets({"JARVIS_NVIDIA_API_KEY": "nv-key"})
        center = ProviderConnectionManager(secrets=secrets)
        result = center.rotate("nvidia")
        assert result["ok"] is True
        assert result["vault_key"] == "JARVIS_NVIDIA_API_KEY"

    def test_provider_ids_completeness(self):
        secrets = _FakeSecrets({})
        center = ProviderConnectionManager(secrets=secrets)
        ids = set(center.provider_ids())
        assert "openai" in ids
        assert "nvidia" in ids
        assert "google" in ids
        assert "aws" in ids
        assert "hf" in ids
        assert "github" in ids
        assert "microsoft" in ids

    def test_testing_status_during_test(self):
        secrets = _FakeSecrets({"JARVIS_OPENAI_API_KEY": "sk-test"})
        center = ProviderConnectionManager(secrets=secrets)
        center._testing.add("openai")
        conn = center.status("openai")
        assert conn.status is ConnectionStatus.TESTING

    def test_revoke_identity_provider_only(self):
        """Revoke on an API-key provider returns an error; on identity it disconnects."""
        secrets = _FakeSecrets({"JARVIS_GITHUB_CLIENT_ID": "gh-id"})
        link_store = _MemLinkStore()
        link_store._d["github:abc"] = {"provider": "github", "jarvis_user_id": "u1", "provider_user_id": "gh-123"}
        center = ProviderConnectionManager(secrets=secrets, link_store=link_store)
        # API-key provider revoke should error.
        assert center.revoke("openai")["ok"] is False
        # Identity provider revoke should disconnect.
        result = center.revoke("github")
        assert result["ok"] is True
