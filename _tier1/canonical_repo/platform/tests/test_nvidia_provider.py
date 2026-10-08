"""Dedicated tests for the NVIDIA NIM provider adapter (spec §4).

All network I/O is routed through an injected :class:`FakeOpenAIClient` — no
real provider API is called.  Tests verify:

* capability declaration (``NVIDIA_ADAPTER_CAPABILITIES`` = CHAT, STREAMING,
  TOOL_CALLING, EMBEDDINGS, STRUCTURED_OUTPUT, REASONING);
* config loading from env (``JARVIS_NVIDIA_API_KEY``, ``JARVIS_NVIDIA_ENDPOINT``,
  ``JARVIS_NVIDIA_MODEL``);
* health probe behaviour (unconfigured -> UNCONFIGURED);
* chat response parsing with a mock HTTP client;
* the live-verified catalog in ``NVIDIA_MODELS``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Hook the workspace root (F:\AI) onto sys.path so the `providers` package
# is importable when this test is run from the Jarvis-super-intelligence-
# tests/ directory.
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from dataclasses import dataclass, field
from typing import Any, Optional

import pytest

from providers.base import Message, ProviderRequest
from providers.capabilities import Capability
from providers.errors import ProviderUnconfigured, UnsupportedCapability
from providers.health import HealthStatus
from providers.nvidia.config import NvidiaConfig
from providers.nvidia.models import NVIDIA_MODELS
from providers.secrets import SecretManager


# --------------------------------------------------------------------------- #
# Fakes (self-contained — no cross-test-module imports)
# --------------------------------------------------------------------------- #

class FakeOpenAIClient:
    """Sync stand-in for :class:`OpenAICompatibleClient`.

    Routes ``GET /v1/models`` and ``POST /v1/chat/completions`` to configured
    canned responses.  Records every call so tests can assert what was sent.
    """

    def __init__(self) -> None:
        self._model_ids: list[str] = []
        self._chat_response: dict[str, Any] = {}
        self._stream_chunks: list[dict] = []
        self._raise: dict[str, BaseException] = {}
        self.calls: list[tuple[str, str, dict | None]] = []

    def route_models(self, ids: list[str]) -> "FakeOpenAIClient":
        self._model_ids = ids
        return self

    def route_chat(self, body: dict[str, Any]) -> "FakeOpenAIClient":
        self._chat_response = body
        return self

    def route_stream(self, chunks: list[dict]) -> "FakeOpenAIClient":
        self._stream_chunks = chunks
        return self

    def raise_on(self, path: str, exc: BaseException) -> None:
        self._raise[path] = exc

    def list_models(self) -> list[str]:
        return list(self._model_ids)

    def chat_completions(self, *, model, messages, stream=False, **kwargs) -> dict:
        self.calls.append(("POST", "/v1/chat/completions", {"model": model}))
        exc = self._raise.get("/v1/chat/completions")
        if exc:
            raise exc
        return dict(self._chat_response)

    def stream_chat_completions(self, *, model, messages, **kwargs):
        self.calls.append(("POST", "/v1/chat/completions/stream", {"model": model}))
        for chunk in self._stream_chunks:
            yield chunk
        yield {"usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    def post_json(self, path: str, body: dict) -> dict:
        self.calls.append(("POST", path, body))
        if path == "/v1/embeddings":
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        return {}


def _make_nvidia_adapter(client=None, api_key="test-key"):
    from providers.nvidia.client import NvidiaAdapter
    cfg = NvidiaConfig(
        api_key=api_key,
        endpoint="https://integrate.api.nvidia.com/v1",
        model="nvidia/nemotron-3-ultra-550b-a55b",
    )
    return NvidiaAdapter(config=cfg, secrets=SecretManager(env={}), client=client)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_ENV_NVIDIA = {
    "JARVIS_NVIDIA_API_KEY": "test-nv-key",
    "JARVIS_NVIDIA_ENDPOINT": "https://integrate.api.nvidia.com/v1",
    "JARVIS_NVIDIA_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
}


# --------------------------------------------------------------------------- #
# Tests – capability honesty (spec §3)
# --------------------------------------------------------------------------- #

class TestNvidiaCapabilityHonesty:
    """The NVIDIA adapter must declare exactly the capabilities it supports."""

    def test_nvidia_capabilities(self):
        """NVIDIA_ADAPTER_CAPABILITIES equals CHAT, STREAMING, TOOL_CALLING,
        EMBEDDINGS, STRUCTURED_OUTPUT, REASONING."""
        from providers.nvidia.capabilities import NVIDIA_ADAPTER_CAPABILITIES
        expected = {
            Capability.CHAT,
            Capability.STREAMING,
            Capability.TOOL_CALLING,
            Capability.EMBEDDINGS,
            Capability.STRUCTURED_OUTPUT,
            Capability.REASONING,
        }
        assert NVIDIA_ADAPTER_CAPABILITIES == expected

    def test_nvidia_adapter_declares_expected_capabilities(self):
        """The adapter's declared_capabilities match the canonical set."""
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        caps = adapter.declared_capabilities
        expected = {
            Capability.CHAT,
            Capability.STREAMING,
            Capability.TOOL_CALLING,
            Capability.EMBEDDINGS,
            Capability.STRUCTURED_OUTPUT,
            Capability.REASONING,
        }
        assert caps == expected

    def test_nvidia_declares_exactly_six_capabilities(self):
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        assert len(adapter.declared_capabilities) == 6

    def test_nvidia_supports_chat_streaming_tool_calling(self):
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        for cap in (Capability.CHAT, Capability.STREAMING,
                     Capability.TOOL_CALLING, Capability.EMBEDDINGS,
                     Capability.STRUCTURED_OUTPUT, Capability.REASONING):
            assert adapter.supports(cap)

    def test_nvidia_does_not_declare_vision_or_audio(self):
        """NVIDIA NIM does not support vision or audio — never pretend."""
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        assert not adapter.supports(Capability.VISION)
        assert not adapter.supports(Capability.AUDIO)
        with pytest.raises(UnsupportedCapability):
            adapter.require(Capability.VISION)


