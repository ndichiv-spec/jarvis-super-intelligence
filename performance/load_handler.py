"""
Graceful load handling and backpressure for Jarvis.

Provides load shedding, backpressure mechanisms, and graceful degradation
to prevent system overload and maintain responsiveness under high load.
Integrates with circuit breakers and resource pools.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Awaitable

from performance.concurrency import TokenBucket, AdaptiveConcurrency, AtomicCounter

logger = logging.getLogger(__name__)


class LoadLevel(Enum):
    NORMAL = auto()
    WARNING = auto()
    CRITICAL = auto()
    OVERLOADED = auto()


class ShedStrategy(Enum):
    DROP_NEWEST = auto()
    DROP_LOWEST_PRIORITY = auto()
    DROP_RANDOM = auto()
    RETURN_STALE = auto()
    QUEUE_AND_DEGRADE = auto()


@dataclass
class LoadMetrics:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    active_requests: int = 0
    queue_depth: int = 0
    response_time_p99: float = 0.0
    error_rate: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def level(self) -> LoadLevel:
        score = 0
        if self.cpu_percent > 80:
            score += 1
        if self.cpu_percent > 95:
            score += 2
        if self.memory_percent > 80:
            score += 1
        if self.memory_percent > 95:
            score += 2
        if self.active_requests > 100:
            score += 1
        if self.response_time_p99 > 5000:
            score += 1
        if self.error_rate > 0.05:
            score += 1

        if score >= 5:
            return LoadLevel.OVERLOADED
        if score >= 3:
            return LoadLevel.CRITICAL
        if score >= 1:
            return LoadLevel.WARNING
        return LoadLevel.NORMAL


class LoadShedder:
    """
    Implements load shedding strategies to protect system resources.

    Features:
    - Multiple shedding strategies (drop, queue, degrade)
    - Priority-based request handling
    - Integration with resource pools and circuit breakers
    - Graceful degradation callbacks
    - Request queuing with bounded size and TTL
    """

    def __init__(
        self,
        max_queue_size: int = 100,
        queue_ttl: float = 30.0,
        strategy: ShedStrategy = ShedStrategy.QUEUE_AND_DEGRADE,
        degradation_callbacks: Optional[List[Callable[[], Awaitable[None]]]] = None,
    ):
        self._max_queue_size = max_queue_size
        self._queue_ttl = queue_ttl
        self._strategy = strategy
        self._degradation_callbacks = degradation_callbacks or []

        self._request_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._active_requests = AtomicCounter()
        self._shed_requests = AtomicCounter()
        self._queue_workers: Set[asyncio.Task] = set()
        self._running = False
        self._current_strategy = strategy
        self._metrics = LoadMetrics()

    async def start(self):
        """Start background queue processing."""
        self._running = True
        worker = asyncio.create_task(self._queue_worker())
        self._queue_workers.add(worker)
        logger.info("Load shedder started")

    async def stop(self):
        """Stop queue processing."""
        self._running = False
        for worker in self._queue_workers:
            worker.cancel()
        await asyncio.gather(*self._queue_workers, return_exceptions=True)
        self._queue_workers.clear()

    async def execute_or_shed(
        self,
        coro: Callable[[], Awaitable[Any]],
        priority: int = 0,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Execute a request or shed it if the system is overloaded.

        Returns the result if executed, raises LoadShedError if shed.
        """
        level = self._metrics.level

        if level == LoadLevel.OVERLOADED and priority < 1:
            await self._shed_requests.inc()
            raise LoadShedError("System overloaded, request shed")

        if level == LoadLevel.CRITICAL and self._strategy == ShedStrategy.DROP_LOWEST_PRIORITY and priority < 3:
            await self._shed_requests.inc()
            raise LoadShedError("Critical load, low-priority request shed")

        return await self._execute_with_queue(coro, priority=priority, timeout=timeout)

    async def update_metrics(self, metrics: LoadMetrics):
        """Update current load metrics."""
        self._metrics = metrics

        if metrics.level in (LoadLevel.CRITICAL, LoadLevel.OVERLOADED):
            for cb in self._degradation_callbacks:
                try:
                    await cb()
                except Exception as e:
                    logger.warning("Degradation callback error: %s", e)

    async def get_shed_count(self) -> int:
        return await self._shed_requests.get()

    async def get_active_count(self) -> int:
        return await self._active_requests.get()

    async def _execute_with_queue(
        self,
        coro: Callable[[], Awaitable[Any]],
        priority: int = 0,
        timeout: Optional[float] = None,
    ) -> Any:
        """Execute a request, queuing if necessary."""
        await self._active_requests.inc()

        try:
            if timeout:
                return await asyncio.wait_for(coro(), timeout=timeout)
            return await coro()
        finally:
            await self._active_requests.dec()

    async def _queue_worker(self):
        """Background worker for queued requests."""
        while self._running:
            try:
                item = await asyncio.wait_for(
                    self._request_queue.get(), timeout=1.0
                )
                coro, future, priority, timeout = item
                try:
                    result = await self._execute_with_queue(coro, priority, timeout)
                    if not future.done():
                        future.set_result(result)
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)
            except asyncio.TimeoutError:
                continue


class LoadShedError(Exception):
    """Raised when a request is shed due to system overload."""


class CircuitBreakerIntegrator:
    """
    Integrates circuit breaker patterns with load handling.

    Automatically adjusts circuit breaker thresholds based on
    system load levels.
    """

    def __init__(
        self,
        base_failure_threshold: int = 5,
        base_recovery_timeout: float = 30.0,
    ):
        self._base_failure = base_failure_threshold
        self._base_recovery = base_recovery_timeout
        self._circuit_breakers: Dict[str, Any] = {}

    def register(self, name: str, circuit_breaker: Any):
        self._circuit_breakers[name] = circuit_breaker

    async def adjust_for_load(self, level: LoadLevel):
        """Adjust circuit breaker thresholds based on load level."""
        if level == LoadLevel.OVERLOADED:
            for cb in self._circuit_breakers.values():
                cb.failure_threshold = max(2, self._base_failure // 2)
                cb.recovery_timeout = self._base_recovery * 2
        elif level == LoadLevel.CRITICAL:
            for cb in self._circuit_breakers.values():
                cb.failure_threshold = max(3, int(self._base_failure * 0.7))
                cb.recovery_timeout = self._base_recovery * 1.5
        elif level == LoadLevel.NORMAL:
            for cb in self._circuit_breakers.values():
                cb.failure_threshold = self._base_failure
                cb.recovery_timeout = self._base_recovery


class GracefulDegradationManager:
    """
    Manages graceful degradation of non-critical features under load.
    """

    def __init__(self):
        self._features: Dict[str, bool] = {}
        self._degradation_hooks: Dict[str, List[Callable[[], Awaitable[None]]]] = {}

    def register_feature(
        self,
        name: str,
        critical: bool = False,
        degradation_hooks: Optional[List[Callable[[], Awaitable[None]]]] = None,
    ):
        self._features[name] = critical
        if degradation_hooks:
            self._degradation_hooks[name] = degradation_hooks

    async def degrade_non_critical(self, level: LoadLevel):
        """Disable non-critical features under high load."""
        if level in (LoadLevel.CRITICAL, LoadLevel.OVERLOADED):
            for name, is_critical in self._features.items():
                if not is_critical:
                    for hook in self._degradation_hooks.get(name, []):
                        try:
                            await hook()
                        except Exception as e:
                            logger.warning("Degradation hook error for '%s': %s", name, e)

    def is_feature_enabled(self, name: str) -> bool:
        return self._features.get(name, True)
