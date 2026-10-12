"""Platform Identity (spec §2) + Capability Registry (spec §1) tests.

Exercises real backend state via the FastAPI TestClient against the live app
graph: real persistence, real availability derivation, real audit logging --
never fabricated. (Spec §13 acceptance: API + authorization + negative +
persistence; §50: no fabricated capability activity.)
"""
from __future__ import annotations

import uuid

from jarvis_backend.core import create_token, get_store, hash_password, now_iso

# Substrings that must NEVER appear in an identity/response surface (#12).
_SECRET_LEAK_MARKERS = ("sk-", "AKIA", "xox", "ghp_", "eyJ")


def _make_admin_user():
    """Create an admin user and return auth headers."""
    uid = str(uuid.uuid4())
    users = get_store("users").load()
    users[uid] = {
        "id": uid, "email": f"admin-{uid}@t.test", "username": "admin_" + uid[:8],
        "password_hash": hash_password("Admin#Jarvis1"),
        "full_name": "Admin", "avatar_url": None, "status": "active",
        "tenant_id": None, "roles": ["admin"], "last_login_at": None,
        "created_at": now_iso(),
    }
    get_store("users").save()
    token = create_token({"sub": uid, "sid": None})
    return {"Authorization": f"Bearer {token}"}


def _make_regular_user():
    uid = str(uuid.uuid4())
    users = get_store("users").load()
    users[uid] = {"id": uid, "email": f"user-{uid}@t.test", "status": "active", "roles": ["user"]}
    get_store("users").save()
    return {"Authorization": f"Bearer {create_token({'sub': uid, 'sid': None})}"}


class TestPlatformIdentity:
    def test_get_identity_requires_admin_and_does_not_expose_metadata(self, client):
        unauthenticated = client.get("/api/v1/platform/identity")
        assert unauthenticated.status_code == 401
        assert "instance_id" not in unauthenticated.text

        regular_user = client.get(
            "/api/v1/platform/identity", headers=_make_regular_user()
        )
        assert regular_user.status_code == 403

    def test_get_identity_returns_real_state(self, client):
        r = client.get("/api/v1/platform/identity", headers=_make_admin_user())
        assert r.status_code == 200
        j = r.json()
        assert j["platform_name"] == "JARVIS Unified System"
        assert j["instance_id"]
        assert j["verification_status"] in ("verified", "unverified")
        assert isinstance(j["configured_providers"], list)
        assert isinstance(j["ai_enabled"], bool)
        assert "last_checked" in j and "provenance" in j
        assert j["provenance"].endswith("platform_identity.py")

    def test_get_identity_never_exposes_secrets(self, client):
        r = client.get("/api/v1/platform/identity", headers=_make_admin_user())
        assert r.status_code == 200
        text = r.text.lower()
        for marker in _SECRET_LEAK_MARKERS:
            assert marker.lower() not in text, f"secret token leaked: {marker}"
        for key in r.json():
            assert not any(s in key.lower() for s in ("key", "secret", "token", "password"))

    def test_put_identity_persists_and_audits(self, client):
        headers = _make_admin_user()
        r = client.put(
            "/api/v1/platform/identity",
            json={"developer_identity": "dev-001", "production_email_identity": "ops@jarvis.local"},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["developer_identity"] == "dev-001"
        assert body["production_email_identity"] == "ops@jarvis.local"
        assert body["verification_status"] == "verified"

        # Real persistence across requests (same app/db within the test):
        g = client.get("/api/v1/platform/identity", headers=headers)
        assert g.status_code == 200
        assert g.json()["developer_identity"] == "dev-001"

        # Real audit event in the shared audit log (spec §6 / #14):
        log = get_store("audit_logs").load()
        assert isinstance(log, list)
        assert any(
            isinstance(e, dict) and e.get("kind") == "identity" and e.get("action") == "updated"
            for e in log
        ), "identity update was not audit-logged"

    def test_put_rejects_secret_shaped_fields(self, client):
        headers = _make_admin_user()
        r = client.put(
            "/api/v1/platform/identity",
            json={"api_key": "sk-1234567890abcdef"},
            headers=headers,
        )
        assert r.status_code == 400
        assert "refusing" in r.text.lower()
        assert "sk-1234567890abcdef" not in r.text

    def test_put_rejects_invalid_transport(self, client):
        headers = _make_admin_user()
        r = client.put(
            "/api/v1/platform/identity",
            json={"notification_configuration": {"transport": "carrier_pigeon"}},
            headers=headers,
        )
        assert r.status_code == 400


class TestCapabilityRegistry:
    def test_registry_backward_compatible_and_rich(self, client):
        headers = _make_admin_user()
        r = client.get("/api/v1/system/capabilities", headers=headers)
        assert r.status_code == 200
        j = r.json()
        # Legacy flat list preserved (backward compatible):
        assert isinstance(j["capabilities"], list) and "chat" in j["capabilities"]
        # Spec §1 rich registry:
        assert isinstance(j["registry"], list) and j["registry"]
        entry = j["registry"][0]
        for field in (
            "capability", "category", "tool", "permissions", "provider",
            "model", "availability", "health", "ai_backed",
            "dependencies", "provenance", "last_checked",
        ):
            assert field in entry, f"capability entry missing {field}"
        assert entry["availability"] in ("available", "unavailable")
        assert entry["health"] in ("ok", "degraded", "offline")

    def test_availability_never_fabricated(self, client):
        """AI-backed availability must mirror ACTUAL platform state (#50)."""
        headers = _make_admin_user()
        identity = client.get("/api/v1/platform/identity", headers=headers).json()
        caps = client.get("/api/v1/system/capabilities", headers=headers).json()
        ai_ok = identity["ai_enabled"] and len(identity["configured_providers"]) > 0
        for e in caps["registry"]:
            if e["ai_backed"]:
                assert e["availability"] == ("available" if ai_ok else "unavailable")
            else:
                # Platform-backed capabilities are real local services.
                assert e["availability"] == "available"
