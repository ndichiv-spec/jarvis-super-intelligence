"""Canonical, validated runtime event projection over JARVIS's event fabric."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .event_fabric import Event, get_event_bus
from . import db


class RuntimeEventType(StrEnum):
    REQUEST_CREATED = "request_created"
    REQUEST_ACCEPTED = "request_accepted"
    REQUEST_REJECTED = "request_rejected"
    PLANNING_STARTED = "planning_started"
    PLANNING_UPDATED = "planning_updated"
    PLANNING_COMPLETED = "planning_completed"
    CAPABILITY_SELECTED = "capability_selected"
    CAPABILITY_STARTED = "capability_started"
    CAPABILITY_PROGRESS = "capability_progress"
    CAPABILITY_COMPLETED = "capability_completed"
    CAPABILITY_FAILED = "capability_failed"
    TOOL_SELECTED = "tool_selected"
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    PROVIDER_SELECTED = "provider_selected"
    PROVIDER_STARTED = "provider_started"
    PROVIDER_COMPLETED = "provider_completed"
    PROVIDER_FAILED = "provider_failed"
    MODEL_STARTED = "model_started"
    MODEL_TOKEN = "model_token"
    MODEL_COMPLETED = "model_completed"
    MODEL_FAILED = "model_failed"
    SEARCH_STARTED = "search_started"
    SEARCH_RESULT = "search_result"
    SEARCH_COMPLETED = "search_completed"
    BROWSER_STARTED = "browser_started"
    BROWSER_NAVIGATED = "browser_navigated"
    BROWSER_CONTENT = "browser_content"
    BROWSER_COMPLETED = "browser_completed"
    LOCATION_REQUESTED = "location_requested"
    LOCATION_RECEIVED = "location_received"
    LOCATION_DENIED = "location_denied"
    MAP_CREATED = "map_created"
    MAP_UPDATED = "map_updated"
    IMAGE_GENERATION_STARTED = "image_generation_started"
    IMAGE_GENERATION_PROGRESS = "image_generation_progress"
    IMAGE_GENERATION_COMPLETED = "image_generation_completed"
    IMAGE_GENERATION_FAILED = "image_generation_failed"
    VOICE_LISTENING_STARTED = "voice_listening_started"
    VOICE_TRANSCRIPTION = "voice_transcription"
    VOICE_SYNTHESIS_STARTED = "voice_synthesis_started"
    VOICE_AUDIO_READY = "voice_audio_ready"
    VOICE_COMPLETED = "voice_completed"
    DEVICE_DISCOVERED = "device_discovered"
    DEVICE_STATE_UPDATED = "device_state_updated"
    DEVICE_ACTION_STARTED = "device_action_started"
    DEVICE_ACTION_COMPLETED = "device_action_completed"
    DEVICE_ACTION_FAILED = "device_action_failed"
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    PRESENTATION_CREATED = "presentation_created"
    PRESENTATION_UPDATED = "presentation_updated"
    PRESENTATION_TRANSITIONED = "presentation_transitioned"
    PRESENTATION_FEEDBACK = "presentation_feedback"
    MESSAGE_STARTED = "message_started"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_COMPLETED = "message_completed"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_FAILED = "request_failed"
    REQUEST_CANCELLED = "request_cancelled"


class RuntimeState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    PLANNING = "planning"
    EXECUTING = "executing"
    SEARCHING = "searching"
    BROWSING = "browsing"
    OBSERVING = "observing"
    NAVIGATING = "navigating"
    GENERATING = "generating"
    SPEAKING = "speaking"
    EXPLAINING = "explaining"
    WORKING = "working"
    LEARNING = "learning"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OFFLINE = "offline"


class RuntimeEventSource(StrEnum):
    CHAT = "chat"
    CAPABILITY_RUNTIME = "capability_runtime"
    TOOL_RUNTIME = "tool_runtime"
    PROVIDER_GATEWAY = "provider_gateway"
    MODEL_RUNTIME = "model_runtime"
    BROWSER_RUNTIME = "browser_runtime"
    VOICE_RUNTIME = "voice_runtime"
    MEDIA_RUNTIME = "media_runtime"
    DEVICE_RUNTIME = "device_runtime"
    TASK_RUNTIME = "task_runtime"
    PRESENTATION_RUNTIME = "presentation_runtime"
    SYSTEM = "system"


class EventRetention(StrEnum):
    EPHEMERAL = "ephemeral"
    SESSION = "session"
    AUDIT = "audit"
    DURABLE = "durable"


class EventSensitivity(StrEnum):
    PUBLIC = "public"
    USER = "user"
    PRIVATE = "private"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class RuntimeEventSecurity(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    retention: EventRetention = EventRetention.SESSION
    sensitivity: EventSensitivity = EventSensitivity.USER
    principal_id: str = Field(exclude=True)


class RuntimeErrorPayload(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    code: str
    category: str
    retryable: bool
    user_message: str
    technical_reference: str | None = None


class RuntimeEvent(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    event_id: str = Field(
        validation_alias=AliasChoices("id", "eventId", "event_id"),
        serialization_alias="id",
    )
    protocol_version: str = "1.0"
    type: RuntimeEventType
    timestamp: datetime
    request_id: str | None = None
    session_id: str
    conversation_id: str | None = None
    capability_id: str | None = None
    execution_id: str | None = None
    message_id: str | None = None
    presentation_id: str | None = None
    source: RuntimeEventSource
    sequence: int = Field(ge=1)
    state: RuntimeState | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    presentation: dict[str, Any] | None = None
    correlation: dict[str, Any] = Field(default_factory=dict)
    security: RuntimeEventSecurity

    @property
    def id(self) -> str:
        return self.event_id

    def sse_data(self) -> str:
        return self.model_dump_json(by_alias=True)


class RuntimeEventService:
    """Canonical runtime projection backed by the shared SQL event journal."""

    def __init__(self, *, max_events: int = 5000, poll_interval: float = 0.25) -> None:
        self._max_events = max_events
        self._poll_interval = poll_interval
        get_event_bus().subscribe_critical("*", self._ingest_event)

    def emit(
        self,
        *,
        event_type: RuntimeEventType,
        user_id: str,
        session_id: str,
        source: RuntimeEventSource,
        event_id: str | None = None,
        request_id: str | None = None,
        conversation_id: str | None = None,
        capability_id: str | None = None,
        execution_id: str | None = None,
        message_id: str | None = None,
        presentation_id: str | None = None,
        presentation: dict[str, Any] | None = None,
        correlation: dict[str, Any] | None = None,
        state: RuntimeState | None = None,
        data: dict[str, Any] | None = None,
        retention: EventRetention = EventRetention.SESSION,
        sensitivity: EventSensitivity = EventSensitivity.USER,
    ) -> RuntimeEvent:
        """Publish a semantic runtime event via the established event fabric."""
        safe_data = _json_safe(data or {})
        event = Event.create(
            event_type=event_type.value,
            source=source.value,
            event_id=event_id,
            capability=capability_id or "",
            correlation_id=request_id or "",
            session_id=session_id,
            user_id=user_id,
            status=state.value if state else event_type.value,
            payload={
                "runtime_protocol": "1.0",
                "runtime_source": source.value,
                "runtime_state": state.value if state else None,
                "runtime_data": safe_data,
                "execution_id": execution_id,
                "message_id": message_id,
                "presentation_id": presentation_id,
                "presentation": _json_safe(presentation) if presentation else None,
                "correlation": _json_safe(correlation or {}),
                "conversation_id": conversation_id,
                "retention": retention.value,
                "sensitivity": sensitivity.value,
            },
        )
        critical_results = get_event_bus().emit(event_type=event_type.value, event=event)
        if not critical_results or not isinstance(critical_results[0], RuntimeEvent):
            raise RuntimeError("The canonical runtime event was not recorded by the SQL journal.")
        return critical_results[0]

    def _ingest_event(self, event: Event) -> RuntimeEvent | None:
        if isinstance(event.payload, dict) and event.payload.get("runtime_protocol") == "1.0":
            event_type_value = event.event_type
            runtime_source = event.payload.get("runtime_source")
            runtime_state = event.payload.get("runtime_state")
            runtime_data = event.payload.get("runtime_data", {})
            execution_id = event.payload.get("execution_id")
            message_id = event.payload.get("message_id")
            presentation_id = event.payload.get("presentation_id")
            presentation = event.payload.get("presentation")
            correlation = event.payload.get("correlation", {})
            conversation_id = event.payload.get("conversation_id")
            retention_value = event.payload.get("retention", EventRetention.SESSION.value)
            sensitivity_value = event.payload.get("sensitivity", EventSensitivity.USER.value)
        else:
            mapped = _adapt_existing_event(event)
            if mapped is None:
                return None
            (
                event_type_value,
                runtime_source,
                runtime_state,
                runtime_data,
                execution_id,
                message_id,
                presentation_id,
                conversation_id,
                retention_value,
                sensitivity_value,
            ) = mapped
            presentation = None
            correlation = {}
        try:
            event_type = RuntimeEventType(event_type_value)
            source = RuntimeEventSource(runtime_source)
            state_value = runtime_state
            state = RuntimeState(state_value) if state_value else None
            retention = EventRetention(retention_value)
            sensitivity = EventSensitivity(sensitivity_value)
            timestamp = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
            runtime_data = _json_safe(runtime_data)
        except (KeyError, TypeError, ValueError):
            return
        if not event.user_id or not event.session_id:
            return None
        event_id = event.event_id or f"evt-{uuid.uuid4().hex}"

        def build_event(
            sequence: int,
            snapshot: dict[str, Any] | None,
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            event_correlation = {
                "requestId": event.correlation_id or None,
                "sessionId": event.session_id,
                "conversationId": conversation_id,
                "capabilityId": event.capability or None,
                "executionId": execution_id,
                "messageId": message_id,
                "presentationId": presentation_id,
            }
            event_correlation = {
                **_json_safe(correlation or {}),
                **event_correlation,
            }
            canonical = RuntimeEvent(
                event_id=event_id,
                type=event_type,
                timestamp=timestamp,
                request_id=event.correlation_id or None,
                session_id=event.session_id,
                conversation_id=conversation_id,
                capability_id=event.capability or None,
                execution_id=execution_id,
                message_id=message_id,
                presentation_id=presentation_id,
                source=source,
                sequence=sequence,
                state=state,
                data=runtime_data,
                presentation=_json_safe(presentation) if presentation else None,
                correlation=event_correlation,
                security=RuntimeEventSecurity(
                    retention=retention,
                    sensitivity=sensitivity,
                    principal_id=event.user_id,
                ),
            )
            next_snapshot = snapshot or {
                "sessionId": event.session_id,
                "activeRequests": {},
                "activeExecutions": {},
                "activePresentations": {},
                "assistantState": RuntimeState.IDLE.value,
                "activeMedia": {},
                "activeTasks": {},
                "sequence": 0,
            }
            self._reduce(next_snapshot, canonical)
            persisted = canonical.model_dump(mode="json", by_alias=True)
            persisted["security"]["principalId"] = event.user_id
            return persisted, next_snapshot

        persisted, _created = db.append_runtime_event(
            event.user_id,
            event.session_id,
            event_id,
            retention.value,
            build_event,
            session_retention_days=max(1, int(os.getenv("JARVIS_RUNTIME_SESSION_RETENTION_DAYS", "30"))),
            audit_retention_days=max(1, int(os.getenv("JARVIS_RUNTIME_AUDIT_RETENTION_DAYS", "90"))),
            max_session_events=self._max_events,
        )
        return RuntimeEvent.model_validate(persisted)

    def _reduce(self, snapshot: dict[str, Any], event: RuntimeEvent) -> None:
        snapshot["sequence"] = event.sequence
        if event.state:
            snapshot["assistantState"] = event.state.value
        if event.type in {
            RuntimeEventType.REQUEST_CREATED,
            RuntimeEventType.REQUEST_ACCEPTED,
        } and event.request_id:
            snapshot["activeRequests"][event.request_id] = {
                "requestId": event.request_id,
                "state": event.state.value if event.state else RuntimeState.WAITING.value,
                "createdAt": event.timestamp.isoformat(),
            }
        elif event.type in {
            RuntimeEventType.REQUEST_COMPLETED,
            RuntimeEventType.REQUEST_FAILED,
            RuntimeEventType.REQUEST_CANCELLED,
        } and event.request_id:
            snapshot["activeRequests"].pop(event.request_id, None)
            snapshot["activeExecutions"] = {
                execution_id: execution
                for execution_id, execution in snapshot["activeExecutions"].items()
                if execution.get("requestId") != event.request_id
            }
        if event.execution_id and event.type in {
            RuntimeEventType.CAPABILITY_STARTED,
            RuntimeEventType.TOOL_STARTED,
            RuntimeEventType.MODEL_STARTED,
        }:
            snapshot["activeExecutions"][event.execution_id] = {
                "executionId": event.execution_id,
                "requestId": event.request_id,
                "capabilityId": event.capability_id,
                "state": event.state.value if event.state else RuntimeState.EXECUTING.value,
            }
        elif event.execution_id and event.type in {
            RuntimeEventType.CAPABILITY_COMPLETED,
            RuntimeEventType.CAPABILITY_FAILED,
            RuntimeEventType.TOOL_COMPLETED,
            RuntimeEventType.TOOL_FAILED,
            RuntimeEventType.MODEL_COMPLETED,
            RuntimeEventType.MODEL_FAILED,
        }:
            snapshot["activeExecutions"].pop(event.execution_id, None)
        if event.type in {
            RuntimeEventType.PRESENTATION_CREATED,
            RuntimeEventType.PRESENTATION_UPDATED,
            RuntimeEventType.PRESENTATION_TRANSITIONED,
        } and event.presentation_id:
            snapshot["activePresentations"][event.presentation_id] = {
                "presentationId": event.presentation_id,
                "requestId": event.request_id,
                "state": event.state.value if event.state else None,
            }
        if event.type in {
            RuntimeEventType.IMAGE_GENERATION_STARTED,
        } and event.execution_id:
            snapshot["activeMedia"][event.execution_id] = {
                "executionId": event.execution_id,
                "type": "image",
                "state": "generating",
            }
        elif event.type in {
            RuntimeEventType.IMAGE_GENERATION_COMPLETED,
            RuntimeEventType.IMAGE_GENERATION_FAILED,
        } and event.execution_id:
            snapshot["activeMedia"].pop(event.execution_id, None)
        if event.type == RuntimeEventType.TASK_CREATED and event.execution_id:
            snapshot["activeTasks"][event.execution_id] = {
                "taskId": event.execution_id,
                "state": event.state.value if event.state else RuntimeState.WAITING.value,
            }
        elif event.type in {
            RuntimeEventType.TASK_COMPLETED,
            RuntimeEventType.TASK_FAILED,
            RuntimeEventType.TASK_CANCELLED,
        } and event.execution_id:
            snapshot["activeTasks"].pop(event.execution_id, None)

    def replay(self, user_id: str, session_id: str, after: int = 0) -> list[RuntimeEvent]:
        stream = db.read_runtime_stream(user_id, session_id, after=after, limit=self._max_events)
        return [RuntimeEvent.model_validate(event) for event in stream["events"]]

    def snapshot(self, user_id: str, session_id: str) -> dict[str, Any]:
        stream = db.read_runtime_stream(user_id, session_id)
        snapshot = stream["snapshot"]
        return {
            **snapshot,
            "activeRequests": list(snapshot["activeRequests"].values()),
            "activeExecutions": list(snapshot["activeExecutions"].values()),
            "activePresentations": list(snapshot["activePresentations"].values()),
            "activeMedia": list(snapshot["activeMedia"].values()),
            "activeTasks": list(snapshot["activeTasks"].values()),
            "oldestAvailableSequence": stream["oldest_available_sequence"],
            "retentionFloor": stream["retention_floor"],
        }

    def resume(
        self,
        user_id: str,
        session_id: str,
        after: int = 0,
        limit: int = 500,
    ) -> dict[str, Any]:
        stream = db.read_runtime_stream(
            user_id,
            session_id,
            after=after,
            limit=max(1, min(limit, 1000)),
        )
        snapshot = stream["snapshot"]
        return {
            "snapshot": {
                **snapshot,
                "activeRequests": list(snapshot["activeRequests"].values()),
                "activeExecutions": list(snapshot["activeExecutions"].values()),
                "activePresentations": list(snapshot["activePresentations"].values()),
                "activeMedia": list(snapshot["activeMedia"].values()),
                "activeTasks": list(snapshot["activeTasks"].values()),
                "oldestAvailableSequence": stream["oldest_available_sequence"],
                "retentionFloor": stream["retention_floor"],
            },
            "events": [
                RuntimeEvent.model_validate(event).model_dump(mode="json", by_alias=True)
                for event in stream["events"]
            ],
            "highWaterSequence": stream["sequence"],
            "oldestAvailableSequence": stream["oldest_available_sequence"],
            "resyncRequired": stream["resync_required"],
            "hasMore": stream["has_more"],
        }

    async def subscribe(
        self,
        user_id: str,
        session_id: str,
        after: int = 0,
    ) -> AsyncIterator[RuntimeEvent]:
        cursor = after
        while True:
            result = self.resume(user_id, session_id, cursor, limit=500)
            if result["resyncRequired"]:
                raise RuntimeHistoryExpiredError(
                    cursor,
                    result["oldestAvailableSequence"],
                    result["highWaterSequence"],
                )
            events = [
                RuntimeEvent.model_validate({
                    **event,
                    "security": {
                        **event.get("security", {}),
                        "principalId": user_id,
                    },
                })
                for event in result["events"]
            ]
            if events:
                for event in events:
                    cursor = event.sequence
                    yield event
                continue
            if cursor < result["highWaterSequence"]:
                cursor = result["highWaterSequence"]
            await asyncio.sleep(self._poll_interval)


class RuntimeHistoryExpiredError(Exception):
    def __init__(self, after: int, oldest_available: int, high_water: int) -> None:
        self.after = after
        self.oldest_available = oldest_available
        self.high_water = high_water
        super().__init__("Runtime event history expired; fetch a fresh runtime snapshot.")


_EXISTING_EVENT_MAP: dict[str, tuple[RuntimeEventType, RuntimeEventSource]] = {
    "capability.execution.started": (RuntimeEventType.CAPABILITY_STARTED, RuntimeEventSource.CAPABILITY_RUNTIME),
    "capability.execution.completed": (RuntimeEventType.CAPABILITY_COMPLETED, RuntimeEventSource.CAPABILITY_RUNTIME),
    "capability.execution.failed": (RuntimeEventType.CAPABILITY_FAILED, RuntimeEventSource.CAPABILITY_RUNTIME),
    "tool.execution.started": (RuntimeEventType.TOOL_STARTED, RuntimeEventSource.TOOL_RUNTIME),
    "tool.execution.completed": (RuntimeEventType.TOOL_COMPLETED, RuntimeEventSource.TOOL_RUNTIME),
    "tool.execution.failed": (RuntimeEventType.TOOL_FAILED, RuntimeEventSource.TOOL_RUNTIME),
    "model.request.started": (RuntimeEventType.MODEL_STARTED, RuntimeEventSource.MODEL_RUNTIME),
    "model.request.completed": (RuntimeEventType.MODEL_COMPLETED, RuntimeEventSource.MODEL_RUNTIME),
    "model.request.failed": (RuntimeEventType.MODEL_FAILED, RuntimeEventSource.MODEL_RUNTIME),
    "knowledge.search.started": (RuntimeEventType.SEARCH_STARTED, RuntimeEventSource.TOOL_RUNTIME),
    "knowledge.search.completed": (RuntimeEventType.SEARCH_COMPLETED, RuntimeEventSource.TOOL_RUNTIME),
    "knowledge.search.failed": (RuntimeEventType.CAPABILITY_FAILED, RuntimeEventSource.TOOL_RUNTIME),
    "browser.navigation.started": (RuntimeEventType.BROWSER_STARTED, RuntimeEventSource.BROWSER_RUNTIME),
    "browser.navigation.completed": (RuntimeEventType.BROWSER_COMPLETED, RuntimeEventSource.BROWSER_RUNTIME),
    "browser.navigation.failed": (RuntimeEventType.CAPABILITY_FAILED, RuntimeEventSource.BROWSER_RUNTIME),
    "location.requested": (RuntimeEventType.LOCATION_REQUESTED, RuntimeEventSource.CAPABILITY_RUNTIME),
    "location.received": (RuntimeEventType.LOCATION_RECEIVED, RuntimeEventSource.CAPABILITY_RUNTIME),
    "location.denied": (RuntimeEventType.LOCATION_DENIED, RuntimeEventSource.CAPABILITY_RUNTIME),
    "location.failed": (RuntimeEventType.CAPABILITY_FAILED, RuntimeEventSource.CAPABILITY_RUNTIME),
    "image.generation.started": (
        RuntimeEventType.IMAGE_GENERATION_STARTED,
        RuntimeEventSource.MEDIA_RUNTIME,
    ),
    "image.generation.completed": (
        RuntimeEventType.IMAGE_GENERATION_COMPLETED,
        RuntimeEventSource.MEDIA_RUNTIME,
    ),
    "image.generation.failed": (
        RuntimeEventType.IMAGE_GENERATION_FAILED,
        RuntimeEventSource.MEDIA_RUNTIME,
    ),
    "voice.session.started": (
        RuntimeEventType.VOICE_LISTENING_STARTED,
        RuntimeEventSource.VOICE_RUNTIME,
    ),
    "voice.transcription.completed": (
        RuntimeEventType.VOICE_TRANSCRIPTION,
        RuntimeEventSource.VOICE_RUNTIME,
    ),
    "voice.synthesis.started": (
        RuntimeEventType.VOICE_SYNTHESIS_STARTED,
        RuntimeEventSource.VOICE_RUNTIME,
    ),
    "voice.synthesis.completed": (
        RuntimeEventType.VOICE_AUDIO_READY,
        RuntimeEventSource.VOICE_RUNTIME,
    ),
    "voice.session.ended": (RuntimeEventType.VOICE_COMPLETED, RuntimeEventSource.VOICE_RUNTIME),
    "task.created": (RuntimeEventType.TASK_CREATED, RuntimeEventSource.TASK_RUNTIME),
    "task.started": (RuntimeEventType.TASK_STARTED, RuntimeEventSource.TASK_RUNTIME),
    "task.progress": (RuntimeEventType.TASK_PROGRESS, RuntimeEventSource.TASK_RUNTIME),
    "task.completed": (RuntimeEventType.TASK_COMPLETED, RuntimeEventSource.TASK_RUNTIME),
    "task.failed": (RuntimeEventType.TASK_FAILED, RuntimeEventSource.TASK_RUNTIME),
    "task.cancelled": (RuntimeEventType.TASK_CANCELLED, RuntimeEventSource.TASK_RUNTIME),
}


def _adapt_existing_event(
    event: Event,
) -> tuple[
    str,
    str,
    str | None,
    dict[str, Any],
    str | None,
    str | None,
    str | None,
    str | None,
    str,
    str,
] | None:
    mapped = _EXISTING_EVENT_MAP.get(event.event_type)
    if mapped is None or not event.user_id or not event.session_id:
        return None
    event_type, source = mapped
    raw = event.payload if isinstance(event.payload, dict) else {}
    safe_keys = {
        "status",
        "progress",
        "provider",
        "model",
        "latency_ms",
        "action",
        "result_count",
        "artifact_count",
    }
    data = {
        to_camel(key): value
        for key, value in raw.items()
        if key in safe_keys and isinstance(value, (str, int, float, bool, type(None)))
    }
    artifact_ids = raw.get("artifact_ids")
    if isinstance(artifact_ids, list):
        data["artifactIds"] = [
            artifact_id[:160]
            for artifact_id in artifact_ids[:20]
            if isinstance(artifact_id, str)
        ]
    if event.status:
        data.setdefault("status", event.status)
    execution_id = raw.get("execution_id")
    if not isinstance(execution_id, str):
        execution_id = (
            f"{event.capability}:{event.correlation_id}"
            if event.capability and event.correlation_id
            else None
        )
    state_by_type = {
        RuntimeEventType.CAPABILITY_STARTED: RuntimeState.EXECUTING,
        RuntimeEventType.TOOL_STARTED: RuntimeState.EXECUTING,
        RuntimeEventType.MODEL_STARTED: RuntimeState.THINKING,
        RuntimeEventType.SEARCH_STARTED: RuntimeState.SEARCHING,
        RuntimeEventType.BROWSER_STARTED: RuntimeState.BROWSING,
        RuntimeEventType.LOCATION_REQUESTED: RuntimeState.OBSERVING,
        RuntimeEventType.LOCATION_RECEIVED: RuntimeState.EXPLAINING,
        RuntimeEventType.IMAGE_GENERATION_STARTED: RuntimeState.GENERATING,
        RuntimeEventType.VOICE_LISTENING_STARTED: RuntimeState.LISTENING,
        RuntimeEventType.VOICE_SYNTHESIS_STARTED: RuntimeState.SPEAKING,
        RuntimeEventType.TASK_STARTED: RuntimeState.WORKING,
        RuntimeEventType.TASK_PROGRESS: RuntimeState.WORKING,
        RuntimeEventType.CAPABILITY_COMPLETED: RuntimeState.COMPLETED,
        RuntimeEventType.TOOL_COMPLETED: RuntimeState.COMPLETED,
        RuntimeEventType.MODEL_COMPLETED: RuntimeState.COMPLETED,
        RuntimeEventType.SEARCH_COMPLETED: RuntimeState.COMPLETED,
        RuntimeEventType.BROWSER_COMPLETED: RuntimeState.COMPLETED,
        RuntimeEventType.IMAGE_GENERATION_COMPLETED: RuntimeState.COMPLETED,
        RuntimeEventType.VOICE_AUDIO_READY: RuntimeState.SPEAKING,
        RuntimeEventType.VOICE_COMPLETED: RuntimeState.COMPLETED,
        RuntimeEventType.TASK_COMPLETED: RuntimeState.COMPLETED,
        RuntimeEventType.CAPABILITY_FAILED: RuntimeState.FAILED,
        RuntimeEventType.LOCATION_DENIED: RuntimeState.FAILED,
        RuntimeEventType.TOOL_FAILED: RuntimeState.FAILED,
        RuntimeEventType.MODEL_FAILED: RuntimeState.FAILED,
        RuntimeEventType.IMAGE_GENERATION_FAILED: RuntimeState.FAILED,
        RuntimeEventType.TASK_FAILED: RuntimeState.FAILED,
        RuntimeEventType.TASK_CANCELLED: RuntimeState.CANCELLED,
    }
    retention = (
        EventRetention.DURABLE.value
        if event_type in {RuntimeEventType.TASK_COMPLETED, RuntimeEventType.TASK_FAILED}
        else EventRetention.SESSION.value
    )
    sensitivity = (
        EventSensitivity.SENSITIVE.value
        if source == RuntimeEventSource.VOICE_RUNTIME
        or event.event_type.startswith("location.")
        else EventSensitivity.USER.value
    )
    return (
        event_type.value,
        source.value,
        state_by_type.get(event_type).value if event_type in state_by_type else None,
        data,
        execution_id,
        raw.get("message_id") if isinstance(raw.get("message_id"), str) else None,
        raw.get("presentation_id") if isinstance(raw.get("presentation_id"), str) else None,
        raw.get("conversation_id") if isinstance(raw.get("conversation_id"), str) else None,
        retention,
        sensitivity,
    )


def _json_safe(value: Any) -> Any:
    sanitized = _sanitize(value)
    encoded = json.dumps(sanitized, default=str, allow_nan=False)
    if len(encoded) > 64 * 1024:
        raise ValueError("Runtime event data exceeds the 64 KiB limit.")
    return json.loads(encoded)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if not any(
                marker in str(key).lower()
                for marker in ("password", "secret", "token", "api_key", "api-key", "authorization", "cookie")
            )
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        value = re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*",
            r"\1[REDACTED]",
            value,
        )
        value = re.sub(
            r"\b(?:sk|pk|rk|ghp|github_pat|AIza)[-_][A-Za-z0-9_-]{16,}\b",
            "[REDACTED]",
            value,
            flags=re.IGNORECASE,
        )
        return re.sub(
            r"(?i)\b(api[_-]?key|password|secret|access[_-]?token|refresh[_-]?token)\b\s*[:=]\s*\S+",
            r"\1=[REDACTED]",
            value,
        )
    return value


runtime_event_service = RuntimeEventService()


def emit_runtime_event(**kwargs: Any) -> RuntimeEvent:
    return runtime_event_service.emit(**kwargs)
