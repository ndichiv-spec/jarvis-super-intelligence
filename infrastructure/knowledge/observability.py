"""
Observability for knowledge management operations.

Tracks metrics, events, and performance for all knowledge subsystems.
"""

from __future__ import annotations
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEvent:
    operation: str
    subsystem: str
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "subsystem": self.subsystem,
            "duration_ms": round(self.duration_ms, 2),
            "details": self.details,
        }


class KnowledgeObservability:
    """
    Observability for all knowledge operations.

    Collects:
      - Operation metrics (count, latency)
      - Events per subsystem
      - Storage statistics snapshots
      - Learning workflow audit
    """

    def __init__(self):
        self._events: List[KnowledgeEvent] = []
        self._counters: Dict[str, int] = {}
        self._latencies: Dict[str, List[float]] = {}
        self._observers: List[Callable[[KnowledgeEvent], None]] = []

    def add_observer(self, fn: Callable[[KnowledgeEvent], None]):
        self._observers.append(fn)

    def record(self, operation: str, subsystem: str, duration_ms: float = 0.0,
               details: Optional[Dict[str, Any]] = None):
        event = KnowledgeEvent(
            operation=operation,
            subsystem=subsystem,
            duration_ms=duration_ms,
            details=details or {},
        )
        self._events.append(event)

        # Update counters
        key = f"{subsystem}:{operation}"
        self._counters[key] = self._counters.get(key, 0) + 1

        # Update latencies
        if duration_ms > 0:
            if key not in self._latencies:
                self._latencies[key] = []
            self._latencies[key].append(duration_ms)
            if len(self._latencies[key]) > 1000:
                self._latencies[key] = self._latencies[key][-1000:]

        # Notify observers
        for fn in self._observers:
            try:
                fn(event)
            except Exception:
                pass

        logger.debug(f"Knowledge event: {subsystem}/{operation} ({duration_ms:.0f}ms)")

    def get_events(self, subsystem: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        events = self._events
        if subsystem:
            events = [e for e in events if e.subsystem == subsystem]
        return [e.to_dict() for e in events[-limit:]]

    def get_metrics(self) -> Dict[str, Any]:
        metrics = {
            "total_events": len(self._events),
            "counters": dict(self._counters),
        }
        latencies = {}
        for key, vals in self._latencies.items():
            if vals:
                latencies[key] = {
                    "count": len(vals),
                    "avg_ms": round(sum(vals) / len(vals), 2),
                    "max_ms": round(max(vals), 2),
                    "min_ms": round(min(vals), 2),
                }
        metrics["latencies"] = latencies
        return metrics

    def make_store_observer(self) -> Callable:
        """Create an observer function for KnowledgeStore."""
        def observer(operation: str, doc_id: str, data: Any):
            self.record(operation, "store", details={"doc_id": doc_id})
        return observer

    def make_learning_observer(self) -> Callable:
        """Create an observer function for LearningController."""
        def observer(action: str, request_id: str, details: dict):
            self.record(action, "learning", details={"request_id": request_id, **details})
        return observer
