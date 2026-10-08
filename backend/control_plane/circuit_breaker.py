"""
Circuit Breaker Pattern - Graceful degradation for dependent services.

Implements the classic circuit-breaker state machine (CLOSED → OPEN → HALF_OPEN →
CLOSED) with configurable failure thresholds, recovery timeout, and half-open
probe count.  When a service is unavailable the breaker opens so requests fail
fast instead of hanging or cascading.

Inspired by:
  * Microsoft resilience/circuitbreaker (Polly pattern)
  * Resilience4j CircuitBreaker

Design:
  * Thread-safe (uses threading.Lock)
  * Callable decorator for wrapping service calls
  * Registry for per-service breakers
  * No external dependencies (psycopg/redis optional)
  * Honest: when OPEN, raises CircuitBreakerOpen rather than fabricating a response.
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("control_plane.circuit_breaker")


class CircuitState(str, Enum):
    """States of the circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker events."""

    def __init__(self, message: str, *, circuit_id: str = ""):
        super().__init__(message)
        self.circuit_id = circuit_id


class CircuitBreakerOpen(CircuitBreakerError):
    """Raised when the circuit is OPEN and the call is rejected."""


class CircuitBreakerTimeout(CircuitBreakerError):
    """Raised when the wrapped call times out."""


@dataclass
class CircuitBreakerConfig:
    """Configuration for a :class:`CircuitBreaker`."""

    failure_threshold: int = 5
    recovery_timeout_sec: float = 30.0
    half_open_max_calls: int = 3
    failure_window_sec: float = 60.0
    timeout_sec: Optional[float] = 10.0
    exception_types: tuple = (Exception,)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_sec": self.recovery_timeout_sec,
            "half_open_max_calls": self.half_open_max_calls,
            "failure_window_sec": self.failure_window_sec,
            "timeout_sec": self.timeout_sec,
            "exception_types": [
                e.__name__ for e in self.exception_types
            ],
        }


@dataclass
class CircuitBreakerStats:
    """Runtime statistics for a circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    total_trip_count: int = 0
    last_failure_time: Optional[float] = None
    last_failure_reason: Optional[str] = None
    last_failure_type: Optional[str] = None
    opened_at: Optional[float] = None
    half_open_successes: int = 0
    half_open_failures: int = 0
    total_calls: int = 0

    def to_dict(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_trip_count": self.total_trip_count,
            "last_failure_time": self.last_failure_time,
            "last_failure_reason": self.last_failure_reason,
            "last_failure_type": self.last_failure_type,
            "opened_at": self.opened_at,
            "time_since_open": now - self.opened_at if self.opened_at else None,
            "half_open_successes": self.half_open_successes,
            "half_open_failures": self.half_open_failures,
            "total_calls": self.total_calls,
            "current_failure_rate": (
                self.failure_count / max(self.total_calls, 1)
            ),
        }


