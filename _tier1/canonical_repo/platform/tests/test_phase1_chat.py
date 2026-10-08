"""Phase 1 — chat service: real provider via gateway, no-fake, retry,
idempotency, and SSE streaming.

Exercises the ChatService <-> ProviderGateway boundary.  No real provider is
available in this environment (no cloud API keys), so the gateway's honest
"no fake" behaviour is tested directly.  Async service methods are driven with
``asyncio.run`` so the suite does not depend on a pytest-asyncio plugin.
"""
from __future__ import annotations

import asyncio
import json

from jarvis_backend import chat_service as cs
from jarvis_backend.errors import ChatError, ErrorCategory
from jarvis_backend.gateway import provider_gateway, ProviderGateway


class FakeGateway:
    """Deterministic test double for ProviderGateway."""

    def __init__(self, content="Hello from the model.", provider="fake",
                 side_effect=None):
        self.content = content
        self.provider = provider
        self.side_effect = side_effect
        self.calls = 0
        self.timeout = 30.0
        self.max_retries = 0

    async def chat(self, messages, model=None, system=None, timeout=None):
        self.calls += 1
        if self.side_effect is not None:
            raise self.side_effect
        return {
            "content": self.content,
            "model": f"{self.provider}:test",
            "provider": self.provider,
            "latency_ms": 5,
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }


class FlakyGateway:
    """Raises a retryable TIMEOUT on the first call, succeeds on the second."""

    def __init__(self):
        self.calls = 0
        self.timeout = 30.0
        self.max_retries = 2

    async def chat(self, messages, model=None, system=None, timeout=None):
        self.calls += 1
        if self.calls < 2:
            raise ChatError(ErrorCategory.TIMEOUT, "slow provider", retryable=True)
        return {"content": "recovered", "model": "fake:ok", "provider": "fake",
                "latency_ms": 7, "usage": {}}


