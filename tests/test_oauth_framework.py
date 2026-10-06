"""Stage 1 — shared OAuth2 token-store framework tests (no network).

Covers ``jarvis_backend/connectors/oauth.py``:
  * HMAC-bound state token (round-trip, tamper detection, expiry/replay).
  * client_config resolution from JARVIS_OAUTH_CLIENTS (graceful None).
  * Fernet-encrypted-at-rest token persistence (plaintext never persisted).
  * connection_metadata status enum (Authorization required | Expired | Connected).
  * access_token lazy-refresh (httpx.post mocked).
"""
from __future__ import annotations

import base64
import json
import os
import time

import pytest

# Deterministic signing/encryption key BEFORE any jarvis_backend import so the
# JWT signer and the Fernet vault agree within this process.
os.environ.setdefault("JARVIS_SECRET_KEY", "stage1-test-secret-key-0123456789abcdef")
os.environ.setdefault("JARVIS_TEST_MODE", "1")

from jarvis_backend.connectors import oauth  # noqa: E402
from jarvis_backend.core import get_store  # noqa: E402

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


@pytest.fixture(autouse=True)
def _clients_env(monkeypatch):
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", json.dumps(GMAIL_CLIENTS))
    yield


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path, monkeypatch):
    from jarvis_backend.connectors import registry
    monkeypatch.setattr(registry, "CONNECTORS_DIR", tmp_path / "connectors")
    monkeypatch.setattr(registry, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(registry, "AUDIT_FILE", tmp_path / "audit" / "connectors.jsonl")
    yield


def _id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": email, "sub": email}).encode()).decode().rstrip("=")
    return f"hdr.{payload}.sig"


# --- state -----------------------------------------------------------------
def test_state_roundtrip():
    state = oauth.make_state("gmail", "user-123")
    k, uid = oauth.verify_state(state)
    assert k == "gmail" and uid == "user-123"


def test_state_tamper_detected():
    state = oauth.make_state("gmail", "user-123")
    payload, _, sig = state.partition(".")
    bad_payload = payload[:-1] + ("A" if payload[-1] != "A" else "B")
    with pytest.raises(oauth.OAuthError, match="invalid state signature"):
        oauth.verify_state(bad_payload + "." + sig)


def test_state_malformed_rejected():
    with pytest.raises(oauth.OAuthError):
        oauth.verify_state("garbage")


def test_state_requires_configured_secret(monkeypatch):
    monkeypatch.delenv("JARVIS_SECRET_KEY", raising=False)
    with pytest.raises(oauth.OAuthError, match="JARVIS_SECRET_KEY"):
        oauth.make_state("gmail", "u1")


def test_state_expires_after_ttl(monkeypatch):
    base = time.time()
    monkeypatch.setattr(oauth.time, "time", lambda: base)
    state = oauth.make_state("gmail", "u1")
    monkeypatch.setattr(oauth.time, "time", lambda: base + 700)  # > STATE_TTL(600)
    with pytest.raises(oauth.OAuthError, match="state expired"):
        oauth.verify_state(state)


def test_exchange_code_rejects_kind_mismatch():
    state = oauth.make_state("gmail", "u1")
    with pytest.raises(oauth.OAuthError, match="does not match"):
        oauth.exchange_code("outlook", "CODE", state, "u1")


# --- client config ---------------------------------------------------------
def test_client_config_resolves_each_kind():
    assert oauth.client_config("gmail")["client_id"] == "test-gmail-id"
    cfg = oauth.client_config("outlook")
    assert cfg["token_url"].startswith("https://login.microsoftonline.com")
    assert cfg["is_microsoft"] is True


def test_client_config_missing_kind(monkeypatch):
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", json.dumps({"github": {"client_id": "x"}}))
    assert oauth.client_config("gmail") is None
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", "not-json")
    assert oauth.client_config("gmail") is None
    monkeypatch.delenv("JARVIS_OAUTH_CLIENTS", raising=False)
    assert oauth.client_config("gmail") is None


def test_authorize_url_contains_state_and_offline_access():
    url = oauth.authorize_url("gmail", "u1")
    assert "client_id=test-gmail-id" in url
    assert "access_type=offline" in url and "prompt=consent" in url
    assert url.split("state=")[1].split("&")[0]  # state present
    assert "redirect_uri=" in url
    assert url.endswith("/connectors/oauth/callback/gmail") or "&redirect_uri=" in url


# --- encrypted-at-rest token persistence -----------------------------------
def test_tokens_are_encrypted_at_rest():
    oauth.save_tokens("gmail", "u1", {
        "access_token": "AT-123", "refresh_token": "RT-456",
        "expires_at": time.time() + 3600, "account": "a@b.com",
        "scope": "gmail.readonly",
    })
    raw = get_store("oauth_tokens").load()["gmail:u1"]
    assert raw["access_token"].startswith("fernet:")
    blob = json.dumps(raw)
    assert "AT-123" not in blob and "RT-456" not in blob


def test_token_round_trip():
    oauth.save_tokens("gmail", "u1", {
        "access_token": "AT-123", "refresh_token": "RT-456",
        "expires_at": time.time() + 3600, "account": "a@b.com",
    })
    loaded = oauth.load_tokens("gmail", "u1")
    assert loaded["access_token"] == "AT-123"
    assert loaded["refresh_token"] == "RT-456"
    assert loaded["account"] == "a@b.com"


def test_delete_tokens():
    oauth.save_tokens("gmail", "u1", {"access_token": "AT", "expires_at": time.time() + 3600})
    assert oauth.load_tokens("gmail", "u1") is not None
    assert oauth.delete_tokens("gmail", "u1") is True
    assert oauth.load_tokens("gmail", "u1") is None
    assert oauth.delete_tokens("gmail", "u1") is False


def test_exchange_code_persists_encrypted_tokens(monkeypatch):
    user_id = f"u1-{time.time_ns()}"
    state = oauth.make_state("gmail", user_id)

    class Resp:
        status_code = 200

        def json(self):
            return {"access_token": "AT", "refresh_token": "RT",
                    "expires_in": 3600, "id_token": _id_token("a@b.com"),
                    "scope": "gmail.readonly"}

    monkeypatch.setattr(oauth.httpx, "post", lambda *a, **k: Resp())
    tokens = oauth.exchange_code("gmail", "CODE", state, user_id)
    assert tokens["access_token"] == "AT"
    stored = get_store("oauth_tokens").load()[f"gmail:{user_id}"]
    assert stored["access_token"].startswith("fernet:")
    assert stored["access_token"] != "AT"
    assert stored["refresh_token"] != "RT"
    assert stored.get("account") == "a@b.com"


# --- connection metadata ---------------------------------------------------
def test_connection_metadata_not_configured():
    m = oauth.connection_metadata("gmail", "nobody")
    assert m["status"] == "Authorization required"
    assert m["connected"] is False


def test_connection_metadata_expired_without_refresh():
    oauth.save_tokens("gmail", "u2", {"access_token": "AT", "refresh_token": None,
                                     "expires_at": time.time() - 10, "account": "a@b.com"})
    m = oauth.connection_metadata("gmail", "u2")
    assert m["status"] == "Expired"
    assert m["connected"] is False
    assert m["token_expires_at"] is not None


def test_connection_metadata_connected():
    oauth.save_tokens("gmail", "u3", {"access_token": "AT", "refresh_token": "RT",
                                     "expires_at": time.time() + 3600, "account": "a@b.com"})
    m = oauth.connection_metadata("gmail", "u3")
    assert m["status"] == "Connected"
    assert m["connected"] is True


def test_non_expiring_oauth_token_remains_connected_and_usable():
    oauth.save_tokens("github", "github-user", {
        "access_token": "gh-oauth-token",
        "account": "octocat",
        "scope": "repo",
    })

    metadata = oauth.connection_metadata("github", "github-user")
    assert metadata["status"] == "Connected"
    assert metadata["connected"] is True
    assert oauth.access_token("github", "github-user") == "gh-oauth-token"


def test_connection_metadata_never_exposes_tokens():
    oauth.save_tokens("gmail", "u3", {"access_token": "AT", "refresh_token": "RT",
                                     "expires_at": time.time() + 3600})
    m = oauth.connection_metadata("gmail", "u3")
    blob = json.dumps(m)
    assert "access_token" not in blob
    assert "refresh_token" not in blob
    assert "fernet:" not in blob


# --- lazy refresh ----------------------------------------------------------
def test_access_token_returns_fresh_when_valid():
    oauth.save_tokens("gmail", "u1", {"access_token": "AT", "refresh_token": "RT",
                                     "expires_at": time.time() + 3600})
    assert oauth.access_token("gmail", "u1") == "AT"


def test_access_token_returns_none_when_no_tokens():
    assert oauth.access_token("gmail", f"missing-{time.time_ns()}") is None


def test_access_token_refreshes_when_expired(monkeypatch):
    oauth.save_tokens("gmail", "u1", {"access_token": "OLD", "refresh_token": "RT",
                                     "expires_at": time.time() - 10, "account": "a@b.com"})

    class Resp:
        status_code = 200

        def json(self):
            return {"access_token": "NEW", "expires_in": 3600, "refresh_token": "RT2"}

    monkeypatch.setattr(oauth.httpx, "post", lambda *a, **k: Resp())
    assert oauth.access_token("gmail", "u1") == "NEW"
