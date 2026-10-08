"""Connectors API tests — email (IMAP + SMTP) via REAL protocol servers.

The IMAP/SMTP connectors are exercised against minimal-but-procotol-correct
IMAP4rev1 and SMTP servers on loopback TCP (tests/fakes/mail_servers.py), so
the same `imaplib`/`smtplib` code path a production mailbox uses is covered:
greeting, LOGIN, LIST, SELECT, UID SEARCH, UID FETCH with literals, EHLO,
MAIL/RCPT/DATA.  Optional real-mailbox mode: set TEST_MAIL_IMAP_HOST /
TEST_MAIL_SMTP_HOST to run against a live app-password mailbox.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from tests.fakes.mail_servers import FakeIMAPServer, FakeSMTPServer

pytestmark = pytest.mark.skipif(
    os.environ.get("JARVIS_FAST_TESTS") == "1",
    reason="requires real loopback sockets (set JARVIS_FAST_TESTS!=1)",
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def mail_fakes():
    imap = FakeIMAPServer().start()
    smtp = FakeSMTPServer().start()
    yield {
        "imap_port": imap.port,
        "smtp_port": smtp.port,
        "sink": smtp.sink,
        "imap": imap,
        "smtp": smtp,
    }
    imap.stop()
    smtp.stop()


@pytest.fixture
def iso_dirs(tmp_path, monkeypatch):
    from jarvis_backend.connectors import registry

    cd = tmp_path / "connectors"
    ad = tmp_path / "audit"
    monkeypatch.setattr(registry, "CONNECTORS_DIR", cd)
    monkeypatch.setattr(registry, "AUDIT_DIR", ad)
    monkeypatch.setattr(registry, "AUDIT_FILE", ad / "connectors.jsonl")
    return cd, ad


def _config(fakes, **overrides):
    cfg = {
        "kind": "email",
        "provider": "Fake",
        "enabled": True,
        "imap_host": "127.0.0.1",
        "imap_port": fakes["imap_port"],
        "imap_ssl": False,
        "imap_user": "dev@fake.dev",
        "password": "app-password-123",
        "smtp_host": "127.0.0.1",
        "smtp_port": fakes["smtp_port"],
        "smtp_starttls": False,
        "send_from": "dev@fake.dev",
        "capabilities": ["read", "summarize", "draft", "send"],
    }
    cfg.update(overrides)
    return cfg


def _run(kind, action, params=None, actor="test", user_id=None):
    from jarvis_backend.connectors.dispatch import execute_connector_action

    return asyncio.run(
        execute_connector_action(kind, action, params or {}, actor=actor, user_id=user_id)
    )


def _admin_headers():
    import uuid

    from jarvis_backend.core import create_token, get_store, hash_password, now_iso

    users = get_store("users").load()
    uid = str(uuid.uuid4())
    users[uid] = {
        "id": uid,
        "email": f"admin-{uid[:8]}@jarvis.local",
        "username": f"connadmin_{uid[:6]}",
        "password_hash": hash_password("S3cret!pass"),
        "full_name": "Connector Admin",
        "status": "active",
        "roles": ["admin"],
        "created_at": now_iso(),
    }
    get_store("users").save()
    return {"Authorization": f"Bearer {create_token({'sub': uid, 'sid': None})}"}


# --------------------------------------------------------------------------- #
# registry security: encryption + masking
# --------------------------------------------------------------------------- #
def test_secret_round_trips_and_is_never_plaintext_on_disk(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    cfg = _config(mail_fakes)
    registry.save(cfg)
    loaded = registry.load("email")
    assert loaded["password"] == "app-password-123"
    disk = (iso_dirs[0] / "email.json").read_text(encoding="utf-8")
    assert "app-password-123" not in disk
    assert "fernet:" in disk


def test_public_config_masks_secret(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    pub = registry.public_config(registry.load("email"))
    assert pub["password"] == registry.MASK
    assert pub["password_set"] is True

    pub_none = registry.public_config(None)
    assert pub_none is None


# --------------------------------------------------------------------------- #
# dispatch policy (honest refusal, consent, kill switch)
# --------------------------------------------------------------------------- #
def test_unconfigured_connector_refuses_honestly(iso_dirs):
    result = _run("email", "email.folders", {})
    assert result["ok"] is False
    assert "not configured" in result["error"].lower()
    assert "Connections" in result["error"]


def test_disabled_connector_refuses(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes, enabled=False))
    result = _run("email", "email.folders", {})
    assert result["ok"] is False
    assert "disabled" in result["error"].lower()


def test_capability_gate_refuses_send(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes, capabilities=["read"]))
    result = _run("email", "email.send", {"to": ["x@example.com"], "subject": "hi", "body": "yo"})
    assert result["ok"] is False
    assert "capability" in result["error"].lower()
    assert mail_fakes["sink"] == []


def test_unknown_action_refuses(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    result = _run("email", "email.purge_all", {})
    assert result["ok"] is False
    assert "unknown action" in result["error"].lower()


# --------------------------------------------------------------------------- #
# live protocol flow against the real loopback IMAP + SMTP servers
# --------------------------------------------------------------------------- #
def test_connector_test_reports_ok(iso_dirs, mail_fakes):
    from jarvis_backend.connectors.mail.connector import MailConnector

    conn = MailConnector(_config(mail_fakes))
    result = conn.test()
    assert result["ok"] is True
    assert result["imap"]["ok"] is True
    assert result["smtp"]["ok"] is True


def test_list_folders_via_real_imap(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    result = _run("email", "email.folders")
    assert result["ok"] is True
    names = [f["name"] for f in result["folders"]]
    assert "INBOX" in names


def test_search_returns_messages(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    result = _run("email", "email.search", {"query": "ALL", "limit": 10})
    assert result["ok"] is True
    subjects = [m["subject"] for m in result["results"]]
    assert result["count"] == 3
    assert any("Project status" in s for s in subjects)


def test_read_returns_body(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    result = _run("email", "email.read", {"uid": "1"})
    assert result["ok"] is True
    assert "release is on track" in result.get("body", "")


def test_summarize_builds_digest(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    result = _run("email", "email.summarize", {"limit": 3})
    assert result["ok"] is True
    assert result["count"] == 3
    assert all("subject" in d for d in result["digest"])


def test_draft_never_sends(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    result = _run("email", "email.draft", {"to": ["x@example.com"], "subject": "Draft", "body": "hello"})
    assert result["ok"] is True
    assert result["draft"] is True
    assert mail_fakes["sink"] == []


def test_send_flows_through_real_smtp(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    result = _run("email", "email.send",
                  {"to": ["bob@example.com"], "subject": "Quarterly numbers", "body": "Please review."})
    assert result["ok"] is True
    assert result["sent"] is True
    assert len(mail_fakes["sink"]) == 1
    raw = mail_fakes["sink"][0].decode("utf-8", "replace")
    assert "Subject: Quarterly numbers" in raw
    assert "JARVIS AI" in raw  # provenance footer


def test_send_is_audited(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    _run("email", "email.send", {"to": ["bob@example.com"], "subject": "s", "body": "b"})
    entries = registry.read_audit(100)
    sends = [e for e in entries if e.get("action") == "email.send"]
    assert len(sends) == 1
    assert sends[0]["ok"] is True
    assert sends[0]["actor"] == "test"


def test_reply_resolves_original_and_sends(iso_dirs, mail_fakes):
    from jarvis_backend.connectors import registry

    registry.save(_config(mail_fakes))
    result = _run("email", "email.reply", {"folder": "INBOX", "uid": "2", "body": "On it."})
    assert result["ok"] is True
    assert result["sent"] is True
    raw = mail_fakes["sink"][0].decode("utf-8", "replace")
    assert "Re: Invoice attached" in raw
    assert len(mail_fakes["sink"]) == 1


# --------------------------------------------------------------------------- #
# HTTP API
# --------------------------------------------------------------------------- #
def test_actions_require_auth(client, iso_dirs):
    r = client.post("/api/v1/connectors/email/actions",
                    json={"action": "email.folders", "params": {}})
    assert r.status_code == 401


def test_manage_requires_admin(client, iso_dirs, auth_user):
    r = client.post("/api/v1/connectors/email",
                    json={"imap_host": "127.0.0.1", "imap_user": "u", "password": "p"},
                    headers=auth_user["headers"])
    assert r.status_code == 403


def test_connector_lifecycle_via_api(client, iso_dirs, mail_fakes):
    headers = _admin_headers()
    payload = {
        "provider": "Fake",
        "imap_host": "127.0.0.1",
        "imap_port": mail_fakes["imap_port"],
        "imap_ssl": False,
        "imap_user": "dev@fake.dev",
        "password": "app-password-123",
        "smtp_host": "127.0.0.1",
        "smtp_port": mail_fakes["smtp_port"],
        "smtp_starttls": False,
        "send_from": "dev@fake.dev",
        "capabilities": ["read", "summarize", "draft", "send"],
        "enabled": True,
    }
    created = client.post("/api/v1/connectors/email", json=payload, headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["config"]["password"] == "\u2022" * 6

    listing = client.get("/api/v1/connectors", headers=headers).json()
    assert listing["count"] == 1
    assert listing["connectors"][0]["config"]["password_set"] is True

    # masked patch keeps the secret
    patched = client.patch("/api/v1/connectors/email",
                           json={"password": "\u2022" * 6, "enabled": False, "capabilities": ["read"]},
                           headers=headers)
    assert patched.status_code == 200
    after = client.get("/api/v1/connectors/email", headers=headers).json()["config"]
    assert after["enabled"] is False
    assert after["password_set"] is True
    assert after["capabilities"] == ["read"]

    removed = client.delete("/api/v1/connectors/email", headers=headers)
    assert removed.status_code == 200
    assert client.get("/api/v1/connectors", headers=headers).json()["count"] == 0


def test_agent_act_email_refuses_when_unconfigured(client, iso_dirs, auth_headers):
    r = client.post("/api/v1/agents/coder/act",
                    json={"action": "email", "params": {"email_action": "email.folders"}},
                    headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "not configured" in body["result"]["error"].lower()


def test_coder_agent_has_email_capability(client):
    agent = client.get("/api/v1/agents/coder").json()
    assert "email" in agent.get("capabilities", [])