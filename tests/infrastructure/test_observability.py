"""Tests for infrastructure.observability — MetricsCollector, Tracer, Middleware."""

from __future__ import annotations
import time
import pytest


class TestCounter:
    def test_initial_value_zero(self, metrics_collector):
        c = metrics_collector.counter("requests")
        assert c.value == 0

    def test_increment(self, metrics_collector):
        c = metrics_collector.counter("requests")
        c.inc()
        assert c.value == 1

    def test_increment_by_amount(self, metrics_collector):
        c = metrics_collector.counter("requests")
        c.inc(5)
        assert c.value == 5

    def test_reset(self, metrics_collector):
        c = metrics_collector.counter("requests")
        c.inc(10)
        c.reset()
        assert c.value == 0

    def test_namespace_in_name(self, metrics_collector):
        c = metrics_collector.counter("hits", namespace="api")
        assert "api" in c.name


class TestGauge:
    def test_set_value(self, metrics_collector):
        g = metrics_collector.gauge("connections")
        g.set(42)
        assert g.value == 42

    def test_increment(self, metrics_collector):
        g = metrics_collector.gauge("connections")
        g.set(10)
        g.inc(5)
        assert g.value == 15

    def test_decrement(self, metrics_collector):
        g = metrics_collector.gauge("connections")
        g.set(10)
        g.dec(3)
        assert g.value == 7


class TestHistogram:
    def test_observe_values(self, metrics_collector):
        h = metrics_collector.histogram("latency")
        h.observe(100)
        h.observe(200)
        snap = h.snapshot()
        assert snap["count"] == 2
        assert snap["min"] == 100
        assert snap["max"] == 200

    def test_empty_snapshot(self, metrics_collector):
        h = metrics_collector.histogram("empty")
        snap = h.snapshot()
        assert snap["count"] == 0

    def test_percentiles(self, metrics_collector):
        h = metrics_collector.histogram("pct")
        for v in range(1, 101):
            h.observe(v)
        snap = h.snapshot()
        assert snap["p50"] >= 50
        assert snap["p50"] <= 51
        assert snap["p90"] >= 90
        assert snap["p90"] <= 91


class TestMetricsCollector:
    def test_counter_is_reused(self, metrics_collector):
        c1 = metrics_collector.counter("same")
        c2 = metrics_collector.counter("same")
        assert c1 is c2

    def test_gauge_is_reused(self, metrics_collector):
        g1 = metrics_collector.gauge("same")
        g2 = metrics_collector.gauge("same")
        assert g1 is g2

    def test_histogram_is_reused(self, metrics_collector):
        h1 = metrics_collector.histogram("same")
        h2 = metrics_collector.histogram("same")
        assert h1 is h2

    def test_snapshot_contains_all_metrics(self, metrics_collector):
        metrics_collector.counter("hits").inc()
        metrics_collector.gauge("temp").set(36.5)
        metrics_collector.histogram("duration").observe(500)
        snap = metrics_collector.snapshot()
        assert "hits" in snap
        assert snap["hits"]["type"] == "counter"
        assert "temp" in snap and snap["temp"]["type"] == "gauge"
        assert "duration" in snap and snap["duration"]["type"] == "histogram"

    def test_clear_removes_all(self, metrics_collector):
        metrics_collector.counter("test").inc()
        metrics_collector.clear()
        assert "test" not in metrics_collector.snapshot()

    def test_prometheus_export(self, metrics_collector):
        c = metrics_collector.counter("http_reqs")
        c.inc()
        g = metrics_collector.gauge("cpu")
        g.set(45.2)
        from infrastructure.observability.metrics import _collector
        output = _collector.prometheus_export()
        assert "jarvis_http_reqs" in output
        _collector.clear()

    def test_flush_calls_exporters(self, metrics_collector):
        exported = []
        from infrastructure.observability.metrics import _collector as global_collector
        global_collector.add_exporter(lambda samples: exported.extend(samples))
        c = metrics_collector.counter("test")
        c.inc()
        global_collector.flush()
        assert len(exported) >= 1
        global_collector.clear()


class TestTracer:
    def test_creates_tracer(self, tracer):
        assert tracer.service_name == "test-service"

    def test_start_span_creates_root(self, tracer):
        span = tracer.start_span("operation")
        assert span.span_id
        assert span.trace_id
        assert span.parent_span_id == ""

    def test_start_span_with_attributes(self, tracer):
        span = tracer.start_span("op", attributes={"key": "val"})
        assert span.attributes.get("key") == "val"

    def test_end_span_records_end_time(self, tracer):
        span = tracer.start_span("op")
        time.sleep(0.01)
        tracer.end_span(span)
        assert span.end_time is not None
        assert span.duration_ms >= 5

    def test_child_inherits_trace_id(self, tracer):
        parent = tracer.start_span("parent")
        child = tracer.start_span("child")
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id

    def test_span_context_manager(self, tracer):
        with tracer.span("auto") as span:
            span.set_attribute("key", "val")
            assert span.name == "auto"
        assert span.end_time is not None

    def test_get_current_context(self, tracer):
        tracer.start_span("test")
        ctx = tracer.get_current_context()
        assert ctx.trace_id
        assert ctx.span_id

    def test_inject_context(self, tracer):
        tracer.start_span("test")
        headers = {}
        tracer.inject_context(headers)
        assert "x-trace-id" in headers
        assert "x-span-id" in headers

    def test_extract_context(self, tracer):
        ctx = tracer.extract_context({"x-trace-id": "trace1", "x-span-id": "span1"})
        assert ctx is not None
        assert ctx.trace_id == "trace1"
        assert ctx.span_id == "span1"

    def test_extract_context_missing(self, tracer):
        ctx = tracer.extract_context({})
        assert ctx is None

    def test_span_add_event(self, tracer):
        span = tracer.start_span("test")
        span.add_event("milestone", {"step": 1})
        assert len(span.events) == 1
        assert span.events[0]["name"] == "milestone"

    def test_snapshot_returns_spans(self, tracer):
        tracer.start_span("a")
        tracer.end_span(tracer.start_span("b"))
        snap = tracer.snapshot()
        assert len(snap) >= 1
