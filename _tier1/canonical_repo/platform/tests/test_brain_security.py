"""§8 Tests for the JARVIS Brain API-key credential + admin identity hardening.

Hermetic: in-memory SQLite (JARVIS_TEST_MODE), no network -- the remote Brain
is a fake ``httpx.AsyncClient`` that records the outbound Authorization header
and returns canned OpenAI-compatible responses.

Covers (per spec §8 / §2 / §5 / §6 / §7):
* Admin identity is env-driven and never hardcoded in source.
* The Brain API key is loaded only through the project secret vault
  (SecretsManager) and is never hardcoded.
* The Brain request carries ``Authorization: Bearer <key>`` (and omits the
  header when the key is absent -- honest, no fabricated availability).
* Brain health is only healthy after a real (mocked) inference; auth failure /
  network error / empty response are all unhealthy (no fabrication).
* The raw key never appears in /api/v1/ai/status, in logs, or in the probe dict.
* The frontend-facing status exposes only a masked boolean indicator.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

# Signing/encryption key MUST exist before importing jarvis_backend (JWT + vault).
import os
os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_SECRET_KEY", "brain-test-secret-key-0123456789abcdef")

from jarvis_backend import core  # noqa: E402
from jarvis_backend.core import admin_email  # noqa: E402
from jarvis_backend.gateway import (  # noqa: E402
    ProviderGateway,
    _jarvis_brain_api_key,
    _jarvis_brain_api_key_configured,
)
from infrastructure.vault.manager import get_secrets_manager  # noqa: E402


# --------------------------------------------------------------------------- #
# Fake remote Brain (records the outbound Authorization header, returns canned
# OpenAI-compatible responses). Patches httpx.AsyncClient globally; the gateway
# does a local ``import httpx`` so the patched class is what gets instantiated.
# --------------------------------------------------------------------------- #
class _FakeDelta:
    def __init__(self, secs: float) -> None:
        self._s = secs

    def total_seconds(self) -> float:
        return self._s


class _FakeResp:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""
        self.elapsed = _FakeDelta(0.05)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("http error", request=None, response=self)


class _FakeAsyncClient:
    posts: list = []
    valid_key: str | None = None  # if set, require this Bearer token; else 401
    force_status: int | None = None
    force_network_error: bool = False
    force_content: str = "ok"

    def __init__(self, *args, **kwargs) -> None:
        # httpx applies client-level headers to every request; the fake must
        # preserve them so the Authorization header reaches the chat POST.
        self._hdr = dict(kwargs.get("headers") or {})

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    @classmethod
    def _chat_response(cls, headers: dict) -> "_FakeResp":
        """One behavior for both the (legacy) async client and the sync
        ``httpx.post`` transport the gateway uses today."""
        cls.posts.append({"url": "<brain>", "headers": dict(headers), "json": None})
        if cls.force_network_error:
            raise httpx.HTTPError("simulated brain unreachable")
        auth = headers.get("Authorization")
        if (cls.valid_key is not None
                and auth != f"Bearer {cls.valid_key}"):
            status = (
                cls.force_status
                if cls.force_status is not None
                else 401
            )
        else:
            status = (
                cls.force_status
                if cls.force_status is not None
                else 200
            )
        if status == 200:
            payload = {
                "choices": [{"message": {"content": cls.force_content}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
            }
        else:
            payload = {}
        return _FakeResp(status, payload)

    async def get(self, url, headers=None):
        # /health lives under the root base (unauthenticated).  The gateway
        # only issues a chat POST after a healthy, non-stub Brain is confirmed
        # (spec §12 honesty gate), so the fake must answer it like the runtime.
        return _FakeResp(
            200,
            {
                "status": "healthy",
                "available": True,
                "stub": False,
                "model": "jarvis-brain-qwen3-4b-v1",
                "backend": "remote-openai-compatible",
                "device": "gpu-remote",
                "loaded": True,
                "warmup_ok": True,
                "revision": "rev-test",
                "parameters": 972_000_000,
            },
        )

    async def post(self, url, headers=None, json=None):
        return self._chat_response(dict(self._hdr, **(headers or {})))


# ``_openai_compatible_post`` (the shared transport used by the Brain remote
# tier) performs a *synchronous* ``httpx.post``, so the recording fake must also
# stand in for that sync call, not just ``httpx.AsyncClient``.
def _sync_brain_post(url, headers=None, json=None, timeout=None):
    resp = _FakeAsyncClient._chat_response(dict(headers or {}))
    resp.request_url = url
    resp.request_json = json
    return resp


@pytest.fixture(autouse=True)
def _reset_brain_fake():
    _FakeAsyncClient.posts = []
    _FakeAsyncClient.valid_key = None
    _FakeAsyncClient.force_status = None
    _FakeAsyncClient.force_network_error = False
    _FakeAsyncClient.force_content = "ok"
    yield
    _FakeAsyncClient.posts = []


@pytest.fixture
def fake_brain(monkeypatch):
    """Patch the real httpx with the recording fake Brain.

    The gateway's Brain remote tier calls the *shared* sync transport
    (``extensions._openai_compatible_post`` -> ``httpx.post``); the async
    client patch is kept for the legacy callers. Both record into
    ``_FakeAsyncClient.posts``.
    """
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("httpx.post", _sync_brain_post)
    return _FakeAsyncClient


BRAIN_SECRET = "secret-xyz"
# --------------------------------------------------------------------------- #
# §1 Admin identity: env-driven, never hardcoded.
# --------------------------------------------------------------------------- #
class TestAdminIdentity:
    def test_canonical_admin_email_not_hardcoded(self):
        # §1: do not hardcode the admin email anywhere in application source.
        base_path = Path(__file__).parent.parent  # tests/ -> project root
        for rel in (
            "jarvis_backend/core.py",
            "jarvis_backend/gateway.py",
            "jarvis_backend/routers/ai.py",
            "jarvis_backend/routers/auth.py",
        ):
            src = (base_path / rel).read_text(encoding="utf-8")
            assert "ndichiv@gmail.com" not in src, f"hardcoded in {rel}"

    def test_admin_email_env_driven(self, monkeypatch):
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "ndichiv@gmail.com")
        assert admin_email() == "ndichiv@gmail.com"

    def test_admin_email_not_used_as_api_credential(self):
        # §3: the admin email is the identity, not the Brain API credential.
        assert "@" in admin_email()
        assert _jarvis_brain_api_key() != admin_email()
        assert _jarvis_brain_api_key() != "ndichiv@gmail.com"

    def test_unrelated_email_is_distinct_from_admin_identity(self, monkeypatch):
        # §8: an unrelated email is not the canonical admin identity.
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "other@example.com")
        assert admin_email() != "ndichiv@gmail.com"


# --------------------------------------------------------------------------- #
# §7 Brain API key: loaded only via the vault, never hardcoded.
# --------------------------------------------------------------------------- #
class TestBrainApiKeyLoading:
    def test_brain_key_loaded_via_vault(self, monkeypatch):
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        sm = get_secrets_manager()
        # The vault EnvBackend reads JARVIS_BRAIN_API_KEY (env / .env).
        assert sm.get_or_none("brain_api_key") == BRAIN_SECRET
        assert _jarvis_brain_api_key() == BRAIN_SECRET
        assert _jarvis_brain_api_key_configured() is True

    def test_brain_key_not_loaded_when_absent(self, monkeypatch):
        monkeypatch.delenv("JARVIS_BRAIN_API_KEY", raising=False)
        assert _jarvis_brain_api_key() == ""
        assert _jarvis_brain_api_key_configured() is False

    def test_brain_key_not_hardcoded_in_source(self):
        # §2: no secret literal in source.
        base_path = Path(__file__).parent.parent  # tests/ -> project root
        for rel in ("jarvis_backend/gateway.py", "jarvis_backend/routers/ai.py"):
            src = (base_path / rel).read_text(encoding="utf-8")
            assert BRAIN_SECRET not in src, rel

    def test_vault_masks_brain_key(self, monkeypatch):
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        sm = get_secrets_manager()
        masked = sm.mask(BRAIN_SECRET)
        assert BRAIN_SECRET not in masked
        assert sm.get_masked("brain_api_key") != BRAIN_SECRET
        assert BRAIN_SECRET not in sm.get_masked("brain_api_key")


# --------------------------------------------------------------------------- #
# §5 Brain request flow: Bearer auth, honest failure, no fabrication.
# --------------------------------------------------------------------------- #
class TestBrainRequestFlow:
    async def test_brain_request_carries_bearer(self, fake_brain, monkeypatch):
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        probe = await ProviderGateway().probe_brain(timeout=5.0)
        assert probe["healthy"] is True
        sent = fake_brain.posts[-1]
        assert sent["headers"]["Authorization"] == f"Bearer {BRAIN_SECRET}"

    async def test_brain_request_omits_header_when_key_absent(
        self, fake_brain, monkeypatch
    ):
        # §2/§5: missing key -> the gateway refuses to send an unauthenticated
        # inference (no Authorization header, no HTTP call) and reports the
        # Brain as honestly unavailable -- never a fake success.
        monkeypatch.delenv("JARVIS_BRAIN_API_KEY", raising=False)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET  # the Brain requires a key
        probe = await ProviderGateway().probe_brain(timeout=5.0)
        assert probe["healthy"] is False
        assert probe.get("category") == "PROVIDER_UNAVAILABLE"
        assert fake_brain.posts == []  # no unauthenticated request was sent

    async def test_brain_invalid_key_fails_auth(self, fake_brain, monkeypatch):
        # §5: an incorrect key is forwarded as Bearer <wrong> and rejected.
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", "wrong-key")
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        probe = await ProviderGateway().probe_brain(timeout=5.0)
        assert probe["healthy"] is False
        assert probe.get("category") == "PROVIDER_UNAVAILABLE"
        sent = fake_brain.posts[-1]
        assert sent["headers"]["Authorization"] == "Bearer wrong-key"


# --------------------------------------------------------------------------- #
# §8 Brain health matrix: healthy only after a real (mocked) inference.
# --------------------------------------------------------------------------- #
class TestBrainHealth:
    async def test_brain_unconfigured_when_endpoint_unset(self, fake_brain, monkeypatch):
        monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)
        monkeypatch.delenv("JARVIS_BRAIN_API_KEY", raising=False)
        probe = await ProviderGateway().probe_brain(timeout=5.0)
        assert probe["configured"] is False
        assert probe["healthy"] is False
        assert probe["detail"] == "JARVIS_BRAIN_ENDPOINT not set"
        assert fake_brain.posts == []  # no HTTP call attempted

    async def test_brain_healthy_after_real_probe(self, fake_brain, monkeypatch):
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        probe = await ProviderGateway().probe_brain(timeout=5.0)
        assert probe["configured"] is True
        assert probe["healthy"] is True
        assert probe["endpoint"] == "http://brain.example.com"

    async def test_brain_unhealthy_on_network_error(self, fake_brain, monkeypatch):
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        fake_brain.force_network_error = True
        probe = await ProviderGateway().probe_brain(timeout=5.0)
        assert probe["healthy"] is False
        # A confirmed-unreachable brain is honestly reported as PROVIDER_UNAVAILABLE
        # (transport failures map to the no-service state, never to healthy).
        assert probe.get("category") == "PROVIDER_UNAVAILABLE"
        assert BRAIN_SECRET not in str(probe)

    async def test_brain_empty_response_not_healthy(self, fake_brain, monkeypatch):
        # §5 honesty guard: an empty inference is never surfaced as healthy.
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        fake_brain.force_content = ""
        probe = await ProviderGateway().probe_brain(timeout=5.0)
        assert probe["healthy"] is False


# --------------------------------------------------------------------------- #
# §2 / §6 No-secret-in-responses, logs, telemetry; masked frontend indicator.
# --------------------------------------------------------------------------- #
class TestBrainSecretNonDisclosure:
    def test_status_exposes_only_masked_indicator(self, client, fake_brain, monkeypatch):
        # §6: Admin Console sees a boolean indicator, never the raw key.
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        r = client.get("/api/v1/ai/status")
        assert r.status_code == 200
        body = r.json()
        assert body["brain_api_key_configured"] is True
        # No field ever carries the raw value.
        assert BRAIN_SECRET not in r.text
        assert body["brain"]["healthy"] is True

    def test_frontend_status_does_not_leak_key(self, client, fake_brain, monkeypatch):
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        body = client.get("/api/v1/ai/status").json()
        blob = json.dumps(body)
        assert BRAIN_SECRET not in blob
        assert isinstance(body["brain_api_key_configured"], bool)
        assert body["brain"]["healthy"] is True

    def test_brain_key_not_in_logs(self, client, fake_brain, monkeypatch, caplog):
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        caplog.set_level(logging.INFO)
        client.get("/api/v1/ai/status")
        assert BRAIN_SECRET not in caplog.text

    async def test_probe_dict_never_contains_key(self, fake_brain, monkeypatch):
        monkeypatch.setenv("JARVIS_BRAIN_API_KEY", BRAIN_SECRET)
        monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://brain.example.com")
        fake_brain.valid_key = BRAIN_SECRET
        probe = await ProviderGateway().probe_brain(timeout=5.0)
        assert BRAIN_SECRET not in str(probe)
        assert "brain_api_key" not in probe