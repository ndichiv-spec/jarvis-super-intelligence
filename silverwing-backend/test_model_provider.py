"""Unit tests for the general multi-model provider abstraction.

Run with:  python -m pytest test_model_provider.py -q
These tests are hermetic: no model SDK or API key is required. Providers
report unavailable without a key/SDK; the always-on LocalProvider and the
manager's fallback logic are exercised directly, plus a registered fake.
"""
import pytest

from model_provider import (
    ModelConfig,
    ModelManager,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    LocalProvider,
    ProviderInfo,
    OpenAIProvider,
    AnthropicProvider,
    GeminiProvider,
    GroqProvider,
    OllamaProvider,
    DeepSeekProvider,
    LlamaCppProvider,
    BedrockProvider,
    VertexProvider,
    SilverwingProvider,
    ModelRouter,
    ModelRegistry,
    CostTracker,
    HealthStatus,
    parse_model,
)


# ---------------------------------------------------------------------------
# ModelRequest / ModelResponse
# ---------------------------------------------------------------------------
class TestModels:
    def test_request_defaults(self):
        req = ModelRequest()
        assert req.messages == []
        assert req.model is None
        assert req.response_model is None

    def test_response_is_pydantic(self):
        r = ModelResponse(content="x", provider="local", model="local-rule")
        assert r.provider == "local"
        assert r.parsed is None
        assert r.usage == {}


# ---------------------------------------------------------------------------
# parse_model
# ---------------------------------------------------------------------------
class TestParseModel:
    @pytest.mark.parametrize("ref,expected", [
        (None, ("local", "local-rule")),
        ("", ("local", "local-rule")),
        ("local-rule", ("local", "local-rule")),
        ("openai:gpt-5.6-sol", ("openai", "gpt-5.6-sol")),
        ("google:gemini-2.5", ("google", "gemini-2.5")),
        ("gemini:gemini-2.5", ("google", "gemini-2.5")),  # gemini alias -> google
        ("anthropic:claude-fable-5", ("anthropic", "claude-fable-5")),
        ("groq:deepseek-v4-pro", ("groq", "deepseek-v4-pro")),
        ("ollama:deepseek-v4-pro", ("ollama", "deepseek-v4-pro")),
        ("bedrock:anthropic.claude-opus-5", ("bedrock", "anthropic.claude-opus-5")),
        ("vertex:gemini-2.5-pro", ("vertex", "gemini-2.5-pro")),
        ("deepseek:deepseek-v4-pro", ("deepseek", "deepseek-v4-pro")),
        ("llamacpp:Qwen3-32B", ("llamacpp", "Qwen3-32B")),
        ("openai", ("openai", "gpt-5.6-sol")),  # bare provider -> default
        ("bedrock", ("bedrock", "anthropic.claude-opus-5")),  # bare provider -> default
        ("deepseek", ("deepseek", "deepseek-v4-pro")),
        ("llamacpp", ("llamacpp", "Qwen3-32B-Q4_K_M.gguf")),
        ("deepseek-chat", ("local", "deepseek-chat")),  # unknown bare -> local fallback
    ])
    def test_parse(self, ref, expected):
        assert parse_model(ref)[:2] == expected  # provider + model; ignores config default for local


# ---------------------------------------------------------------------------
# Cloud providers: unavailable without key/SDK
# ---------------------------------------------------------------------------
class TestCloudProvidersUnavailable:
    @pytest.mark.parametrize("factory", [
        OpenAIProvider, AnthropicProvider, GeminiProvider, GroqProvider,
        DeepSeekProvider, BedrockProvider, VertexProvider,
    ])
    def test_no_key_means_unavailable(self, factory):
        # In the hermetic test env (no keys, no SDKs) every cloud provider that
        # requires credentials is unavailable; LocalProvider remains available
        # so the system degrades.
        p = factory(ModelConfig())
        assert isinstance(p.is_available(), bool)
        assert p.is_available() is False
        assert p.authorized is False

    @pytest.mark.parametrize("factory", [OllamaProvider, LlamaCppProvider])
    def test_local_server_unavailable_without_config(self, factory):
        # Providers that talk to a local server (Ollama / llama.cpp) require
        # an explicit host env var; without it they must report unavailable
        # even when the SDK is installed.
        p = factory(ModelConfig())
        assert isinstance(p.is_available(), bool)
        assert p.is_available() is False
        assert p.authorized is False


class TestLocalProvider:
    def test_always_available(self):
        assert LocalProvider(ModelConfig()).is_available() is True

    def test_echoes_last_user_message(self):
        import asyncio
        lp = LocalProvider(ModelConfig())
        req = ModelRequest(messages=[{"role": "user", "content": "hello there"}])
        resp = asyncio.run(lp.chat(req))
        assert resp.provider == "local"
        assert resp.content == "[local] hello there"
        assert resp.finish_reason == "stop"

    def test_no_user_message(self):
        import asyncio
        lp = LocalProvider(ModelConfig())
        req = ModelRequest(messages=[{"role": "assistant", "content": "hi"}])
        resp = asyncio.run(lp.chat(req))
        assert "no user message" in resp.content

    def test_response_model_json_parsing(self):
        import asyncio
        lp = LocalProvider(ModelConfig())
        req = ModelRequest(
            model="local-rule",
            messages=[{"role": "user", "content": '{"a": 1, "b": 2}'}],
            response_model="anything",
        )
        resp = asyncio.run(lp.chat(req))
        assert resp.parsed == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# Manager: fallback + registry + dispatch
