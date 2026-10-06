"""Security regression suite for the JARVIS admin / OAuth / RBAC hardening.

Maps to the implementation spec:
  §7  Admin configuration (JARVIS_ADMIN_EMAIL, dev default, prod fail-fast)
  §8  Token expiry (valid / expired / near-expiry) + API-key ``expires_at`` bug
  §9  RBAC roles (OWNER/ADMIN/OPERATOR/DEVELOPER/ANALYST/VIEWER) + authz/denial
  §10/§17 OAuth callback validation + read-only scope validation
  §3/§11 Secret non-disclosure (API keys, OAuth tokens, audit logs)
  §6/§18 Admin audit logging

All tests are hermetic: no network, in-memory SQLite (JARVIS_TEST_MODE), and
env vars are controlled with ``monkeypatch`` so each case is isolated.
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import pytest

# Signing/encryption key MUST be set before any jarvis_backend import so the JWT
# signer and the Fernet vault agree within this process. This mirrors the
# pattern in tests/test_oauth_framework.py.
os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_SECRET_KEY", "regression-test-secret-key-0123456789abcdef")

from jarvis_backend import core  # noqa: E402
from jarvis_backend.core import (  # noqa: E402
    admin_email, api_key_prefix, create_token, decode_token, create_refresh_token,
    generate_api_key, now, now_iso, iso_expire_at, is_api_key_expired,
    _iso_to_epoch, is_production, get_store, hash_password, refresh_access_token,
)
from jarvis_backend.connectors import oauth  # noqa: E402

# OAuth client fixtures (read-only scopes by default -- least privilege, §4/#15).
GMAIL_CLIENTS = {
    "gmail": {
        "client_id": "test-gmail-id",
        "client_secret": "test-gmail-secret",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "is_google": True,
    },
    "outlook": {
        "client_id": "test-outlook-id",
        "client_secret": "test-outlook-secret",
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "Mail.Read",
        "is_microsoft": True,
    },
}

CANONICAL_ROLES = ["owner", "admin", "operator", "developer", "analyst", "viewer"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": email, "sub": email}).encode()).decode().rstrip("=")
    return f"hdr.{payload}.sig"


def _user_token(roles):
    """Create a user in the store with ``roles`` and return a Bearer header string."""
    uid = str(uuid.uuid4())
    users = get_store("users").load()
    users[uid] = {
        "id": uid, "email": f"{uid}@t.test", "username": "u_" + uid[:8],
        "password_hash": hash_password("pw"), "full_name": "T User",
        "avatar_url": None, "status": "active", "tenant_id": None,
        "roles": roles, "last_login_at": None, "created_at": now_iso(),
    }
    get_store("users").save()
    return {"Authorization": f"Bearer {create_token({'sub': uid, 'sid': None})}"}


@pytest.fixture(autouse=True)
def _oauth_clients(monkeypatch):
    """Seed JARVIS_OAUTH_CLIENTS for the OAuth-scoped tests (isolated per test)."""
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", json.dumps(GMAIL_CLIENTS))


def _make_admin_user():
    """Create an admin user in the store; return (user_id, Authorization headers)."""
    uid = str(uuid.uuid4())
    users = get_store("users").load()
    users[uid] = {
        "id": uid, "email": f"admin-{uid[:8]}@t.test", "username": "admin_" + uid[:8],
        "password_hash": hash_password("Admin#Jarvis1"),
        "full_name": "Admin", "avatar_url": None, "status": "active",
        "tenant_id": None, "roles": ["admin"], "last_login_at": None, "created_at": now_iso(),
    }
    get_store("users").save()
    return uid, {"Authorization": f"Bearer {create_token({'sub': uid, 'sid': None})}"}


@pytest.fixture
def admin_headers():
    _, headers = _make_admin_user()
    return headers


# --------------------------------------------------------------------------- #
# §7 Admin configuration
# --------------------------------------------------------------------------- #
class TestAdminConfig:
    def test_dev_default_admin_email(self, monkeypatch):
        monkeypatch.delenv("JARVIS_ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("JARVIS_ENV", raising=False)
        assert admin_email() == "admin@jarvis.local"

    def test_dev_uses_configured_email(self, monkeypatch):
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "dev-team@example.com")
        monkeypatch.setenv("JARVIS_ENV", "development")
        assert admin_email() == "dev-team@example.com"

    def test_prod_missing_admin_email_raises(self, monkeypatch):
        monkeypatch.delenv("JARVIS_ADMIN_EMAIL", raising=False)
        monkeypatch.setenv("JARVIS_ENV", "production")
        with pytest.raises(RuntimeError, match="JARVIS_ADMIN_EMAIL is required"):
            admin_email()

    def test_prod_with_configured_email(self, monkeypatch):
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "admin@example.org")
        monkeypatch.setenv("JARVIS_ENV", "production")
        assert admin_email() == "admin@example.org"

    def test_prod_aliases_recognized(self, monkeypatch):
        monkeypatch.setenv("JARVIS_ENV", "prod")
        monkeypatch.delenv("JARVIS_ADMIN_EMAIL", raising=False)
        assert is_production() is True
        with pytest.raises(RuntimeError):
            admin_email()

    def test_start_backend_fail_fast_in_prod_without_email(self, monkeypatch):
        # The real startup path must refuse to come up in production without a
        # configured admin email (fail-fast, clear error).
        monkeypatch.delenv("JARVIS_ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("JARVIS_ADMIN_PASSWORD", raising=False)
        monkeypatch.setenv("JARVIS_ENV", "production")
        with pytest.raises(RuntimeError, match="JARVIS_ADMIN_EMAIL is required"):
            core.start_backend()

    def test_start_backend_seeds_configured_admin(self, monkeypatch):
        # Development can seed a configured email against the isolated test DB.
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "prod-admin@example.com")
        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "Admin#Jarvis1")
        monkeypatch.delenv("JARVIS_ENV", raising=False)
        core.start_backend()
        users = get_store("users").load()
        admin = next((u for u in users.values() if u.get("email") == "prod-admin@example.com"), None)
        assert admin is not None
        assert "admin" in admin["roles"]

    def test_configured_admin_email_is_loaded(self, monkeypatch):
        # A configured JARVIS_ADMIN_EMAIL is recognized as the JARVIS
        # administrator (the seeded admin account carries that email + role).
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "ndichiv@gmail.com")
        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "Admin#Jarvis1")
        monkeypatch.delenv("JARVIS_ENV", raising=False)
        core.start_backend()
        users = get_store("users").load()
        admin = next((u for u in users.values() if u.get("email") == "ndichiv@gmail.com"), None)
        assert admin is not None
        assert "admin" in admin["roles"]

    def test_another_email_not_granted_admin(self, monkeypatch):
        # A non-administrator email must not be incorrectly granted
        # administrator privileges just because it exists in the user store.
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "Admin#Jarvis1")
        monkeypatch.delenv("JARVIS_ENV", raising=False)
        core.start_backend()
        users = get_store("users").load()
        # Register a normal user with a different email
        misc = get_store("misc").load()
        misc.setdefault("reset_tokens", {})
        get_store("misc").save()
        user = {
            "id": str(uuid.uuid4()),
            "email": "normal@example.com",
            "username": "normal",
            "password_hash": core.hash_password("pw"),
            "full_name": "Normal",
            "status": "active",
            "roles": ["user"],
            "created_at": core.now_iso(),
        }
        users[user["id"]] = user
        get_store("users").save()
        # Confirm the seeded admin is admin@example.com (not normal@example.com)
        admin = next((u for u in users.values() if u.get("email") == "admin@example.com"), None)
        assert admin is not None and "admin" in admin["roles"]
        normal = next((u for u in users.values() if u.get("email") == "normal@example.com"), None)
        assert normal is not None and "admin" not in normal["roles"]

    def test_admin_email_not_exposed_in_logs(self, monkeypatch, caplog):
        # The admin email must not be written to logs/telemetry.
        import logging
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "ndichiv@gmail.com")
        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "Admin#Jarvis1")
        monkeypatch.delenv("JARVIS_ENV", raising=False)
        with caplog.at_level(logging.INFO):
            core.start_backend()
        for record in caplog.records:
            assert "ndichiv@gmail.com" not in record.getMessage()

    def test_dev_fallback_admin_email(self, monkeypatch):
        # Development fallback (admin@jarvis.local) still works when
        # JARVIS_ADMIN_EMAIL is unset and JARVIS_ENV is not production.
        monkeypatch.delenv("JARVIS_ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("JARVIS_ENV", raising=False)
        assert core.admin_email() == "admin@jarvis.local"


# --------------------------------------------------------------------------- #
# §8 Token expiry (JWT access / refresh) + API-key expires_at bug
# --------------------------------------------------------------------------- #
class TestTokenExpiry:
    def test_valid_token_decodes(self):
        t = create_token({"sub": "u1"})
        assert decode_token(t) is not None

    def test_expired_token_rejected(self, monkeypatch):
        t = create_token({"sub": "u1"})
        payload = decode_token(t)
        exp = payload["exp"]
        monkeypatch.setattr(core.time, "time", lambda: exp + 1)  # past expiry
        assert decode_token(t) is None

    def test_near_expiry_token_still_valid(self, monkeypatch):
        # expires_at is numeric epoch; a token expiring THIS second is still
        # accepted (strict ``<`` comparison, not ``<=``).
        t = create_token({"sub": "u2"})
        exp = decode_token(t)["exp"]
        monkeypatch.setattr(core.time, "time", lambda: exp - 1)  # 1s of life left
        assert decode_token(t) is not None

    def test_utc_now_is_timezone_aware(self):
        # Regression: datetime.utcnow() is deprecated/naive and breaks tz
        # comparisons. now_iso() must emit an aware ISO-8601 UTC string.
        iso = now_iso()
        assert iso.endswith("Z")
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        # now() helper must be timezone-aware too.
        assert now().tzinfo is not None

    def test_refresh_token_lifecycle(self):
        t = create_refresh_token("u1")
        # A valid (non-expired) refresh token mints a new access token.
        access = refresh_access_token(t)
        assert access is not None and decode_token(access) is not None

    def test_refresh_token_rejected_when_expired(self, monkeypatch):
        t = create_refresh_token("u1")
        entry = decode_token(t)
        jti = entry["jti"]
        stored_exp = get_store("refresh_tokens").load()[jti]["exp"]
        monkeypatch.setattr(core.time, "time", lambda: stored_exp + 1)
        # Past the refresh-token's own expiry -> cannot mint a new access.
        assert refresh_access_token(t) is None


class TestApiKeyExpiryBug:
    """Regression for auth.py create_api_key: expires_at was set to 'now'."""

    def test_expires_at_is_in_the_future(self):
        exp = iso_expire_at(30)
        epoch = _iso_to_epoch(exp)
        assert epoch > time.time()  # strictly in the future
        # ~30 days out (allow a small clock skew window).
        assert epoch > time.time() + 30 * 86400 - 5

    def test_expires_at_not_now(self):
        # The bug set expires_at == now_iso() (immediately expired). The fix
        # pushes it into the future by expires_in_days.
        exp = iso_expire_at(7)
        assert _iso_to_epoch(exp) > time.time()

    def test_is_api_key_expired_helpers(self):
        assert not is_api_key_expired({"expires_at": iso_expire_at(30)})   # valid
        assert not is_api_key_expired({"expires_at": None})                # non-expiring
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        assert is_api_key_expired({"expires_at": past})                    # expired
        # Near-expiry: a key expiring within the grace window is flagged.
        soon = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
        assert is_api_key_expired({"expires_at": soon}, grace_seconds=30)
        assert not is_api_key_expired({"expires_at": soon}, grace_seconds=0)

    def test_create_api_key_endpoint_sets_future_expiry(self, client, admin_headers):
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "reg-key", "expires_in_days": 30, "scopes": ["admin"]},
                        headers=admin_headers)
        assert r.status_code == 200
        exp = r.json()["api_key"]["expires_at"]
        assert exp is not None
        assert _iso_to_epoch(exp) > time.time()


# --------------------------------------------------------------------------- #
# §9 RBAC: canonical roles + authorized / unauthorized paths
# --------------------------------------------------------------------------- #
class TestRBAC:
    def test_canonical_roles_seeded(self):
        core._seed_canonical_roles()
        names = {r.get("name") for r in get_store("roles").load().values()}
        for role in CANONICAL_ROLES:
            assert role in names, f"canonical role {role!r} missing"

    def test_admin_role_has_wildcard_permissions(self):
        core._seed_canonical_roles()
        roles = get_store("roles").load()
        admin = roles.get("admin") or next((r for r in roles.values() if r.get("name") == "admin"), None)
        assert admin is not None
        assert "*" in admin["permissions"]

    def test_least_privilege_viewer(self):
        core._seed_canonical_roles()
        roles = get_store("roles").load()
        viewer = next(r for r in roles.values() if r.get("name") == "viewer")
        # Viewer must NOT carry write or admin capabilities.
        perms = set(viewer["permissions"])
        assert "*" not in perms
        assert all(p.endswith(":read") or p == "read" or p == "system:read" for p in perms)

    def test_admin_authorized_to_create_role(self, client):
        headers = _user_token(["admin"])
        r = client.post("/api/v1/rbac/roles",
                        json={"name": "qa", "description": "q", "permissions": ["read"]},
                        headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "qa"

    def test_regular_user_denied_create_role(self, client):
        headers = _user_token(["user"])
        r = client.post("/api/v1/rbac/roles",
                        json={"name": "qa2", "permissions": ["read"]},
                        headers=headers)
        assert r.status_code == 403

    def test_no_auth_denied(self, client):
        r = client.post("/api/v1/rbac/roles",
                        json={"name": "qa3", "permissions": ["read"]})
        assert r.status_code == 401

    def test_owner_role_grants_admin_access(self, client):
        # OWNER carries '*' permissions -> should pass the admin gate. The
        # '*' permission is resolved against the roles store, so seed them first.
        core._seed_canonical_roles()
        headers = _user_token(["owner"])
        r = client.post("/api/v1/rbac/roles",
                        json={"name": "owner-ok", "permissions": ["read"]},
                        headers=headers)
        assert r.status_code == 200

    def test_tenant_settings_model_dump_works_for_admin(self, client):
        # Exercises the .dict() -> .model_dump() fix end-to-end via the API.
        headers = _user_token(["admin"])
        r = client.put("/api/v1/rbac/tenant/settings",
                       json={"max_users": 5}, headers=headers)
        assert r.status_code == 200
        assert r.json()["max_users"] == 5


# --------------------------------------------------------------------------- #
# Sections 5-10 / 12-20: API-key at-rest security
# --------------------------------------------------------------------------- #
class TestApiKeyAtRestSecurity:
    """Raw jarvis_ API keys must never persist, be logged, or be recoverable."""

    def test_create_key_requires_admin(self, client, auth_headers):
        # A regular (non-admin) user cannot mint service credentials.
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "nope", "scopes": ["admin"]}, headers=auth_headers)
        assert r.status_code == 403

    def test_create_returns_raw_key_once(self, client, admin_headers):
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "once", "scopes": ["admin"]}, headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["key"].startswith("jarvis_")
        assert body["key_id"]
        assert body["prefix"].startswith("jarvis_")
        assert body["warning"]

    def test_raw_key_not_persisted(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "p", "scopes": ["admin"]}, headers=admin_headers).json()["key"]
        for rec in get_store("api_keys").load().values():
            blob = json.dumps(rec)
            assert raw not in blob
            assert "key" not in rec
            assert "raw_key" not in rec
            assert "secret" not in rec
            assert "token" not in rec
            assert rec.get("hash", "").startswith("pbkdf2_sha256$")
            assert rec.get("prefix", "").startswith("jarvis_")
            import hashlib as _hl
            assert rec["hash"] != _hl.sha256(raw.encode()).hexdigest()

    def test_list_never_returns_raw_key(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "nd", "scopes": ["admin"]}, headers=admin_headers).json()["key"]
        body = client.get("/api/v1/auth/api-keys", headers=admin_headers).json()
        blob = json.dumps(body)
        assert raw not in blob
        for rec in body["api_keys"]:
            assert "key" not in rec
            assert "hash" not in rec

    def test_authentication_succeeds(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "k", "scopes": ["admin"]}, headers=admin_headers).json()["key"]
        r = client.get("/api/v1/auth/me",
                       headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 200
        assert r.json()["email"].startswith("admin-")

    def test_wrong_key_fails(self, client, admin_headers):
        client.post("/api/v1/auth/api-keys",
                    json={"name": "k", "scopes": ["admin"]}, headers=admin_headers)
        r = client.get("/api/v1/auth/me",
                       headers={"Authorization": "Bearer jarvis_notarealkey"})
        assert r.status_code == 401

    def test_expired_key_fails(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "exp", "scopes": ["admin"], "expires_in_days": 1},
                          headers=admin_headers).json()["key"]
        keys = get_store("api_keys").load()
        kid = next(k for k, v in keys.items() if v.get("prefix") == api_key_prefix(raw))
        keys[kid]["expires_at"] = (datetime.now(timezone.utc)
                                   - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        get_store("api_keys").save()
        r = client.get("/api/v1/auth/me",
                       headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401

    def test_revoked_key_fails(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "rev", "scopes": ["admin"]}, headers=admin_headers).json()["key"]
        keys = get_store("api_keys").load()
        kid = next(k for k, v in keys.items() if v.get("prefix") == api_key_prefix(raw))
        client.delete(f"/api/v1/auth/api-keys/{kid}", headers=admin_headers)
        r = client.get("/api/v1/auth/me",
                       headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401

    def test_scope_denial(self, client, admin_headers):
        # A read-scoped key cannot perform admin actions (e.g. create a key).
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "read", "scopes": ["read"]}, headers=admin_headers).json()["key"]
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "child", "scopes": ["admin"]},
                        headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 403

    def test_rotation(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "orig", "scopes": ["admin"]}, headers=admin_headers).json()["key"]
        keys = get_store("api_keys").load()
        kid = next(k for k, v in keys.items() if v.get("prefix") == api_key_prefix(raw))
        rot = client.post(f"/api/v1/auth/api-keys/{kid}/rotate",
                          headers=admin_headers).json()
        new_raw = rot["key"]
        assert new_raw.startswith("jarvis_")
        assert rot["key_id"] != kid
        # old key revoked -> cannot authenticate
        keys = get_store("api_keys").load()
        assert keys[kid]["status"] == "revoked"
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401
        # new key works
        r2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_raw}"})
        assert r2.status_code == 200

    def test_migration_from_plaintext(self, client, admin_headers):
        # Simulate a legacy pre-hashing record (plaintext key field, no hash).
        uid, _ = _make_admin_user()
        raw = generate_api_key()[0]
        keys = get_store("api_keys").load()
        kid = str(uuid.uuid4())
        keys[kid] = {
            "id": kid, "key_id": kid, "user_id": uid, "owner": uid,
            "name": "legacy", "scopes": ["admin"],
            "key": raw, "created_at": now_iso(), "status": "active",
        }
        get_store("api_keys").save()
        # Authenticating with the raw key migrates it in place.
        r = client.get("/api/v1/auth/me",
                       headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 200
        rec = get_store("api_keys").load()[kid]
        assert "key" not in rec
        assert rec.get("hash", "").startswith("pbkdf2_sha256$")
        assert rec.get("prefix") == api_key_prefix(raw)
        assert raw not in json.dumps(get_store("audit_logs").load())

    def test_no_secret_in_audit_logs(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "s", "scopes": ["admin"]}, headers=admin_headers).json()["key"]
        for entry in get_store("audit_logs").load():
            assert raw not in json.dumps(entry)

    def test_security_regression_raw_key_absent(self, client, admin_headers):
        # Mandatory regression (section 20): raw key absent from persisted record,
        # logs, and is only ever correlated by key_id/prefix.
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "reg", "scopes": ["admin"]}, headers=admin_headers).json()["key"]
        rec = next(r for r in get_store("api_keys").load().values() if r.get("name") == "reg")
        assert raw not in json.dumps(rec)
        assert rec["prefix"] == api_key_prefix(raw)
        assert raw not in json.dumps(get_store("audit_logs").load())


# --------------------------------------------------------------------------- #
# §10/§17 OAuth callback validation + read-only scope validation
# --------------------------------------------------------------------------- #
class TestOAuthFlow:
    def test_state_tamper_detected(self):
        state = oauth.make_state("gmail", "u1")
        payload, _, sig = state.partition(".")
        bad = payload[:-1] + ("A" if payload[-1] != "A" else "B")
        with pytest.raises(oauth.OAuthError, match="invalid state signature"):
            oauth.verify_state(bad + "." + sig)

    def test_state_kind_mismatch_rejected(self):
        state = oauth.make_state("gmail", "u1")
        with pytest.raises(oauth.OAuthError, match="does not match"):
            oauth.exchange_code("outlook", "CODE", state, "u1")

    def test_state_expires_after_ttl(self, monkeypatch):
        base = time.time()
        monkeypatch.setattr(oauth.time, "time", lambda: base)
        state = oauth.make_state("gmail", "u1")
        monkeypatch.setattr(oauth.time, "time", lambda: base + oauth.STATE_TTL + 1)
        with pytest.raises(oauth.OAuthError, match="expired"):
            oauth.verify_state(state)

    def test_gmail_authorize_url_uses_readonly_scope(self):
        # Least privilege: Gmail authorize uses gmail.readonly, never gmail.send
        # or gmail.compose for the default connect flow.
        url = oauth.authorize_url("gmail", "u1")
        assert "gmail.readonly" in url
        assert "gmail.send" not in url
        assert "gmail.compose" not in url
        assert "access_type=offline" in url  # refresh-token acquisition
        assert "prompt=consent" in url

    def test_outlook_authorize_url_uses_read_scope(self):
        url = oauth.authorize_url("outlook", "u1")
        assert "Mail.Read" in url
        # Send-level scopes must not be auto-requested.
        assert "Mail.Send" not in url
        assert "Mail.ReadWrite" not in url

    def test_tokens_encrypted_at_rest(self):
        oauth.save_tokens("gmail", "u1", {
            "access_token": "PLAINTEXT-AT", "refresh_token": "PLAINTEXT-RT",
            "expires_at": time.time() + 3600, "account": "a@b.com",
            "scope": "gmail.readonly",
        })
        raw = get_store("oauth_tokens").load()["gmail:u1"]
        assert raw["access_token"].startswith("fernet:")
        assert raw["refresh_token"].startswith("fernet:")
        blob = json.dumps(raw)
        assert "PLAINTEXT-AT" not in blob
        assert "PLAINTEXT-RT" not in blob
        # Round-trip decryption recovers the plaintext (server-side only).
        loaded = oauth.load_tokens("gmail", "u1")
        assert loaded["access_token"] == "PLAINTEXT-AT"
        assert loaded["refresh_token"] == "PLAINTEXT-RT"

    def test_connection_metadata_never_exposes_tokens(self):
        oauth.save_tokens("gmail", "u1", {
            "access_token": "AT-secret", "refresh_token": "RT-secret",
            "expires_at": time.time() + 3600, "account": "a@b.com",
            "scope": "gmail.readonly",
        })
        m = oauth.connection_metadata("gmail", "u1")
        blob = json.dumps(m)
        assert "AT-secret" not in blob
        assert "RT-secret" not in blob
        assert "access_token" not in blob
        assert "refresh_token" not in blob
        assert "fernet:" not in blob
        # Only safe metadata is surfaced (§11).
        assert m["connected"] is True
        assert "provider" in m or "account" in m


# --------------------------------------------------------------------------- #
# §3/§11 Secret non-disclosure via the auth + API-key surface
# --------------------------------------------------------------------------- #
class TestSecretNonDisclosure:
    def test_api_key_list_never_returns_raw_key(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "nd", "expires_in_days": 30, "scopes": ["admin"]},
                          headers=admin_headers).json()["key"]
        body = client.get("/api/v1/auth/api-keys", headers=admin_headers).json()
        blob = json.dumps(body)
        assert raw not in blob
        assert "key" not in body["api_keys"][0]
        assert "hash" not in body["api_keys"][0]
        # raw_key must NOT appear again on the list endpoint.
        assert "raw_key" not in blob

    def test_api_key_create_returns_raw_key_once(self, client, admin_headers):
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "once", "scopes": ["admin"]}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["key"].startswith("jarvis_")
        assert r.json()["key_id"]
        assert r.json()["prefix"].startswith("jarvis_")
        # but the persisted api_key object omits the plaintext key/hash fields
        assert "key" not in r.json()["api_key"]
        assert "hash" not in r.json()["api_key"]

    def test_audit_logs_never_contain_passwords_or_tokens(self, client):
        # Register + login, then inspect the audit trail for secret leakage.
        email = f"{uuid.uuid4().hex[:8]}@audit.test"
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": email, "username": "auditor", "password": "S3cret!audit1"},
        )
        user_id = registered.json()["user"]["id"]
        users = get_store("users")
        user = users.load()[user_id]
        user["email_verified"] = True
        users.save()
        r = client.post("/api/v1/auth/login",
                        json={"identifier": email, "password": "S3cret!audit1"})
        assert r.status_code == 200
        logs = get_store("audit_logs").load()
        blob = json.dumps(logs)
        assert "S3cret!audit1" not in blob
        assert "password_hash" not in blob
        assert any(l.get("action") == "login" for l in logs)
        assert any(l.get("action") == "register" for l in logs)


# --------------------------------------------------------------------------- #
# §6/§18 Admin audit logging (login / register / api-key create are audited)
# --------------------------------------------------------------------------- #
class TestAdminAuditLogging:
    def test_login_is_audited(self, client):
        email = f"{uuid.uuid4().hex[:8]}@aud.test"
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": email, "username": "a1", "password": "S3cret!1"},
        )
        user_id = registered.json()["user"]["id"]
        users = get_store("users")
        user = users.load()[user_id]
        user["email_verified"] = True
        users.save()
        client.post("/api/v1/auth/login",
                    json={"identifier": email, "password": "S3cret!1"})
        logs = get_store("audit_logs").load()
        assert any(l["action"] == "register" for l in logs)
        assert any(l["action"] == "login" and l.get("actor_id") for l in logs)

    def test_api_key_creation_is_audited(self, client, admin_headers):
        client.post("/api/v1/auth/api-keys",
                    json={"name": "audited-key", "scopes": ["admin"]}, headers=admin_headers)
        logs = get_store("audit_logs").load()
        assert any(l["action"] == "create_api_key" and l.get("detail") == "audited-key"
                   for l in logs)

    def test_audit_entry_shape(self, client, admin_headers):
        client.post("/api/v1/auth/api-keys",
                    json={"name": "shape", "scopes": ["admin"]}, headers=admin_headers)
        logs = get_store("audit_logs").load()
        entry = [l for l in logs if l.get("action") == "create_api_key"][-1]
        for field in ("id", "actor_id", "action", "resource_type", "timestamp"):
            assert field in entry
        assert entry["resource_type"] == "auth"
        # The audit entry must never reference a secret value or field alias.
        assert "key" not in entry
        assert "hash" not in entry


# --------------------------------------------------------------------------- #
# §5/§6 The patched implementation surfaces as the admin login identity
# --------------------------------------------------------------------------- #
class TestAdminSurface:
    def test_admin_login_uses_configured_email(self, monkeypatch):
        # The seeded dev admin always signs in with the configured/default email.
        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "Admin#Jarvis1")
        from starlette.testclient import TestClient
        from jarvis_backend.main import app

        with TestClient(app) as client:
            core.start_backend()
            users = get_store("users").load()
            admin = next(u for u in users.values() if "admin" in (u.get("roles") or []))
            # Dev default when no JARVIS_ADMIN_EMAIL is set.
            assert admin["email"] == "admin@jarvis.local"
            r = client.post(
                "/api/v1/auth/login",
                json={"identifier": "admin@jarvis.local", "password": "Admin#Jarvis1"},
            )
            assert r.status_code == 200
            assert r.json()["user"]["email"] == "admin@jarvis.local"

    def test_admin_login_uses_configured_prod_email(self, client, monkeypatch):
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "prod-admin@example.com")
        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "Admin#Jarvis1")
        core.start_backend()
        users = get_store("users").load()
        admin = next(u for u in users.values() if "admin" in (u.get("roles") or []))
        assert admin["email"] == "prod-admin@example.com"
