"""JARVIS Brain model-gateway (Layer 3) client + platform routing tests.

Mirrors ``tests/test_silverwing_gateway.py``: all network I/O is routed through an
injected ``FakeAsyncHTTPClient``.  Covers the BrainClient honesty gate, bearer
auth + credential redaction, error-code mapping, and the platform
``ProviderGateway`` Brain-primary / Brain-down -> Silverwing-fallback decision.

These tests never start a socket and never import torch/transformers: the real
``TransformersBackend`` is exercised only by the integration-marked test in
``test_jarvis_brain_runtime.py``.  ``jarvis_backend`` imports are kept lazy so
the default test run stays fast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from backend.model_gateway.brain_client import BrainClient, _mask
from backend.model_gateway.models import (
    GatewayError,
    GatewayResponse,
    GatewayUsage,
)

pytestmark = pytest.mark.brain

API_KEY = "test-brain-key"
ENDPOINT = "http://fake:9999"


# --------------------------------------------------------------------------- #
# Fake HTTP client (async httpx stand-in, header-capturing)
# --------------------------------------------------------------------------- #
@dataclass
class FakeHTTPResponse:
    status_code: int = 200
    _json: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return self._json


class FakeAsyncHTTPClient:
    """Injected via ``_httpx_client``; returns canned responses or raises."""

    def __init__(self) -> None:
        self._route: dict[str, FakeHTTPResponse] = {}
        self._raise: dict[str, BaseException] = {}
        self._calls: list[tuple[str, str, Any, dict[str, str] | None]] = []

    def route(self, path: str, status: int = 200, body: dict[str, Any] | None = None):
        self._route[path] = FakeHTTPResponse(status_code=status, _json=body or {})

    def raise_on(self, path: str, exc: BaseException) -> None:
        self._raise[path] = exc

    async def request(self, method: str, url: str, *, json: Any = None,
                      headers: dict[str, str] | None = None, timeout: float = 30,
                      **_: Any) -> FakeHTTPResponse:
        self._calls.append((method, url, json, headers))
        # http://fake:9999/<path> -> "/<path>"
        path = url.split("/", 3)[-1] if "/" in url else ""
        key = "/" + path if path else "/"
        if key in self._raise:
            raise self._raise[key]
        resp = self._route.get(key)
        if resp is None:
            return FakeHTTPResponse(404, {"error": "not found"})
        return resp


def _br_client(
    routes: dict[str, tuple[int, dict[str, Any] | None]] | None = None,
    raises: dict[str, BaseException] | None = None,
    key: str = API_KEY,
) -> tuple[BrainClient, FakeAsyncHTTPClient]:
    http = FakeAsyncHTTPClient()
    for p, (st, body) in (routes or {}).items():
        http.route(p, status=st, body=body)
    for p, exc in (raises or {}).items():
        http.raise_on(p, exc)
    client = BrainClient(
        endpoint=ENDPOINT, api_key=key, model="jarvis-brain-qwen3-4b-v1",
        timeout=5, _httpx_client=http,
    )
    return client, http


_HEALTHY = {
    "status": "healthy", "model": "jarvis-brain-qwen3-4b-v1", "revision": "r1",
    "loaded": True, "device": "cpu", "backend": "transformers",
    "parameters": 4_000_000_000, "warmup_ok": True, "stub": False,
    "available": True, "authorized": True, "production_health": True, "detail": None,
}
_STUB_HEALTH = {
    "status": "stub", "stub": True, "available": False, "production_health": False,
    "loaded": True, "backend": "brain-stub", "model": "jarvis-brain-qwen3-4b-v1",
    "detail": "development stub",
}
_CHAT = {
    "object": "chat.completion", "model": "jarvis-brain-qwen3-4b-v1", "revision": "r1",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "brain answer"},
                 "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
}


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #
def test_mask_never_reveals_credential():
    masked = _mask("test-brain-key")
    assert "test-brain-key" not in masked
    assert masked == "test...ey"  # 4 prefix + "..." + 2 suffix


def test_mask_edge_cases():
    assert _mask("") == "<none>"
    assert _mask("ab") == "****"
    assert _mask(None) == "<none>"


def test_brain_client_api_key_masked():
    client = BrainClient(endpoint=ENDPOINT, api_key=API_KEY, model="m", timeout=1,
                         _httpx_client=None)
    # The masked accessor never reveals the raw credential.
    assert API_KEY not in client.api_key_masked
    assert client.api_key_masked == "test...ey"
    # The raw value is held in memory only for the outbound header; it is never
    # logged or returned by any accessor.
    assert client.api_key == API_KEY


# --------------------------------------------------------------------------- #
# Health honesty gate
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_brain_health_stub_rejected():
    client, _ = _br_client(routes={"/health": (503, _STUB_HEALTH)})
    h = await client.health(refresh=True)
    assert h.status.value == "offline"
    assert h.available is False
    with pytest.raises(GatewayError, match="gw_brain_unavailable"):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_brain_health_offline_rejected():
    body = {"status": "offline", "available": False, "stub": False,
            "loaded": False, "backend": "transformers"}
    client, _ = _br_client(routes={"/health": (503, body)})
    with pytest.raises(GatewayError, match="gw_brain_unavailable"):
        await client.chat([{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------------- #
# Chat success path (healthy brain) — auth header + redaction in transit
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_brain_chat_healthy_sends_auth_header():
    client, http = _br_client(routes={
        "/health": (200, _HEALTHY),
        "/v1/chat/completions": (200, _CHAT),
    })
    resp = await client.chat([{"role": "user", "content": "ping"}])
    assert resp.content == "brain answer"
    assert resp.metadata["provider"] == "jarvis-brain"
    assert resp.usage.total_tokens == 5
    # The bearer key was sent on the chat call.
    chat_call = [c for c in http._calls if c[0] == "POST" and "/v1/chat/completions" in c[1]]
    assert len(chat_call) == 1
    sent_headers = chat_call[0][3] or {}
    assert sent_headers.get("Authorization") == f"Bearer {API_KEY}"
    # Redaction: the raw key must never appear in any URL or unmasked header dump.
    for _method, url, _json, hdrs in http._calls:
        assert API_KEY not in str(url)
        if hdrs:
            assert API_KEY not in str(hdrs).replace(
                f"Bearer {API_KEY}", "<redacted>", 1
            )


# --------------------------------------------------------------------------- #
# Server-side auth failure surfaces as brain-unavailable (gateway falls back)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_brain_chat_server_401_maps_to_unavailable():
    client, _ = _br_client(routes={
        "/health": (200, _HEALTHY),
        "/v1/chat/completions": (401, {"error": "unauthorized"}),
    })
    with pytest.raises(GatewayError, match="gw_brain_unavailable"):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_brain_down_invalid_key_rejected_by_server():
    # A 401 from the runtime means the configured key is wrong; surface as
    # brain-unavailable so the platform falls back rather than retrying the key.
    http = FakeAsyncHTTPClient()
    http.route("/health", 200, _HEALTHY)
    http.route("/v1/chat/completions", 401, {"error": "invalid key"})
    client = BrainClient(endpoint=ENDPOINT, api_key="WRONG",
                         model="jarvis-brain-qwen3-4b-v1", timeout=5, _httpx_client=http)
    with pytest.raises(GatewayError, match="gw_brain_unavailable"):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_brain_empty_content_rejected():
    client, _ = _br_client(routes={
        "/health": (200, _HEALTHY),
        "/v1/chat/completions": (200, {
            "object": "chat.completion", "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ""},
                         "finish_reason": "stop"}],
            "usage": {},
        }),
    })
    with pytest.raises(GatewayError, match="gw_brain_unavailable"):
        await client.chat([{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------------- #
# Transport error mapping (connection-refused is NOT retryable transient)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_brain_down_connecterror_is_unavailable():
    import httpx
    client, _ = _br_client(raises={"/health": httpx.ConnectError("refused")})
    h = await client.health(refresh=True)
    assert h.status.value == "offline"
    assert h.available is False
    with pytest.raises(GatewayError, match="gw_brain_unavailable"):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_brain_timeout_is_transient():
    import httpx
    client, _ = _br_client(routes={"/health": (200, _HEALTHY)},
                           raises={"/v1/chat/completions": httpx.TimeoutException("slow")})
    with pytest.raises(GatewayError, match="gw_chat_transient") as ei:
        await client.chat([{"role": "user", "content": "hi"}])
    assert ei.value.retryable is True


# --------------------------------------------------------------------------- #
# Models list (no health gate) — still sends the bearer header
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_brain_models_list_sends_auth():
    client, http = _br_client(routes={
        "/v1/models": (200, {"object": "list", "data": [
            {"id": "jarvis-brain-qwen3-4b-v1"}, {"id": "jarvis-brain-qwen3-4b-sft-v1"}
        ]}),
    })
    models = await client.models()
    assert {m["id"] for m in models} == {
        "jarvis-brain-qwen3-4b-v1", "jarvis-brain-qwen3-4b-sft-v1",
    }
    models_call = [c for c in http._calls if c[0] == "GET" and "/v1/models" in c[1]]
    assert (models_call[0][3] or {}).get("Authorization") == f"Bearer {API_KEY}"


# --------------------------------------------------------------------------- #
# Endpoint normalisation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_brain_endpoint_normalisation(monkeypatch):
    # bare host -> /v1 appended; root base used for /health (no /v1 under it)
    client = BrainClient(endpoint="http://host:8011", api_key="k", model="m", timeout=1)
    assert client.endpoint == "http://host:8011/v1"
    assert client._root == "http://host:8011"
    # already /v1 -> unchanged
    client2 = BrainClient(endpoint="http://host:8011/v1", api_key="k", model="m", timeout=1)
    assert client2.endpoint == "http://host:8011/v1"
    assert client2._root == "http://host:8011"
    # empty / unconfigured -> both empty, not configured (no "/v1" ghost endpoint).
    # Clear ambient env vars (jarvis_backend.main's load_dotenv during full-suite
    # collection sets JARVIS_BRAIN_ENDPOINT from .env) so endpoint=None truly
    # falls back to the empty default.
    monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)
    client3 = BrainClient(endpoint=None, api_key=None, model="m", timeout=1)
    assert client3.endpoint == ""
    assert client3._root == ""
    assert client3.is_configured is False


# --------------------------------------------------------------------------- #
# Platform ProviderGateway routing (Brain-primary / Brain-down -> Silverwing)
# --------------------------------------------------------------------------- #
class _FakeBrainOk:
    """BrainClient double whose chat() returns a real Brain response."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, *, system=None, timeout=None, **kwargs):
        self.calls += 1
        return GatewayResponse(
            content="brain answer",
            model="jarvis-brain-qwen3-4b-v1",
            revision="r1",
            latency_ms=12.0,
            finish_reason="stop",
            usage=GatewayUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            metadata={"provider": "jarvis-brain", "backend": "transformers", "device": "gpu"},
        )


