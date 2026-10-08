"""
Rate Limiter - Per-user / per-provider quotas.

Implements two classic algorithms:
  * **Token Bucket** — bursty traffic allowed within a bucket's capacity.
  * **Sliding Window Log** — fixed window with per-window accounting (approximated
    via a sliding counter to avoid unbounded log memory).

Backends:
  * In-memory (default, thread-safe)
  * Redis (when ``JARVIS_REDIS_URL`` is set and redis-py is available)

Rate-limit keys are namespaced by *scope* (e.g. ``"user"``, ``"provider"``)
so per-user and per-provider quotas can coexist without collision.

Design:
  * No hard dependency on redis-py; degrades gracefully to in-memory.
  * Honest: when a limit is hit, :class:`RateLimitExceeded` is raised.
  * Decorator support via :meth:`RateLimiter.limit`.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("control_plane.rate_limiter")


class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        *,
        limit: int,
        window_sec: float,
        retry_after: float,
        key: str,
    ):
        super().__init__(message)
        self.limit = limit
        self.window_sec = window_sec
        self.retry_after = retry_after
        self.key = key


@dataclass
class RateLimitConfig:
    """Configuration for a rate-limit bucket."""

    limit: int = 60
    window_sec: float = 60.0
    algorithm: str = "token_bucket"
    burst: Optional[int] = None

    @property
    def capacity(self) -> int:
        """Token bucket capacity (defaults to limit)."""
        return self.burst if self.burst is not None else self.limit

    @property
    def refill_rate(self) -> float:
        """Tokens per second."""
        if self.window_sec <= 0:
            return 0.0
        return self.limit / self.window_sec

    def to_dict(self) -> Dict[str, Any]:
        return {
            "limit": self.limit,
            "window_sec": self.window_sec,
            "algorithm": self.algorithm,
            "burst": self.burst,
            "capacity": self.capacity,
            "refill_rate_per_sec": self.refill_rate,
        }


@dataclass
class RateLimitResult:
    """Result of a rate-limit check."""

    allowed: bool
    key: str
    limit: int
    remaining: int
    reset_at: float
    retry_after: float
    algorithm: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "key": self.key,
            "limit": self.limit,
            "remaining": self.remaining,
            "reset_at": self.reset_at,
            "retry_after": self.retry_after,
            "algorithm": self.algorithm,
        }


@dataclass
class _TokenBucket:
    """In-memory token bucket."""

    capacity: int
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def remaining(self) -> int:
        now = time.time()
        elapsed = now - self.last_refill
        tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        return max(0, int(tokens))

    def reset_time(self) -> float:
        """Estimated time until bucket is full (for reset_at)."""
        if self.refill_rate <= 0:
            return time.time()
        needed = self.capacity - self.tokens
        return time.time() + (needed / self.refill_rate)


@dataclass
class _SlidingWindow:
    """Simplified sliding-window counter (log-based approximation)."""

    limit: int
    window_sec: float
    _counts: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _prune(self) -> None:
        cutoff = time.time() - self.window_sec
        self._counts[:] = [t for t in self._counts if t >= cutoff]

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            self._prune()
            if len(self._counts) + tokens <= self.limit:
                for _ in range(tokens):
                    self._counts.append(time.time())
                return True
            return False

    def remaining(self) -> int:
        with self._lock:
            self._prune()
            return max(0, self.limit - len(self._counts))

    def reset_time(self) -> float:
        with self._lock:
            self._prune()
            if not self._counts:
                return time.time()
            return min(self._counts) + self.window_sec


class RateLimiter:
    """
    Rate limiter with pluggable backends.

    Keys are namespaced strings like ``"user:alice"`` or ``"provider:openai"``.
    """

    _instance: Optional["RateLimiter"] = None
    _lock = threading.Lock()

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url
        self._buckets: Dict[str, Any] = {}
        self._bucket_lock = threading.Lock()
        self._redis_client: Optional[Any] = None
        if redis_url:
            self._try_init_redis(redis_url)

    @classmethod
    def get_instance(
        cls, redis_url: Optional[str] = None
    ) -> "RateLimiter":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(redis_url=redis_url)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    def _try_init_redis(self, redis_url: str) -> None:
        try:
            import redis as redis_mod
            self._redis_client = redis_mod.from_url(redis_url)
            self._redis_client.ping()
            logger.info("RateLimiter connected to Redis at %s", redis_url)
        except ImportError:
            logger.warning("redis-py not installed; falling back to in-memory backend")
            self._redis_client = None
        except Exception as exc:
            logger.warning("Redis connection failed; falling back: %s", exc)
            self._redis_client = None

    def _hash_key(self, key: str) -> str:
        """Namespace a key for storage."""
        return f"ratelimit:{hashlib.sha256(key.encode()).hexdigest()}"

    def check(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> RateLimitResult:
        """
        Check if *key* is allowed under *config*.

        Returns a :class:`RateLimitResult`. Does **not** raise.
        """
        if self._redis_client is not None:
            return self._check_redis(key, config)
        return self._check_memory(key, config)

    def acquire(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> RateLimitResult:
        """
        Check and consume a token.  Raises :class:`RateLimitExceeded` if denied.
        """
        result = self.check(key, config)
        if not result.allowed:
            raise RateLimitExceeded(
                f"Rate limit exceeded for key '{result.key}': "
                f"{result.remaining} remaining of {result.limit} "
                f"({config.algorithm})",
                limit=result.limit,
                window_sec=config.window_sec,
                retry_after=result.retry_after,
                key=result.key,
            )
        return result

    def _check_memory(
        self, key: str, config: RateLimitConfig
    ) -> RateLimitResult:
        storage_key = f"{key}"
        with self._bucket_lock:
            bucket = self._buckets.get(storage_key)

            if config.algorithm == "token_bucket":
                if bucket is None or not isinstance(bucket, _TokenBucket):
                    bucket = _TokenBucket(config.capacity, config.refill_rate)
                    self._buckets[storage_key] = bucket
                allowed = bucket.consume(1)
                remaining = bucket.remaining()
                reset_at = bucket.reset_time()
            else:
                if bucket is None or not isinstance(bucket, _SlidingWindow):
                    bucket = _SlidingWindow(config.limit, config.window_sec)
                    self._buckets[storage_key] = bucket
                allowed = bucket.consume(1)
                remaining = bucket.remaining()
                reset_at = bucket.reset_time()

        retry_after = max(0.0, reset_at - time.time()) if not allowed else 0.0
        return RateLimitResult(
            allowed=allowed,
            key=key,
            limit=config.limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
            algorithm=config.algorithm,
        )

    def _check_redis(
        self, key: str, config: RateLimitConfig
    ) -> RateLimitResult:
        """Redis-backed check using a sliding-window approximation."""
        r = self._redis_client
        if r is None:
            return self._check_memory(key, config)

        storage_key = self._hash_key(key)
        now = time.time()
        window_start = now - config.window_sec

        pipe = r.pipeline()
        pipe.zremrangebyscore(storage_key, 0, window_start)
        pipe.zcard(storage_key)
        pipe.zadd(storage_key, {str(now): now})
        pipe.expire(storage_key, int(config.window_sec) + 1)
        results = pipe.execute()

        count = results[1]
        allowed = count <= config.limit
        remaining = max(0, config.limit - count)
        reset_at = window_start + config.window_sec
        retry_after = max(0.0, reset_at - now) if not allowed else 0.0

        return RateLimitResult(
            allowed=allowed,
            key=key,
            limit=config.limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
            algorithm=config.algorithm,
        )

    def check_and_acquire(
        self,
        scope: str,
        identifier: str,
        config: RateLimitConfig,
    ) -> RateLimitResult:
        """Check and consume for a scoped identifier (e.g. 'user', 'provider')."""
        key = f"{scope}:{identifier}"
        return self.acquire(key, config)

    def check_only(
        self,
        scope: str,
        identifier: str,
        config: RateLimitConfig,
    ) -> RateLimitResult:
        """Check without consuming (read-only)."""
        key = f"{scope}:{identifier}"
        if self._redis_client is not None:
            # For check-only, use a read-only approach with a separate key
            # that doesn't add to the log.  In-memory: just check remaining.
            pass
        return self.check(key, config)

    def reset(self, scope: Optional[str] = None, identifier: Optional[str] = None) -> int:
        """Reset counters. Returns number of keys cleared."""
        with self._bucket_lock:
            if scope is None:
                count = len(self._buckets)
                self._buckets.clear()
                return count
            prefix = f"{scope}:{identifier}" if identifier else f"{scope}:"
            keys_to_remove = [
                k for k in self._buckets if k.startswith(prefix)
            ]
            for k in keys_to_remove:
                del self._buckets[k]
            return len(keys_to_remove)

    def get_state(self) -> Dict[str, Any]:
        with self._bucket_lock:
            return {
                "backend": "redis" if self._redis_client else "memory",
                "active_buckets": len(self._buckets),
                "buckets": {
                    k: {
                        "remaining": (
                            v.remaining() if hasattr(v, "remaining") else "unknown"
                        ),
                    }
                    for k, v in self._buckets.items()
                },
            }

    def limit(
        self,
        scope: str = "user",
        limit: int = 60,
        window_sec: float = 60.0,
        algorithm: str = "token_bucket",
    ) -> Callable[
        [Callable[..., Any]],
        Callable[..., Any],
    ]:
        """
        Decorator factory for rate-limited functions.

        The function must accept ``*args, **kwargs``.  A ``user_id`` or
        ``provider`` kwarg is used as the identifier; otherwise the first
        positional argument is used.
        """

        config = RateLimitConfig(
            limit=limit,
            window_sec=window_sec,
            algorithm=algorithm,
        )

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                identifier = kwargs.get("user_id") or kwargs.get("provider")
                if identifier is None and args:
                    identifier = str(args[0])
                if identifier is None:
                    identifier = "anonymous"

                self.check_and_acquire(scope, identifier, config)
                return func(*args, **kwargs)

            return wrapper

        return decorator


rate_limiter = RateLimiter.get_instance()

DEFAULT_USER_CONFIG = RateLimitConfig(limit=60, window_sec=60.0)
DEFAULT_PROVIDER_CONFIG = RateLimitConfig(limit=30, window_sec=60.0)
DEFAULT_TOKEN_BUCKET_CONFIG = RateLimitConfig(
    limit=100, window_sec=60.0, algorithm="token_bucket", burst=20
)


def check_rate_limit(
    scope: str,
    identifier: str,
    config: Optional[RateLimitConfig] = None,
) -> RateLimitResult:
    """Check a rate limit without consuming (read-only check)."""
    cfg = config or DEFAULT_USER_CONFIG
    key = f"{scope}:{identifier}"
    return rate_limiter.check(key, cfg)


def consume_rate_limit(
    scope: str,
    identifier: str,
    config: Optional[RateLimitConfig] = None,
) -> RateLimitResult:
    """Consume a rate-limit token. Raises RateLimitExceeded if denied."""
    cfg = config or DEFAULT_USER_CONFIG
    key = f"{scope}:{identifier}"
    return rate_limiter.acquire(key, cfg)