# ---------------------------------------------------------------------------
class FakeProvider(ModelProvider):
    """A test provider that always answers; injectable via the registry."""

    name = "fake"

    def is_available(self) -> bool:
        return True

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content="fake-reply", parsed="ok", usage={"calls": 1},
            provider=self.name, model="fake-m", finish_reason="stop",
        )


class TestModelManager:
    def test_local_is_available_others_report_false(self):
        mgr = ModelManager()
        infos = {p.name: p for p in mgr.list_providers()}
        assert infos["local"].available is True
        # cloud providers with key/credential requirements have no keys in
        # the test env, so they must all report unavailable.
        for name in ("openai", "anthropic", "google", "groq",
                      "deepseek", "bedrock", "vertex"):
            assert infos[name].available is False
        # local-server providers require explicit host config
        for name in ("ollama", "llamacpp"):
            assert infos[name].available is False

    def test_provider_for_unknown_falls_back_to_local(self):
        mgr = ModelManager()
        provider, model = mgr.provider_for("does-not-exist:model-x")
        assert provider.name == "local"
        assert model == "model-x"

    def test_provider_for_unavailable_cloud_falls_back_to_local(self):
        mgr = ModelManager()
        provider, model = mgr.provider_for("openai:gpt-5.6-sol")
        # openai has no key/sdk in tests -> LocalProvider
        assert provider.name == "local"
        assert model == "gpt-5.6-sol"

    def test_register_and_dispatch_fake(self):
        import asyncio
        mgr = ModelManager(config=ModelConfig(default_model="local-rule"))
        mgr.register(FakeProvider(mgr.config))
        provider, model = mgr.provider_for("fake:some-model")
        assert provider.name == "fake"

        async def go():
            return await mgr.achat(ModelRequest(model="fake:some-model",
                                                messages=[{"role": "user", "content": "x"}]))
        resp = asyncio.run(go())
        assert resp.provider == "fake"
        assert resp.content == "fake-reply"
        assert resp.parsed == "ok"

    def test_set_and_get_default(self):
        mgr = ModelManager(config=ModelConfig())
        assert mgr.default_model() == "local-rule"
        mgr.set_default("openai:gpt-5.6-sol")
        assert "openai" in mgr.default_model()

    def test_auth_status_shape(self):
        mgr = ModelManager()
        st = mgr.auth_status()
        assert set(st) == {"default", "any_cloud_key", "providers", "schemas", "catalog_size"}
        assert st["any_cloud_key"] is False  # no keys in test env
        assert st["catalog_size"] > 0          # static catalog always populated
        assert "local" in st["providers"]
        # new providers are registered
        for prov in ("bedrock", "vertex", "deepseek", "llamacpp"):
            assert prov in st["providers"]

    def test_model_catalog_available(self):
        """The model catalog is populated and queryable."""
        from model_provider import MODEL_CATALOG
        assert len(MODEL_CATALOG) > 10
        assert "openai:gpt-5.6-sol" in MODEL_CATALOG
        assert "anthropic:claude-opus-5" in MODEL_CATALOG
        assert "google:gemini-2.5-pro" in MODEL_CATALOG
        assert "bedrock:anthropic.claude-opus-5" in MODEL_CATALOG
        assert "vertex:gemini-2.5-pro" in MODEL_CATALOG
        assert "deepseek:deepseek-v4-pro" in MODEL_CATALOG
        # Open-weights models are self-hostable
        from model_catalog import list_open_weights
        assert len(list_open_weights()) >= 3

    def test_fallback_to_local_for_new_providers(self):
        """Unregistered / unavailable providers fall back to LocalProvider."""
        mgr = ModelManager()
        provider, model = mgr.provider_for("deepseek:deepseek-v4-pro")
        assert provider.name == "local"
        assert model == "deepseek-v4-pro"
        provider, model = mgr.provider_for("bedrock:anthropic.claude-opus-5")
        assert provider.name == "local"
        assert model == "anthropic.claude-opus-5"

    def test_register_schema(self):
        mgr = ModelManager()

        class MyOut:  # stand-in; not validated here
            pass
        mgr.register_schema("my_schema", MyOut)
        assert mgr.get_schema("my_schema") is MyOut
        assert mgr.get_schema("missing") is None


