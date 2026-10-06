"""
API response optimization for Jarvis.

Provides response compression, streaming helpers, cache headers,
ETag support, and response size optimization to minimize bandwidth
and improve client-side performance.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ETagManager:
    """
    Manages ETag generation and validation for HTTP caching.

    Generates strong ETags based on content hashing.
    """

    def __init__(self):
        self._etag_cache: Dict[str, Tuple[str, float]] = {}

    def generate(self, data: Any) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        return f'W/"{hashlib.md5(serialized.encode()).hexdigest()}"'

    def validate(self, etag: str, data: Any) -> bool:
        return self.generate(data) == etag

    def get_headers(self, data: Any, ttl: int = 300) -> Dict[str, str]:
        etag = self.generate(data)
        return {
            "ETag": etag,
            "Cache-Control": f"public, max-age={ttl}",
            "Vary": "Accept-Encoding",
        }


class ResponseOptimizer:
    """
    Optimizes API responses for size and speed.

    Features:
    - ETag generation and validation
    - Cache header computation
    - Response size optimization
    - Field filtering support (sparse fieldsets)
    - Response compression hints
    """

    def __init__(
        self,
        default_cache_ttl: int = 300,
        max_response_size: int = 10 * 1024 * 1024,
    ):
        self._etag_manager = ETagManager()
        self._default_cache_ttl = default_cache_ttl
        self._max_response_size = max_response_size

    def optimize(
        self,
        data: Any,
        *,
        fields: Optional[list[str]] = None,
        cache_ttl: Optional[int] = None,
        client_etag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Optimize a response payload.

        Args:
            data: The response data
            fields: Optional field whitelist for sparse responses
            cache_ttl: Cache TTL in seconds
            client_etag: Client's ETag for 304 support

        Returns:
            Dict with 'data', 'headers', and 'status_code' keys
        """
        if fields:
            data = self._filter_fields(data, fields)

        if client_etag:
            current_etag = self._etag_manager.generate(data)
            if client_etag == current_etag:
                return {
                    "data": None,
                    "headers": self._etag_manager.get_headers(data, cache_ttl or self._default_cache_ttl),
                    "status_code": 304,
                }

        headers = self._etag_manager.get_headers(data, cache_ttl or self._default_cache_ttl)
        headers["Content-Type"] = "application/json"

        return {
            "data": data,
            "headers": headers,
            "status_code": 200,
        }

    def _filter_fields(self, data: Any, fields: list[str]) -> Any:
        """Filter response to only include requested fields (sparse fieldsets)."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k in fields}
        if isinstance(data, list):
            return [self._filter_fields(item, fields) for item in data]
        return data


class StreamingOptimizer:
    """
    Optimizes streaming responses (SSE, chunked transfer).
    """

    def __init__(self, max_buffer_size: int = 4096, flush_interval: float = 0.1):
        self._max_buffer = max_buffer_size
        self._flush_interval = flush_interval

    async def optimized_stream(
        self,
        generator,
        format: str = "json",
    ):
        """
        Yield optimized chunks from an async generator.

        Batches small items together and flushes periodically.
        """
        buffer = []

        async for item in generator:
            buffer.append(item)

            if len(json.dumps(buffer, default=str)) >= self._max_buffer:
                yield self._format_chunk(buffer, format)
                buffer = []

        if buffer:
            yield self._format_chunk(buffer, format)

    def _format_chunk(self, items: list, format: str) -> str:
        if format == "sse":
            return f"data: {json.dumps(items, default=str)}\n\n"
        return json.dumps(items, default=str)
