"""JARVIS BRAIN v1 - remote gateway path (Qwen3-4B over OpenAI-compatible HTTP).

Exercises the ``JARVIS_BRAIN_ENDPOINT`` routing introduced in gateway.py:

* primary remote chat path returns real content with honest provenance
  (provider = ``jarvis-brain``, backend = ``remote-openai-compatible``)
* honest fallback: when the brain is unreachable, the request falls back to
  the offline Silverwing runtime and the reply records ``fallback`` docs
* honest rejection: empty / invalid responses are never presented as an answer
* ``probe_brain`` reports healthy only after a real (tiny) inference succeeds

The real ``httpx`` module is monkeypatched so no network is needed.
"""
from __future__ import annotations

from jarvis_backend.errors import ChatError, ErrorCategory
from jarvis_backend.gateway import ProviderGateway


class FakeHttpxClient:
    """Stand-in for httpx.AsyncClient; captures the request and returns a
    canned OpenAI-style response."""

    captured_url = None
    captured_payload = None
    response = None

    def __init__(self, timeout=None, headers=None):
        self.timeout = timeout
        self._hdr = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        # The honesty gate (spec §12) checks /health at the root base before
        # any chat POST; mirror the real runtime's healthy, non-stub payload.
        FakeHttpxClient.captured_url = url
        return FakeHealthResponse()

    async def post(self, url, headers=None, json=None):
        FakeHttpxClient.captured_url = url
        FakeHttpxClient.captured_payload = json
        if isinstance(FakeHttpxClient.response, Exception):
            raise FakeHttpxClient.response
        return FakeHttpxClient.response


class FakeHealthResponse:
    def __init__(self):
        self.status_code = 200
        self.text = ""
        self.elapsed = type(
            "E", (), {"total_seconds": lambda s: 0.001})()

    def json(self):
        return {
            "status": "healthy",
            "available": True,
            "stub": False,
            "model": "jarvis-brain-qwen3-4b-sft-v1",
            "backend": "remote-openai-compatible",
            "device": "gpu-remote",
            "loaded": True,
            "warmup_ok": True,
            "revision": "rev-test",
        }


class FakeResponse:
    def __init__(self, *, status_code=200, content="hello from the brain",
                 latency_ms=87.0, usage=None):
        self.status_code = status_code
        self._content = content
        self._usage = usage or {
            "prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8,
        }
        self.elapsed = type(
            "E", (), {"total_seconds": lambda s: latency_ms / 1000.0})()
        self.text = ""

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "model": "jarvis-brain-qwen3-4b-sft-v1",
            "backend": "remote-openai-compatible",
            "device": "gpu-remote",
            "revision": "rev-test",
            "usage": self._usage,
        }

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                "http error", request=None, response=self)


def _sync_brain_post(url, headers=None, json=None, timeout=None):
    """Stand-in for ``extensions._openai_compatible_post``'s synchronous
    ``httpx.post`` call (the transport the Brain remote tier uses today)."""
    FakeHttpxClient.captured_url = url
    FakeHttpxClient.captured_payload = json
    if isinstance(FakeHttpxClient.response, Exception):
        raise FakeHttpxClient.response
    return FakeHttpxClient.response


def _patch_httpx(monkeypatch, response):
    import jarvis_backend.gateway as gw_mod
    import httpx
    FakeHttpxClient.response = response
    monkeypatch.setattr(httpx, "AsyncClient", FakeHttpxClient)
    monkeypatch.setattr(httpx, "post", _sync_brain_post)
    monkeypatch.setattr(gw_mod, "_jarvis_brain_endpoint",
                        lambda: "https://kaggle.example")
    monkeypatch.setattr(gw_mod, "_silverwing_endpoint", lambda: "")
    # The remote tier requires an upstream credential for the Brain boundary.
    monkeypatch.setenv("JARVIS_BRAIN_API_KEY", "test-brain-key")
    return gw_mod


def _rai():
    return asyncio_get()


def asyncio_get():
    return None


def test_remote_brain_primary_path(monkeypatch):
    """Chat routes to the remote brain and returns real content + provenance."""
    import asyncio
    _patch_httpx(monkeypatch, FakeResponse())
    gw = ProviderGateway(router=None, timeout=30.0)
    result = asyncio.run(gw.chat([{"role": "user", "content": "hi"}]))
    assert result["content"] == "hello from the brain"
    assert result["provider"] == "jarvis-brain"
    assert result["backend"] == "remote-openai-compatible"
    assert result["device"] == "gpu-remote"
    assert result["model"] == "jarvis-brain-qwen3-4b-sft-v1"
    assert FakeHttpxClient.captured_url == "https://kaggle.example/v1/chat/completions"
    # normalised endpoint without /v1 suffix -> appended
    import jarvis_backend.gateway as gw_mod
    monkeypatch.setattr(gw_mod, "_jarvis_brain_endpoint",
                        lambda: "https://kaggle.example")
    asyncio.run(gw.chat([{"role": "user", "content": "hi"}]))
    assert FakeHttpxClient.captured_url == "https://kaggle.example/v1/chat/completions"


