"""Unit tests for the supported infrastructure metrics collector."""

from infrastructure.observability import MetricsCollector


def test_metrics_collector_records_counters_and_gauges():
    collector = MetricsCollector()
    requests = collector.counter("requests", namespace="test")
    queue_depth = collector.gauge("queue_depth", namespace="test")

    requests.inc(2)
    queue_depth.set(3)

    snapshot = collector.snapshot()
    assert snapshot["requests"] == {"type": "counter", "value": 2}
    assert snapshot["queue_depth"] == {"type": "gauge", "value": 3}