class _FakeBrainUnavailable:
    """BrainClient double whose chat() fails like an unreachable Brain."""

    async def chat(self, messages, *, system=None, timeout=None, **kwargs):
        raise GatewayError("brain unreachable", code="gw_brain_unavailable", retryable=False)


class _FakeBrainTimeout:
    """BrainClient double whose chat() times out (must NOT fall back)."""

    async def chat(self, messages, *, system=None, timeout=None, **kwargs):
        raise GatewayError("brain slow", code="gw_chat_transient", retryable=True)


class _FakeModelGateway:
    """Silverwing ModelGateway double (stands in for the real runtime)."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, task="chat", model=None, policy=None,
                   system=None, timeout=None, **kwargs):
        self.calls += 1
        return (
            GatewayResponse(
                content="silverwing real answer",
                model="silverwing-120m-base-v1",
                revision="r1",
                latency_ms=20.0,
                finish_reason="stop",
                usage=GatewayUsage(prompt_tokens=2, completion_tokens=2, total_tokens=4),
                metadata={"provider": "silverwing", "backend": "torch", "device": "cpu"},
            ),
            None,
        )


def _gateway_with_brain(brain_client, monkeypatch, *, brain_ep="http://127.0.0.1:8011/v1",
                        silverwing_ep="http://127.0.0.1:8010",
                        brain_model="jarvis-brain-qwen3-4b-v1",
                        silverwing_fake=None):
    """Build a ProviderGateway with a faked Brain client and (optionally) Silverwing."""
    monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", brain_ep)
    if silverwing_ep is not None:
        monkeypatch.setenv("SILVERWING_ENDPOINT", silverwing_ep)
    else:
        monkeypatch.delenv("SILVERWING_ENDPOINT", raising=False)
    monkeypatch.setenv("JARVIS_BRAIN_MODEL", brain_model)

    from jarvis_backend.gateway import ProviderGateway

    gw = ProviderGateway(brain_client=brain_client)
    if silverwing_fake is not None:
        import backend.model_gateway.routing as routing

        monkeypatch.setattr(routing, "default_gateway", silverwing_fake)
    return gw


@pytest.mark.asyncio
async def test_gateway_brain_primary_success(monkeypatch):
    # Runs inside asyncio.to_thread -> the transport double is sync.
    def fake_post(url, payload, key, *, provider=None, timeout=30.0):
        return {
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": "brain answer"},
                         "finish_reason": "stop"}],
            "model": payload["model"],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }

    from jarvis_backend.routers import extensions as _ext

    monkeypatch.setattr(_ext, "_openai_compatible_post", fake_post)
    monkeypatch.setenv("JARVIS_BRAIN_API_KEY", API_KEY)
    gw = _gateway_with_brain(_FakeBrainOk(), monkeypatch)
    result = await gw.chat([{"role": "user", "content": "hi"}])
    assert result["provider"] == "jarvis-brain"
    assert result["content"] == "brain answer"
    assert "fallback" not in result


@pytest.mark.asyncio
async def test_gateway_brain_down_falls_back_to_silverwing(monkeypatch):
    """When Brain is down, the gateway should fall back to Silverwing via HTTP."""
    import httpx
    import os

    # Set required environment variables
    monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://127.0.0.1:8011/v1")
    monkeypatch.setenv("SILVERWING_ENDPOINT", "http://127.0.0.1:8010")
    monkeypatch.setenv("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1")
    monkeypatch.setenv("JARVIS_BRAIN_API_KEY", API_KEY)
    # Set a cloud key so the honesty guard passes (needed when falling through to cloud path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fallback-key")

    # Mock the HTTP client used by _chat_via_model_gateway
    class FakeHTTPResponse:
        status_code = 200
        def json(self):
            return {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "model": "silverwing-120m-base-v1",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "silverwing real answer",
                    },
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 2,
                    "total_tokens": 4,
                },
                "metadata": {"provider": "silverwing", "backend": "torch", "device": "cpu"},
            }

    class FakeAsyncClient:
        async def __aenter__(self_inner):
            return self_inner
        async def __aexit__(self_inner, *args):
            pass
        async def post(self, url, **kwargs):
            return FakeHTTPResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: FakeAsyncClient())

    from jarvis_backend.gateway import ProviderGateway

    async def no_fabric(*args, **kwargs):
        return None

    monkeypatch.setattr(ProviderGateway, "_chat_via_phase6_fabric", no_fabric)
    gw = ProviderGateway(brain_client=_FakeBrainUnavailable())
    result = await gw.chat([{"role": "user", "content": "hi"}])

    # Honest fallback: Silverwing serves, provenance recorded from JARVIS_BRAIN_MODEL.
    assert result["provider"] == "silverwing"
    assert result["content"] == "silverwing real answer"
    assert result["fallback"]["from"] == "jarvis-brain-qwen3-4b-v1"


@pytest.mark.asyncio
async def test_gateway_brain_timeout_does_not_fallback(monkeypatch):
    # A timeout is retryable, not a confirmed-unavailable Brain -> no fallback.
    from fastapi import HTTPException
    from jarvis_backend.errors import ChatError, ErrorCategory
    from jarvis_backend.routers import extensions as _ext

    def fake_timeout(*args, **kwargs):
        raise HTTPException(status_code=504, detail="brain slow")

    monkeypatch.setattr(_ext, "_openai_compatible_post", fake_timeout)
    monkeypatch.setenv("JARVIS_BRAIN_API_KEY", API_KEY)

    gw = _gateway_with_brain(_FakeBrainTimeout(), monkeypatch, silverwing_ep=None)
    with pytest.raises(ChatError) as exc_info:
        await gw.chat([{"role": "user", "content": "hi"}])
    assert exc_info.value.category == ErrorCategory.TIMEOUT
    assert exc_info.value.retryable is True


def test_phase6_model_reference_parsing():
    from jarvis_backend.gateway import _parse_model_reference

    assert _parse_model_reference("google:gemini-2.5-flash") == (
        "google",
        "gemini-2.5-flash",
    )
    assert _parse_model_reference("nvidia:nvidia/llama-3.3-70b-instruct") == (
        "nvidia",
        "nvidia/llama-3.3-70b-instruct",
    )
    assert _parse_model_reference("auto") == (None, None)


def test_provider_fabric_import_uses_parent_workspace_root():
    from pathlib import Path
    from jarvis_backend.gateway import (
        _PROVIDER_FABRIC_ROOT,
        _ensure_provider_fabric_import_path,
    )

    assert _PROVIDER_FABRIC_ROOT == Path(r"F:\AI")
    assert _ensure_provider_fabric_import_path() == str(Path(r"F:\AI"))
    from providers.bootstrap import bootstrap_fabric
    assert callable(bootstrap_fabric)


@pytest.mark.asyncio
async def test_explicit_google_bypasses_silverwing_and_normalizes_usage(monkeypatch):
    from providers.base import ProviderResponse, Usage
    from providers.bootstrap import bootstrap_fabric
    from jarvis_backend.gateway import ProviderGateway

    class FakeAdapter:
        provider_id = "google"
        configured = True

        def chat(self, request):
            assert request.model == "gemini-2.5-flash"
            return ProviderResponse(
                provider="google",
                model="gemini-2.5-flash",
                text="4",
                usage=Usage(prompt_tokens=3, completion_tokens=2),
            )

    class FakeRegistry:
        def get(self, provider_id):
            return FakeAdapter() if provider_id == "google" else None

    registry = FakeRegistry()
    monkeypatch.setattr(
        "providers.bootstrap.bootstrap_fabric",
        lambda: registry,
    )
    monkeypatch.setenv("SILVERWING_ENDPOINT", "http://127.0.0.1:8010")

    async def silverwing_must_not_run(*args, **kwargs):
        raise AssertionError("Silverwing must not be called for explicit Google")

    monkeypatch.setattr(ProviderGateway, "_chat_via_model_gateway", silverwing_must_not_run)
    result = await ProviderGateway(timeout=2).chat(
        [{"role": "user", "content": "What is 2+2?"}],
        model="google:gemini-2.5-flash",
    )

    assert result["provider"] == "google"
    assert result["content"] == "4"
    assert result["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }


@pytest.mark.asyncio
async def test_automatic_fabric_route_does_not_short_circuit_with_silverwing(monkeypatch):
    from jarvis_backend.gateway import ProviderGateway

    monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)
    monkeypatch.setenv("SILVERWING_ENDPOINT", "http://127.0.0.1:8010")

    async def fabric_route(self, messages, model, system, deadline):
        return {
            "content": "4",
            "model": "gemini-2.5-flash",
            "provider": "google",
            "latency_ms": 3,
            "usage": None,
        }

    async def silverwing_must_not_run(*args, **kwargs):
        raise AssertionError("Silverwing must not short-circuit automatic fabric routing")

    monkeypatch.setattr(ProviderGateway, "_chat_via_phase6_fabric", fabric_route)
    monkeypatch.setattr(ProviderGateway, "_chat_via_model_gateway", silverwing_must_not_run)
    result = await ProviderGateway(timeout=2).chat(
        [{"role": "user", "content": "What is 2+2?"}],
    )

    assert result["provider"] == "google"
    assert result["content"] == "4"
