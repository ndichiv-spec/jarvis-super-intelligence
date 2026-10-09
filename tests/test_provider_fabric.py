"""Phase 1 provider fabric smoke tests (spec §3, §7, §34, §35, §36).

All network I/O is routed through injected fakes — no real provider API is called.
Tests verify:

* each adapter declares the right capabilities (capability honesty);
* unconfigured adapters report ``configured=False`` / health ``unconfigured``;
* configured adapters with injected fake HTTP clients can chat and stream;
* the registry + router produce correct, policy-driven routing decisions;
* cost is ``None`` when pricing is unknown (spec §34);
* ``JARVIS_PROVIDER_PRIORITY`` overrides scoring (no hard-coded winner);
* privacy routing is enforced (LOCAL_ONLY never leaves the machine);
* secret-isolation guard rejects credentials in the request context.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest

from providers.base import ProviderRequest, Message
from providers.capabilities import Capability
from providers.errors import (
    ProviderUnconfigured,
    SecretLeakError,
    UnsupportedCapability,
)
from providers.registry import ProviderRegistry, reset_registry
from providers.routing import ProviderRouter, TaskClassifier, TaskProfile
from providers.secrets import SecretManager, reset_secret_manager
from providers.bootstrap import build_adapters, bootstrap_fabric


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

@dataclass
class FakeHTTPResponse:
    status_code: int = 200
    _json: dict[str, Any] = field(default_factory=dict)
    _text: str = ""

    def json(self) -> dict[str, Any]:
        return self._json

    @property
    def text(self) -> str:
        return self._text or ""


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


# --------------------------------------------------------------------------- #
# Helpers to build adapters with controlled config (no env leakage)
# --------------------------------------------------------------------------- #

def _make_openai_adapter(client=None, api_key="test-key"):
    from providers.openai.client import OpenAIAdapter
    from providers.openai.config import OpenAIConfig
    cfg = OpenAIConfig(api_key=api_key, model="gpt-5")
    return OpenAIAdapter(config=cfg, secrets=SecretManager(env={}), client=client)


def _make_nvidia_adapter(client=None, api_key="test-key"):
    from providers.nvidia.client import NvidiaAdapter
    from providers.nvidia.config import NvidiaConfig
    cfg = NvidiaConfig(api_key=api_key, endpoint="https://integrate.api.nvidia.com/v1", model="meta/llama-3.3-70b-instruct")
    return NvidiaAdapter(config=cfg, secrets=SecretManager(env={}), client=client)


def _make_hf_adapter(client=None, token="hf_test_token", endpoint=None):
    from providers.huggingface.client import HuggingFaceAdapter
    from providers.huggingface.config import HuggingFaceConfig
    cfg = HuggingFaceConfig(token=token, inference_endpoint=endpoint, model="meta-llama/Llama-3.3-70B-Instruct")
    return HuggingFaceAdapter(config=cfg, secrets=SecretManager(env={}), client=client)


# --------------------------------------------------------------------------- #
# Tests — capability honesty
# --------------------------------------------------------------------------- #

class TestCapabilityHonesty:
    """Each adapter declares exactly the capabilities it implements (spec §3)."""

    def test_all_providers_registered_in_catalog(self):
        adapters = build_adapters(secrets=SecretManager(env={}))
        assert set(adapters) == {"openai", "nvidia", "google", "aws", "hf"}

    def test_openai_declares_expected_capabilities(self):
        adapters = build_adapters(secrets=SecretManager(env={}))
        caps = adapters["openai"].declared_capabilities
        expected = {
            Capability.CHAT, Capability.RESPONSES, Capability.STREAMING,
            Capability.TOOL_CALLING, Capability.VISION, Capability.AUDIO,
            Capability.EMBEDDINGS, Capability.STRUCTURED_OUTPUT,
            Capability.REASONING, Capability.BATCH, Capability.FINE_TUNING,
            Capability.EVALUATION, Capability.WEB_SEARCH, Capability.FILE_SEARCH,
            Capability.COMPUTER_USE,
        }
        assert caps == expected

    def test_nvidia_declares_expected_capabilities(self):
        adapters = build_adapters(secrets=SecretManager(env={}))
        caps = adapters["nvidia"].declared_capabilities
        expected = {
            Capability.CHAT, Capability.STREAMING, Capability.TOOL_CALLING,
            Capability.EMBEDDINGS, Capability.STRUCTURED_OUTPUT,
            Capability.REASONING,
        }
        assert caps == expected

    def test_google_declares_expected_capabilities(self):
        adapters = build_adapters(secrets=SecretManager(env={}))
        caps = adapters["google"].declared_capabilities
        expected = {
            Capability.CHAT, Capability.STREAMING, Capability.TOOL_CALLING,
            Capability.VISION, Capability.AUDIO, Capability.EMBEDDINGS,
            Capability.STRUCTURED_OUTPUT, Capability.REASONING,
        }
        assert caps == expected

    def test_aws_declares_expected_capabilities(self):
        adapters = build_adapters(secrets=SecretManager(env={}))
        caps = adapters["aws"].declared_capabilities
        expected = {
            Capability.CHAT, Capability.STREAMING, Capability.TOOL_CALLING,
            Capability.VISION, Capability.EMBEDDINGS, Capability.REASONING,
        }
        assert caps == expected

    def test_hf_declares_expected_capabilities(self):
        adapters = build_adapters(secrets=SecretManager(env={}))
        caps = adapters["hf"].declared_capabilities
        expected = {
            Capability.CHAT, Capability.STREAMING, Capability.TOOL_CALLING,
            Capability.EMBEDDINGS, Capability.STRUCTURED_OUTPUT,
        }
        assert caps == expected

    def test_unsupported_capability_rejected(self):
        """Reranking is not declared by any adapter — must raise."""
        adapters = build_adapters(secrets=SecretManager(env={}))
        for adapter in adapters.values():
            assert not adapter.supports(Capability.RERANKING)
            with pytest.raises(UnsupportedCapability):
                adapter.require(Capability.RERANKING)


# --------------------------------------------------------------------------- #
# Tests — health honesty (unconfigured when no credentials)
# --------------------------------------------------------------------------- #

class TestHealthHonesty:
    """Adapters report real health; never assume availability (spec §7, §73)."""

    def test_unconfigured_openai_reports_unconfigured(self):
        adapter = _make_openai_adapter(api_key=None)
        assert adapter.configured is False
        health = adapter.health(force=True)
        from providers.health import HealthStatus
        assert health.status is HealthStatus.UNCONFIGURED

    def test_unconfigured_nvidia_reports_unconfigured(self):
        adapter = _make_nvidia_adapter(api_key=None)
        assert adapter.configured is False
        health = adapter.health(force=True)
        from providers.health import HealthStatus
        assert health.status is HealthStatus.UNCONFIGURED

    def test_unconfigured_aws_reports_unconfigured(self):
        from providers.aws.config import AwsConfig
        from providers.aws.client import AwsBedrockAdapter
        cfg = AwsConfig(region=None)
        adapter = AwsBedrockAdapter(config=cfg, secrets=SecretManager(env={}))
        assert adapter.configured is False
        health = adapter.health(force=True)
        from providers.health import HealthStatus
        assert health.status is HealthStatus.UNCONFIGURED

    def test_model_list_health_does_not_claim_inference_verified(self):
        fake = FakeOpenAIClient()
        fake.route_models(["gpt-5"])
        adapter = _make_openai_adapter(client=fake)
        health = adapter.health(force=True)

        assert health.endpoint_reachable is True
        assert health.models_found == 1
        assert health.inference_verified is False
        assert health.to_dict()["inference_verified"] is False

        adapter.mark_inference_verified()
        verified = adapter.health(force=False)
        assert verified.inference_verified is True
        assert verified.credential_authorized is True

    def test_hf_token_without_endpoint_is_not_inference_ready(self):
        """Registry role only: token present, no endpoint => not ready for chat."""
        adapter = _make_hf_adapter(token="hf-token", endpoint=None)
        assert adapter.configured is True  # registry role available
        assert adapter.inference_ready is False
        health = adapter.health(force=True)
        from providers.health import HealthStatus
        assert health.status is HealthStatus.UNKNOWN
        assert "no inference endpoint" in health.detail


# --------------------------------------------------------------------------- #
# Tests — chat via injected fake client
# --------------------------------------------------------------------------- #

class TestChatWithFakeClient:
    """Configured adapters with fake HTTP clients can chat (no real network)."""

    def test_openai_chat_returns_response(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "hello from openai"},
                          "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        })
        adapter = _make_openai_adapter(client=fake)
        req = ProviderRequest(
            messages=[Message.user("hi")],
            model="gpt-5",
        )
        resp = adapter.chat(req)
        assert resp.provider == "openai"
        assert resp.model == "gpt-5"
        assert resp.text == "hello from openai"
        assert resp.usage.prompt_tokens == 3
        assert resp.usage.completion_tokens == 2

    def test_nvidia_chat_returns_response(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "hello from nvidia"},
                          "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
        adapter = _make_nvidia_adapter(client=fake)
        req = ProviderRequest(messages=[Message.user("hi")], model="meta/llama-3.3-70b-instruct")
        resp = adapter.chat(req)
        assert resp.provider == "nvidia"
        assert resp.text == "hello from nvidia"

    def test_hf_chat_with_endpoint_works(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "hello from hf"},
                          "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        })
        adapter = _make_hf_adapter(client=fake, token="hf-token", endpoint="https://my-hf-endpoint.com/v1")
        req = ProviderRequest(messages=[Message.user("hi")], model="meta-llama/Llama-3.3-70B-Instruct")
        resp = adapter.chat(req)
        assert resp.provider == "hf"
        assert resp.text == "hello from hf"

    def test_hf_chat_without_endpoint_raises(self):
        """Token present but no inference endpoint — chat must refuse, not fake."""
        adapter = _make_hf_adapter(token="hf-token", endpoint=None)
        req = ProviderRequest(messages=[Message.user("hi")], model="meta-llama/Llama-3.3-70B-Instruct")
        with pytest.raises(ProviderUnconfigured):
            adapter.chat(req)

    def test_openai_streaming_works(self):
        fake = FakeOpenAIClient()
        fake.route_stream([
            {"choices": [{"delta": {"content": "hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ])
        adapter = _make_openai_adapter(client=fake)
        req = ProviderRequest(messages=[Message.user("hi")], model="gpt-5", stream=True)
        chunks = list(adapter.stream(req))
        assert chunks[-1].done is True
        texts = [c.text for c in chunks if c.text]
        assert "".join(texts) == "hello"

    def test_openai_streaming_preserves_tool_call_deltas(self):
        fake = FakeOpenAIClient()
        fake.route_stream([
            {"choices": [{"delta": {"tool_calls": [{
                "index": 0,
                "id": "call-1",
                "function": {"name": "web_search", "arguments": "{\"query\":"},
            }]}}]},
            {"choices": [{"delta": {"tool_calls": [{
                "index": 0,
                "function": {"arguments": "\"jarvis\"}"},
            }]}}]},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        ])
        adapter = _make_openai_adapter(client=fake)
        chunks = list(adapter.stream(ProviderRequest(
            messages=[Message.user("search")], model="gpt-5", stream=True,
        )))

        deltas = [
            call for chunk in chunks if not chunk.done
            for call in (chunk.tool_calls or [])
        ]
        assert [call.name for call in deltas] == ["web_search", ""]
        assert "".join(call.arguments or "" for call in deltas) == '{"query":"jarvis"}'
        assert chunks[-1].done is True
        assert chunks[-1].tool_calls[0].id == "call-1"
        assert chunks[-1].tool_calls[0].name == "web_search"


# --------------------------------------------------------------------------- #
# Tests — secret isolation (spec §16, §69)
# --------------------------------------------------------------------------- #

class TestSecretIsolation:
    """Provider secrets must never appear in the model context."""

    def test_secret_in_request_is_rejected(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
        # Register the key in the SecretManager's env so the guard can find it
        sm = SecretManager(env={"OPENAI_API_KEY": "sk-test-secret-12345"})
        adapter = _make_openai_adapter(client=fake, api_key="sk-test-secret-12345")
        # Override the adapter's secret manager so it knows about the key
        adapter.secrets = sm
        req = ProviderRequest(
            messages=[Message.user("the key is sk-test-secret-12345")],
            model="gpt-5",
        )
        with pytest.raises(SecretLeakError):
            adapter.chat(req)

    def test_no_secret_in_response_metadata(self):
        fake = FakeOpenAIClient()
        fake.route_chat({
            "choices": [{"message": {"content": "reply"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
        sm = SecretManager(env={"OPENAI_API_KEY": "sk-super-secret-key"})
        adapter = _make_openai_adapter(client=fake, api_key="sk-super-secret-key")
        adapter.secrets = sm
        req = ProviderRequest(messages=[Message.user("hello")], model="gpt-5")
        resp = adapter.chat(req)
        assert "sk-super-secret-key" not in str(resp.to_dict())
        assert "sk-super-secret-key" not in str(resp.raw)


# --------------------------------------------------------------------------- #
# Tests — routing (spec §34, §35, §36)
# --------------------------------------------------------------------------- #

class TestRouting:
    """Policy-driven routing: no hard-coded winner, cost None when unknown."""

    def _fabric_with_openai(self, monkeypatch):
        """Build a registry with one configured provider (OpenAI) using fakes."""
        reset_registry()
        reset_secret_manager()
        registry = ProviderRegistry()

        fake = FakeOpenAIClient()
        fake.route_models(["gpt-5", "gpt-4o", "text-embedding-3-small"])
        fake.route_chat({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        })
        adapter = _make_openai_adapter(client=fake, api_key="test-key")
        registry.register(adapter)
        return registry

    def test_router_selects_by_capability(self):
        registry = self._fabric_with_openai(monkeypatch=None)
        router = ProviderRouter(registry, policy="best_quality")
        decision = router.route_text("explain this codebase")
        assert decision.selected_provider == "openai"
        assert decision.selected_model is not None
        assert decision.reason != ""

    def test_router_preserves_canonical_request_id(self):
        registry = self._fabric_with_openai(monkeypatch=None)
        request_id = "canonical-request-id"
        decision = ProviderRouter(registry).route(
            TaskClassifier().classify("chat"),
            request_id=request_id,
        )
        request = ProviderRequest(messages=[], request_id=request_id)

        assert decision.request_id == request_id
        assert request.request_id == request_id

    def test_empty_priority_uses_health_backed_candidates(self, monkeypatch):
        monkeypatch.delenv("JARVIS_PROVIDER_PRIORITY", raising=False)
        registry = ProviderRegistry()
        usable = FakeOpenAIClient()
        usable.route_models(["gpt-5"])
        registry.register(_make_openai_adapter(client=usable, api_key="openai-test"))
        unavailable = FakeOpenAIClient()
        unavailable.route_models([])
        registry.register(_make_nvidia_adapter(client=unavailable, api_key="nvidia-test"))

        decision = ProviderRouter(registry=registry, priority="").route_text("chat")

        assert decision.selected_provider == "openai"
        assert decision.selected_model == "openai:gpt-5"

    def test_router_finds_no_match_for_reranking(self):
        registry = self._fabric_with_openai(monkeypatch=None)
        router = ProviderRouter(registry, policy="best_quality")
        # No provider declares reranking — decision must have no selection
        profile = TaskProfile(capabilities=frozenset({Capability.RERANKING}))
        decision = router.route(profile)
        assert decision.selected_provider is None
        assert decision.candidate_count == 0
        assert "no configured provider" in decision.reason

    def test_cost_is_none_when_unknown(self):
        """Spec §34: cost must be None, never fabricated."""
        registry = self._fabric_with_openai(monkeypatch=None)
        router = ProviderRouter(registry, policy="best_quality")
        decision = router.route_text("chat about")
        assert decision.cost_estimate is None
        # pricing_per_1k may be populated if the model declares it, or None
        # The key invariant: cost_estimate is never a fabricated float

    def test_provider_priority_overrides_scoring(self, monkeypatch):
        """Spec §35: JARVIS_PROVIDER_PRIORITY overrides default scoring."""
        monkeypatch.setenv("JARVIS_PROVIDER_PRIORITY", "nvidia,openai")
        reset_registry()
        reset_secret_manager()
        registry = ProviderRegistry()

        # Register OpenAI first with high-scoring models, NVIDIA with lower
        # scoring models — but priority says nvidia first
        fake_oai = FakeOpenAIClient()
        fake_oai.route_models(["gpt-5"])
        fake_oai.route_chat({
            "choices": [{"message": {"content": "oai"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
        # OpenAI declares REASONING capability (high score); NVIDIA also does.
        # With priority "nvidia,openai", nvidia should come first even though
        # openai might score higher on "best_quality".
        adapter_oai = _make_openai_adapter(client=fake_oai, api_key="oai-key")

        fake_nvidia = FakeOpenAIClient()
        fake_nvidia.route_models(["meta/llama-3.3-70b-instruct"])
        adapter_nvidia = _make_nvidia_adapter(client=fake_nvidia, api_key="nv-key")

        registry.register(adapter_nvidia)
        registry.register(adapter_oai)

        router = ProviderRouter(registry, policy="best_quality")
        decision = router.route_text("chat")
        assert decision.selected_provider == "nvidia"

    def test_local_only_privacy_never_leaves_machine(self):
        """Spec §36: LOCAL_ONLY work can never use a hosted provider."""
        reset_registry()
        reset_secret_manager()
        registry = ProviderRegistry()
        fake = FakeOpenAIClient()
        fake.route_models(["gpt-5"])
        adapter = _make_openai_adapter(client=fake)
        registry.register(adapter)

        router = ProviderRouter(registry, policy="best_quality")
        profile = TaskProfile(
            capabilities=frozenset({Capability.CHAT}),
            privacy=__import__("providers").PrivacyClass.LOCAL_ONLY,
        )
        decision = router.route(profile)
        assert decision.selected_provider is None
        assert decision.candidate_count == 0

    def test_registry_health_snapshot(self):
        registry = self._fabric_with_openai(monkeypatch=None)
        snapshot = registry.health_snapshot(force=True)
        assert "openai" in snapshot
        # OpenAI with a fake client that has models => healthy
        from providers.health import HealthStatus
        assert snapshot["openai"].status is HealthStatus.HEALTHY


# --------------------------------------------------------------------------- #
# Tests — bootstrap factory
# --------------------------------------------------------------------------- #

class TestBootstrap:
    """The bootstrap factory wires all 5 adapters into the registry."""

    def test_bootstrap_returns_registry_with_all_providers(self, monkeypatch):
        # Clear env vars that would make adapters "configured" via real keys
        for var in ("OPENAI_API_KEY", "JARVIS_OPENAI_API_KEY",
                     "NVIDIA_API_KEY", "JARVIS_NVIDIA_API_KEY",
                     "GOOGLE_API_KEY", "JARVIS_GOOGLE_API_KEY",
                     "HF_TOKEN", "JARVIS_HF_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        # Also neutralize the .env file (live keys must not configure adapters).
        from pathlib import Path
        from providers.secrets import SecretManager
        reset_registry()
        reset_secret_manager(
            SecretManager(
                env={},
                dotenv_path=Path("F:/AI/__no_such_env_file__.env"),
            )
        )
        registry = bootstrap_fabric()
        ids = set(registry.provider_ids())
        assert ids == {"openai", "nvidia", "google", "aws", "hf"}
        # Baseline catalogs with no keys configured: 8+8+4+6+3.
        assert len(registry.catalog()) == 29

    def test_fabric_status_no_secrets(self, monkeypatch):
        for var in ("OPENAI_API_KEY", "JARVIS_OPENAI_API_KEY",
                     "GOOGLE_API_KEY", "JARVIS_GOOGLE_API_KEY",
                     "HF_TOKEN", "JARVIS_HF_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        reset_secret_manager()
        from providers.bootstrap import fabric_status
        status = fabric_status()
        # No raw secrets should appear in the status dict
        serialized = str(status)
        assert "sk-" not in serialized
        assert "hf_" not in serialized
        for info in status.values():
            assert "api_key" not in info
            assert "token" not in info