class CircuitBreaker:
    """
    A thread-safe circuit breaker wrapping a callable.

    Usage::

        breaker = CircuitBreaker("my-service")
        result = breaker.call(my_function, arg1, kwarg1=val)

    Or as a decorator::

        @breaker.with_circuit_breaker
        def my_function(...):
            ...
    """

    def __init__(self, circuit_id: str, config: Optional[CircuitBreakerConfig] = None):
        self.circuit_id = circuit_id
        self.config = config or CircuitBreakerConfig()
        self._stats = CircuitBreakerStats()
        self._lock = threading.RLock()  # reentrant: _allow_request calls sub-methods that also lock
        self._recent_failures: list = []

    @property
    def stats(self) -> CircuitBreakerStats:
        return self._stats

    @property
    def state(self) -> CircuitState:
        return self._stats.state

    def _prune_old_failures(self) -> None:
        """Remove failures outside the failure window."""
        cutoff = time.time() - self.config.failure_window_sec
        self._recent_failures = [
            t for t in self._recent_failures if t >= cutoff
        ]

    def _should_trip(self) -> bool:
        """Check if the circuit should trip to OPEN."""
        with self._lock:
            self._prune_old_failures()
            return len(self._recent_failures) >= self.config.failure_threshold

    def _record_failure(self, exc: Optional[Exception] = None) -> None:
        with self._lock:
            self._stats.failure_count += 1
            self._stats.total_trip_count = self._stats.failure_count
            self._stats.last_failure_time = time.time()
            self._stats.last_failure_type = (
                type(exc).__name__ if exc else "unknown"
            )
            self._stats.last_failure_reason = str(exc) if exc else "unknown"
            self._recent_failures.append(time.time())
            self._stats.total_calls += 1

    def _record_success(self) -> None:
        with self._lock:
            self._stats.success_count += 1
            self._stats.total_calls += 1

    def _transition_to_open(self) -> None:
        with self._lock:
            if self._stats.state == CircuitState.OPEN:
                return
            self._stats.state = CircuitState.OPEN
            self._stats.opened_at = time.time()
            self._stats.half_open_successes = 0
            self._stats.half_open_failures = 0
            logger.warning(
                "Circuit '%s' OPENED due to %d failures in %.1fs. "
                "Opened at %s. Recovery timeout: %.1fs",
                self.circuit_id,
                len(self._recent_failures),
                self.config.failure_window_sec,
                self._stats.opened_at,
                self.config.recovery_timeout_sec,
            )

    def _try_half_open(self) -> bool:
        """Attempt transition to HALF_OPEN. Returns True if transitioned."""
        with self._lock:
            if self._stats.state != CircuitState.OPEN:
                return False
            if self._stats.opened_at is None:
                return False
            elapsed = time.time() - self._stats.opened_at
            if elapsed >= self.config.recovery_timeout_sec:
                self._stats.state = CircuitState.HALF_OPEN
                self._stats.half_open_successes = 0
                self._stats.half_open_failures = 0
                logger.info("Circuit '%s' -> HALF_OPEN (recovery timeout elapsed)", self.circuit_id)
                return True
            return False

    def _transition_to_closed(self) -> None:
        with self._lock:
            if self._stats.state == CircuitState.CLOSED:
                return
            self._stats.state = CircuitState.CLOSED
            self._stats.opened_at = None
            self._stats.half_open_successes = 0
            self._stats.half_open_failures = 0
            self._recent_failures = []
            logger.info("Circuit '%s' CLOSED (recovered)", self.circuit_id)

    def _allow_request(self) -> bool:
        """Check if a request should be allowed, transitioning if needed."""
        with self._lock:
            state = self._stats.state

            if state == CircuitState.CLOSED:
                return True

            if state == CircuitState.OPEN:
                if self._try_half_open():
                    return True
                return False

            # HALF_OPEN
            if (
                self._stats.half_open_successes
                + self._stats.half_open_failures
                >= self.config.half_open_max_calls
            ):
                return False
            return True

    def _on_success(self) -> None:
        with self._lock:
            if self._stats.state == CircuitState.HALF_OPEN:
                self._stats.half_open_successes += 1
                if self._stats.half_open_successes >= self.config.half_open_max_calls:
                    self._transition_to_closed()
            else:
                self._transition_to_closed()
            self._record_success()

    def _on_failure(self, exc: Optional[Exception] = None) -> None:
        with self._lock:
            if self._stats.state == CircuitState.HALF_OPEN:
                self._stats.half_open_failures += 1
                self._transition_to_open()
            else:
                self._record_failure(exc)
                if self._should_trip():
                    self._transition_to_open()

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute *func* with circuit-breaker protection.

        Raises :class:`CircuitBreakerOpen` if the circuit is OPEN.
        Re-raises the original exception on failure.
        """
        if not self._allow_request():
            raise CircuitBreakerOpen(
                f"Circuit '{self.circuit_id}' is OPEN",
                circuit_id=self.circuit_id,
            )

        start = time.time()
        try:
            if self.config.timeout_sec is not None:
                import threading as _t

                result: list = []
                exc_box: list = []

                def _target() -> None:
                    try:
                        result.append(func(*args, **kwargs))
                    except BaseException as e:
                        exc_box.append(e)

                thread = _t.Thread(target=_target, daemon=True)
                thread.start()
                thread.join(timeout=self.config.timeout_sec)

                if thread.is_alive():
                    self._on_failure(CircuitBreakerTimeout(
                        f"Timeout after {self.config.timeout_sec}s",
                        circuit_id=self.circuit_id,
                    ))
                    raise CircuitBreakerTimeout(
                        f"Call to '{self.circuit_id}' timed out after "
                        f"{self.config.timeout_sec}s",
                        circuit_id=self.circuit_id,
                    )

                if exc_box:
                    exc = exc_box[0]
                    raise exc

                value = result[0] if result else None
            else:
                value = func(*args, **kwargs)

            self._on_success()
            return value

        except self.config.exception_types as exc:
            self._on_failure(exc)
            raise
        except CircuitBreakerOpen:
            raise
        except CircuitBreakerTimeout:
            self._on_failure(None)
            raise
        except Exception:
            raise

    def with_circuit_breaker(
        self, func: Callable[..., Any]
    ) -> Callable[..., Any]:
        """Decorator that wraps *func* with this circuit breaker."""

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.call(func, *args, **kwargs)

        return wrapper

    def trip_manually(self, reason: str = "manual") -> None:
        """Force the circuit into OPEN state (admin action)."""
        with self._lock:
            self._stats.state = CircuitState.OPEN
            self._stats.opened_at = time.time()
            self._stats.last_failure_reason = reason
            self._stats.total_trip_count += 1
        logger.warning("Circuit '%s' manually tripped: %s", self.circuit_id, reason)

    def reset(self) -> None:
        """Reset the circuit to CLOSED with zeroed stats."""
        with self._lock:
            self._stats = CircuitBreakerStats()
            self._recent_failures = []
        logger.info("Circuit '%s' reset", self.circuit_id)

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit state and stats."""
        return self.stats.to_dict()


