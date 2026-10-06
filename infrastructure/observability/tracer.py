"""
Distributed tracing subsystem.

Provides lightweight span-based tracing with context propagation via contextvars.
Compatible with OpenTelemetry export format.
"""

import time
import uuid
import json
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextvars import ContextVar
from datetime import datetime, timezone


_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
_span_id_var: ContextVar[str] = ContextVar("span_id", default="")


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "ok"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.events.append({
            "name": name,
            "timestamp": datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(),
            "attributes": attributes or {},
        })

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


@dataclass
class TraceContext:
    trace_id: str
    span_id: str

    def to_dict(self) -> Dict[str, str]:
        return {"trace_id": self.trace_id, "span_id": self.span_id}


class Tracer:
    """
    Lightweight distributed tracer.

    Usage:
        tracer = Tracer()
        with tracer.span("agent.run") as span:
            span.set_attribute("agent_id", agent.id)
            span.add_event("started")
    """

    def __init__(self, service_name: str = "jarvis", max_spans: int = 1000):
        self.service_name = service_name
        self.max_spans = max_spans
        self._lock = threading.Lock()
        self._spans: List[Span] = []
        self._exporters: List[Any] = []

    def add_exporter(self, exporter: Any):
        self._exporters.append(exporter)

    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
        trace_id = _trace_id_var.get()
        parent_span_id = _span_id_var.get()
        span_id = uuid.uuid4().hex[:16]

        if not trace_id:
            trace_id = uuid.uuid4().hex[:32]
            _trace_id_var.set(trace_id)

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )

        _span_id_var.set(span_id)
        with self._lock:
            if len(self._spans) < self.max_spans:
                self._spans.append(span)
        return span

    def end_span(self, span: Span, status: str = "ok"):
        span.end_time = time.time()
        span.status = status
        _span_id_var.set(span.parent_span_id)

    def span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        return _SpanContextManager(self, name, attributes, **kwargs)

    def set_attribute(self, key: str, value: Any):
        if self._spans:
            with self._lock:
                if self._spans:
                    self._spans[-1].attributes[key] = value

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        if self._spans:
            event = {
                "name": name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attributes": attributes or {},
            }
            with self._lock:
                if self._spans:
                    self._spans[-1].events.append(event)

    def flush(self):
        with self._lock:
            spans = list(self._spans)
            self._spans.clear()
        for exporter in self._exporters:
            try:
                exporter(spans)
            except Exception:
                pass

    def get_current_context(self) -> TraceContext:
        return TraceContext(
            trace_id=_trace_id_var.get(),
            span_id=_span_id_var.get(),
        )

    def inject_context(self, headers: Dict[str, str]):
        headers["x-trace-id"] = _trace_id_var.get()
        headers["x-span-id"] = _span_id_var.get()

    @staticmethod
    def extract_context(headers: Dict[str, str]) -> Optional[TraceContext]:
        trace_id = headers.get("x-trace-id", "")
        span_id = headers.get("x-span-id", "")
        if trace_id:
            return TraceContext(trace_id=trace_id, span_id=span_id)
        return None

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._spans[-50:]]


class _SpanContextManager:
    """Context manager for tracing spans."""

    def __init__(self, tracer: Tracer, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.tracer = tracer
        self.name = name
        self.attributes = attributes or {}
        self.span: Optional[Span] = None

    def __enter__(self) -> Span:
        self.span = self.tracer.start_span(self.name, self.attributes)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            status = "error" if exc_type else "ok"
            self.tracer.end_span(self.span, status)
        return False


_tracer = Tracer()


def get_tracer() -> Tracer:
    return _tracer


def set_trace_context(trace_id: str = "", span_id: str = ""):
    if trace_id:
        _trace_id_var.set(trace_id)
    if span_id:
        _span_id_var.set(span_id)


def clear_trace_context():
    _trace_id_var.set("")
    _span_id_var.set("")
