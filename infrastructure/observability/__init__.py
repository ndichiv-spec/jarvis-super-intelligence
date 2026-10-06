"""
Observability subsystem.

Provides a unified interface for metrics, distributed tracing, and request
instrumentation across all Jarvis subsystems (orchestrator, agents, memory, API, automation).

Design principles:
  - Vendor-neutral interface (swap backends without code changes)
  - Context propagation via contextvars (no thread-local coupling)
  - Minimal overhead for hot paths
  - Structured span attributes for rich querying
"""

from .metrics import MetricsCollector, Counter, Gauge, Histogram, get_metrics_collector
from .tracer import Tracer, Span, TraceContext, get_tracer, set_trace_context, clear_trace_context
from .middleware import ObservabilityMiddleware

__all__ = [
    "MetricsCollector", "Counter", "Gauge", "Histogram", "get_metrics_collector",
    "Tracer", "Span", "TraceContext", "get_tracer", "set_trace_context", "clear_trace_context",
    "ObservabilityMiddleware",
]
