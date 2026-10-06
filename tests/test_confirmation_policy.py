"""Stage 1 — human-in-the-loop confirmation gate (dispatch, spec §10/§34/§40).

HIGH/CRITICAL actions and any requires_confirmation action must be blocked until
the same request is re-issued with params['confirm']=true. The gate is audited.
Also pins the canonical RBAC role seed (spec §44).
"""
from __future__ import annotations

import json
import os
import time
from unittest import mock

import pytest

os.environ.setdefault("JARVIS_SECRET_KEY", "stage1-test-secret-key-0123456789abcdef")
os.environ.setdefault("JARVIS_TEST_MODE", "1")

from jarvis_backend.connectors import dispatch, oauth  # noqa: E402
from jarvis_backend.connectors import registry  # noqa: E402
from jarvis_backend.connectors.mail.gmail_oauth import GmailOAuthConnector  # noqa: E402
from jarvis_backend.connectors.base import ActionSpec, Connector  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONNECTORS_DIR", tmp_path / "connectors")
    monkeypatch.setattr(registry, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(registry, "AUDIT_FILE", tmp_path / "audit" / "connectors.jsonl")
    yield


def _configure_gmail(caps=("read", "summarize", "draft", "send")):
    registry.save({
        "kind": "gmail", "provider": "gmail", "oauth_user_id": "u1",
        "capabilities": list(caps), "enabled": True,
    })


async def _send(params):
    return await dispatch.execute_connector_action(
        "gmail", "gmail.send", params, actor="dev", user_id="u1")


async def test_send_blocked_without_confirmation():
    _configure_gmail()
    res = await _send({"to": ["a@b.com"], "subject": "hi", "body": "hello"})
    assert res["ok"] is False
    assert res["confirmation_required"] is True
    assert res["risk_level"] == "HIGH"
    assert res["summary"] == "Send an email (audited, requires confirmation)"
    # the message body must never be echoed back in the preview
    assert "body" not in res.get("preview", {})
    # body chars only, no plaintext body
    assert res["preview"].get("body_chars") == len("hello")


async def test_send_blocked_audit_entry_written():
    _configure_gmail()
    await _send({"to": ["a@b.com"], "subject": "hi", "body": "hello"})
    blocks = [e for e in registry.read_audit(100)
              if e.get("action") == "gmail.send" and e.get("confirmation_required") is True
              and e.get("ok") is False]
    assert blocks and blocks[-1]["risk_level"] == "HIGH"
    # the blocked entry records that no confirmation was supplied (key only
    # present on executed action audits; blocked audits carry confirmation_required)
    assert "confirmed" not in blocks[-1] or blocks[-1].get("confirmed") is False


async def test_send_confirmed_then_executes_and_audits_confirmed(monkeypatch):
    _configure_gmail()
    # Pre-seed a valid token so _token() resolves without network.
    oauth.save_tokens("gmail", "u1", {"access_token": "AT", "refresh_token": "RT",
                                      "expires_at": time.time() + 3600, "account": "a@b.com"})

    async def _fake_run(self, name, params):
        return {"sent": True, "message_id": "msg-1"}

    monkeypatch.setenv("JARVIS_SECRET_KEY", "stage1-test-secret-key-0123456789abcdef")
    with mock.patch.object(GmailOAuthConnector, "run_action", _fake_run):
        res = await _send({"to": ["a@b.com"], "subject": "hi", "body": "hello", "confirm": True})
    assert res["ok"] is True
    conf = [e for e in registry.read_audit(100)
            if e.get("action") == "gmail.send" and e.get("confirmed") is True and e.get("ok") is True]
    assert conf and conf[-1]["risk_level"] == "HIGH"


async def test_capability_denied_without_send_consent():
    _configure_gmail(caps=("read",))  # send capability disabled
    res = await _send({"to": ["a@b.com"], "subject": "hi", "body": "hello"})
    assert res["ok"] is False
    assert "capability" in res["error"].lower() or "capability" in res.get("error", "").lower()
    assert "send" in res["error"]


async def test_unconfigured_connector_honest_refusal():
    # No config saved for 'gmail' -> honest refusal, no fabricated result.
    res = await dispatch.execute_connector_action(
        "gmail", "gmail.send", {"to": ["a@b.com"], "subject": "x", "body": "y"})
    assert res["ok"] is False
    assert isinstance(res.get("error"), str) and len(res["error"]) > 0
    assert "results" not in res and "sent" not in res


async def test_unknown_action_honest_refusal():
    _configure_gmail()
    res = await dispatch.execute_connector_action("gmail", "gmail.nope", {"confirm": True})
    assert res["ok"] is False and "unknown action" in res["error"].lower()


def test_canonical_rbac_roles_seeded():
    from jarvis_backend.core import start_backend, get_store
    start_backend()
    roles = get_store("roles").load()
    present = {r.get("name") for r in roles.values() if isinstance(r, dict)}
    required = {"owner", "admin", "operator", "developer", "analyst", "viewer"}
    assert required <= present
    # owner/admin are wildcard-permissioned
    assert "*" in (roles.get("owner") or roles.get("admin") or {}).get("permissions", [])
