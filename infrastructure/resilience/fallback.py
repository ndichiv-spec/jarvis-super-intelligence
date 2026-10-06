"""
Graceful degradation and fallback handling.

Provides:
  - Fallback chains (try primary, then secondary, then tertiary)
  - Degradation policies (what to degrade when dependencies fail)
  - Stale cache fallback (serve stale data when fresh unavailable)
"""

import time
import asyncio
import logging
from typing import Callable, Any, Optional, List, Tuple, Type, Dict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DegradationLevel(Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    LIMITED = "limited"
    OFFLINE = "offline"


@dataclass
class FallbackResult:
    success: bool
    value: Any = None
    error: Optional[str] = None
    provider: str = ""
    duration_ms: float = 0.0


class FallbackProvider:
    """A single fallback provider with metadata."""

    def __init__(self, name: str, fn: Callable, timeout: float = 30.0,
                 is_async: Optional[bool] = None):
        self.name = name
        self.fn = fn
        self.timeout = timeout
        self.is_async = is_async if is_async is not None else asyncio.iscoroutinefunction(fn)


class FallbackChain:
    """
    Chain of fallback providers. Tries primary; if it fails, tries secondary, etc.

    Usage:
        chain = FallbackChain([
            FallbackProvider("primary", call_primary),
            FallbackProvider("cache", call_cache),
            FallbackProvider("default", lambda: "fallback response"),
        ])
        result = await chain.execute()
    """

    def __init__(self, providers: List[FallbackProvider],
                 break_on: Optional[Tuple[Type[Exception], ...]] = None):
        self.providers = providers
        self.break_on = break_on or ()

    async def execute(self, *args, **kwargs) -> FallbackResult:
        last_error: Optional[str] = None

        for provider in self.providers:
            try:
                start = time.time()
                if provider.is_async:
                    result = await asyncio.wait_for(
                        provider.fn(*args, **kwargs), timeout=provider.timeout
                    )
                else:
                    result = provider.fn(*args, **kwargs)
                duration = (time.time() - start) * 1000

                return FallbackResult(
                    success=True,
                    value=result,
                    provider=provider.name,
                    duration_ms=duration,
                )
            except asyncio.TimeoutError:
                last_error = f"Provider '{provider.name}' timed out after {provider.timeout}s"
                logger.warning(last_error)
            except Exception as e:
                if isinstance(e, self.break_on):
                    raise
                last_error = f"Provider '{provider.name}' failed: {e}"
                logger.warning(last_error)

        return FallbackResult(
            success=False,
            error=last_error or "All fallback providers failed",
        )


class DegradationPolicy:
    """
    Determines what level of degradation is acceptable for a given operation.

    Usage:
        policy = DegradationPolicy()
        policy.register("ai_completion", DegradationLevel.DEGRADED, fallback="use_cache")
        level = policy.get_level("ai_completion")
    """

    def __init__(self, default_level: DegradationLevel = DegradationLevel.NORMAL):
        self.default_level = default_level
        self._policies: Dict[str, DegradationLevel] = {}
        self._fallbacks: Dict[str, str] = {}

    def register(self, operation: str, level: DegradationLevel, fallback: str = ""):
        self._policies[operation] = level
        if fallback:
            self._fallbacks[operation] = fallback

    def get_level(self, operation: str) -> DegradationLevel:
        return self._policies.get(operation, self.default_level)

    def get_fallback(self, operation: str) -> str:
        return self._fallbacks.get(operation, "")

    def degrade(self, operation: str) -> DegradationLevel:
        """Increase degradation level for an operation."""
        current = self.get_level(operation)
        levels = list(DegradationLevel)
        idx = levels.index(current)
        if idx < len(levels) - 1:
            new_level = levels[idx + 1]
            self._policies[operation] = new_level
        return self.get_level(operation)

    def recover(self, operation: str):
        """Reset degradation level to normal."""
        self._policies[operation] = DegradationLevel.NORMAL


class StaleCacheFallback:
    """
    Serve stale cached data when the primary source is unavailable.

    Usage:
        cache_fallback = StaleCacheFallback(ttl=300, max_stale_age=3600)

        async def get_data():
            if cached := cache_fallback.get_cached("key"):
                return cached.value
            fresh = await fetch_from_api()
            cache_fallback.set("key", fresh)
            return fresh
    """

    def __init__(self, ttl: float = 300.0, max_stale_age: float = 3600.0):
        self.ttl = ttl
        self.max_stale_age = max_stale_age
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        age = time.time() - self._timestamps.get(key, 0)
        if age > self.max_stale_age:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            return None
        return self._cache[key]

    def get_stale(self, key: str) -> Optional[Any]:
        """Get even stale data (within max_stale_age)."""
        if key not in self._cache:
            return None
        age = time.time() - self._timestamps.get(key, 0)
        if age > self.max_stale_age:
            return None
        return self._cache[key]

    def is_fresh(self, key: str) -> bool:
        if key not in self._cache:
            return False
        return (time.time() - self._timestamps.get(key, 0)) < self.ttl

    def set(self, key: str, value: Any):
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def invalidate(self, key: str):
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

    def clear(self):
        self._cache.clear()
        self._timestamps.clear()