class CircuitBreakerRegistry:
    """Registry for managing per-service circuit breakers."""

    _instance: Optional["CircuitBreakerRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}

    @classmethod
    def get_instance(cls) -> "CircuitBreakerRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    def register(
        self,
        circuit_id: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        breaker = self._breakers.get(circuit_id)
        if breaker is None:
            breaker = CircuitBreaker(circuit_id, config)
            self._breakers[circuit_id] = breaker
        elif config is not None:
            breaker.config = config
        return breaker

    def get(self, circuit_id: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(circuit_id)

    def get_or_create(
        self, circuit_id: str, config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        breaker = self.get(circuit_id)
        if breaker is None:
            return self.register(circuit_id, config)
        return breaker

    def get_all_state(self) -> Dict[str, Dict[str, Any]]:
        return {
            cid: b.get_state() for cid, b in self._breakers.items()
        }

    def reset(self, circuit_id: Optional[str] = None) -> None:
        if circuit_id is None:
            self._breakers.clear()
        else:
            breaker = self._breakers.pop(circuit_id, None)
            if breaker:
                breaker.reset()

    def is_available(self, circuit_id: str) -> bool:
        """Check if a service is available (circuit not OPEN)."""
        breaker = self.get(circuit_id)
        if breaker is None:
            return True
        return breaker.state != CircuitState.OPEN


circuit_breaker_registry = CircuitBreakerRegistry.get_instance()

DEFAULT_CONFIG = CircuitBreakerConfig()


def get_circuit_breaker(
    circuit_id: str, config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """Get or create a circuit breaker by service ID."""
    return circuit_breaker_registry.get_or_create(circuit_id, config)
