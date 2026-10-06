"""
AI request routing and batching for Jarvis.

Provides intelligent request routing to AI providers based on load,
latency, and cost. Supports request batching for compatible providers
to maximize throughput and reduce per-request overhead.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, List, Optional, Set,
    Tuple, TypeVar, Awaitable,
)

from performance.concurrency import AdaptiveConcurrency, AtomicCounter, TokenBucket
from performance.task_queue import WorkerPool, TaskPriority

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RoutingStrategy(Enum):
    """AI request routing strategies."""
    ROUND_ROBIN = auto()
    LEAST_BUSY = auto()
    LOWEST_LATENCY = auto()
    PREFERRED_ORDER = auto()
    COST_OPTIMIZED = auto()


@dataclass
class AIProvider:
    """Registered AI provider metadata."""
    name: str
    models: List[str]
    call: Callable[..., Awaitable[Any]]
    max_concurrency: int = 5
    cost_per_token: float = 0.0
    latency_p50: float = 0.0
    supports_batching: bool = False
    batch_max_size: int = 1
    is_active: bool = True


@dataclass
class BatchJob:
    """A batch of AI requests for a single provider."""
    batch_id: str
    provider: str
    model: str
    requests: List[Dict[str, Any]] = field(default_factory=list)
    futures: List[asyncio.Future] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    max_size: int = 1
    flush_interval: float = 0.05

    def is_ready(self) -> bool:
        return len(self.requests) >= self.max_size

    def is_expired(self, max_wait: float = 0.1) -> bool:
        return len(self.requests) > 0 and (time.time() - self.created_at) >= max_wait


class AIBatcher:
    """
    Intelligent AI request router and batcher.

    Features:
    - Multi-provider routing (round-robin, least-busy, lowest-latency, cost-optimized)
    - Request batching for compatible providers (e.g., embeddings)
    - Per-provider adaptive concurrency
    - Provider health tracking
    - Request queuing when all providers are busy
    """

    def __init__(
        self,
        strategy: RoutingStrategy = RoutingStrategy.LEAST_BUSY,
        batch_flush_interval: float = 0.05,
        batch_max_wait: float = 0.1,
    ):
        self._strategy = strategy
        self._batch_flush_interval = batch_flush_interval
        self._batch_max_wait = batch_max_wait
        self._providers: Dict[str, AIProvider] = {}
        self._concurrency_limiters: Dict[str, AdaptiveConcurrency] = {}
        self._active_batches: Dict[str, BatchJob] = {}
        self._pending_requests: Dict[str, List[asyncio.Future]] = {}
        self._provider_order: List[str] = []
        self._rr_index: int = 0
        self._lock = asyncio.Lock()
        self._total_routed = AtomicCounter()
        self._total_batched = AtomicCounter()
        self._total_errors = AtomicCounter()
        self._batch_worker: Optional[asyncio.Task] = None
        self._running = False

    def register_provider(self, provider: AIProvider):
        """Register an AI provider for routing."""
        self._providers[provider.name] = provider
        self._concurrency_limiters[provider.name] = AdaptiveConcurrency(
            initial_limit=provider.max_concurrency,
        )
        if provider.name not in self._provider_order:
            self._provider_order.append(provider.name)

    async def route(
        self,
        model: str,
        request: Dict[str, Any],
        *,
        preferred_providers: Optional[List[str]] = None,
        strategy: Optional[RoutingStrategy] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Route an AI request to the best available provider.

        Returns the provider's response.
        """
        strategy = strategy or self._strategy
        providers = preferred_providers or self._provider_order
        provider = await self._select_provider(providers, model, strategy)

        if provider is None:
            raise RuntimeError(f"No available provider for model '{model}'")

        concurrency = self._concurrency_limiters[provider.name]

        async with concurrency:
            start = time.time()
            try:
                result = await provider.call(model=model, **request)
                await concurrency.on_success()
                await self._total_routed.inc()

                latency = (time.time() - start) * 1000
                provider.latency_p50 = 0.9 * provider.latency_p50 + 0.1 * latency

                return result

            except Exception:
                await concurrency.on_failure()
                await self._total_errors.inc()
                raise

    async def route_batch(
        self,
        model: str,
        requests: List[Dict[str, Any]],
        *,
        preferred_providers: Optional[List[str]] = None,
    ) -> List[Any]:
        """
        Route a batch of requests, grouping by provider.

        For providers that support batching, requests are sent together.
        Otherwise, they are sent concurrently.
        """
        providers = preferred_providers or self._provider_order
        provider = await self._select_provider(providers, model, RoutingStrategy.LEAST_BUSY)

        if provider is None:
            raise RuntimeError(f"No available provider for model '{model}'")

        if provider.supports_batching and len(requests) > 1:
            return await self._execute_batch(provider, model, requests)

        tasks = [self.route(model, req, preferred_providers=preferred_providers) for req in requests]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def enqueue_for_batching(
        self,
        model: str,
        request: Dict[str, Any],
        *,
        preferred_providers: Optional[List[str]] = None,
    ) -> asyncio.Future:
        """
        Enqueue a request for automatic batching.

        Returns a Future that resolves when the batch is processed.
        """
        providers = preferred_providers or self._provider_order
        provider = await self._select_provider(providers, model, RoutingStrategy.LEAST_BUSY)

        if provider is None:
            raise RuntimeError(f"No available provider for model '{model}'")

        future: asyncio.Future = asyncio.Future()
        batch_key = f"{provider.name}:{model}"

        async with self._lock:
            if batch_key not in self._active_batches:
                self._active_batches[batch_key] = BatchJob(
                    batch_id=str(uuid.uuid4()),
                    provider=provider.name,
                    model=model,
                    max_size=provider.batch_max_size,
                    flush_interval=self._batch_flush_interval,
                )

            batch = self._active_batches[batch_key]
            batch.requests.append(request)
            batch.futures.append(future)

        return future

    async def start(self):
        """Start the batch processing worker."""
        if self._running:
            return
        self._running = True
        self._batch_worker = asyncio.create_task(self._batch_worker_loop())
        logger.info("AI batcher started with %d providers", len(self._providers))

    async def stop(self):
        """Stop the batch processing worker."""
        self._running = False
        if self._batch_worker:
            self._batch_worker.cancel()
            try:
                await self._batch_worker
            except asyncio.CancelledError:
                pass

    def get_stats(self) -> Dict[str, Any]:
        return {
            "providers": list(self._providers.keys()),
            "strategy": self._strategy.name,
            "total_routed": self._total_routed,
            "total_batched": self._total_batched,
            "total_errors": self._total_errors,
        }

    async def _select_provider(
        self,
        candidates: List[str],
        model: str,
        strategy: RoutingStrategy,
    ) -> Optional[AIProvider]:
        """Select the best provider using the given strategy."""
        available = [
            p for name, p in self._providers.items()
            if name in candidates and p.is_active and model in p.models
        ]

        if not available:
            return None

        if strategy == RoutingStrategy.ROUND_ROBIN:
            async with self._lock:
                idx = self._rr_index % len(available)
                self._rr_index += 1
                return available[idx]

        if strategy == RoutingStrategy.LEAST_BUSY:
            return min(
                available,
                key=lambda p: self._concurrency_limiters[p.name]._limit,
            )

        if strategy == RoutingStrategy.LOWEST_LATENCY:
            return min(available, key=lambda p: p.latency_p50)

        if strategy == RoutingStrategy.COST_OPTIMIZED:
            return min(available, key=lambda p: p.cost_per_token)

        return available[0]

    async def _execute_batch(
        self,
        provider: AIProvider,
        model: str,
        requests: List[Dict[str, Any]],
    ) -> List[Any]:
        """Execute a batch request against a provider."""
        start = time.time()
        try:
            result = await provider.call(model=model, requests=requests)
            await self._total_batched.inc()

            latency = (time.time() - start) * 1000
            provider.latency_p50 = 0.9 * provider.latency_p50 + 0.1 * latency

            return result
        except Exception as e:
            await self._total_errors.inc()
            raise

    async def _batch_worker_loop(self):
        """Background worker that processes accumulated batches."""
        while self._running:
            await asyncio.sleep(self._batch_flush_interval)

            async with self._lock:
                ready_batches = [
                    bk for bk, bj in self._active_batches.items()
                    if bj.is_ready() or bj.is_expired(self._batch_max_wait)
                ]

                for batch_key in ready_batches:
                    batch = self._active_batches.pop(batch_key, None)
                    if batch is None or not batch.requests:
                        continue

                    asyncio.create_task(self._process_batch(batch))

    async def _process_batch(self, batch: BatchJob):
        """Process a single accumulated batch."""
        provider = self._providers.get(batch.provider)
        if not provider:
            for future in batch.futures:
                if not future.done():
                    future.set_exception(RuntimeError(f"Provider '{batch.provider}' not found"))
            return

        results = await self._execute_batch(provider, batch.model, batch.requests)

        if len(results) != len(batch.futures):
            for future in batch.futures:
                if not future.done():
                    future.set_exception(RuntimeError("Batch result count mismatch"))
            return

        for result, future in zip(results, batch.futures):
            if not future.done():
                future.set_result(result)
