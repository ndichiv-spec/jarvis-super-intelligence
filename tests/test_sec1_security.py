"""SEC-1 — Unified Authentication, Authorization & Credential Boundary.

These tests are hermetic (JARVIS_TEST_MODE, in-memory SQL, isolated DB via the
autouse ``_reset_state`` fixture in conftest.py). They assert the security
invariants preserved/added by the SEC-1 hardening pass and complement the
existing test_auth / test_security_regression / test_platform_identity suites.

Coverage map (SEC-1 phases):
  P3  centralized authorization boundary (is_admin predicate, _require_admin)
  P4  system host-op protection (processes/files/clipboard/screenshot/launch),
      deny-list-first ordering so shutdown is 403 even unauthenticated,
      path-traversal confinement
  P6  legacy plaintext provider secrets migrated to Fernet, truthiness preserved
  P7  provider-settings: scrubbed GET, secret-shaped PUT rejected
  P8  sensitive actions audited (audit_logs entries present)
  P9  security headers on responses
  P10 error responses carry no exception/path leakage
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi import HTTPException

# Signing/encryption key MUST be set before any jarvis_backend import so the
# JWT signer and the Fernet vault agree within this process (mirrors
# tests/test_security_regression.py).
os.environ.setdefault("JARVIS_SECRET_KEY", "sec1-test-secret-key-0123456789abcdef")
os.environ.setdefault("JARVIS_TEST_MODE", "1")

from jarvis_backend import core  # noqa: E402
from jarvis_backend.core import (  # noqa: E402
    get_store, hash_password, create_token, now_iso, is_admin, _require_admin,
    _migrate_legacy_provider_secrets,
)


def _make_user(roles, email=None, password="S3cret!pass"):
    """Create a user in the (reset) store and return (uid, bearer headers)."""
    uid = str(uuid.uuid4())
    users = get_store("users").load()
    users[uid] = {
        "id": uid,
        "email": email or f"{uid}@t.test",
        "username": f"u_{uid[:8]}",
        "password_hash": hash_password(password),
        "full_name": "Probe User",
        "avatar_url": None,
        "status": "active",
        "tenant_id": None,
        "roles": list(roles),
        "is_admin": "admin" in roles,
        "last_login_at": None,
        "created_at": now_iso(),
    }
    get_store("users").save()
    headers = {"Authorization": f"Bearer {create_token({'sub': uid, 'sid': None})}"}
    return uid, headers


@pytest.fixture
def admin_headers():
    _, headers = _make_user(["admin"], email="admin@jarvis.local")
    return headers


@pytest.fixture
def user_headers():
    _, headers = _make_user(["user"])
    return headers


# --------------------------------------------------------------------------- #
# P3: centralized authorization boundary
# --------------------------------------------------------------------------- #
class TestAuthorizationBoundary:
    def test_is_admin_true_for_admin_role(self):
        uid, _ = _make_user(["admin"])
        user = get_store("users").load()[uid]
        assert is_admin(user) is True

    def test_is_admin_true_for_owner_wildcard(self):
        core._seed_canonical_roles()
        uid, _ = _make_user(["owner"])
        user = get_store("users").load()[uid]
        assert is_admin(user) is True

    def test_is_admin_false_for_regular_user(self):
        uid, _ = _make_user(["user"])
        user = get_store("users").load()[uid]
        assert is_admin(user) is False

    def test_require_admin_denies_regular_user(self):
        # _require_admin delegates to the centralized is_admin predicate.
        uid, _ = _make_user(["user"])
        user = get_store("users").load()[uid]
        with pytest.raises(HTTPException) as exc:
            _require_admin(user)
        assert exc.value.status_code == 403

    def test_require_admin_allows_admin(self):
        uid, _ = _make_user(["admin"])
        user = get_store("users").load()[uid]
        # _require_admin returns the user on success (routers do `user = ...`).
        result = _require_admin(user)
        assert result["id"] == uid


# --------------------------------------------------------------------------- #
# P4: system host-op protection (auth + destructive lockdown)
# --------------------------------------------------------------------------- #
class TestSystemHostOps:
    def test_public_readonly_surface(self, client):
        for path in ("/api/v1/system/capabilities",
                     "/api/v1/platform/identity",
                     "/api/v1/system/dashboard",
                     "/api/v1/system/status",
                     "/health", "/api/ping"):
            r = client.get(path)
            assert r.status_code == 200, (path, r.status_code, r.text)

    def test_unauthenticated_host_ops_rejected(self, client):
        for path in ("/api/v1/system/processes",
                     "/api/v1/system/provider-settings",
                     "/api/v1/system/files",
                     "/api/v1/system/clipboard"):
            r = client.get(path)
            assert r.status_code == 401, (path, r.status_code)

    @pytest.mark.parametrize("command", ["shutdown", "reboot", "halt", "poweroff"])
    def test_shutdown_lockdown_unauthenticated(self, client, command):
        r = client.post("/api/v1/system/launch", json={"app": command})
        assert r.status_code == 403
        # Structured error format: {"error": {"code": "AUTHORIZATION_ERROR", "message": "..."}}
        body = r.json()
        assert "error" in body
        assert "AUTHORIZATION_ERROR" in body["error"].get("code", "")

    def test_shutdown_lockdown_even_when_authenticated(self, client, user_headers):
        # An authenticated NON-admin still gets 403 for destructive commands
        # (deny-list is evaluated before the admin check).
        r = client.post("/api/v1/system/launch",
                        json={"app": "shutdown"}, headers=user_headers)
        assert r.status_code == 403

    def test_non_admin_cannot_launch(self, client, user_headers):
        r = client.post("/api/v1/system/launch",
                        json={"app": "cmd", "args": "/c echo sec1"}, headers=user_headers)
        assert r.status_code == 403

    def test_admin_can_launch_non_destructive(self, client, admin_headers):
        r = client.post("/api/v1/system/launch",
                        json={"app": "cmd", "args": "/c echo sec1"}, headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["app"] == "cmd"

    def test_admin_can_read_processes(self, client, admin_headers):
        r = client.get("/api/v1/system/processes", headers=admin_headers)
        assert r.status_code == 200


# --------------------------------------------------------------------------- #
# P4: path-traversal confinement for file APIs
# --------------------------------------------------------------------------- #
class TestFileBoundary:
    def test_file_read_confined_to_root(self, client, admin_headers):
        for bad in ("/etc/passwd", "..\\..\\..\\windows\\win.ini", "../../../etc/hosts"):
            r = client.post("/api/v1/system/files/read",
                            json={"path": bad}, headers=admin_headers)
            assert r.status_code == 403, (bad, r.status_code, r.text)
            # Structured error format
            body = r.json()
            assert "error" in body or "detail" in body

    def test_file_list_confined_to_root(self, client, admin_headers):
        r = client.get("/api/v1/system/files?path=..\\..\\..\\etc", headers=admin_headers)
        assert r.status_code == 403


# --------------------------------------------------------------------------- #
# P6/P7: provider settings — scrubbed read, secret-shape rejection, migration
# --------------------------------------------------------------------------- #
class TestProviderSettingsBoundary:
    def test_put_saves_non_secret_provider_preferences(self, client, admin_headers):
        response = client.put(
            "/api/v1/system/provider-settings",
            json={
                "ollama_base_url": "http://localhost:11434",
                "ollama_model": "mistral",
                "aws_region": "eu-west-1",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        settings = get_store("misc").load()["provider_settings"]
        assert settings["ollama_model"] == "mistral"
        assert settings["aws_region"] == "eu-west-1"
        assert response.json()["settings"]["ollama_model"] == "mistral"
        assert response.json()["settings"]["openai_api_key"] is None

    def test_put_rejects_secret_shaped_fields(self, client, admin_headers):
        for field in ("openai_api_key", "google_gemini_api_key", "aws_secret_token",
                      "anthropic_api_key"):
            r = client.put("/api/v1/system/provider-settings",
                           json={field: "sk-test-value"}, headers=admin_headers)
            assert r.status_code == 400, (field, r.status_code)
            assert "refusing" in r.text.lower()

    def test_get_scrubs_secret_values(self, client, admin_headers):
        misc = get_store("misc").load()
        ps = misc.setdefault("provider_settings", {})
        ps["openai_api_key"] = "sk-super-secret-plain-123"
        ps["ollama_model"] = "llama3"
        get_store("misc").save()
        r = client.get("/api/v1/system/provider-settings", headers=admin_headers)
        assert r.status_code == 200
        text = r.text
        assert "sk-super-secret-plain-123" not in text  # value never returned
        assert "openai_api_key" in text                  # key name is safe metadata


class TestLegacySecretMigration:
    def test_plaintext_provider_secret_migrated_to_fernet(self):
        misc = get_store("misc").load()
        ps = misc.setdefault("provider_settings", {})
        ps["openai_api_key"] = "sk-legacy-plaintext-xyz"
        ps["anthropic_api_key"] = "sk-anthropic-abc"
        ps["ollama_model"] = "llama3"  # non-secret: must not be touched
        get_store("misc").save()
        n = _migrate_legacy_provider_secrets()
        assert n == 2
        ps = get_store("misc").load().get("provider_settings") or {}
        assert ps["openai_api_key"].startswith("fernet:")
        assert ps["anthropic_api_key"].startswith("fernet:")
        assert ps["ollama_model"] == "llama3"  # truthy non-secret untouched
        # plaintext is gone
        for v in ps.values():
            assert v != "sk-legacy-plaintext-xyz"

    def test_migration_is_idempotent(self):
        misc = get_store("misc").load()
        ps = misc.setdefault("provider_settings", {})
        ps["openai_api_key"] = "sk-legacy-plaintext-xyz"
        get_store("misc").save()
        assert _migrate_legacy_provider_secrets() == 1
        assert _migrate_legacy_provider_secrets() == 0  # already canonical


# --------------------------------------------------------------------------- #
# P8: sensitive actions are audited
# --------------------------------------------------------------------------- #
class TestAuditTrail:
    def test_launch_denial_is_audited(self, client):
        before = len([e for e in (get_store("audit_logs").load() or [])
                      if isinstance(e, dict) and e.get("kind") == "system_launch"])
        client.post("/api/v1/system/launch", json={"app": "shutdown"})
        after = [e for e in (get_store("audit_logs").load() or [])
                 if isinstance(e, dict) and e.get("kind") == "system_launch"]
        assert len(after) >= before + 1
        denials = [e for e in after if e.get("status") == "denied"]
        assert denials
        assert denials[-1]["app"] == "shutdown"
        assert denials[-1]["actor"] == "anonymous"  # no authenticated principal


# --------------------------------------------------------------------------- #
# P9: security headers
# --------------------------------------------------------------------------- #
class TestSecurityHeaders:
    def test_defensive_headers_present(self, client):
        r = client.get("/api/v1/system/status")
        assert r.status_code == 200
        for hdr, val in (("x-content-type-options", "nosniff"),
                         ("x-frame-options", "DENY"),
                         ("referrer-policy", "no-referrer"),
                         ("cache-control", "no-store")):
            assert hdr in r.headers, hdr
            assert r.headers[hdr] == val, (hdr, r.headers[hdr])


# --------------------------------------------------------------------------- #
# P10: no exception / path leakage in error responses
# --------------------------------------------------------------------------- #
class TestErrorSanitization:
    def test_file_read_error_is_generic(self, client, admin_headers):
        r = client.post("/api/v1/system/files/read",
                        json={"path": "nonexistent_file.txt"}, headers=admin_headers)
        # confined path exists check -> 404 "File not found", never a traceback
        assert r.status_code in (403, 404)
        body = r.json()
        # Structured error format: {"error": {...}}
        body_str = json.dumps(body).lower()
        assert "traceback" not in body_str
        assert "errno" not in body_str

    def test_no_strace_in_provider_settings_error(self, client, admin_headers):
        r = client.put("/api/v1/system/provider-settings",
                       json={"openai_api_key": "sk-should-not-echo"}, headers=admin_headers)
        assert r.status_code == 400
        body = r.json()
        # Structured error format: {"error": {"message": "..."}}
        if "error" in body:
            detail = json.dumps(body["error"]).lower()
        else:
            detail = json.dumps(body).lower()
        assert "refusing" in detail or "secret" in detail
        # the secret-shaped VALUE must never be echoed back, only the field name
        assert "sk-should-not-echo" not in detail
        assert "traceback" not in detail
        assert ".py" not in detail
