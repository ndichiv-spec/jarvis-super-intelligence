"""
Metrics collection subsystem.

Provides counter, gauge, and histogram primitives with optional Prometheus export.
All metrics are namespaced by subsystem (api, agent, memory, automation, system).
"""

import time
import json
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from contextvars import ContextVar


@dataclass
class MetricLabel:
    name: str
    value: str


@dataclass
class MetricSample:
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class Counter:
    """Monotonic counter - use for requests, errors, events."""

    def __init__(self, name: str, description: str = "", namespace: str = "jarvis"):
        self.name = f"{namespace}_{name}"
        self.description = description
        self._value: float = 0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1, labels: Optional[Dict[str, str]] = None):
        with self._lock:
            self._value += amount
        _collector._record(MetricSample(name=self.name, value=self._value, labels=labels or {}))

    def reset(self):
        with self._lock:
            self._value = 0

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


class Gauge:
    """Point-in-time measurement - use for queue depth, connections, memory."""

    def __init__(self, name: str, description: str = "", namespace: str = "jarvis"):
        self.name = f"{namespace}_{name}"
        self.description = description
        self._value: float = 0
        self._lock = threading.Lock()

    def set(self, value: float, labels: Optional[Dict[str, str]] = None):
        with self._lock:
            self._value = value
        _collector._record(MetricSample(name=self.name, value=self._value, labels=labels or {}))

    def inc(self, amount: float = 1, labels: Optional[Dict[str, str]] = None):
        with self._lock:
            self._value += amount
        _collector._record(MetricSample(name=self.name, value=self._value, labels=labels or {}))

    def dec(self, amount: float = 1, labels: Optional[Dict[str, str]] = None):
        with self._lock:
            self._value -= amount
        _collector._record(MetricSample(name=self.name, value=self._value, labels=labels or {}))

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


class Histogram:
    """Distribution of values - use for latency, payload size."""

    def __init__(self, name: str, description: str = "", namespace: str = "jarvis",
                 buckets: Optional[List[float]] = None):
        self.name = f"{namespace}_{name}"
        self.description = description
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._values: List[float] = []
        self._lock = threading.Lock()

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None):
        with self._lock:
            self._values.append(value)
        _collector._record(MetricSample(name=self.name, value=value, labels=labels or {}))

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            if not self._values:
                return {"count": 0, "sum": 0, "min": 0, "max": 0, "avg": 0}
            sorted_vals = sorted(self._values)
            n = len(sorted_vals)
            return {
                "count": n,
                "sum": sum(sorted_vals),
                "min": sorted_vals[0],
                "max": sorted_vals[-1],
                "avg": sum(sorted_vals) / n,
                "p50": sorted_vals[int(n * 0.5)],
                "p90": sorted_vals[int(n * 0.9)],
                "p99": sorted_vals[int(n * 0.99)],
            }


class MetricsCollector:
    """
    Central metrics registry.
    Collectors register their metrics here; a single export method can push to Prometheus, stdout, etc.
    """

    def __init__(self):
        self._samples: List[MetricSample] = []
        self._lock = threading.Lock()
        self._exporters: List[Callable[[List[MetricSample]], None]] = []
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}

    def counter(self, name: str, description: str = "", namespace: str = "jarvis") -> Counter:
        if name not in self._counters:
            self._counters[name] = Counter(name, description, namespace)
        return self._counters[name]

    def gauge(self, name: str, description: str = "", namespace: str = "jarvis") -> Gauge:
        if name not in self._gauges:
            self._gauges[name] = Gauge(name, description, namespace)
        return self._gauges[name]

    def histogram(self, name: str, description: str = "", namespace: str = "jarvis",
                  buckets: Optional[List[float]] = None) -> Histogram:
        if name not in self._histograms:
            self._histograms[name] = Histogram(name, description, namespace, buckets)
        return self._histograms[name]

    def add_exporter(self, exporter: Callable[[List[MetricSample]], None]):
        self._exporters.append(exporter)

    def _record(self, sample: MetricSample):
        with self._lock:
            self._samples.append(sample)

    def flush(self):
        with self._lock:
            samples = list(self._samples)
            self._samples.clear()
        for exporter in self._exporters:
            try:
                exporter(samples)
            except Exception:
                pass

    def snapshot(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for name, c in self._counters.items():
            result[name] = {"type": "counter", "value": c.value}
        for name, g in self._gauges.items():
            result[name] = {"type": "gauge", "value": g.value}
        for name, h in self._histograms.items():
            result[name] = {"type": "histogram", **h.snapshot()}
        return result

    def prometheus_export(self) -> str:
        lines: List[str] = []
        with self._lock:
            for sample in self._samples:
                labels = ",".join(f'{k}="{v}"' for k, v in sample.labels.items())
                labels_str = f"{{{labels}}}" if labels else ""
                lines.append(f"{sample.name}{labels_str} {sample.value}")
        return "\n".join(lines)

    def clear(self):
        with self._lock:
            self._samples.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    return _collector
