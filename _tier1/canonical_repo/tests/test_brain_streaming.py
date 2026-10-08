"""Tests for real SSE token streaming + the single-chunk fallback (spec Part O).

The streaming path is driven end-to-end through ``brain_runtime.server``
against a mocked upstream: a real-SSE transport and a complete-response
(non-streaming) transport.  No live provider credentials are required.
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from brain_runtime.backends.remote import RemoteBrainBackend
from brain_runtime.backends.stub import StubBackend
from brain_runtime.config import BrainConfig
from brain_runtime.generation import BrainGenerationConfig
from brain_runtime.server import create_app


def _models_response(*ids: str) -> dict:
    return {"object": "list", "data": [{"id": m} for m in ids]}


def _make_remote(mock_transport: httpx.MockTransport) -> RemoteBrainBackend:
    backend = RemoteBrainBackend(
        endpoint="https://integrate.api.nvidia.com/v1",
        api_key="nvidia-token",
        model="nvidia/nemotron-3-ultra-550b-a55b",
        timeout=10.0,
    )
    backend._client = httpx.Client(transport=mock_transport, base_url="https://integrate.api.nvidia.com/v1")
    return backend


def _sse_lines(*deltas: str) -> str:
    out = []
    for i, d in enumerate(deltas):
        out.append(
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-x",
                    "object": "chat.completion.chunk",
                    "model": "nvidia/nemotron-3-ultra-550b-a55b",
                    "choices": [
                        {"index": 0, "delta": {"content": d}, "finish_reason": None}
                    ],
                }
            )
        )
    out.append("data: [DONE]")
    return "\n".join(out) + "\n"


@pytest.mark.brain
class TestRealStreaming:
    def test_remote_stream_yields_real_sse_chunks(self):
        sse = _sse_lines("hello", " from", " nvidia")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json=_models_response("nvidia/nemotron-3-ultra-550b-a55b"))
            # POST /v1/chat/completions
            return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

        backend = _make_remote(httpx.MockTransport(handler))
        backend.load()

        cfg = BrainConfig(backend="nvidia", api_key="test-key")
        app = create_app(config=cfg, backend=backend)
        client = TestClient(app)
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={
                "model": "nvidia/nemotron-3-ultra-550b-a55b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        text = resp.text
        # Each SSE delta appears on the wire verbatim.
        assert "data: " in text
        assert "hello" in text
        assert "from" in text
        assert "nvidia" in text
        assert "[DONE]" in text
        # The role-only opening chunk and the final stop chunk are present.
        assert "finish_reason" in text
        assert "streaming complete" not in text  # log line, not body

    def test_remote_stream_handles_complete_response(self):
        """An endpoint that ignores ``stream=True`` and returns a complete
        chat.completion is faithfully surfaced as a single content chunk (real
        content, not fabricated tokens)."""
        complete = {
            "object": "chat.completion",
            "model": "nvidia/nemotron-3-ultra-550b-a55b",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hello from nvidia"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 3, "total_tokens": 6},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json=_models_response("nvidia/nemotron-3-ultra-550b-a55b"))
            return httpx.Response(200, json=complete)

        backend = _make_remote(httpx.MockTransport(handler))
        backend.load()

        cfg = BrainConfig(backend="nvidia", api_key="test-key")
        app = create_app(config=cfg, backend=backend)
        client = TestClient(app)
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={
                "model": "nvidia/nemotron-3-ultra-550b-a55b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        assert "hello from nvidia" in resp.text
        assert "[DONE]" in resp.text


@pytest.mark.brain
class TestStubStreamingFallback:
    def test_stub_stream_single_chunk_preserves_label(self):
        """A non-streaming backend (the stub) honors ``stream=True`` with a
        single content chunk + ``[DONE]`` rather than fabricating tokens."""
        stub = StubBackend(model_id="jarvis-brain-qwen3-4b-v1", revision="stub")
        cfg = BrainConfig(backend="stub", api_key="test-key")
        app = create_app(config=cfg, backend=stub)
        client = TestClient(app)
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={
                "model": "jarvis-brain-qwen3-4b-v1",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        assert "[brain-stub]" in resp.text
        assert "[DONE]" in resp.text
        assert "data: " in resp.text
