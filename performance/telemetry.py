"""
Performance monitoring hooks and telemetry for Jarvis.

Provides instrumentation hooks for request/response timing,
custom metrics, integration with Prometheus, and real-user
monitoring capabilities.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable

from performance.concurrency import AtomicCounter, AtomicFloat

logger = logging.getLogger(__name__)


@dataclass
class TelemetrySpan:
    """A timed operation span."""
    name: str
    start_time: float
    end_time: float = 0.0
    duration_ms: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self, error: Optional[str] = None):
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.error = error


@dataclass
class HistogramBucket:
    """A histogram bucket for latency distributions."""
    bounds_ms: List[float]
    counts: List[int] = field(default_factory=list)

    def __post_init__(self):
        self.counts = [0] * (len(self.bounds_ms) + 1)

    def observe(self, value_ms: float):
        for i, bound in enumerate(self.bounds_ms):
            if value_ms <= bound:
                self.counts[i] += 1
                return
        self.counts[-1] += 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "bounds_ms": self.bounds_ms,
            "counts": self.counts,
            "total": sum(self.counts),
        }


class TelemetryCollector:
    """
    Collects and exposes performance telemetry.

    Integrates with the infrastructure observability system
    to push metrics to Prometheus and other backends.
    """

    def __init__(self):
        self._counters: Dict[str, AtomicCounter] = {}
        self._gauges: Dict[str, AtomicFloat] = {}
        self._histograms: Dict[str, HistogramBucket] = {}
        self._spans: Dict[str, List[TelemetrySpan]] = {}
        self._hooks: Dict[str, List[Callable]] = {}

    def counter(self, name: str) -> AtomicCounter:
        if name not in self._counters:
            self._counters[name] = AtomicCounter()
        return self._counters[name]

    def gauge(self, name: str) -> AtomicFloat:
        if name not in self._gauges:
            self._gauges[name] = AtomicFloat()
        return self._gauges[name]

    def histogram(self, name: str, bounds: Optional[List[float]] = None) -> HistogramBucket:
        if name not in self._histograms:
            self._histograms[name] = HistogramBucket(
                bounds_ms=bounds or [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
            )
        return self._histograms[name]

    def on(self, event: str, hook: Callable):
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(hook)

    async def emit(self, event: str, **kwargs):
        for hook in self._hooks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(**kwargs)
                else:
                    hook(**kwargs)
            except Exception as e:
                logger.warning("Telemetry hook '%s' error: %s", event, e)

    def record_span(self, span: TelemetrySpan):
        if span.name not in self._spans:
            self._spans[span.name] = []
        self._spans[span.name].append(span)

        hist = self.histogram(f"span:{span.name}")
        hist.observe(span.duration_ms)

        if span.error:
            counter = self.counter(f"error:{span.name}")
            asyncio.ensure_future(counter.inc())

    def snapshot(self) -> Dict[str, Any]:
        return {
            "counters": {
                name: asyncio.run(c.get()) if hasattr(c, 'get') else 0
                for name, c in self._counters.items()
            },
            "histograms": {
                name: h.snapshot()
                for name, h in self._histograms.items()
            },
            "events": list(self._hooks.keys()),
        }

    def clear(self):
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._spans.clear()


class TelemetryTracer:
    """
    Provides span-based tracing for request/response cycles.

    Usage:
        with telemetry_tracer.span("llm_call", model="gpt-4") as span:
            result = await llm.call(prompt)
    """

    def __init__(self, collector: TelemetryCollector):
        self._collector = collector
        self._active_spans: Dict[str, TelemetrySpan] = {}

    @asynccontextmanager
    async def span(self, name: str, **tags):
        span = TelemetrySpan(name=name, start_time=time.time(), tags=tags)
        span_id = f"{name}:{id(span)}"
        self._active_spans[span_id] = span
        try:
            yield span
        except Exception as e:
            span.finish(error=str(e))
            raise
        else:
            span.finish()
        finally:
            self._collector.record_span(span)
            self._active_spans.pop(span_id, None)

    def get_active_spans(self) -> List[TelemetrySpan]:
        return list(self._active_spans.values())


class RequestTracker:
    """
    Tracks HTTP request metrics: count, duration, status codes, endpoints.
    """

    def __init__(self):
        self._request_count = AtomicCounter()
        self._error_count = AtomicCounter()
        self._total_duration = AtomicFloat()
        self._endpoint_counts: Dict[str, AtomicCounter] = {}
        self._status_counts: Dict[int, AtomicCounter] = {}

    async def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ):
        await self._request_count.inc()
        await self._total_duration.add(duration_ms)

        endpoint = f"{method}:{path}"
        if endpoint not in self._endpoint_counts:
            self._endpoint_counts[endpoint] = AtomicCounter()
        await self._endpoint_counts[endpoint].inc()

        if status_code >= 400:
            await self._error_count.inc()
            if status_code not in self._status_counts:
                self._status_counts[status_code] = AtomicCounter()
            await self._status_counts[status_code].inc()

    async def get_stats(self) -> Dict[str, Any]:
        count = await self._request_count.get()
        total_dur = await self._total_duration.get()
        return {
            "total_requests": count,
            "total_errors": await self._error_count.get(),
            "error_rate": await self._error_count.get() / max(count, 1),
            "avg_duration_ms": total_dur / max(count, 1),
            "endpoints": {
                ep: await c.get()
                for ep, c in self._endpoint_counts.items()
            },
        }


# Global singleton
_telemetry_collector: Optional[TelemetryCollector] = None


def get_telemetry_collector() -> TelemetryCollector:
    global _telemetry_collector
    if _telemetry_collector is None:
        _telemetry_collector = TelemetryCollector()
    return _telemetry_collector
