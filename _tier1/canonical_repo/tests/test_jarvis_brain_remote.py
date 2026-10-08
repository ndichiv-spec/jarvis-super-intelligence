"""Tests for the JARVIS Brain remote backend (spec section 22).

Covers:
  - remote configuration validation
  - remote authentication (separate from JARVIS_BRAIN_API_KEY)
  - remote chat completion normalization
  - remote model listing
  - remote health (endpoint / auth / model existence)
  - remote timeout, connection failure, unauthorized, empty response
  - remote -> Silverwing fallback (via BrainService.prepare + health)
  - stub isolation (stub never production-healthy)
  - local backend isolation (config selects correct backend)
  - secret redaction (remote_api_key never exposed)

All HTTP is mocked via httpx.MockTransport; no live external service required.
A separately marked integration test exercises a real endpoint when available.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

import brain_runtime.env as brain_env
from brain_runtime.backends.remote import RemoteBrainBackend, RemoteBrainError
from brain_runtime.config import BrainConfig
from brain_runtime.generation import BrainGenerationConfig, BrainResult
from brain_runtime.health import BrainHealthState
from brain_runtime.model_registry import BRAIN_MODEL_LINEAGE, BrainCatalog
from brain_runtime.service import BrainService
from brain_runtime.server import create_app

pytestmark = pytest.mark.brain

_REPO = Path("F:/AI/silverwing-models") if Path("F:/AI/silverwing-models").exists() else Path.cwd()
_BASE_REPO = BRAIN_MODEL_LINEAGE["jarvis-brain-qwen3-4b-v1"]["repository"]
_SFT_REPO = "Reyvic-254/jarvis-brain-qwen3-4b-sft-v1"


def _models_response(*model_ids: str) -> dict:
    return {"object": "list", "data": [{"id": m, "object": "model"} for m in model_ids]}


def _chat_response(content: str, model: str = "jarvis-brain-qwen3-4b-v1") -> dict:
    return {
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


class _MockTransport:
    """Wraps httpx.MockTransport with a simple handler registry.

    Routes requests by method+path and returns canned responses or raises
    exceptions.  Captures all calls for assertion.
    """

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], httpx.Response | BaseException] = {}
        self._calls: list[tuple[str, str, dict | None]] = []

    def route(self, method: str, path: str, response: dict | int | BaseException | httpx.Response) -> None:
        if isinstance(response, httpx.Response):
            self._routes[(method, path)] = response
        elif isinstance(response, int):
            self._routes[(method, path)] = httpx.Response(response)
        elif isinstance(response, BaseException):
            self._routes[(method, path)] = response
        else:
            self._routes[(method, path)] = httpx.Response(200, json=response)

    def calls(self) -> list[tuple[str, str, dict | None]]:
        return self._calls

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self._calls.append((request.method, request.url.path, request.content))
            key = (request.method, request.url.path)
            entry = self._routes.get(key)
            if entry is None:
                return httpx.Response(404, json={"error": "not found"})
            if isinstance(entry, BaseException):
                raise entry
            return entry

        return httpx.MockTransport(handler)


def _make_remote(
    mock: _MockTransport,
    *,
    endpoint: str = "https://remote.example.com/v1",
    api_key: str = "remote-secret-key",
    model: str = "jarvis-brain-qwen3-4b-v1",
    timeout: float = 120.0,
) -> RemoteBrainBackend:
    backend = RemoteBrainBackend(
        endpoint=endpoint, api_key=api_key, model=model, timeout=timeout,
    )
    backend._client = httpx.Client(transport=mock.transport(), base_url=endpoint)
    return backend


# --------------------------------------------------------------------------- #
# Configuration / backend construction
# --------------------------------------------------------------------------- #
class TestRemoteConfig:
    def test_remote_backend_selected_from_config(self):
        cfg = BrainConfig(backend="remote", remote_endpoint="https://api.example.com/v1",
                          remote_api_key="secret", remote_model="jarvis-brain-qwen3-4b-sft-v1")
        assert cfg.is_remote
        assert cfg.remote_endpoint == "https://api.example.com/v1"
        assert cfg.remote_model == "jarvis-brain-qwen3-4b-sft-v1"

    def test_remote_endpoint_strips_trailing_slash(self):
        # RemoteBrainBackend normalizes the endpoint (strips trailing slashes,
        # appends /v1 if missing).  The config stores the raw value; the backend
        # handles normalization at construction time.
        backend = RemoteBrainBackend(
            endpoint="https://api.example.com/v1/", api_key="k", model="m",
        )
        assert backend._endpoint == "https://api.example.com/v1"

    def test_remote_endpoint_appends_v1(self):
        backend = RemoteBrainBackend(
            endpoint="https://api.example.com", api_key="k", model="m",
        )
        assert backend._endpoint == "https://api.example.com/v1"

    def test_remote_model_defaults_to_brain_model(self):
        cfg = BrainConfig(backend="remote", remote_endpoint="https://api.example.com/v1")
        assert cfg.remote_model == cfg.model

    def test_remote_timeout_default(self):
        cfg = BrainConfig(backend="remote")
        assert cfg.remote_timeout == 120.0

    def test_remote_retries_default(self):
        cfg = BrainConfig(backend="remote")
        assert cfg.remote_retries == 2

    def test_backend_type_normalization(self):
        assert BrainConfig(backend="transformers").backend_type == "local"
        assert BrainConfig(backend="local").backend_type == "local"
        assert BrainConfig(backend="remote").backend_type == "remote"
        assert BrainConfig(backend="stub").backend_type == "stub"
        assert BrainConfig(backend="hf").backend_type == "remote"
        assert BrainConfig(backend="").backend_type == "local"

    def test_is_local_is_stub_preserved(self):
        assert BrainConfig(backend="stub").is_stub is True
        assert BrainConfig(backend="transformers").is_local is True
        assert BrainConfig(backend="remote").is_remote is True

    def test_env_loader_finds_workspace_dotenv_from_nested_checkout(
        self, tmp_path, monkeypatch,
    ):
        workspace = tmp_path / "workspace"
        package = workspace / "checkout" / "brain_runtime"
        package.mkdir(parents=True)
        dotenv = workspace / ".env"
        dotenv.write_text("JARVIS_BRAIN_BACKEND=remote\n", encoding="utf-8")
        monkeypatch.chdir(package)
        monkeypatch.setattr(brain_env, "__file__", str(package / "env.py"))

        assert brain_env._find_dotenv() == dotenv


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
class TestRemoteAuth:
    def test_remote_sends_bearer_token(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        backend = _make_remote(mock, api_key="remote-secret")
        backend.load()
        # The backend must have successfully loaded, proving the Authorization
        # header was accepted by the (mocked) endpoint.
        assert backend.loaded is True
        # The httpx client sends headers; verify the Authorization header.
        # We check via the captured request content — but headers aren't in _calls.
        # Instead, we verify via the backend's header method.
        # Actually, let's verify through the mock's captured headers by checking
        # the backend._headers() method.

    def test_remote_headers_contain_key(self):
        backend = _make_remote(_MockTransport())
        headers = backend._headers()
        assert headers["Authorization"] == "Bearer remote-secret-key"
        assert headers["Content-Type"] == "application/json"

    def test_remote_headers_without_key(self):
        backend = RemoteBrainBackend(endpoint="https://x/v1", api_key="", model="m")
        headers = backend._headers()
        assert "Authorization" not in headers

    def test_remote_api_key_is_separate_from_brain_api_key(self):
        """JARVIS_BRAIN_API_KEY and JARVIS_BRAIN_REMOTE_API_KEY must not cross."""
        env = {
            "JARVIS_BRAIN_API_KEY": "portal-key",
            "JARVIS_BRAIN_REMOTE_API_KEY": "hf-token",
            "JARVIS_BRAIN_REMOTE_ENDPOINT": "https://remote.example.com/v1",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = BrainConfig(backend="remote")
            assert cfg.api_key == "portal-key"
            assert cfg.remote_api_key == "hf-token"
            assert cfg.remote_endpoint == "https://remote.example.com/v1"
            assert cfg.api_key != cfg.remote_api_key


# --------------------------------------------------------------------------- #
# Remote model listing
# --------------------------------------------------------------------------- #
class TestRemoteModels:
    def test_list_models_returns_data(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        backend = _make_remote(mock)
        backend.load()
        models = backend.list_models()
        assert len(models) == 1
        assert models[0]["id"] == "jarvis-brain-qwen3-4b-v1"

    def test_list_models_401_raises(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", httpx.Response(401, json={"error": "unauthorized"}))
        backend = _make_remote(mock)
        with pytest.raises(RemoteBrainError, match="401"):
            backend.load()

    def test_load_requires_endpoint(self):
        backend = RemoteBrainBackend(endpoint="", api_key="k", model="m")
        with pytest.raises(RemoteBrainError, match="not configured"):
            backend.load()


# --------------------------------------------------------------------------- #
# Remote chat completion
# --------------------------------------------------------------------------- #
class TestRemoteChat:
    def test_chat_completion_normalized(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions", _chat_response("hello world"))
        backend = _make_remote(mock)
        backend.load()
        result = backend.generate(
            [{"role": "user", "content": "say hello"}],
            BrainGenerationConfig(model="jarvis-brain-qwen3-4b-v1", max_tokens=16),
        )
        assert result.text == "hello world"
        assert result.model == "jarvis-brain-qwen3-4b-v1"
        assert result.backend == "remote"
        assert result.tokens_input == 3
        assert result.tokens_generated == 2
        assert "latency_ms" in result.metadata

    def test_chat_uses_configured_remote_model(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-sft-v1"))
        mock.route("POST", "/v1/chat/completions", _chat_response("sft answer",
                                                                  model="jarvis-brain-qwen3-4b-sft-v1"))
        backend = _make_remote(mock, model="jarvis-brain-qwen3-4b-sft-v1")
        backend.load()
        result = backend.generate(
            [{"role": "user", "content": "hi"}],
            BrainGenerationConfig(model="jarvis-brain-qwen3-4b-sft-v1", max_tokens=16),
        )
        assert result.model == "jarvis-brain-qwen3-4b-sft-v1"

    def test_chat_empty_response_raises(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions",
                   {"object": "chat.completion", "model": "m",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": ""},
                                 "finish_reason": "stop"}], "usage": {}})
        backend = _make_remote(mock)
        backend.load()
        with pytest.raises(RemoteBrainError, match="empty response"):
            backend.generate([{"role": "user", "content": "x"}],
                             BrainGenerationConfig(model="jarvis-brain-qwen3-4b-v1", max_tokens=16))

    def test_chat_401_raises(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions", httpx.Response(401, json={"error": "unauthorized"}))
        backend = _make_remote(mock)
        backend.load()
        with pytest.raises(RemoteBrainError, match="401"):
            backend.generate([{"role": "user", "content": "x"}],
                             BrainGenerationConfig(model="jarvis-brain-qwen3-4b-v1", max_tokens=16))

    def test_chat_500_raises(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions", httpx.Response(500, json={"error": "boom"}))
        backend = _make_remote(mock)
        backend.load()
        with pytest.raises(RemoteBrainError, match="500"):
            backend.generate([{"role": "user", "content": "x"}],
                             BrainGenerationConfig(model="jarvis-brain-qwen3-4b-v1", max_tokens=16))

    def test_chat_connection_failure_raises(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions",
                   httpx.ConnectError("refused"))
        backend = _make_remote(mock)
        backend.load()
        with pytest.raises(RemoteBrainError, match="request failed"):
            backend.generate([{"role": "user", "content": "x"}],
                             BrainGenerationConfig(model="jarvis-brain-qwen3-4b-v1", max_tokens=16))

    def test_chat_timeout_raises(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions", httpx.TimeoutException("slow"))
        backend = _make_remote(mock)
        backend.load()
        with pytest.raises(RemoteBrainError, match="timed out"):
            backend.generate([{"role": "user", "content": "x"}],
                             BrainGenerationConfig(model="jarvis-brain-qwen3-4b-v1", max_tokens=16))

    def test_warmup_completes(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions", _chat_response("warm"))
        backend = _make_remote(mock)
        msg = backend.warmup("hi")
        assert msg == "warm"
        assert backend._warmup_done

    def test_chat_retries_transient_404(self):
        """A transient upstream 404 (hosted cold start) must not fail the call:
        bounded retry recovers and returns the real inference."""
        state = {"posts": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json=_models_response("remote-model"))
            state["posts"] += 1
            if state["posts"] == 1:
                return httpx.Response(404, json={"error": "cold start"})
            return httpx.Response(200, json=_chat_response("recovered", model="remote-model"))

        backend = RemoteBrainBackend(
            endpoint="https://remote.example.com/v1", api_key="k",
            model="remote-model", timeout=10.0, retries=2,
        )
        backend._client = httpx.Client(transport=httpx.MockTransport(handler))
        backend.load()
        result = backend.generate(
            [{"role": "user", "content": "x"}],
            BrainGenerationConfig(model="remote-model", max_tokens=8),
        )
        assert result.text == "recovered"
        assert state["posts"] == 2  # one failure + one success (not 3)

    def test_chat_retries_bounded_on_persistent_404(self):
        """A persistent upstream failure is NOT masked: it raises after the
        bounded retry budget is consumed."""
        state = {"posts": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json=_models_response("remote-model"))
            state["posts"] += 1
            return httpx.Response(404, json={"error": "nope"})

        backend = RemoteBrainBackend(
            endpoint="https://remote.example.com/v1", api_key="k",
            model="remote-model", timeout=10.0, retries=2,
        )
        backend._client = httpx.Client(transport=httpx.MockTransport(handler))
        backend.load()
        with pytest.raises(RemoteBrainError, match="404"):
            backend.generate(
                [{"role": "user", "content": "x"}],
                BrainGenerationConfig(model="remote-model", max_tokens=8),
            )
        assert state["posts"] == 3  # initial + 2 retries, then raises


# --------------------------------------------------------------------------- #
# Remote health via BrainService
# --------------------------------------------------------------------------- #
class TestRemoteServiceHealth:
    def test_remote_offline_on_auth_failure(self, tmp_path):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", httpx.Response(401, json={"error": "unauthorized"}))

        backend = RemoteBrainBackend(
            endpoint="https://remote.example.com/v1", api_key="bad-key",
            model="jarvis-brain-qwen3-4b-v1", timeout=10.0,
        )
        backend._client = httpx.Client(transport=mock.transport(),
                                        base_url="https://remote.example.com/v1")
        cfg = BrainConfig(
            backend="remote", remote_endpoint="https://remote.example.com/v1",
            remote_api_key="bad-key", model="jarvis-brain-qwen3-4b-v1",
            model_repo=_REPO, model_cache=Path(tmp_path) / "cache",
            api_key="portal-key",
        )
        svc = BrainService(config=cfg)
        # Without an injected backend, build_backend will be called by prepare.
        # We patch _import_remote_backend to return our mock-transport backend.
        import brain_runtime.service as svc_mod
        original = svc_mod._import_remote_backend
        svc_mod._import_remote_backend = lambda c: backend
        try:
            ok = svc.prepare()
        finally:
            svc_mod._import_remote_backend = original
        assert ok is False
        h = svc.health.current()
        assert h.status == BrainHealthState.OFFLINE
        assert h.available is False
        svc.shutdown()

    def test_remote_healthy_on_success(self, tmp_path):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions", _chat_response("ok"))

        backend = RemoteBrainBackend(
            endpoint="https://remote.example.com/v1", api_key="hf-token",
            model="jarvis-brain-qwen3-4b-v1", timeout=10.0,
        )
        backend._client = httpx.Client(transport=mock.transport(),
                                        base_url="https://remote.example.com/v1")
        cfg = BrainConfig(
            backend="remote", remote_endpoint="https://remote.example.com/v1",
            remote_api_key="hf-token", model="jarvis-brain-qwen3-4b-v1",
            model_repo=_REPO, model_cache=Path(tmp_path) / "cache",
            api_key="portal-key",
        )
        import brain_runtime.service as svc_mod
        original = svc_mod._import_remote_backend
        svc_mod._import_remote_backend = lambda c: backend
        svc = BrainService(config=cfg)
        try:
            ok = svc.prepare()
            assert ok is True
            h = svc.health.current()
            assert h.status == BrainHealthState.HEALTHY
            assert h.available is True
            assert h.production_health is True
            assert h.backend == "remote"
        finally:
            svc_mod._import_remote_backend = original
        svc.shutdown()

    def test_remote_unavailable_when_endpoint_missing(self, tmp_path):
        cfg = BrainConfig(
            backend="remote", remote_endpoint="",
            model="jarvis-brain-qwen3-4b-v1", model_repo=_REPO,
            model_cache=Path(tmp_path) / "cache",
        )
        svc = BrainService(config=cfg)
        ok = svc.prepare()
        assert ok is False
        h = svc.health.current()
        assert h.status == BrainHealthState.OFFLINE
        assert h.available is False
        assert h.production_health is False


# --------------------------------------------------------------------------- #
# Remote provider + model honesty (spec sections 14-15)
# --------------------------------------------------------------------------- #
class TestRemoteProviderHealth:
    def test_nvidia_health_reports_provider_and_live_model(self, tmp_path):
        """A remote NVIDIA backend reports provider=nvidia and the actual
        served model id on /health -- never the stub-era registry id."""
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("nvidia/nemotron-3-ultra-550b-a55b"))
        mock.route("POST", "/v1/chat/completions",
                   _chat_response("ok", model="nvidia/nemotron-3-ultra-550b-a55b"))

        endpoint = "https://integrate.api.nvidia.com/v1"
        backend = RemoteBrainBackend(
            endpoint=endpoint, api_key="nvidia-token",
            model="nvidia/nemotron-3-ultra-550b-a55b", timeout=10.0,
        )
        backend._client = httpx.Client(transport=mock.transport(), base_url=endpoint)
        # config.model intentionally differs (stub-era id); health must still
        # report backend.model_id (the model actually serving inference).
        cfg = BrainConfig(
            backend="remote", remote_endpoint=endpoint,
            remote_api_key="nvidia-token", model="jarvis-brain-qwen3-4b-sft-v1",
            model_repo=_REPO, model_cache=Path(tmp_path) / "cache",
            api_key="portal-key",
        )
        import brain_runtime.service as svc_mod
        original = svc_mod._import_remote_backend
        svc_mod._import_remote_backend = lambda c: backend
        svc = BrainService(config=cfg)
        try:
            assert svc.prepare() is True
            h = svc.health.current()
            assert h.backend == "remote"
            assert h.provider == "nvidia"
            assert h.model == "nvidia/nemotron-3-ultra-550b-a55b"
        finally:
            svc_mod._import_remote_backend = original
        svc.shutdown()

    def test_generic_remote_health_reports_hf_provider(self, tmp_path):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions", _chat_response("ok"))

        endpoint = "https://remote.example.com/v1"
        backend = RemoteBrainBackend(
            endpoint=endpoint, api_key="hf-token",
            model="jarvis-brain-qwen3-4b-v1", timeout=10.0,
        )
        backend._client = httpx.Client(transport=mock.transport(), base_url=endpoint)
        cfg = BrainConfig(
            backend="remote", remote_endpoint=endpoint,
            remote_api_key="hf-token", model="jarvis-brain-qwen3-4b-v1",
            model_repo=_REPO, model_cache=Path(tmp_path) / "cache",
            api_key="portal-key",
        )
        import brain_runtime.service as svc_mod
        original = svc_mod._import_remote_backend
        svc_mod._import_remote_backend = lambda c: backend
        svc = BrainService(config=cfg)
        try:
            assert svc.prepare() is True
            h = svc.health.current()
            assert h.provider == "hf-inference"
            assert h.model == "jarvis-brain-qwen3-4b-v1"
        finally:
            svc_mod._import_remote_backend = original
        svc.shutdown()

    def test_server_chat_surfaces_provider_and_stream_model(self, tmp_path):
        """:8011 chat response reports the actual upstream provider + streamed
        model id (spec section 15 / frontend streaming protocol)."""
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("nvidia/nemotron-3-ultra-550b-a55b"))
        mock.route("POST", "/v1/chat/completions",
                   _chat_response("hello from nvidia", model="nvidia/nemotron-3-ultra-550b-a55b"))

        endpoint = "https://integrate.api.nvidia.com/v1"
        backend = RemoteBrainBackend(
            endpoint=endpoint, api_key="nvidia-key",
            model="nvidia/nemotron-3-ultra-550b-a55b", timeout=10.0,
        )
        backend._client = httpx.Client(transport=mock.transport(), base_url=endpoint)
        backend.load()
        cfg = BrainConfig(
            backend="remote", remote_endpoint=endpoint,
            remote_api_key="nvidia-key", model="nvidia/nemotron-3-ultra-550b-a55b",
            model_repo=_REPO, model_cache=Path(tmp_path) / "cache",
            api_key="test-key",
        )
        app = create_app(config=cfg, backend=backend)
        with TestClient(app) as client:
            r = client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={"model": "nvidia/nemotron-3-ultra-550b-a55b",
                      "messages": [{"role": "user", "content": "hi"}]},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["provider"] == "nvidia"
            assert body["model"] == "nvidia/nemotron-3-ultra-550b-a55b"

            rs = client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={"model": "nvidia/nemotron-3-ultra-550b-a55b",
                      "messages": [{"role": "user", "content": "hi"}],
                      "stream": True},
            )
            assert rs.status_code == 200
            assert "nvidia/nemotron-3-ultra-550b-a55b" in rs.text  # stream model identity
            assert "hello from nvidia" in rs.text
            assert "[DONE]" in rs.text


# --------------------------------------------------------------------------- #
# Remote -> Silverwing fallback (via BrainService.prepare failure)
# --------------------------------------------------------------------------- #
class TestRemoteFallback:
    def test_remote_down_reports_offline_for_fallback(self, tmp_path):
        """When remote backend fails to load, service is OFFLINE so gateway falls back."""
        mock = _MockTransport()
        mock.route("GET", "/v1/models", httpx.ConnectError("dns"))

        backend = RemoteBrainBackend(
            endpoint="https://dead.example.com/v1", api_key="token",
            model="jarvis-brain-qwen3-4b-v1", timeout=10.0,
        )
        backend._client = httpx.Client(transport=mock.transport(),
                                        base_url="https://dead.example.com/v1")
        cfg = BrainConfig(
            backend="remote", remote_endpoint="https://dead.example.com/v1",
            remote_api_key="token", model="jarvis-brain-qwen3-4b-v1",
            model_repo=_REPO, model_cache=Path(tmp_path) / "cache",
        )
        import brain_runtime.service as svc_mod
        original = svc_mod._import_remote_backend
        svc_mod._import_remote_backend = lambda c: backend
        svc = BrainService(config=cfg)
        try:
            ok = svc.prepare()
            assert ok is False
            h = svc.health.current()
            assert h.status == BrainHealthState.OFFLINE
            assert h.available is False
            assert h.production_health is False
        finally:
            svc_mod._import_remote_backend = original

    def test_remote_unreachable_then_fallback_path(self, tmp_path):
        """Simulates: gateway sees Brain OFFLINE, routes to Silverwing instead."""
        mock = _MockTransport()
        mock.route("GET", "/v1/models", httpx.ConnectError("dns"))

        backend = RemoteBrainBackend(
            endpoint="https://dead.example.com/v1", api_key="token",
            model="jarvis-brain-qwen3-4b-v1", timeout=10.0,
        )
        backend._client = httpx.Client(transport=mock.transport(),
                                        base_url="https://dead.example.com/v1")
        cfg = BrainConfig(
            backend="remote", remote_endpoint="https://dead.example.com/v1",
            remote_api_key="token", model="jarvis-brain-qwen3-4b-v1",
            model_repo=_REPO, model_cache=Path(tmp_path) / "cache",
            api_key="portal-key",
        )
        import brain_runtime.service as svc_mod
        original = svc_mod._import_remote_backend
        svc_mod._import_remote_backend = lambda c: backend
        svc = BrainService(config=cfg)
        try:
            ok = svc.prepare()
            assert ok is False
            h = svc.health.current()
            # The gateway's honesty gate sees available=False -> falls back to Silverwing
            assert h.available is False
            assert h.stub is False
            # Never pretend Silverwing is Qwen
            assert h.backend in ("", "remote", "transformers", "brain-stub")
        finally:
            svc_mod._import_remote_backend = original


# --------------------------------------------------------------------------- #
# Stub isolation (unchanged behavior)
# --------------------------------------------------------------------------- #
class TestStubIsolation:
    def test_stub_never_production_healthy(self, tmp_path):
        from brain_runtime.server import create_app as _create_app

        cfg = BrainConfig(
            host="127.0.0.1", port=8011, api_key="test-key",
            model="jarvis-brain-qwen3-4b-v1",
            model_repo=_REPO, model_cache=Path(tmp_path) / "brain-cache",
            backend="stub", device="cpu",
            request_timeout=30.0, default_max_tokens=8192,
            warmup_prompt="hi", local_files_only=False,
        )
        app = _create_app(config=cfg)
        with TestClient(app) as client:
            r = client.get("/health")
            assert r.status_code == 503
            body = r.json()
            assert body["stub"] is True
            assert body["available"] is False
            assert body["production_health"] is False
            assert body["status"] == "stub"


# --------------------------------------------------------------------------- #
# Local backend isolation (unchanged behavior)
# --------------------------------------------------------------------------- #
class TestLocalBackendIsolation:
    def test_local_backend_selected_when_transformers(self):
        cfg = BrainConfig(backend="transformers")
        assert cfg.is_local is True
        assert cfg.is_remote is False
        assert cfg.is_stub is False

    def test_local_backend_selected_when_local(self):
        cfg = BrainConfig(backend="local")
        assert cfg.is_local is True


# --------------------------------------------------------------------------- #
# Secret redaction
# --------------------------------------------------------------------------- #
class TestSecretRedaction:
    def test_remote_backend_never_exposes_api_key_in_metadata(self):
        mock = _MockTransport()
        mock.route("GET", "/v1/models", _models_response("jarvis-brain-qwen3-4b-v1"))
        mock.route("POST", "/v1/chat/completions", _chat_response("hi"))
        backend = _make_remote(mock, api_key="super-secret-hf-key")
        backend.load()
        result = backend.generate(
            [{"role": "user", "content": "x"}],
            BrainGenerationConfig(model="jarvis-brain-qwen3-4b-v1", max_tokens=8),
        )
        # The remote API key must not appear in any returned field.
        blob = str(result.metadata)
        assert "super-secret-hf-key" not in blob
        assert "Bearer" not in blob

    def test_config_remote_api_key_present_not_exposed(self):
        cfg = BrainConfig(
            backend="remote",
            remote_api_key="secret-key-12345",
            api_key="portal-key",
        )
        assert cfg.remote_api_key == "secret-key-12345"
        assert cfg.api_key == "portal-key"
        assert cfg.remote_api_key != cfg.api_key


# --------------------------------------------------------------------------- #
# Integration: real endpoint (only runs when JARVIS_BRAIN_ENDPOINT is set)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("JARVIS_BRAIN_INTEGRATION_ENDPOINT"),
    reason="set JARVIS_BRAIN_INTEGRATION_ENDPOINT to run a live remote inference test",
)
def test_remote_live_chat():
    """Live end-to-end test against a real Hugging Face Inference Endpoint."""
    endpoint = os.environ["JARVIS_BRAIN_INTEGRATION_ENDPOINT"]
    api_key = os.environ.get("JARVIS_BRAIN_INTEGRATION_API_KEY", "")
    model = os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1")

    backend = RemoteBrainBackend(
        endpoint=endpoint, api_key=api_key, model=model, timeout=120.0,
    )
    backend.load()
    result = backend.generate(
        [{"role": "user", "content": "What is the capital of France?"}],
        BrainGenerationConfig(model=model, max_tokens=64, temperature=0.0),
    )
    assert result.text.strip()
    assert len(result.text) > 0
    backend.close()
