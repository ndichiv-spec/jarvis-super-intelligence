"""Stage 1 — credential-leakage hardening tests (security).

Spec §19/§20/#50: OAuth tokens/refresh_tokens/secrets must never appear in any
/connectors response. Secret fields are Fernet-encrypted at rest and masked in
public_config; OAuth tokens live only in the encrypted SQL vault.
"""
from __future__ import annotations

import json
import os
import time

os.environ.setdefault("JARVIS_SECRET_KEY", "stage1-test-secret-key-0123456789abcdef")
os.environ.setdefault("JARVIS_TEST_MODE", "1")

import pytest  # noqa: E402

from jarvis_backend.connectors import oauth, registry  # noqa: E402
from jarvis_backend.connectors.crypto import decrypt_secret, encrypt_secret  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONNECTORS_DIR", tmp_path / "connectors")
    monkeypatch.setattr(registry, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(registry, "AUDIT_FILE", tmp_path / "audit" / "connectors.jsonl")
    yield


FORBIDDEN = ("access_token", "refresh_token", "client_secret", "password")


def _assert_no_secret(blob: str):
    blob = blob.lower()
    assert "fernet:" not in blob, blob
    for tok in ("at-123", "rt-456", "super-secret-pw", "client-secret-value"):
        assert tok not in blob.lower(), blob


def test_public_config_masks_secrets():
    raw = {"kind": "email", "provider": "IMAP", "imap_host": "h", "password": "super-secret-pw",
           "api_key": "client-secret-value"}
    pub = registry.public_config(raw)
    assert pub["password"] == registry.MASK
    assert pub["password_set"] is True
    assert pub["api_key"] == registry.MASK
    assert pub["api_key_set"] is True
    _assert_no_secret(json.dumps(pub))


def test_password_save_encrypts_at_rest(tmp_path):
    # registry already isolated by autouse fixture
    registry.save({"kind": "email", "provider": "IMAP", "password": "super-secret-pw",
                   "imap_host": "h", "capabilities": ["read"]})
    on_disk = json.loads(registry.CONNECTORS_DIR.joinpath("email.json").read_text(encoding="utf-8"))
    # The stored value must be the encrypted form (not plaintext).
    assert on_disk["password"].startswith("fernet:")
    assert "super-secret-pw" not in json.dumps(on_disk)
    # The public (API) view masks the secret, still no plaintext / token.
    pub = registry.public_config(on_disk)
    assert pub["password"] == registry.MASK
    assert "super-secret-pw" not in json.dumps(pub)


def test_gmail_token_never_in_connectors_api(client, admin_headers):
    # Connect gmail (oauth_user_id) and store an encrypted token in the SQL vault.
    registry.save({"kind": "gmail", "provider": "gmail", "owner_user_id": "test-admin",
                   "oauth_user_id": "test-admin",
                   "capabilities": ["read", "summarize", "draft", "send"], "enabled": True})
    oauth.save_tokens("gmail", "test-admin", {"access_token": "AT-123", "refresh_token": "RT-456",
                                      "expires_at": time.time() + 3600, "account": "a@b.com"})
    for path in ("/api/v1/connectors", "/api/v1/connectors/gmail"):
        r = client.get(path, headers=admin_headers)
        assert r.status_code == 200
        blob = json.dumps(r.json())
        assert "AT-123" not in blob
        assert "RT-456" not in blob
        assert "fernet:" not in blob
        assert "access_token" not in blob and "refresh_token" not in blob


def test_fernet_round_trips_via_crypto():
    enc = encrypt_secret("top-secret")
    assert enc.startswith("fernet:")
    assert decrypt_secret(enc) == "top-secret"
    # empty secret cannot be encrypted (no silent plaintext)
    with pytest.raises(Exception):
        encrypt_secret("")
