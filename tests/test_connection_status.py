"""Stage 1 — connection status + token expiry exposure (spec §38/§21).

GET /api/v1/connectors must enumerate gmail/outlook and report a safe
connection status (`Authorization required` | `Expired` | `Connected`) plus
token_expires_at — while NEVER returning a credential.
"""
from __future__ import annotations

import os

os.environ.setdefault("JARVIS_SECRET_KEY", "stage1-test-secret-key-0123456789abcdef")
os.environ.setdefault("JARVIS_TEST_MODE", "1")

import pytest  # noqa: E402

from jarvis_backend.connectors import oauth, registry  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONNECTORS_DIR", tmp_path / "connectors")
    monkeypatch.setattr(registry, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(registry, "AUDIT_FILE", tmp_path / "audit" / "connectors.jsonl")
    yield


def _blob(resp) -> str:
    return resp.data.decode("utf-8", "replace") if hasattr(resp, "data") else str(resp)


def test_list_includes_gmail_and_outlook(client, admin_headers):
    r = client.get("/api/v1/connectors", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    kinds = {c["kind"] for c in body["connectors"]}
    assert {"gmail", "outlook"} <= kinds
    blob = _blob(r)
    # No credential material may ever appear in the listing.
    assert "fernet:" not in blob
    assert "access_token" not in blob and "refresh_token" not in blob


def test_list_reports_authorization_required_when_unconnected(client, admin_headers):
    registry.save({"kind": "gmail", "provider": "gmail", "oauth_user_id": "test-admin",
                   "capabilities": ["read"], "enabled": True})
    r = client.get("/api/v1/connectors", headers=admin_headers)
    assert r.status_code == 200
    gmail = next(c for c in r.json()["connectors"] if c["kind"] == "gmail")
    assert gmail["configured"] is True
    assert gmail["connection_status"] == "Authorization required"
    # The OAuth owner id and bearer are private server-side connector metadata.
    assert "oauth_user_id" not in gmail.get("config", {})
    assert gmail.get("account") is None


def test_get_connector_reports_connection_status(client, admin_headers):
    registry.save({"kind": "gmail", "provider": "gmail", "oauth_user_id": "test-admin",
                   "capabilities": ["read", "summarize", "draft", "send"], "enabled": True})
    r = client.get("/api/v1/connectors/gmail", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["connection_status"]["status"] == "Authorization required"
    assert "access_token" not in body["connection_status"]
    assert "refresh_token" not in body["connection_status"]
    blob = _blob(r)
    assert "fernet:" not in blob


def test_get_connector_unknown_kind(client, admin_headers):
    r = client.get("/api/v1/connectors/nope", headers=admin_headers)
    assert r.status_code == 404


def test_list_actions_carry_risk_and_confirmation(client, admin_headers):
    r = client.get("/api/v1/connectors", headers=admin_headers)
    actions_by_kind = {c["kind"]: c["actions"] for c in r.json()["connectors"]}
    send = next(a for a in actions_by_kind["gmail"] if a["name"] == "gmail.send")
    assert send["risk_level"] == "HIGH"
    assert send["requires_confirmation"] is True
    search = next(a for a in actions_by_kind["outlook"] if a["name"] == "outlook.search")
    assert search["risk_level"] == "LOW" and search["requires_confirmation"] is False


def test_connector_metadata_requires_authentication(client):
    assert client.get("/api/v1/connectors").status_code == 401
    assert client.get("/api/v1/connectors/activity").status_code == 401
    assert client.get("/api/v1/connectors/gmail").status_code == 401
