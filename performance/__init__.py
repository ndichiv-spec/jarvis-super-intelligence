"""
Jarvis Performance Optimization and Scalability Infrastructure.

Central facade that wires together all performance subsystems:
  - Concurrency primitives (locks, atomic ops, rate limiters)
  - Async task queue with worker pool
  - Connection/resource pooling
  - AI request routing and batching
  - Context window optimization
  - Load handling and graceful degradation
  - Response optimization
  - Startup performance optimization
  - Telemetry and monitoring hooks
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PerformanceFacade:
    """
    Central facade for all performance optimization subsystems.

    Provides a clean API for initializing, starting, and stopping
    all performance components. Integrates with the existing
    JarvisInfrastructure class.

    Usage:
        perf = PerformanceFacade()
        await perf.initialize()
        await perf.start()
        # ... application runs ...
        await perf.stop()
    """

    def __init__(self):
        self._initialized = False
        self._running = False

        # Lazy-imported sub-systems
        self.concurrency = None
        self.task_queue = None
        self.connection_pools = None
        self.ai_batcher = None
        self.context_optimizer = None
        self.load_shedder = None
        self.response_optimizer = None
        self.startup_optimizer = None
        self.telemetry = None

        self._pools: Dict[str, Any] = {}
        self._workers: List[asyncio.Task] = []

    async def initialize(self):
        """Initialize all performance subsystems."""
        from performance.concurrency import (
            AtomicCounter, AtomicFloat, ReadWriteLock, KeyedLock,
            AdaptiveConcurrency, TokenBucket, AtomicDict, Throttle,
        )
        from performance.task_queue import WorkerPool, TaskGroup
        from performance.connection_pool import (
            ResourcePool, HTTPSessionPool, PoolConfig,
        )
        from performance.ai_batcher import AIBatcher, AIProvider, RoutingStrategy
        from performance.context_optimizer import (
            ContextOptimizer, ContextSummarizer, TokenCounter,
        )
        from performance.load_handler import (
            LoadShedder, CircuitBreakerIntegrator,
            GracefulDegradationManager, LoadMetrics,
        )
        from performance.response_optimizer import (
            ResponseOptimizer, ETagManager, StreamingOptimizer,
        )
        from performance.startup_optimizer import (
            StartupOptimizer, LazyLoader, StartupError,
        )
        from performance.telemetry import (
            TelemetryCollector, TelemetryTracer, RequestTracker,
        )

        self.concurrency = {
            "AtomicCounter": AtomicCounter,
            "AtomicFloat": AtomicFloat,
            "ReadWriteLock": ReadWriteLock,
            "KeyedLock": KeyedLock,
            "AdaptiveConcurrency": AdaptiveConcurrency,
            "TokenBucket": TokenBucket,
            "AtomicDict": AtomicDict,
            "Throttle": Throttle,
        }

        self.task_queue = WorkerPool(
            name="jarvis-default",
            min_workers=4,
            max_workers=20,
        )

        self.ai_batcher = AIBatcher()
        self.context_optimizer = ContextOptimizer()
        self.load_shedder = LoadShedder()
        self.response_optimizer = ResponseOptimizer()
        self.startup_optimizer = StartupOptimizer()
        self.telemetry = TelemetryCollector()

        self._initialized = True
        logger.info("Performance subsystems initialized")

    async def start(self):
        """Start all background workers and monitoring."""
        if not self._initialized or self._running:
            return

        self._running = True
        await self.task_queue.start()
        await self.ai_batcher.start()
        await self.load_shedder.start()

        self._workers = [
            asyncio.create_task(self._background_telemetry_loop()),
        ]

        logger.info("Performance subsystems started")

    async def stop(self):
        """Gracefully stop all subsystems."""
        self._running = False

        await self.ai_batcher.stop()
        await self.load_shedder.stop()
        await self.task_queue.stop(wait=True, timeout=10.0)

        for pool in self._pools.values():
            try:
                await pool.close()
            except Exception as e:
                logger.warning("Pool close error: %s", e)

        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        logger.info("Performance subsystems stopped")

    def register_connection_pool(self, name: str, pool: Any):
        """Register a connection pool for lifecycle management."""
        self._pools[name] = pool

    def get_http_pool(self, base_url: str = "", max_size: int = 10) -> Any:
        """Get or create an HTTP connection pool."""
        pool_key = f"http:{base_url}"
        if pool_key not in self._pools:
            from performance.connection_pool import HTTPSessionPool
            pool = HTTPSessionPool(base_url=base_url, max_size=max_size)
            self._pools[pool_key] = pool
        return self._pools[pool_key]

    def create_worker_pool(
        self,
        name: str,
        min_workers: int = 2,
        max_workers: int = 10,
    ) -> Any:
        """Create a named worker pool."""
        from performance.task_queue import WorkerPool
        pool = WorkerPool(name=name, min_workers=min_workers, max_workers=max_workers)
        return pool

    def get_stats(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "running": self._running,
            "task_queue": self.task_queue.get_stats() if self.task_queue else {},
            "connection_pools": {
                name: {
                    "type": type(pool).__name__,
                }
                for name, pool in self._pools.items()
            },
            "ai_batcher": self.ai_batcher.get_stats() if self.ai_batcher else {},
        }

    async def _background_telemetry_loop(self):
        """Periodically log performance telemetry."""
        while self._running:
            await asyncio.sleep(60)
            try:
                stats = self.get_stats()
                logger.debug("Performance stats: %s", stats)
            except Exception as e:
                logger.warning("Telemetry loop error: %s", e)


# Global singleton
_performance: Optional[PerformanceFacade] = None


def get_performance() -> PerformanceFacade:
    """Get or create the global PerformanceFacade singleton."""
    global _performance
    if _performance is None:
        _performance = PerformanceFacade()
    return _performance


async def initialize_performance():
    """Initialize and start all performance subsystems."""
    perf = get_performance()
    await perf.initialize()
    await perf.start()
    return perf


async def shutdown_performance():
    """Gracefully shut down all performance subsystems."""
    perf = get_performance()
    await perf.stop()


__all__ = [
    "PerformanceFacade",
    "get_performance",
    "initialize_performance",
    "shutdown_performance",
]
