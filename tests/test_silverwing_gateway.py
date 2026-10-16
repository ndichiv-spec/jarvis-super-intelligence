"""Model gateway (Layer 3) tests.

All network calls are routed through a FakeAsyncHTTPClient injected into the
gateway client.  The platform fallback path is not tested here (it depends on
``jarvis_backend`` live imports); instead we verify:

* Client parses health / models / chat / generate responses correctly.
* Client propagates latency_ms, usage, device, and revision metadata.
* Routing selects Silverwing when healthy and falls back honestly.
* Routing records decision telemetry through the Observatory bridge.
* GatewayError is raised (never fabricated output) when Silverwing is offline.
* LangChain adapter wraps messages and invokes the client correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from backend.model_gateway import SilverwingClient
from backend.model_gateway.health import HealthLevel
from backend.model_gateway.langchain import SilverwingLLM, _normalize_messages
from backend.model_gateway.models import GatewayError
from backend.model_gateway.routing import ModelGateway, RoutingDecision

pytestmark = pytest.mark.silverwing


# --------------------------------------------------------------------------- #
# Fake HTTP client (async httpx stand-in)
# --------------------------------------------------------------------------- #
@dataclass
class FakeHTTPResponse:
    status_code: int = 200
    _json: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return self._json


class FakeAsyncHTTPClient:
    """Injected via ``_httpx_client``; returns canned responses."""

    def __init__(self) -> None:
        self._route: dict[str, Any] = {}
        self._calls: list[tuple] = []

    def route(self, path: str, status: int = 200, body: dict[str, Any] | None = None):
        self._route[path] = FakeHTTPResponse(status_code=status, _json=body or {})

    async def request(
        self, method: str, url: str, *, json: Any = None, timeout: float = 30, **_: Any
    ) -> FakeHTTPResponse:
        self._calls.append((method, url, json))
        path = url.split("/", 3)[-1] if "/" in url else ""
        resp = self._route.get("/" + path)
        if resp is None:
            return FakeHTTPResponse(status_code=404, _json={"error": "not found"})
        return resp


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_HEALTHY_BODY = {
    "status": "healthy",
    "model": "test-model-v1",
    "revision": "r1",
    "loaded": True,
    "device": "cuda:0",
    "parameters": 1_000,
    "warmup_ok": True,
    "detail": None,
}
_MODELS_BODY = {
    "object": "list",
    "data": [
        {
            "id": "test-model-v1",
            "context_length": 512,
            "parameters": 1_000,
            "capabilities": ["text-generation"],
            "status": "experimental",
        },
    ],
}
_CHAT_BODY = {
    "object": "chat.completion",
    "model": "test-model-v1",
    "revision": "r1",
    "device": "cuda:0",
    "latency_ms": 42.5,
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
def _client(
    route_path: str = "/v1/health",
    body: dict | None = None,
    status: int = 200,
    endpoint: str = "http://fake:9999",
) -> tuple[SilverwingClient, FakeAsyncHTTPClient]:
    http = FakeAsyncHTTPClient()
    http.route(route_path, status=status, body=body or _HEALTHY_BODY)
    client = SilverwingClient(
        endpoint=endpoint,
        api_key="",
        model="test-model-v1",
        timeout=5,
        _httpx_client=http,
    )
    # Force remote mode
    client.mode = "remote"
    return client, http


def _with_routes(
    endpoint: str = "http://fake:9999", routes: dict[str, FakeHTTPResponse] | None = None
) -> tuple[SilverwingClient, FakeAsyncHTTPClient]:
    http = FakeAsyncHTTPClient()
    http._route = dict(routes or {})
    client = SilverwingClient(
        endpoint=endpoint,
        api_key="",
        model="test-model-v1",
        timeout=5,
        _httpx_client=http,
    )
    client.mode = "remote"
    return client, http


@pytest.mark.asyncio
async def test_client_health_parses_fields():
    client, _ = _client()
    h = await client.health(refresh=True)
    assert h.status == HealthLevel.HEALTHY
    assert h.model == "test-model-v1"
    assert h.revision == "r1"
    assert h.device == "cuda:0"
    assert h.parameters == 1_000
    assert h.warmup_ok is True


@pytest.mark.asyncio
async def test_client_health_degraded_on_503():
    client, _ = _client(status=503, body={"status": "starting", "loaded": False})
    h = await client.health(refresh=True)
    assert h.status == HealthLevel.DEGRADED


@pytest.mark.asyncio
async def test_client_models_list():
    client, _ = _with_routes(
        routes={
            "/v1/models": FakeHTTPResponse(200, _MODELS_BODY),
        }
    )
    models = await client.models()
    assert len(models) == 1
    assert models[0].id == "test-model-v1"
    assert models[0].capabilities == ["text-generation"]


@pytest.mark.asyncio
async def test_client_chat_parses_latency_and_usage():
    client, _ = _with_routes(
        routes={
            "/v1/chat/completions": FakeHTTPResponse(200, _CHAT_BODY),
        }
    )
    resp = await client.chat([{"role": "user", "content": "ping"}])
    assert resp.content == "pong"
    assert resp.model == "test-model-v1"
    assert resp.revision == "r1"
    assert resp.latency_ms == 42.5
    assert resp.usage.total_tokens == 15
    assert resp.usage.prompt_tokens == 10
    assert resp.metadata.get("device") == "cuda:0"


@pytest.mark.asyncio
async def test_client_chat_raises_on_error():
    client, _ = _with_routes(
        routes={
            "/v1/chat/completions": FakeHTTPResponse(500, {"error": "boom"}),
        }
    )
    with pytest.raises(GatewayError, match="gw_chat_failed"):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_client_generate_parses_usage():
    generate_body = {
        "object": "text_completion",
        "model": "test-model-v1",
        "revision": "r1",
        "device": "cpu",
        "latency_ms": 7.0,
        "choices": [{"index": 0, "text": "hello", "finish_reason": "stop"}],
        "usage": {"output_tokens": 3, "total_tokens": 3},
    }
    client, _ = _with_routes(
        routes={
            "/v1/generate": FakeHTTPResponse(200, generate_body),
        }
    )
    resp = await client.generate("hello")
    assert resp.content == "hello"
    assert resp.latency_ms == 7.0
    assert resp.usage.total_tokens == 3


@pytest.mark.asyncio
async def test_client_local_mode_avoids_remote():
    client, http = _client(endpoint="")
    client.mode = "local"
    h = await client.health(refresh=True)
    # local mode hits the registry-backed path, not the http client.
    assert http._calls == []
    assert h.status in (HealthLevel.HEALTHY, HealthLevel.OFFLINE)


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_routing_selects_healthy_silverwing():
    gw = ModelGateway(
        silverwing=_with_routes(
            routes={
                "/v1/models": FakeHTTPResponse(200, _MODELS_BODY),
                "/v1/health": FakeHTTPResponse(200, _HEALTHY_BODY),
                "/v1/chat/completions": FakeHTTPResponse(200, _CHAT_BODY),
            }
        )[0]
    )
    resp, decision = await gw.chat(
        [{"role": "user", "content": "hi"}],
        task="chat",
    )
    assert decision.selected_provider == "silverwing"
    assert decision.selected_model == "test-model-v1"
    assert decision.fallback_from is None
    assert resp.content == "pong"


@pytest.mark.asyncio
async def test_routing_honest_failure_when_offline(monkeypatch):
    http = FakeAsyncHTTPClient()
    http.route("/v1/health", status=503, body={"status": "offline", "loaded": False})
    offline = SilverwingClient(
        endpoint="http://127.0.0.1:9999",
        api_key="",
        model="m",
        timeout=0.1,
        _httpx_client=http,
    )
    offline.mode = "remote"

    # Force the platform fallback to be unavailable so this test is hermetic:
    # ambient provider credentials must not let a unit test reach a live
    # provider (the honest-failure path is what is under test here).
    import jarvis_backend.gateway as _jarvis_gateway

    async def _no_fallback(*_args, **_kwargs):
        raise RuntimeError("no fallback provider configured (test)")

    monkeypatch.setattr(_jarvis_gateway.provider_gateway, "chat", _no_fallback)

    gw = ModelGateway(silverwing=offline)
    with pytest.raises(GatewayError, match="gw_fallback_unavailable"):
        await gw.chat([{"role": "user", "content": "hi"}], task="chat")


@pytest.mark.asyncio
async def test_routing_records_decision_and_observatory():
    from jarvis_backend.observability import GATEWAY_EVENT_LOG

    gw = ModelGateway(
        silverwing=_with_routes(
            routes={
                "/v1/models": FakeHTTPResponse(200, _MODELS_BODY),
                "/v1/health": FakeHTTPResponse(200, _HEALTHY_BODY),
                "/v1/chat/completions": FakeHTTPResponse(200, _CHAT_BODY),
            }
        )[0]
    )
    before = GATEWAY_EVENT_LOG["counts"]["requests"]
    await gw.chat([{"role": "user", "content": "hi"}], task="chat")
    after = GATEWAY_EVENT_LOG["counts"]["requests"]
    assert after == before + 1


# --------------------------------------------------------------------------- #
# RoutingDecision
# --------------------------------------------------------------------------- #
def test_decision_serializes_cleanly():
    d = RoutingDecision(
        requested_model="m",
        selected_provider="silverwing",
        selected_model="m-v1",
        fallback_from="sw:m-v1",
    )
    out = d.to_dict()
    assert out["fallback_from"] == "sw:m-v1"
    assert out["timestamp"] > 0


# --------------------------------------------------------------------------- #
# LangChain adapter
# --------------------------------------------------------------------------- #
def test_normalize_messages_string():
    msgs = _normalize_messages("hello world")
    assert msgs == [{"role": "user", "content": "hello world"}]


def test_normalize_messages_dict():
    msgs = _normalize_messages([{"role": "user", "content": "hi"}])
    assert msgs[0]["role"] == "user"


def test_normalize_messages_langchain_objects():
    """Duck-typed messages (attributes role + content) are normalized."""

    class FakeMsg:
        role = "assistant"
        content = "yes"

    msgs = _normalize_messages([FakeMsg()])
    assert msgs == [{"role": "assistant", "content": "yes"}]


def test_silverwing_llm_identifying_params():
    llm = SilverwingLLM(endpoint="http://x:9999", model="my-model")
    assert llm._identifying_params["model"] == "my-model"
    assert llm._llm_type == "silverwing"
