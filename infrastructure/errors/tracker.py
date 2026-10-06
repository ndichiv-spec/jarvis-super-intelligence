"""
Error tracking and aggregation subsystem.

Collects error events from all subsystems for analysis and alerting.
"""

import time
import json
import threading
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ErrorEvent:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    code: str = ""
    message: str = ""
    subsystem: str = ""
    severity: str = "error"
    traceback: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "code": self.code,
            "message": self.message,
            "subsystem": self.subsystem,
            "severity": self.severity,
            "context": self.context,
            "tags": self.tags,
        }


class ErrorTracker:
    """
    Aggregates errors from all subsystems.

    Provides:
      - Error event collection with deduplication window
      - Severity-based reporting
      - Subsystem filtering
      - Exporter interface for external error services (Sentry, DataDog, etc.)
    """

    def __init__(self, max_events: int = 10000, dedup_window: float = 60.0):
        self.max_events = max_events
        self.dedup_window = dedup_window
        self._events: List[ErrorEvent] = []
        self._recent_codes: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._exporters: List[Callable[[ErrorEvent], None]] = []

    def add_exporter(self, exporter: Callable[[ErrorEvent], None]):
        self._exporters.append(exporter)

    def track(self, event: ErrorEvent):
        """Record an error event (with deduplication)."""
        dedup_key = f"{event.subsystem}:{event.code}"

        with self._lock:
            now = time.time()
            if dedup_key in self._recent_codes:
                if now - self._recent_codes[dedup_key] < self.dedup_window:
                    return
            self._recent_codes[dedup_key] = now

            self._events.append(event)
            if len(self._events) > self.max_events:
                self._events.pop(0)

        for exporter in self._exporters:
            try:
                exporter(event)
            except Exception:
                pass

    def track_exception(self, exc: Exception, subsystem: str = "",
                        context: Optional[Dict[str, Any]] = None,
                        tags: Optional[Dict[str, str]] = None):
        """Track an exception as an error event."""
        import traceback

        code = "internal_error"
        message = str(exc) or "Unknown error"
        severity = "error"

        if hasattr(exc, "code") and exc.code:
            code = exc.code
        if hasattr(exc, "subsystem") and exc.subsystem:
            subsystem = subsystem or exc.subsystem

        event = ErrorEvent(
            code=code,
            message=message,
            subsystem=subsystem,
            severity=severity,
            traceback=traceback.format_exc(),
            context=context or {},
            tags=tags or {},
        )
        self.track(event)

    def get_events(self, subsystem: Optional[str] = None,
                   severity: Optional[str] = None,
                   limit: int = 100) -> List[ErrorEvent]:
        with self._lock:
            events = list(self._events)
        if subsystem:
            events = [e for e in events if e.subsystem == subsystem]
        if severity:
            events = [e for e in events if e.severity == severity]
        return events[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._events)
            by_subsystem: Dict[str, int] = {}
            by_severity: Dict[str, int] = {}
            by_code: Dict[str, int] = {}
            for e in self._events:
                by_subsystem[e.subsystem] = by_subsystem.get(e.subsystem, 0) + 1
                by_severity[e.severity] = by_severity.get(e.severity, 0) + 1
                by_code[e.code] = by_code.get(e.code, 0) + 1

        return {
            "total_events": total,
            "by_subsystem": by_subsystem,
            "by_severity": by_severity,
            "by_code": by_code,
        }

    def clear(self):
        with self._lock:
            self._events.clear()
            self._recent_codes.clear()


_tracker = ErrorTracker()


def get_error_tracker() -> ErrorTracker:
    return _tracker