# -- HTTP-level --------------------------------------------------------------- #
def test_chat_returns_real_provider_response(client, auth_headers, monkeypatch):
    fake = FakeGateway(content="Hello from the model.")
    monkeypatch.setattr(cs.chat_service, "gateway", fake)
    r = client.post("/api/chat", json={"message": "hi"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "COMPLETED"
    assert data["reply"] == "Hello from the model."
    assert data["model"].startswith("fake:")
    assert data["provider"] == "fake"
    assert data["error"] is None
    assert fake.calls == 1


def test_no_fake_when_provider_unavailable(client, auth_headers, monkeypatch):
    """Scenario C: with no cloud key, responses are FAILED — never fabricated."""
    monkeypatch.setattr(cs.chat_service, "gateway", provider_gateway)
    r = client.post("/api/chat", json={"message": "hi"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "FAILED"
    assert data["error"]["category"] == "PROVIDER_UNAVAILABLE"
    assert data["error"]["retryable"] is False
    assert not data.get("reply")  # no canned text leaked


def test_streaming_emits_sse_events(client, auth_headers, monkeypatch):
    monkeypatch.setattr(cs.chat_service, "gateway",
                        FakeGateway(content="Hello from the model."))
    events = _collect_sse(client, "/api/chat/stream", auth_headers)
    types = [e["type"] for e in events]
    assert "meta" in types and "complete" in types
    chunks = "".join(e.get("content", "") for e in events if e["type"] == "chunk")
    assert "Hello from the model." in chunks


def test_streaming_provider_failure_emits_error_event(client, auth_headers, monkeypatch):
    monkeypatch.setattr(cs.chat_service, "gateway", provider_gateway)
    events = _collect_sse(client, "/api/chat/stream", auth_headers)
    types = [e["type"] for e in events]
    assert "error" in types
    err = next(e for e in events if e["type"] == "error")
    assert err["category"] == "PROVIDER_UNAVAILABLE"


def _collect_sse(client, path, headers):
    events = []
    with client.stream("POST", path, json={"message": "hi"}, headers=headers) as response:
        raw = b"".join(response.iter_bytes())
    body = raw.decode("utf-8", "replace")
    for line in body.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                events.append(json.loads(payload))
    return events


# -- unit-level retry + idempotency (in-process ChatService) ------------------ #
def test_retry_then_completes():
    fake = FlakyGateway()
    svc = cs.ChatService(gateway=fake)
    svc.create_session("u1", "sid-retry", "retry test")
    res = asyncio.run(svc.send_message("u1", "sid-retry", "go"))
    assert res["status"] == "COMPLETED"
    assert res["message"] == "recovered"
    assert fake.calls == 2  # first failed (TIMEOUT), second succeeded


def test_fatal_error_is_not_retried():
    """A non-retryable PROVIDER_UNAVAILABLE must NOT be retried."""

    class OnceGateway:
        calls = 0
        timeout = 30.0
        max_retries = 0

        async def chat(self, messages, model=None, system=None, timeout=None):
            OnceGateway.calls += 1
            raise ChatError(ErrorCategory.PROVIDER_UNAVAILABLE, "no provider",
                            retryable=False)

    svc = cs.ChatService(gateway=OnceGateway())
    svc.create_session("u1", "sid-once", "once test")
    res = asyncio.run(svc.send_message("u1", "sid-once", "go"))
    assert res["status"] == "FAILED"
    assert res["error"]["category"] == "PROVIDER_UNAVAILABLE"
    assert OnceGateway.calls == 1  # raised immediately, no retry


def test_idempotent_resend_returns_cached_reply():
    fake = FakeGateway(content="Hello from the model.")
    svc = cs.ChatService(gateway=fake)
    svc.create_session("u1", "sid-idem", "idempotent test")
    first = asyncio.run(
        svc.send_message("u1", "sid-idem", "hi", client_message_id="cid-1"))
    second = asyncio.run(
        svc.send_message("u1", "sid-idem", "hi", client_message_id="cid-1"))
    assert first["status"] == "COMPLETED"
    assert second["resumed"] is True
    assert second["message"] == "Hello from the model."
    assert fake.calls == 1  # gateway called once; reply reused



# ---------------------------------------------------------------------------
# Self-resilient chat bridge: when the local Silverwing runtime (:8010) is
# unreachable AND a connected cloud provider key is configured, /api/chat
# must fall back to that provider instead of failing. With no cloud key the
# honesty guard still fires (PROVIDER_UNAVAILABLE, never faked).
# ---------------------------------------------------------------------------
def _bridge_runtime_down_exc():
    return ChatError(ErrorCategory.PROVIDER_UNAVAILABLE, "runtime down", retryable=False)


async def _bridge_down(*a, **k):
    raise _bridge_runtime_down_exc()


def test_chat_bridges_to_cloud_when_runtime_down_and_key_configured(client, auth_headers, monkeypatch):
    """Self-resilience: local runtime unreachable + a connected cloud key
    configured -> /api/chat serves the real connected provider (not faked,
    not failed). This is "Jarvis connected as an AI platform"."""
    class _Resp:
        provider = "openai"
        model = "gpt-4o-mini"
        content = "real cloud reply via connected OpenAI"
        latency_ms = 12
        usage = {"prompt_tokens": 2, "completion_tokens": 4, "total_tokens": 6}

    class _Router:
        calls = 0
        async def route_and_chat(self, request, task="chat"):
            _Router.calls += 1
            return (_Resp(), None)

    class _Sw:
        @staticmethod
        def ModelRequest(messages, model, system):
            return {"messages": messages, "model": model, "system": system}

    gw = ProviderGateway(router=_Router())
    monkeypatch.setattr(gw, "_chat_via_model_gateway", _bridge_down)
    monkeypatch.setattr("jarvis_backend.gateway._silverwing_endpoint", lambda: "http://127.0.0.1:8010")
    monkeypatch.setattr("jarvis_backend.gateway._load_silverwing", lambda: _Sw())
    monkeypatch.setattr("jarvis_backend.gateway._has_cloud_key", lambda sw: True)
    monkeypatch.setattr(cs.chat_service, "gateway", gw)

    r = client.post("/api/chat", json={"message": "hi"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "COMPLETED"
    assert data["reply"] == "real cloud reply via connected OpenAI"
    assert data["model"].startswith("openai:")
    assert _Router.calls == 1  # the connected cloud provider was actually used


def test_chat_does_not_bridge_without_a_cloud_key(client, auth_headers, monkeypatch):
    """Runtime down but NO cloud key -> still PROVIDER_UNAVAILABLE (never
    faked, never bridged). Honesty contract preserved."""
    class _Sw:
        @staticmethod
        def ModelRequest(messages, model, system):
            return {}

    class _Router:
        async def route_and_chat(self, request, task="chat"):
            return (None, None)  # should never be reached

    gw = ProviderGateway(router=None)
    monkeypatch.setattr(gw, "_chat_via_model_gateway", _bridge_down)
    monkeypatch.setattr("jarvis_backend.gateway._silverwing_endpoint", lambda: "http://127.0.0.1:8010")
    monkeypatch.setattr("jarvis_backend.gateway._load_silverwing", lambda: _Sw())
    monkeypatch.setattr("jarvis_backend.gateway._has_cloud_key", lambda sw: False)
    monkeypatch.setattr(cs.chat_service, "gateway", gw)

    r = client.post("/api/chat", json={"message": "hi"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "FAILED"
    assert data["error"]["category"] == "PROVIDER_UNAVAILABLE"
    assert not data.get("reply")
