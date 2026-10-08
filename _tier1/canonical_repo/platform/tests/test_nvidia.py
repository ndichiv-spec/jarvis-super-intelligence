"""Hermetic tests for the NVIDIA NIM adapter (spec sections 1-8, 36-37).

These assert the REAL routing shape -- NVIDIA NIM's OpenAI-compatible
``/v1/chat/completions`` and ``/v1/models`` -- with the network swapped for
deterministic fakes. The live credential test lives separately in
``tests/test_nvidia_live.py`` (skipped unless ``NVIDIA_API_KEY`` is present) so
the primary path is *never* a stub success (spec section 37): a missing/invalid
key is reported as ``PROVIDER_UNAVAILABLE`` / ``INVALID_KEY``, not as a reply.

Reuse contract (spec section 6): ``_invoke_nvidia`` and the JARVIS Brain remote
tier both call the shared ``extensions._openai_compatible_post`` transport -- no
second HTTP client is introduced.
"""
from __future__ import annotations

import asyncio

import pytest

NVIDIA_KEY = "nv-test-not-a-real-key"
NVIDIA_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"


# --------------------------------------------------------------------------- #
# HTTP fakes
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)


class _FakeHttp:
    """Drop-in for the ``httpx`` module reference used by validators/discovery."""

    last = None

    def __init__(self, resp):
        self._resp = resp

    def get(self, url, headers=None, params=None, timeout=None):
        _FakeHttp.last = (url, headers, params)
        return self._resp


