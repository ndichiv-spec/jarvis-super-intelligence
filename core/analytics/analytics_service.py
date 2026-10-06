from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class EventType(str, Enum):
    USER_ACTION = "user_action"
    SYSTEM_EVENT = "system_event"
    ERROR = "error"


class AnalyticsService:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._gauges: dict[str, list[tuple[float, dict[str, Any]]]] = defaultdict(list)
        self._timers: list[dict[str, Any]] = []
        self._counters: dict[str, float] = defaultdict(float)

    async def track_event(
        self,
        event_type: EventType | str,
        properties: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        self._events.append(
            {
                "id": event_id,
                "event_type": str(event_type),
                "properties": properties or {},
                "metrics": metrics or {},
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        return event_id

    async def increment_counter(self, name: str, value: float = 1, tags: dict[str, Any] | None = None) -> None:
        self._counters[name] += float(value)

    async def record_gauge(self, name: str, value: float, tags: dict[str, Any] | None = None) -> None:
        self._gauges[name].append((float(value), tags or {}))

    async def record_timer(self, name: str, value: float, tags: dict[str, Any] | None = None) -> None:
        self._timers.append({"name": name, "value": float(value), "tags": tags or {}, "timestamp": datetime.utcnow().isoformat()})

    async def get_kpi_dashboard(self) -> dict[str, Any]:
        unique_users = {
            event["user_id"]
            for event in self._events
            if event.get("user_id") and datetime.fromisoformat(event["timestamp"]) >= datetime.utcnow() - timedelta(days=1)
        }
        dashboard = {
            "kpis": {
                "active_users_24h": max(len(unique_users), 1),
                "total_events": len(self._events),
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
        return dashboard

    async def generate_report(self, report_type: str, days: int = 7) -> dict[str, Any]:
        return {
            "report_type": report_type,
            "period": f"last_{days}_days",
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def get_service_stats(self) -> dict[str, Any]:
        return {
            "total_events_tracked": len(self._events),
            "total_gauges": sum(len(v) for v in self._gauges.values()),
        }

    async def get_performance_metrics(self, hours: int = 1) -> dict[str, Any]:
        total_requests = len(self._events)
        return {"total_requests": total_requests, "window_hours": hours, "generated_at": datetime.utcnow().isoformat()}


analytics_service = AnalyticsService()

__all__ = ["EventType", "AnalyticsService", "analytics_service"]
