"""
Rate limiting subsystem.

Provides:
  - Token bucket algorithm for per-client rate limiting
  - Sliding window counter for aggregate rate limiting
  - In-memory and Redis-backed implementations
"""

import os
import time
import json
import hashlib
import asyncio
import threading
from typing import Dict, Optional, Tuple, Callable, Any
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class TokenBucket:
    """Token bucket rate limiter (per-client)."""
    capacity: int
    refill_rate: float
    tokens: float = 0
    last_refill: float = field(default_factory=time.time)

    def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def remaining(self) -> float:
        now = time.time()
        elapsed = now - self.last_refill
        return min(self.capacity, self.tokens + elapsed * self.refill_rate)


@dataclass
class SlidingWindowEntry:
    count: int = 0
    window_start: float = field(default_factory=time.time)


class SlidingWindowCounter:
    """Sliding window counter for aggregate rate limiting."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._entries: Dict[str, SlidingWindowEntry] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, weight: int = 1) -> bool:
        now = time.time()
        with self._lock:
            if key not in self._entries:
                self._entries[key] = SlidingWindowEntry()
            entry = self._entries[key]

            if now - entry.window_start > self.window_seconds:
                entry.window_start = now
                entry.count = 0

            entry.count += weight
            if entry.count > self.max_requests:
                entry.count -= weight
                return False
            return True

    def remaining(self, key: str) -> int:
        with self._lock:
            if key not in self._entries:
                return self.max_requests
            entry = self._entries[key]
            now = time.time()
            if now - entry.window_start > self.window_seconds:
                return self.max_requests
            return max(0, self.max_requests - entry.count)

    def reset(self, key: str):
        with self._lock:
            self._entries.pop(key, None)


class RateLimitResult:
    def __init__(self, allowed: bool, remaining: int, reset_after: float, retry_after: float = 0):
        self.allowed = allowed
        self.remaining = remaining
        self.reset_after = reset_after
        self.retry_after = retry_after

    def to_headers(self) -> Dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.remaining + (1 if self.allowed else 0)),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(time.time() + self.reset_after)),
        }


class RateLimiter:
    """
    Multi-strategy rate limiter.

    Supports per-IP, per-user, per-endpoint rate limiting with configurable limits.
    """

    def __init__(self, default_limit: int = 100, window_seconds: float = 60.0,
                 backend: str = "memory"):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.backend = backend
        self._buckets: Dict[str, TokenBucket] = {}
        self._counters: Dict[str, SlidingWindowCounter] = {}
        self._lock = threading.Lock()

    def _key(self, client_id: str, endpoint: str = "") -> str:
        return hashlib.sha256(f"{client_id}:{endpoint}".encode()).hexdigest()

    def check(self, client_id: str, endpoint: str = "",
              limit: Optional[int] = None) -> RateLimitResult:
        eff_limit = limit or self.default_limit
        key = self._key(client_id, endpoint)

        with self._lock:
            if key not in self._counters:
                self._counters[key] = SlidingWindowCounter(eff_limit, self.window_seconds)

            counter = self._counters[key]
            allowed = counter.allow(key)
            remaining = counter.remaining(key)
            now = time.time()
            reset_after = (counter._entries[key].window_start + self.window_seconds - now
                           if key in counter._entries else 0)

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_after=max(0, reset_after),
                retry_after=max(0, reset_after) if not allowed else 0,
            )

    def check_bucket(self, client_id: str, tokens: int = 1,
                     capacity: int = 10, refill_rate: float = 1.0) -> bool:
        key = f"bucket:{self._key(client_id)}"
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(capacity=capacity, refill_rate=refill_rate)
            return self._buckets[key].consume(tokens)

    def reset(self, client_id: str, endpoint: str = ""):
        key = self._key(client_id, endpoint)
        with self._lock:
            self._counters.pop(key, None)

    def middleware(self, app: Callable) -> Callable:
        """ASGI middleware wrapper for rate limiting."""
        async def rate_limited_app(scope: Dict[str, Any], receive: Callable, send: Callable):
            if scope["type"] != "http":
                await app(scope, receive, send)
                return

            client_ip = "unknown"
            headers = dict(scope.get("headers", []))
            for header_name in [b"x-forwarded-for", b"x-real-ip", b"remote-addr"]:
                if header_name in headers:
                    client_ip = headers[header_name].decode().split(",")[0].strip()
                    break

            path = scope.get("path", "")
            result = self.check(client_ip, path)

            if not result.allowed:
                body = json.dumps({
                    "error": "rate_limit_exceeded",
                    "detail": f"Rate limit exceeded. Retry after {result.retry_after:.0f}s",
                }).encode()
                headers = [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(int(result.retry_after)).encode()),
                ]
                for k, v in result.to_headers().items():
                    headers.append((k.encode(), v.encode()))
                await send({
                    "type": "http.response.start",
                    "status": 429,
                    "headers": headers,
                })
                await send({"type": "http.response.body", "body": body})
                return

            await app(scope, receive, send)

        return rate_limited_app