def _scrub_nvidia_env(monkeypatch):
    for k in ("NVIDIA_API_KEY", "JARVIS_API_KEY_NVIDIA", "JARVIS_NVIDIA_API_KEY",
              "JARVIS_NVIDIA_ENDPOINT", "JARVIS_NVIDIA_MODEL",
              "JARVIS_BRAIN_ENDPOINT", "JARVIS_BRAIN_MODEL",
              "JARVIS_BRAIN_API_KEY", "JARVIS_BRAIN_REMOTE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


# --------------------------------------------------------------------------- #
# Fabric registration (spec section 6)
# --------------------------------------------------------------------------- #
def test_nvidia_registered_in_fabric():
    from jarvis_backend.routers import extensions as ext

    assert "nvidia" in ext._API_KEY_PROVIDERS
    assert ext._API_KEY_PROVIDERS["nvidia"]["validator"] == "_validate_nvidia_key"
    assert ext._API_KEY_PROVIDERS["nvidia"]["console_url"].startswith(
        "https://catalog.ngc.nvidia.com"
    )
    assert "nvidia" in ext._PROVIDER_INVOKE_HANDLERS
    assert "_validate_nvidia_key" in ext._VALIDATORS
    assert "nvidia.chat" in ext._extension_capabilities("nvidia")
    assert "nvidia.generate" in ext._extension_capabilities("nvidia")


# --------------------------------------------------------------------------- #
# NVIDIAHealth (spec section 6) -- _validate_nvidia_key
# --------------------------------------------------------------------------- #
def test_validate_nvidia_key(monkeypatch):
    from jarvis_backend.routers import extensions as ext

    # 200 -> verified
    monkeypatch.setattr(ext, "httpx", _FakeHttp(_FakeResp(200, {"data": []})))
    v, err = ext._validate_nvidia_key(NVIDIA_KEY)
    assert v is True and err is None
    assert _FakeHttp.last[0] == NVIDIA_MODELS_URL
    assert _FakeHttp.last[1]["Authorization"] == f"Bearer {NVIDIA_KEY}"

    # 401 -> invalid
    monkeypatch.setattr(ext, "httpx", _FakeHttp(_FakeResp(401)))
    v, err = ext._validate_nvidia_key(NVIDIA_KEY)
    assert v is False
    assert "NVIDIA" in err

    # network error -> inconclusive (accepted as stored, not rejected)
    class _Boom:
        def get(self, *a, **k):
            import httpx

            raise httpx.ConnectError("no network")
    monkeypatch.setattr(ext, "httpx", _Boom())
    v, err = ext._validate_nvidia_key(NVIDIA_KEY)
    assert v is None and err is None


# --------------------------------------------------------------------------- #
# NVIDIAModelDiscovery (spec section 5) -- _discover_nvidia_models
# --------------------------------------------------------------------------- #
def test_discover_nvidia_models(monkeypatch):
    from jarvis_backend.routers import extensions as ext

    payload = {"data": [
        {"id": "nvidia/llama-3.1-70b-instruct", "owned_by": "nvidia", "object": "model"},
        {"id": "nvidia/llama-3.1-8b-instruct", "owned_by": "nvidia", "object": "model"},
    ]}
    monkeypatch.setattr(ext, "httpx", _FakeHttp(_FakeResp(200, payload)))
    disc = ext._discover_nvidia_models(NVIDIA_KEY)
    assert disc["configured"] is True
    assert disc["models"][0]["model_id"] == "nvidia/llama-3.1-70b-instruct"
    assert disc["models"][0]["provider"] == "nvidia"
    assert disc["selected"]  # first model selected when no override

    # JARVIS_NVIDIA_MODEL honoured only when it matches a discovered model.
    monkeypatch.setenv("JARVIS_NVIDIA_MODEL", "nvidia/llama-3.1-8b-instruct")
    disc = ext._discover_nvidia_models(NVIDIA_KEY)
    assert disc["selected"] == "nvidia/llama-3.1-8b-instruct"
    assert disc["override_applied"] is True
    monkeypatch.delenv("JARVIS_NVIDIA_MODEL", raising=False)

    # Invalid key -> discovered disabled, honest error.
    monkeypatch.setattr(ext, "httpx", _FakeHttp(_FakeResp(401)))
    disc = ext._discover_nvidia_models(NVIDIA_KEY)
    assert disc["configured"] is False
    assert "invalid" in disc["error"]


def test_discover_nvidia_models_never_returns_undiscovered_model(monkeypatch):
    from jarvis_backend.routers import extensions as ext

    # Override names a model that does NOT exist in /v1/models -> not selected.
    monkeypatch.setenv("JARVIS_NVIDIA_MODEL", "nvidia/does-not-exist-v9")
    monkeypatch.setattr(ext, "httpx", _FakeHttp(_FakeResp(200, {"data": [
        {"id": "nvidia/llama-3.1-70b-instruct", "owned_by": "nvidia"}]})))
    disc = ext._discover_nvidia_models(NVIDIA_KEY)
    assert disc["selected"] == "nvidia/llama-3.1-70b-instruct"  # falls back, not the override
    assert disc["override_applied"] is False
    monkeypatch.delenv("JARVIS_NVIDIA_MODEL", raising=False)


# --------------------------------------------------------------------------- #
# NVIDIAClient (spec section 6) -- _invoke_nvidia reuses _openai_compatible_post
# --------------------------------------------------------------------------- #
def test_invoke_nvidia_chat_reuses_openai_compatible_shape(monkeypatch):
    from jarvis_backend.routers import extensions as ext

    captured = {}

    def fake_post(url, payload, key, *, provider="openai", timeout=30):
        captured["url"] = url
        captured["payload"] = payload
        captured["key"] = key
        captured["provider"] = provider
        return {
            "choices": [{"message": {"content": "nVIDIA reply"}}],
            "model": "nvidia/llama-3.1-70b-instruct",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }

    monkeypatch.setattr(ext, "_openai_compatible_post", fake_post)
    result = ext._invoke_nvidia(
        "nvidia", "nvidia.chat",
        {"model": "nvidia/llama-3.1-70b-instruct",
         "messages": [{"role": "user", "content": "hello"}]},
        NVIDIA_KEY,
    )
    assert result["provider"] == "nvidia"
    assert result["content"] == "nVIDIA reply"
    assert result["model"] == "nvidia/llama-3.1-70b-instruct"
    assert result["usage"] == {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
    # Proves the adapter reuses the shared transport to the NVIDIA endpoint:
    assert captured["url"] == NVIDIA_CHAT_URL
    assert captured["key"] == NVIDIA_KEY
    assert captured["provider"] == "nvidia"
    assert captured["payload"]["model"] == "nvidia/llama-3.1-70b-instruct"


def test_invoke_nvidia_honors_jarvis_nvidia_model_env(monkeypatch):
    from jarvis_backend.routers import extensions as ext

    monkeypatch.setenv("JARVIS_NVIDIA_MODEL", "nvidia/llama-3.1-8b-instruct")
    captured = {}

    def fake_post(url, payload, key, *, provider="openai", timeout=30):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}],
                "model": payload["model"], "usage": {}}

    monkeypatch.setattr(ext, "_openai_compatible_post", fake_post)
    result = ext._invoke_nvidia(
        "nvidia", "nvidia.chat",
        {"messages": [{"role": "user", "content": "hi"}]},
        NVIDIA_KEY,
    )
    assert captured["payload"]["model"] == "nvidia/llama-3.1-8b-instruct"
    assert result["provider"] == "nvidia"
    monkeypatch.delenv("JARVIS_NVIDIA_MODEL", raising=False)


def test_invoke_nvidia_requires_messages():
    from fastapi import HTTPException
    from jarvis_backend.routers import extensions as ext

    with pytest.raises(HTTPException) as ei:
        ext._invoke_nvidia("nvidia", "nvidia.chat", {}, NVIDIA_KEY)
    assert ei.value.status_code == 400
    # Unsupported capability is rejected (never a canned success).
    with pytest.raises(HTTPException) as ei:
        ext._invoke_nvidia("nvidia", "nvidia.bogus", {"messages": []}, NVIDIA_KEY)
    assert ei.value.status_code == 400