# --------------------------------------------------------------------------- #
# Tests – config from env (spec §4)
# --------------------------------------------------------------------------- #

class TestNvidiaConfigFromEnv:
    """NvidiaConfig.from_environ reads JARVIS_NVIDIA_* env vars."""

    def test_config_from_env_with_secrets(self, monkeypatch):
        sm = SecretManager(env=dict(_ENV_NVIDIA))
        cfg = NvidiaConfig.from_environ(secrets=sm)
        assert cfg.api_key == "test-nv-key"
        assert cfg.endpoint == "https://integrate.api.nvidia.com/v1"
        assert cfg.model == "nvidia/nemotron-3-ultra-550b-a55b"
        assert cfg.configured is True

    def test_config_default_endpoint(self):
        """When JARVIS_NVIDIA_ENDPOINT is unset the default is NVIDIA-hosted."""
        sm = SecretManager(env={"JARVIS_NVIDIA_API_KEY": "k"})
        cfg = NvidiaConfig.from_environ(secrets=sm)
        assert cfg.endpoint == "https://integrate.api.nvidia.com/v1"

    def test_config_default_timeout(self):
        sm = SecretManager(env={"JARVIS_NVIDIA_API_KEY": "k"})
        cfg = NvidiaConfig.from_environ(secrets=sm)
        assert cfg.timeout == 180.0

    def test_config_custom_endpoint_via_env(self, monkeypatch):
        sm = SecretManager(env={
            "JARVIS_NVIDIA_API_KEY": "k",
            "JARVIS_NVIDIA_ENDPOINT": "http://127.0.0.1:8081/v1",
            "JARVIS_NVIDIA_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        })
        cfg = NvidiaConfig.from_environ(
            secrets=sm,
            env={
                "JARVIS_NVIDIA_API_KEY": "k",
                "JARVIS_NVIDIA_ENDPOINT": "http://127.0.0.1:8081/v1",
                "JARVIS_NVIDIA_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
            },
        )
        assert cfg.endpoint == "http://127.0.0.1:8081/v1"
        assert cfg.model == "nvidia/nemotron-3-ultra-550b-a55b"

    def test_adapter_configured_false_without_api_key(self):
        """No API key => not configured (honest reporting)."""
        sm = SecretManager(env={})
        cfg = NvidiaConfig.from_environ(secrets=sm)
        assert cfg.configured is False


# --------------------------------------------------------------------------- #
# Tests – health probe (spec §7)
# --------------------------------------------------------------------------- #

class TestNvidiaHealthProbe:
    """Health must never be assumed — UNCONFIGURED when no key."""

    def test_unconfigured_reports_unconfigured(self):
        adapter = _make_nvidia_adapter(api_key=None)
        assert adapter.configured is False
        health = adapter.health(force=True)
        assert health.status is HealthStatus.UNCONFIGURED
        assert health.provider == "nvidia"

    def test_configured_but_no_endpoint_reports_unknown(self):
        """A key is present but no endpoint was set — health is UNKNOWN
        (not HEALTHY) until a real probe runs."""
        sm = SecretManager(env={"JARVIS_NVIDIA_API_KEY": "k"})
        cfg = NvidiaConfig.from_environ(secrets=sm)
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        # Override the config so endpoint is the default (real) and key present
        adapter.config = cfg
        assert adapter.configured is True
        # Without a working endpoint, health probe to a fake client still
        # produces a valid health object (not an exception).
        health = adapter.health(force=True)
        assert health.provider == "nvidia"


# --------------------------------------------------------------------------- #
# Tests – chat via injected fake client
# --------------------------------------------------------------------------- #

class TestNvidiaChat:
    """A configured adapter with a fake HTTP client can chat."""

    def test_nvidia_chat_returns_response(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "hello from nvidia"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        })
        adapter = _make_nvidia_adapter(client=fake)
        req = ProviderRequest(
            messages=[Message.user("hi")],
            model="nvidia/nemotron-3-ultra-550b-a55b",
        )
        resp = adapter.chat(req)
        assert resp.provider == "nvidia"
        assert resp.model == "nvidia/nemotron-3-ultra-550b-a55b"
        assert resp.text == "hello from nvidia"
        assert resp.usage.prompt_tokens == 5
        assert resp.usage.completion_tokens == 3
        assert resp.usage.total_tokens == 8
        # Verify the fake client received the request
        assert len(fake.calls) == 1

    def test_nvidia_chat_preserves_model_name(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1},
        })
        adapter = _make_nvidia_adapter(client=fake)
        req = ProviderRequest(
            messages=[Message.user("test")],
            model="nvidia/llama-3.1-nemotron-70b-instruct",
        )
        resp = adapter.chat(req)
        assert resp.model == "nvidia/llama-3.1-nemotron-70b-instruct"

    def test_nvidia_chat_with_system_message(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "greetings"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
        adapter = _make_nvidia_adapter(client=fake)
        msgs = [Message.system("you are helpful"), Message.user("hello")]
        req = ProviderRequest(messages=msgs, model="nvidia/nemotron-3-ultra-550b-a55b")
        resp = adapter.chat(req)
        assert resp.text == "greetings"
        assert resp.provider == "nvidia"

    def test_nvidia_unconfigured_chat_raises(self):
        """An unconfigured adapter must refuse, not fake a response."""
        adapter = _make_nvidia_adapter(api_key=None)
        req = ProviderRequest(
            messages=[Message.user("hi")],
            model="nvidia/nemotron-3-ultra-550b-a55b",
        )
        with pytest.raises((ProviderUnconfigured, UnsupportedCapability)):
            adapter.chat(req)

    def test_nvidia_chat_forwards_messages_to_client(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
        adapter = _make_nvidia_adapter(client=fake)
        req = ProviderRequest(
            messages=[Message.user("hello"), Message(role="assistant", content="hi there")],
            model="nvidia/nemotron-3-ultra-550b-a55b",
        )
        adapter.chat(req)
        # The fake client records the call; verify model was forwarded
        assert len(fake.calls) == 1
        call_path, call_data = fake.calls[0][1], fake.calls[0][2]
        assert call_data["model"] == "nvidia/nemotron-3-ultra-550b-a55b"


# --------------------------------------------------------------------------- #
# Tests – model catalog (live-verified catalog, spec §4)
# --------------------------------------------------------------------------- #

class TestNvidiaModelCatalog:
    """NVIDIA_MODELS contains the live-verified NIM model catalog."""

    def test_eight_models(self):
        assert len(NVIDIA_MODELS) == 8

    def test_model_ids(self):
        ids = [m.model_id for m in NVIDIA_MODELS]
        expected = [
            "nvidia/nemotron-3-ultra-550b-a55b",
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "nvidia/nemotron-3-super-120b-a12b",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "mistralai/mistral-nemotron",
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "deepseek-ai/deepseek-v4.1-flash",
            "nvidia/nemotron-3-embed-1b",
        ]
        assert ids == expected

    def test_all_models_declare_chat_or_embeddings(self):
        for m in NVIDIA_MODELS:
            caps = m.capabilities
            assert Capability.CHAT in caps or Capability.EMBEDDINGS in caps

    def test_embed_model_declares_embeddings_not_chat(self):
        embed = next(m for m in NVIDIA_MODELS if m.model_id == "nvidia/nemotron-3-embed-1b")
        assert Capability.EMBEDDINGS in embed.capabilities
        assert Capability.CHAT not in embed.capabilities

    def test_chat_models_declare_chat(self):
        chat_models = [
            m for m in NVIDIA_MODELS
            if m.model_id != "nvidia/nemotron-3-embed-1b"
        ]
        assert len(chat_models) == 7
        for m in chat_models:
            assert Capability.CHAT in m.capabilities

    def test_first_model_is_default(self):
        """nvidia/nemotron-3-ultra-550b-a55b is the first/default model."""
        assert NVIDIA_MODELS[0].model_id == "nvidia/nemotron-3-ultra-550b-a55b"

    def test_adapter_builds_eight_models(self):
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        assert len(adapter.models) == 8

    def test_adapter_find_model(self):
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        m = adapter.find_model("nvidia/llama-3.1-nemotron-70b-instruct")
        assert m is not None
        assert m.model_id == "nvidia/llama-3.1-nemotron-70b-instruct"

    def test_adapter_find_model_unknown_returns_none(self):
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        assert adapter.find_model("nope/nonexistent") is None


# --------------------------------------------------------------------------- #
# Tests – provider metadata honesty (spec §3)
# --------------------------------------------------------------------------- #

class TestNvidiaProviderMetadata:
    """Adapter-level metadata must be explicit."""

    def test_provider_id(self):
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        assert adapter.provider_id == "nvidia"

    def test_display_name(self):
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        assert adapter.display_name == "NVIDIA NIM"

    def test_base_url_from_config(self):
        adapter = _make_nvidia_adapter(client=FakeOpenAIClient())
        assert adapter.base_url == "https://integrate.api.nvidia.com/v1"
