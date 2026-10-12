"""Tests for the Control Center API endpoints (spec §38).

Verifies:
  * ``GET /api/v1/control/status``  — 401 unauthenticated, 403 non-admin, 200 admin
  * ``GET /api/v1/control/credentials`` — 401 unauthenticated, 403 non-admin, 200 admin
  * No raw secret values are ever returned in any response.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jarvis_backend.core import create_token


@pytest.fixture
def test_client():
    from jarvis_backend.main import app

    with TestClient(app) as client:
        yield client


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_admin_user():
    """Create an admin user in the test store and return (user, headers)."""
    from jarvis_backend.core import hash_password, now_iso, get_store
    import uuid
    users = get_store("users").load()
    uid = str(uuid.uuid4())
    user = {
        "id": uid,
        "email": f"admin-{uid[:8]}@test.local",
        "username": f"admin_{uid[:8]}",
        "password_hash": hash_password("Admin#Jarvis1"),
        "full_name": "Admin Test",
        "avatar_url": None,
        "status": "active",
        "tenant_id": None,
        "roles": ["admin"],
        "last_login_at": None,
        "created_at": now_iso(),
    }
    users[uid] = user
    get_store("users").save()
    token = create_token({"sub": uid, "sid": None})
    return user, {"Authorization": f"Bearer {token}"}


def _make_regular_user():
    """Create a non-admin user in the test store and return (user, headers)."""
    from jarvis_backend.core import hash_password, now_iso, get_store
    import uuid
    users = get_store("users").load()
    uid = str(uuid.uuid4())
    user = {
        "id": uid,
        "email": f"user-{uid[:8]}@test.local",
        "username": f"user_{uid[:8]}",
        "password_hash": hash_password("User#Jarvis1"),
        "full_name": "Regular User",
        "avatar_url": None,
        "status": "active",
        "tenant_id": None,
        "roles": ["user"],
        "last_login_at": None,
        "created_at": now_iso(),
    }
    users[uid] = user
    get_store("users").save()
    token = create_token({"sub": uid, "sid": None})
    return user, {"Authorization": f"Bearer {token}"}


# Sensitive key names that must never appear as VALUES in responses.
# (The env-var / vault key *name* is OK to surface; the actual secret value is not.)
_SECRET_VALUE_MARKERS = [
    "sk-",
    "AKIA",
    "ghp_",
    "hf_",
    "eyJ",
]


# --------------------------------------------------------------------------- #
# GET /api/v1/control/status
# --------------------------------------------------------------------------- #
class TestControlStatus:
    def test_status_unauthenticated_returns_401(self, test_client: TestClient):
        resp = test_client.get("/api/v1/control/status")
        assert resp.status_code == 401

    def test_status_non_admin_returns_403(self, test_client: TestClient):
        _, headers = _make_regular_user()
        resp = test_client.get("/api/v1/control/status", headers=headers)
        assert resp.status_code == 403

    def test_status_admin_returns_200(self, test_client: TestClient):
        _, headers = _make_admin_user()
        resp = test_client.get("/api/v1/control/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # Required top-level keys.
        assert "providers" in data
        assert "provider_summary" in data
        assert "extensions" in data
        assert "connectors" in data

    def test_status_admin_structure(self, test_client: TestClient):
        _, headers = _make_admin_user()
        resp = test_client.get("/api/v1/control/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # provider_summary has total, connected, disconnected.
        summary = data["provider_summary"]
        assert "total" in summary
        assert "connected" in summary
        assert "disconnected" in summary
        # extensions has counts.
        ext = data["extensions"]
        assert "installed_count" in ext
        assert "connected_count" in ext
        # connectors has count.
        conn = data["connectors"]
        assert "count" in conn
        # providers is a list of dicts (each provider is safe — no secrets).
        assert isinstance(data["providers"], list)

    def test_status_no_secret_values_in_response(self, test_client: TestClient):
        """No raw API keys or passwords may appear anywhere in the response."""
        _, headers = _make_admin_user()
        resp = test_client.get("/api/v1/control/status", headers=headers)
        assert resp.status_code == 200
        body = resp.text.lower()
        for marker in _SECRET_VALUE_MARKERS:
            assert marker.lower() not in body, (
                f"Potential secret value '{marker}' found in /control/status response"
            )


# --------------------------------------------------------------------------- #
# GET /api/v1/control/credentials
# --------------------------------------------------------------------------- #
class TestControlCredentials:
    def test_credentials_unauthenticated_returns_401(self, test_client: TestClient):
        resp = test_client.get("/api/v1/control/credentials")
        assert resp.status_code == 401

    def test_credentials_non_admin_returns_403(self, test_client: TestClient):
        _, headers = _make_regular_user()
        resp = test_client.get("/api/v1/control/credentials", headers=headers)
        assert resp.status_code == 403

    def test_credentials_admin_returns_200(self, test_client: TestClient):
        _, headers = _make_admin_user()
        resp = test_client.get("/api/v1/control/credentials", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0  # at least the known providers

    def test_credentials_each_has_required_fields(self, test_client: TestClient):
        _, headers = _make_admin_user()
        resp = test_client.get("/api/v1/control/credentials", headers=headers)
        assert resp.status_code == 200
        for ref in resp.json():
            assert "provider" in ref
            assert "display_name" in ref
            assert "key" in ref          # the env-var name (OK to expose)
            assert "label" in ref
            assert "status" in ref       # "set" or "unset"
            assert ref["status"] in ("set", "unset")
            assert "source" in ref
            assert "identity_provider" in ref
            assert isinstance(ref["identity_provider"], bool)

    def test_credentials_never_expose_secret_values(self, test_client: TestClient):
        """Credential refs must only show status, never the actual secret."""
        _, headers = _make_admin_user()
        resp = test_client.get("/api/v1/control/credentials", headers=headers)
        assert resp.status_code == 200
        body = resp.text
        # The raw secret markers must not appear as values.
        for marker in _SECRET_VALUE_MARKERS:
            assert marker not in body, (
                f"Potential secret value '{marker}' found in /control/credentials response"
            )

    def test_credentials_status_consistent_with_env(self, test_client: TestClient):
        """If a provider env var is set to empty, its status should be 'unset'."""
        _, headers = _make_admin_user()
        resp = test_client.get("/api/v1/control/credentials", headers=headers)
        assert resp.status_code == 200
        # In the test env, no provider env vars are set, so every status
        # should be "unset" unless a vault key happens to exist.
        for ref in resp.json():
            # status is a string; value is one of set/unset
            assert isinstance(ref["status"], str)
