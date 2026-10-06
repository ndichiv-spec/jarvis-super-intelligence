"""
Circuit breaker pattern implementation.

Prevents cascading failures by stopping calls to a failing service
when the error rate exceeds a threshold. Supports half-open state
for automatic recovery detection.
"""

import time
import asyncio
import threading
import logging
from enum import Enum
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""
    pass


@dataclass
class CircuitBreakerStats:
    total_calls: int = 0
    failed_calls: int = 0
    success_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state: CircuitState = CircuitState.CLOSED

    @property
    def failure_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.failed_calls / self.total_calls

    def reset(self):
        self.total_calls = 0
        self.failed_calls = 0
        self.success_calls = 0
        self.last_failure_time = None
        self.last_success_time = None


class CircuitBreaker:
    """
    Circuit breaker with configurable thresholds.

    States:
      CLOSED   - requests pass through normally
      OPEN     - requests are rejected immediately
      HALF_OPEN - limited requests allowed to test recovery

    Usage:
        breaker = CircuitBreaker("openai", failure_threshold=5, recovery_timeout=30)

        async with breaker:
            result = await call_openai()

        # Or:
        result = await breaker.call(call_openai)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._lock = asyncio.Lock() if hasattr(asyncio, "Lock") else threading.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        return self._stats

    async def call(self, fn: Callable, *args, **kwargs) -> Any:
        """Execute a call through the circuit breaker."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - (self._stats.last_failure_time or 0) > self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._half_open_successes = 0
                else:
                    raise CircuitOpenError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Failure rate: {self._stats.failure_rate:.1%}"
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitOpenError(
                        f"Circuit breaker '{self.name}' is HALF_OPEN and at capacity"
                    )
                self._half_open_calls += 1

        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = fn(*args, **kwargs)
        except Exception as e:
            await self._on_failure()
            raise

        await self._on_success()
        return result

    async def _on_success(self):
        async with self._lock:
            self._stats.total_calls += 1
            self._stats.success_calls += 1
            self._stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.success_threshold:
                    logger.info(f"Circuit breaker '{self.name}' recovered, closing")
                    self._state = CircuitState.CLOSED
                    self._stats.reset()

    async def _on_failure(self):
        async with self._lock:
            self._stats.total_calls += 1
            self._stats.failed_calls += 1
            self._stats.last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit breaker '{self.name}' half-open call failed, reopening")
                self._state = CircuitState.OPEN
                return

            if self._stats.failure_rate >= 0.5 and self._stats.failed_calls >= self.failure_threshold:
                logger.warning(
                    f"Circuit breaker '{self.name}' opening. "
                    f"Failed {self._stats.failed_calls}/{self._stats.total_calls} calls"
                )
                self._state = CircuitState.OPEN

    def reset(self):
        self._state = CircuitState.CLOSED
        self._stats.reset()
        self._half_open_calls = 0
        self._half_open_successes = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self._state.value,
            "stats": {
                "total_calls": self._stats.total_calls,
                "failed_calls": self._stats.failed_calls,
                "success_calls": self._stats.success_calls,
                "failure_rate": round(self._stats.failure_rate, 4),
            },
            "config": {
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "half_open_max_calls": self.half_open_max_calls,
                "success_threshold": self.success_threshold,
            },
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and exc_type is not CircuitOpenError:
            await self._on_failure()
            return False
        if exc_type is None:
            await self._on_success()
        return exc_type is CircuitOpenError