# --------------------------------------------------------------------------- #
# JARVIS Brain remote tier -> NVIDIA (spec sections 1 / 7 / 8 / 23 / 33 / 37)
# --------------------------------------------------------------------------- #
def test_brain_remote_path_uses_nvidia_key_when_endpoint_is_nvidia(monkeypatch):
    from jarvis_backend.gateway import ProviderGateway
    from jarvis_backend.routers import extensions as ext

    _scrub_nvidia_env(monkeypatch)
    monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-brain-key")

    captured = {}

    def fake_post(url, payload, key, *, provider="openai", timeout=30):
        captured.update(url=url, key=key, provider=provider, payload=payload)
        return {"choices": [{"message": {"content": "ok"}}],
                "model": "nvidia/llama-3.1-70b-instruct",
                "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1}}

    monkeypatch.setattr(ext, "_openai_compatible_post", fake_post)
    gw = ProviderGateway()
    result = asyncio.run(gw._chat_via_remote_brain(
        "https://integrate.api.nvidia.com/v1",
        [{"role": "user", "content": "Reply with the single word: ok"}],
        None, None, 30.0,
    ))
    # §15: Brain health reports backend=remote, provider=nvidia.
    assert result["provider"] == "nvidia"
    assert result["backend"] == "remote-openai-compatible"
    assert result["content"] == "ok"
    # §33: the upstream credential is NVIDIA_API_KEY, not brain_api_key.
    assert captured["key"] == "nv-brain-key"
    assert captured["provider"] == "nvidia"
    assert captured["url"].endswith("/chat/completions")


def test_brain_remote_path_missing_key_is_provider_unavailable(monkeypatch):
    """§21/§37: no NVIDIA_API_KEY -> honest PROVIDER_UNAVAILABLE, never a stub."""
    from fastapi import HTTPException
    from jarvis_backend.gateway import ProviderGateway, ChatError, ErrorCategory

    _scrub_nvidia_env(monkeypatch)
    monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "https://integrate.api.nvidia.com/v1")
    # No NVIDIA_API_KEY, no JARVIS_BRAIN_API_KEY -> empty upstream key.

    # If a key were present we'd hit the provider; guard against a surprise
    # network call by also stubbing the transport (must never be reached).
    from jarvis_backend.routers import extensions as ext

    def _boom(*a, **k):
        raise AssertionError("transport must not be called without a key")
    monkeypatch.setattr(ext, "_openai_compatible_post", _boom)

    gw = ProviderGateway()
    with pytest.raises(ChatError) as ei:
        asyncio.run(gw._chat_via_remote_brain(
            "https://integrate.api.nvidia.com/v1",
            [{"role": "user", "content": "hi"}],
            None, None, 30.0,
        ))
    assert ei.value.category == ErrorCategory.PROVIDER_UNAVAILABLE
    assert "no upstream API key" in str(ei.value)


def test_brain_remote_path_401_maps_to_provider_unavailable(monkeypatch):
    """A real 401 (invalid NVIDIA key) -> PROVIDER_UNAVAILABLE so chat() can
    honestly fall back to Silverwing; never a synthetic 'ok' reply."""
    from fastapi import HTTPException
    from jarvis_backend.gateway import ProviderGateway, ChatError, ErrorCategory
    from jarvis_backend.routers import extensions as ext

    _scrub_nvidia_env(monkeypatch)
    monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setenv("NVIDIA_API_KEY", "bad-key")

    def fake_post(url, payload, key, *, provider="openai", timeout=30):
        raise HTTPException(status_code=401, detail="invalid NVIDIA API key")
    monkeypatch.setattr(ext, "_openai_compatible_post", fake_post)

    gw = ProviderGateway()
    with pytest.raises(ChatError) as ei:
        asyncio.run(gw._chat_via_remote_brain(
            "https://integrate.api.nvidia.com/v1",
            [{"role": "user", "content": "hi"}],
            None, None, 30.0,
        ))
    assert ei.value.category == ErrorCategory.PROVIDER_UNAVAILABLE


def test_brain_remote_path_non_nvidia_uses_brain_key(monkeypatch):
    """§33: a custom (non-NVIDIA) Brain endpoint must use JARVIS_BRAIN_API_KEY,
    never NVIDIA_API_KEY."""
    from jarvis_backend.gateway import ProviderGateway, _brain_upstream_key, _brain_provider

    _scrub_nvidia_env(monkeypatch)
    monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "https://my-brain.example.com/v1")
    monkeypatch.setenv("NVIDIA_API_KEY", "must-not-be-used")
    monkeypatch.setenv("JARVIS_BRAIN_API_KEY", "brain-boundary-key")
    assert _brain_provider("https://my-brain.example.com/v1") == "jarvis-brain"
    assert _brain_upstream_key("https://my-brain.example.com/v1") == "brain-boundary-key"
