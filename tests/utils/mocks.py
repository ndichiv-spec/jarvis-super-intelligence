"""Mock providers and services for testing without real infrastructure."""

from __future__ import annotations
import asyncio
import time
import json
from typing import Dict, List, Optional, Any, AsyncIterator, Callable, Awaitable
from dataclasses import dataclass, field
from unittest.mock import MagicMock


class MockAIProvider:
    """Simulates an AI model provider for testing.

    Returns deterministic responses with configurable latency,
    error injection, and token tracking.
    """

    def __init__(self, response_template: str = "Mock answer to: {query}",
                 latency: float = 0.0, fail_on: Optional[List[str]] = None):
        self.response_template = response_template
        self.latency = latency
        self.fail_on = fail_on or []
        self.call_count = 0
        self.call_history: List[Dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs) -> str:
        await self._simulate_latency()
        self.call_count += 1
        self.call_history.append({"prompt": prompt, **kwargs})
        for trigger in self.fail_on:
            if trigger in prompt:
                raise RuntimeError(f"Mock failure triggered by: {trigger}")
        query = prompt[:100]
        return self.response_template.format(query=query)

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        response = await self.generate(prompt, **kwargs)
        for chunk in [response[i:i+10] for i in range(0, len(response), 10)]:
            yield chunk
            await asyncio.sleep(0.001)

    async def embed(self, text: str) -> List[float]:
        await self._simulate_latency()
        self.call_count += 1
        return [hash(text) % 100 / 100.0 for _ in range(384)]

    async def _simulate_latency(self):
        if self.latency > 0:
            await asyncio.sleep(self.latency)


class MockEmbeddingProvider:
    """Produces deterministic embeddings for testing.

    Generates reproducible float vectors from text content
    using simple hashing — NOT for production use.
    """

    def __init__(self, dimension: int = 384, normalize: bool = True):
        self.dimension = dimension
        self.normalize = normalize

    def embed(self, text: str) -> List[float]:
        vec = [hash(f"{text}:{i}") % 1000 / 1000.0 for i in range(self.dimension)]
        if self.normalize:
            mag = sum(x * x for x in vec) ** 0.5
            if mag > 0:
                vec = [x / mag for x in vec]
        return vec

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]

    @property
    def dimension(self) -> int:
        return self._dimension

    @dimension.setter
    def dimension(self, value: int):
        self._dimension = value


class MockLLMProvider:
    """Mock LLM that returns configurable responses.

    Supports template-based answers, error injection,
    streaming simulation, and usage tracking.
    """

    def __init__(self, responses: Optional[Dict[str, str]] = None,
                 default_response: str = "Default mock response."):
        self.responses = responses or {}
        self.default_response = default_response
        self.usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

    async def complete(self, prompt: str, **kwargs) -> str:
        self.usage["prompt_tokens"] += len(prompt) // 4
        for key, resp in self.responses.items():
            if key in prompt:
                self.usage["completion_tokens"] += len(resp) // 4
                return resp
        self.usage["completion_tokens"] += len(self.default_response) // 4
        return self.default_response

    async def complete_stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        response = await self.complete(prompt, **kwargs)
        for token in response.split():
            yield token + " "
            await asyncio.sleep(0.001)


class MockPluginContext:
    """Simulates PluginContext for testing plugins in isolation.

    Provides stubbed permission checks, configuration access,
    and subsystem interfaces without a full plugin runtime.
    """

    def __init__(self, plugin_id: str = "test-plugin",
                 allowed_capabilities: Optional[List[str]] = None,
                 config: Optional[Dict[str, Any]] = None):
        from infrastructure.plugins.types import PluginPermission
        self.plugin_id = plugin_id
        self._allowed = set(allowed_capabilities or [
            PluginPermission.KNOWLEDGE_READ.value,
            PluginPermission.MEMORY_READ.value,
        ])
        self._config = config or {}
        self._http_calls: List[Dict[str, Any]] = []
        self._events_emitted: List[Dict[str, Any]] = []

    def has_permission(self, permission: str) -> bool:
        return permission in self._allowed

    def assert_permission(self, permission: str):
        if not self.has_permission(permission):
            raise PermissionError(f"Missing permission: {permission}")

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    async def http_request(self, method: str, url: str, **kwargs) -> "FakeResponse":
        call = {"method": method, "url": url, **kwargs}
        self._http_calls.append(call)
        return FakeResponse(status_code=200, body={"ok": True})

    async def emit_event(self, event_type: str, data: dict):
        self._events_emitted.append({"type": event_type, "data": data})

    @property
    def calls(self) -> List[Dict[str, Any]]:
        return self._http_calls


class MockAsyncBackend:
    """Simulates an asynchronous storage backend for testing.

    Provides in-memory CRUD with configurable latency and failures.
    """

    def __init__(self, latency: float = 0.0, fail_rate: float = 0.0):
        self._data: Dict[str, Any] = {}
        self.latency = latency
        self.fail_rate = fail_rate
        self.ops: List[str] = []

    async def get(self, key: str) -> Optional[Any]:
        self.ops.append(f"get:{key}")
        await self._maybe_fail()
        await self._delay()
        return self._data.get(key)

    async def set(self, key: str, value: Any) -> bool:
        self.ops.append(f"set:{key}")
        await self._maybe_fail()
        await self._delay()
        self._data[key] = value
        return True

    async def delete(self, key: str) -> bool:
        self.ops.append(f"delete:{key}")
        await self._maybe_fail()
        await self._delay()
        return self._data.pop(key, None) is not None

    async def list_keys(self, prefix: str = "") -> List[str]:
        self.ops.append(f"list:{prefix}")
        await self._delay()
        return [k for k in self._data if k.startswith(prefix)]

    async def _maybe_fail(self):
        if self.fail_rate > 0 and hash(str(time.time())) % 100 < self.fail_rate * 100:
            raise ConnectionError("Simulated backend failure")

    async def _delay(self):
        if self.latency > 0:
            await asyncio.sleep(self.latency)


class FakeResponse:
    """Drop-in replacement for httpx.Response / aiohttp.Response for testing."""

    def __init__(self, status_code: int = 200, body: Any = None,
                 headers: Optional[Dict[str, str]] = None,
                 json_data: Optional[dict] = None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self._json_data = json_data

    def json(self) -> Any:
        return self._json_data or {"status": "ok"}

    @property
    def text(self) -> str:
        return str(self._body) if self._body else ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