# ---------------------------------------------------------------------------
# SilverwingProvider
# ---------------------------------------------------------------------------
class TestSilverwingProvider:
    def test_available_in_test_env(self):
        p = SilverwingProvider(ModelConfig())
        assert p.is_available() is True
        assert p.name == "silverwing"
        assert p.authorized is True

    def test_health_available(self):
        import asyncio
        p = SilverwingProvider(ModelConfig())
        status = asyncio.run(p.health())
        assert status == HealthStatus.AVAILABLE

    def test_chat_echoes_with_prefix(self):
        import asyncio
        # Force echo mode: unreachable server URL (``SILVERWING_SERVER_URL``
        # wins over the live default endpoint for this instance).
        p = SilverwingProvider(ModelConfig())
        p.server_url = "http://127.0.0.1:9"
        req = ModelRequest(messages=[{"role": "user", "content": "hello silverwing"}])
        resp = asyncio.run(p.chat(req))
        assert resp.provider == "silverwing"
        assert "[silverwing]" in resp.content
        assert "echo-fallback" in resp.content
        assert "hello silverwing" in resp.content
        assert resp.finish_reason == "stop"

    def test_embed_returns_vector(self):
        import asyncio
        p = SilverwingProvider(ModelConfig())
        emb = asyncio.run(p.embed("test embedding text"))
        assert isinstance(emb, list)
        assert len(emb) > 0
        # embed returns a list of per-input vectors (each a list of floats)
        first = emb[0]
        assert isinstance(first, list)
        assert len(first) > 0
        assert all(isinstance(x, float) for x in first)

    def test_no_user_message(self):
        import asyncio
        p = SilverwingProvider(ModelConfig())
        p.server_url = "http://127.0.0.1:9"
        req = ModelRequest(messages=[{"role": "assistant", "content": "hi"}])
        resp = asyncio.run(p.chat(req))
        assert "[silverwing]" in resp.content


# ---------------------------------------------------------------------------
# ModelRouter — capability-based selection + fallback chain
# ---------------------------------------------------------------------------
class TestModelRouter:
    def test_default_select_local(self):
        r = ModelRouter()
        d = r.select()
        assert d.success is True
        assert d.selected_model == "local:local-rule"
        assert d.provider == "local"

    def test_coding_task_selects_silverwing(self):
        r = ModelRouter()
        d = r.select(task="coding")
        assert d.success is True
        assert d.selected_model == "silverwing:silverwing-120m-base-v1"
        assert d.provider == "silverwing"

    def test_fast_response_private_pref_local(self):
        r = ModelRouter()
        d = r.select(task="fast_response", privacy="private", cost="low_cost")
        assert d.success is True
        assert d.provider in ("local", "silverwing")

    def test_fallback_chain_populated(self):
        r = ModelRouter()
        d = r.select()
        assert isinstance(d.fallback_chain, list)
        assert len(d.fallback_chain) > 0
        assert d.fallback is not None

    def test_decision_has_cost_estimate(self):
        r = ModelRouter()
        d = r.select()
        assert hasattr(d, "cost_estimate")
        assert "cost_estimate" in d.model_dump()

    def test_decision_has_latency(self):
        r = ModelRouter()
        d = r.select()
        assert hasattr(d, "latency_ms")
        assert "latency_ms" in d.model_dump()


# ---------------------------------------------------------------------------
# ModelRegistry — persistent capability registry
# ---------------------------------------------------------------------------
class TestModelRegistry:
    def test_registry_has_entries(self):
        reg = ModelRegistry()
        entries = reg.list()
        assert len(entries) >= 10

    def test_get_existing_model(self):
        reg = ModelRegistry()
        entry = reg.get("silverwing:silverwing-120m-base-v1")
        assert entry is not None
        assert entry.provider == "silverwing"
        assert entry.model_id == "silverwing-120m-base-v1"

    def test_get_missing_model(self):
        reg = ModelRegistry()
        entry = reg.get("nonexistent:does-not-exist")
        assert entry is None

    def test_by_provider(self):
        reg = ModelRegistry()
        silverwing_models = reg.by_provider("silverwing")
        assert len(silverwing_models) >= 2
        for m in silverwing_models:
            assert m.provider == "silverwing"

    def test_by_capability(self):
        reg = ModelRegistry()
        coding_models = reg.by_capability("coding")
        assert len(coding_models) > 0
        for m in coding_models:
            assert "coding" in m.capabilities

    def test_all_available(self):
        reg = ModelRegistry()
        avail = reg.all_available()
        assert len(avail) > 0
        providers = {m.provider for m in avail}
        assert "local" in providers
        assert "silverwing" in providers


# ---------------------------------------------------------------------------
# CostTracker — cost / pricing tracking
# ---------------------------------------------------------------------------
class TestCostTracker:
    def test_total_cost_starts_zero(self):
        ct = CostTracker()
        assert ct.total_cost() == 0.0

    def test_record_and_total(self):
        ct = CostTracker()
        cost = ct.record("local", "local-rule", 100, 50, 10.0)
        assert cost == 0.0
        assert ct.total_cost() == 0.0

    def test_record_creates_history(self):
        ct = CostTracker()
        ct.record("local", "local-rule", 100, 50, 10.0)
        assert len(ct.history) >= 1

    def test_estimate_cost_none_if_unknown(self):
        ct = CostTracker()
        result = ct.estimate_cost("nonexistent", "model-x", 100, 200)
        assert result is None
