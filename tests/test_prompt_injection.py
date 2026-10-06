"""Stage 1 — honest refusal / no-fabrication (dispatch boundary, spec §24/§34).

The AI must never make a connector action succeed by inventing state. Every
policy failure returns a plain refusal describing what is *missing*. This file
also covers the OAuth authorize/callback route guards (401 / 409 / state).
"""
from __future__ import annotations

import os
import json
import uuid

os.environ.setdefault("JARVIS_SECRET_KEY", "stage1-test-secret-key-0123456789abcdef")
os.environ.setdefault("JARVIS_TEST_MODE", "1")

import pytest  # noqa: E402

from jarvis_backend.connectors import dispatch, registry  # noqa: E402
from jarvis_backend.core import (  # noqa: E402
    create_token,
    get_store,
    hash_password,
    now_iso,
    start_backend,
)


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONNECTORS_DIR", tmp_path / "connectors")
    monkeypatch.setattr(registry, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(registry, "AUDIT_FILE", tmp_path / "audit" / "connectors.jsonl")
    yield


def _admin_user():
    start_backend()
    uid = str(uuid.uuid4())
    users = get_store("users").load()
    users[uid] = {
        "id": uid, "email": "admin@example.com", "username": "admin",
        "password_hash": hash_password("Admin#Jarvis1"), "full_name": "Admin",
        "avatar_url": None, "status": "active", "tenant_id": None,
        "roles": ["admin"], "last_login_at": None, "created_at": now_iso(),
    }
    get_store("users").save()
    tok = create_token({"sub": uid})
    return {"token": tok, "headers": {"Authorization": f"Bearer {tok}"}}


# --- dispatch-level honest refusal ----------------------------------------
async def test_unknown_kind_is_refused():
    res = await dispatch.execute_connector_action("nope", "x", {})
    assert res["ok"] is False
    assert "unknown connector kind" in res["error"]
    assert "result" not in res and "results" not in res


async def test_unconfigured_gmail_refused_not_fabricated():
    res = await dispatch.execute_connector_action(
        "gmail", "gmail.send", {"to": ["a@b.com"], "subject": "s", "body": "b"})
    assert res["ok"] is False
    assert isinstance(res.get("error"), str) and res["error"]
    # no success-shaped payload
    for key in ("results", "sent", "draft", "message_id"):
        assert key not in res


async def test_send_without_capability_refused():
    registry.save({"kind": "gmail", "provider": "gmail", "oauth_user_id": "u1",
                   "capabilities": ["read"], "enabled": True})
    res = await dispatch.execute_connector_action(
        "gmail", "gmail.send", {"to": ["a@b.com"], "subject": "s", "body": "b"})
    assert res["ok"] is False
    assert "send" in res["error"] and "capability" in res["error"].lower()


def test_unknown_action_describe_only():
    registry.save({"kind": "gmail", "provider": "gmail", "oauth_user_id": "u1",
                   "capabilities": ["read", "summarize", "draft", "send"], "enabled": True})
    # action_spec is the schema surface the AI may propose; unknown names resolve null
    assert dispatch.connector_class("gmail")({}).action_spec("gmail.nope") is None


# --- OAuth route guards ----------------------------------------------------
def test_oauth_authorize_requires_auth(client):
    r = client.post("/api/v1/connectors/gmail/oauth/authorize")
    assert r.status_code == 401


def test_oauth_authorize_409_when_no_client(client, monkeypatch):
    monkeypatch.delenv("JARVIS_OAUTH_CLIENTS", raising=False)
    admin = _admin_user()
    r = client.post("/api/v1/connectors/gmail/oauth/authorize",
                    headers=admin["headers"])
    assert r.status_code == 409


def test_oauth_authorize_404_for_non_oauth_kind(client):
    admin = _admin_user()
    r = client.post("/api/v1/connectors/email/oauth/authorize", headers=admin["headers"])
    assert r.status_code == 404


def test_oauth_callback_rejects_bad_state(client, monkeypatch):
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", json.dumps({
        "gmail": {"client_id": "x", "client_secret": "y",
                  "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                  "token_url": "https://oauth2.googleapis.com/token",
                  "scope": "https://www.googleapis.com/auth/gmail.readonly",
                  "is_google": True}}))
    r = client.get("/api/v1/connectors/oauth/callback/gmail?code=x&state=bogus")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "state" in body["error"].lower() or "signature" in body["error"].lower()


def test_oauth_callback_unknown_kind(client):
    r = client.get("/api/v1/connectors/oauth/callback/nope?code=x&state=y")
    assert r.status_code == 404
