"""Provider telemetry for the JARVIS Provider Fabric (spec §37, §63).

Per-provider and per-model counters plus a bounded event log (JSONL-appendable).
The fabric records requests, latency, tokens, errors, timeouts, fallbacks and
health probes. Values tagged with provider/model so Observatory-style dashboards
can aggregate without string matching.
"""

from __future__ import annotations

import json
import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProviderEvent:
    timestamp: float = field(default_factory=time.time)
    provider: str = ""
    model: str = ""
    request_id: str = ""
    kind: str = "request"  # request | stream | embedding | error | timeout | fallback | health
    latency_ms: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    bytes: int = 0
    status: str = ""
    error: str = ""
    privacy_class: str = ""
    cost_estimate: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "kind": self.kind,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "bytes": self.bytes,
            "status": self.status,
            "error": self.error,
            "privacy_class": self.privacy_class,
            "cost_estimate": self.cost_estimate,
        }


@dataclass
class ProviderStats:
    requests: int = 0
    errors: int = 0
    timeouts: int = 0
    fallbacks: int = 0
    streams: int = 0
    embeddings: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_latency_ms: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    last_checked: float = 0.0

    @property
    def avg_latency_ms(self) -> Optional[float]:
        if not self.latencies_ms:
            return None
        return self.total_latency_ms / len(self.latencies_ms)

    @property
    def p95_latency_ms(self) -> Optional[float]:
        if not self.latencies_ms:
            return None
        ordered = sorted(self.latencies_ms)
        idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
        return ordered[idx]

    def add_latency(self, ms: float) -> None:
        self.total_latency_ms += ms
        self.latencies_ms.append(ms)
        if len(self.latencies_ms) > 1000:
            self.latencies_ms = self.latencies_ms[-500:]


class ProviderTelemetry:
    """Thread-safe per-provider/model telemetry collector."""

    def __init__(self, max_events: int = 5000, event_log_path: Optional[Path] = None) -> None:
        self.max_events = max_events
        self.event_log_path = event_log_path
        self._events: deque[ProviderEvent] = deque(maxlen=max_events)
        self._stats: dict[tuple[str, str], ProviderStats] = defaultdict(ProviderStats)
        self._lock = threading.Lock()
        if event_log_path is not None:
            event_log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: ProviderEvent) -> None:
        with self._lock:
            self._events.append(event)
            key = (event.provider or "", event.model or "")
            stats = self._stats[key]
            stats.last_checked = event.timestamp
            if event.kind == "request":
                stats.requests += 1
                if event.latency_ms is not None:
                    stats.add_latency(event.latency_ms)
            elif event.kind == "stream":
                stats.streams += 1
                if event.latency_ms is not None:
                    stats.add_latency(event.latency_ms)
            elif event.kind == "embedding":
                stats.embeddings += 1
            elif event.kind == "error":
                stats.errors += 1
            elif event.kind == "timeout":
                stats.timeouts += 1
            elif event.kind == "fallback":
                stats.fallbacks += 1
            stats.total_prompt_tokens += event.prompt_tokens
            stats.total_completion_tokens += event.completion_tokens
        if self.event_log_path is not None:
            try:
                with self.event_log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event.to_dict()) + "\n")
            except OSError:
                pass

    def event(self, **kwargs) -> ProviderEvent:
        ev = ProviderEvent(**kwargs)
        self.record(ev)
        return ev

    def snapshot(self) -> dict:
        with self._lock:
            stats: dict[str, dict] = {}
            for (provider, model), s in self._stats.items():
                stats[f"{provider}:{model}"] = {
                    "provider": provider,
                    "model": model,
                    "requests": s.requests,
                    "errors": s.errors,
                    "timeouts": s.timeouts,
                    "fallbacks": s.fallbacks,
                    "streams": s.streams,
                    "embeddings": s.embeddings,
                    "total_prompt_tokens": s.total_prompt_tokens,
                    "total_completion_tokens": s.total_completion_tokens,
                    "avg_latency_ms": s.avg_latency_ms,
                    "p95_latency_ms": s.p95_latency_ms,
                    "last_checked": s.last_checked,
                }
            recent = [ev.to_dict() for ev in self._events]
            return {
                "providers": stats,
                "recent_events": recent,
                "event_count": len(self._events),
            }

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [ev.to_dict() for ev in list(self._events)[-limit:]]


_default_telemetry: ProviderTelemetry | None = None
_telemetry_lock = threading.Lock()


def get_telemetry() -> ProviderTelemetry:
    global _default_telemetry
    with _telemetry_lock:
        if _default_telemetry is None:
            _default_telemetry = ProviderTelemetry()
        return _default_telemetry


def reset_telemetry(telemetry: ProviderTelemetry | None = None) -> None:
    global _default_telemetry
    with _telemetry_lock:
        _default_telemetry = telemetry if telemetry is not None else ProviderTelemetry()