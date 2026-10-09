"""Adapt actual capability/chat runtime events into presentation event vocabulary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .events import PresentationEvent
from .schemas import PRESENTATION_VERSION

_EVENT_TYPES = {
    "capability_action_started": "updated",
    "capability_action_completed": "updated",
    "capability_failed": "error",
    "capability_unavailable": "capability_changed",
    "provider.started": "updated",
    "provider.completed": "updated",
    "provider.failed": "error",
    "tool.started": "updated",
    "tool.progress": "updated",
    "tool.completed": "updated",
    "tool.failed": "error",
    "assistant.started": "created",
    "assistant.streaming": "updated",
    "assistant.completed": "updated",
    "location.requested": "updated",
    "location.available": "updated",
    "location.failed": "error",
    "image.generating": "updated",
    "image.completed": "media_ready",
    "navigation.started": "updated",
    "navigation.updated": "updated",
    "navigation.completed": "updated",
    "device.connected": "capability_changed",
    "device.disconnected": "capability_changed",
    "learning.started": "updated",
    "learning.progress": "updated",
    "learning.completed": "updated",
}


class PresentationEventAdapter:
    def adapt(
        self,
        event: dict[str, Any],
        *,
        presentation_id: str,
        session_id: str,
        sequence: int,
    ) -> PresentationEvent | None:
        event_type = str(event.get("event_type") or event.get("type") or "")
        presentation_type = _EVENT_TYPES.get(event_type)
        if presentation_type is None:
            return None
        timestamp = event.get("timestamp")
        try:
            occurred_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            occurred_at = datetime.now(UTC)
        safe_payload = {
            key: value
            for key, value in event.items()
            if key in {
                "capability_id", "capability", "action", "status", "message",
                "event_id", "error", "progress",
            }
            and isinstance(value, (str, bool, int, float, type(None)))
        }
        return PresentationEvent(
            protocol="jarvis.presentation",
            version=PRESENTATION_VERSION,
            presentation_id=presentation_id,
            session_id=session_id,
            sequence=sequence,
            type=presentation_type,
            occurred_at=occurred_at,
            payload=safe_payload,
        )


presentation_event_adapter = PresentationEventAdapter()