def test_remote_brain_honest_fallback(monkeypatch):
    """Brain unreachable + Silverwing runtime up -> fallback reply records the
    fallback provenance honestly (never confuses brain with silverwing)."""
    import asyncio
    _patch_httpx(monkeypatch, FakeResponse())
    gw = ProviderGateway(router=None, timeout=30.0)
    monkeypatch.setenv("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1")

    async def _phase6_unavailable(*args, **kwargs):
        return None

    monkeypatch.setattr(gw, "_chat_via_phase6_fabric", _phase6_unavailable)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    async def _brain_down(*a, **k):
        raise ChatError(ErrorCategory.PROVIDER_UNAVAILABLE, "brain down")

    async def _silverwing_up(*a, **k):
        return {
            "content": "offline silverwing reply",
            "model": "silverwing-120m-base-v1",
            "provider": "silverwing",
            "revision": "r1",
            "backend": "torch",
            "device": "cpu",
            "latency_ms": 10,
            "usage": {},
        }

    monkeypatch.setattr(gw, "_chat_via_remote_brain", _brain_down)
    monkeypatch.setattr(gw, "_chat_via_model_gateway", _silverwing_up)
    import jarvis_backend.gateway as gw_mod
    monkeypatch.setattr(gw_mod, "_silverwing_endpoint",
                        lambda: "http://127.0.0.1:8010")

    result = asyncio.run(gw.chat([{"role": "user", "content": "hi"}]))
    assert result["content"] == "offline silverwing reply"
    assert result["provider"] == "silverwing"
    assert result["fallback"]["from"] == "jarvis-brain-qwen3-4b-v1"
    assert result["fallback"]["to"] == "silverwing-120m-base-v1"


def test_remote_brain_no_fallback_without_silverwing(monkeypatch):
    """Brain unreachable AND no Silverwing runtime -> PROVIDER_UNAVAILABLE,
    never faked."""
    import asyncio
    _patch_httpx(monkeypatch, FakeResponse())
    gw = ProviderGateway(router=None, timeout=30.0)

    async def _phase6_unavailable(*args, **kwargs):
        return None

    monkeypatch.setattr(gw, "_chat_via_phase6_fabric", _phase6_unavailable)
    monkeypatch.setattr("jarvis_backend.gateway._has_cloud_key", lambda _sw: False)

    async def _brain_down(*a, **k):
        raise ChatError(ErrorCategory.PROVIDER_UNAVAILABLE, "brain down")

    monkeypatch.setattr(gw, "_chat_via_remote_brain", _brain_down)

    try:
        asyncio.run(gw.chat([{"role": "user", "content": "hi"}]))
        raised = False
    except ChatError as exc:
        raised = True
        assert exc.category == ErrorCategory.PROVIDER_UNAVAILABLE
    assert raised


def test_remote_brain_empty_reply_rejected(monkeypatch):
    """Empty content from the brain is never a real answer."""
    import asyncio
    _patch_httpx(monkeypatch, FakeResponse(content=""))
    gw = ProviderGateway(router=None, timeout=30.0)
    async def _phase6_unavailable(*args, **kwargs):
        return None

    monkeypatch.setattr(gw, "_chat_via_phase6_fabric", _phase6_unavailable)

    try:
        asyncio.run(gw.chat([{"role": "user", "content": "hi"}]))
        raised = False
    except ChatError as exc:
        raised = True
        assert exc.category == ErrorCategory.PROVIDER_UNAVAILABLE
    assert raised


def test_probe_brain_healthy_after_real_inference(monkeypatch):
    """probe_brain reports healthy only after a real inference succeeds."""
    import asyncio
    _patch_httpx(monkeypatch, FakeResponse(latency_ms=123.0))
    gw = ProviderGateway(router=None, timeout=15.0)
    probe = asyncio.run(gw.probe_brain())
    assert probe["configured"] is True
    assert probe["healthy"] is True
    # latency is the real wall-clock measurement of the probe call, not assumed
    assert probe["latency_ms"] is not None
    # the probe actually hit the model endpoint (not an assumed health)
    assert (FakeHttpxClient.captured_url or "").endswith("/v1/chat/completions")


def test_probe_brain_unhealthy_when_unconfigured(monkeypatch):
    """No JARVIS_BRAIN_ENDPOINT -> configured False, healthy False."""
    import asyncio
    import jarvis_backend.gateway as gw_mod
    monkeypatch.setattr(gw_mod, "_jarvis_brain_endpoint", lambda: "")
    gw = ProviderGateway(router=None, timeout=15.0)
    probe = asyncio.run(gw.probe_brain())
    assert probe["configured"] is False
    assert probe["healthy"] is False