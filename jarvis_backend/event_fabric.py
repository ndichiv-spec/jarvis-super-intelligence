"""
JARVIS EVENT FABRIC
====================

Provides the common event contract for all JARVIS capabilities.

Events represent REAL operations, not display artifacts. Every event has:
- event_id: unique identifier
- timestamp: ISO-formatted UTC timestamp
- correlation_id: links events to capability execution
- session_id: links events to user session
- user_id: who triggered it
- source: which capability/component emitted it
- event_type: semantic type (e.g., "voice.session.started")
- status: started/completed/failed
- payload: event-specific data
- metrics: timing/resource metrics

Usage:
    from jarvis_backend.event_fabric import get_event_bus

    bus = get_event_bus()
    bus.emit("conversation.created", {
        "session_id": "xyz",
        "user_id": "user1",
        "payload": {"session_id": "xyz"},
    })
"""

from __future__ import annotations

import asyncio
import json
import time
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable, Awaitable
from collections import defaultdict


@dataclass
class Event:
    """A JARVIS event representing a real operation."""
    event_id: str
    timestamp: str
    correlation_id: str
    session_id: str
    user_id: str
    source: str
    capability: str
    event_type: str
    status: str  # started, completed, failed, cancelled
    payload: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        event_type: str,
        source: str,
        capability: str = "",
        correlation_id: str = "",
        session_id: str = "",
        user_id: str = "",
        status: str = "started",
        payload: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> 'Event':
        """Create a new event with auto-generated IDs."""
        import uuid
        return cls(
            event_id=event_id or f"evt-{uuid.uuid4().hex}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            correlation_id=correlation_id,
            session_id=session_id,
            user_id=user_id,
            source=source,
            capability=capability,
            event_type=event_type,
            status=status,
            payload=payload or {},
            metrics=metrics or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Standard event types used across all capabilities
STANDARD_EVENTS = {
    # Conversation
    'conversation.created',
    'conversation.message.received',
    'conversation.message.sent',
    'conversation.ended',
    'conversation.restored',

    # Voice
    'voice.session.started',
    'voice.audio.received',
    'voice.transcription.started',
    'voice.transcription.completed',
    'voice.transcription.failed',
    'voice.understanding.started',
    'voice.understanding.completed',
    'voice.reasoning.started',
    'voice.brain.reasoning',
    'voice.action.started',
    'voice.action.completed',
    'voice.response.generated',
    'voice.synthesis.started',
    'voice.synthesis.completed',
    'voice.synthesis.failed',
    'voice.speaking.started',
    'voice.speaking.completed',
    'voice.session.ended',
    'voice.session.interrupted',
    'voice.session.error',
    'voice.session.offline',

    # Vision
    'vision.analysis.started',
    'vision.analysis.completed',
    'vision.analysis.failed',
    'vision.image.received',

    # Image Generation
    'image.generation.started',
    'image.generation.completed',
    'image.generation.failed',

    # Brain
    'brain.reasoning.started',
    'brain.reasoning.completed',
    'brain.tool.request',
    'brain.tool.result',
    'brain.memory.retrieve',
    'brain.memory.store',

    # Memory
    'memory.retrieval.started',
    'memory.retrieval.completed',
    'memory.store.started',
    'memory.store.completed',
    'memory.store.failed',

    # Knowledge/Search
    'knowledge.search.started',
    'knowledge.search.completed',
    'knowledge.search.failed',

    # Tools
    'tool.execution.started',
    'tool.execution.completed',
    'tool.execution.failed',
    'tool.authorization.started',
    'tool.authorization.completed',
    'tool.authorization.failed',

    # Browser
    'browser.session.created',
    'browser.navigation.started',
    'browser.navigation.completed',
    'browser.navigation.failed',
    'browser.session.closed',

    # Provider/Model
    'model.request.started',
    'model.request.completed',
    'model.request.failed',
    'provider.health.check',
    'provider.status.changed',

    # Capability lifecycle
    'capability.registered',
    'capability.unregistered',
    'capability.status.changed',
    'capability.execution.started',
    'capability.execution.completed',

    # Tasks
    'task.created',
    'task.started',
    'task.completed',
    'task.failed',
    'task.paused',
    'task.resumed',
    'task.cancelled',
    'task.recovered',
}


class EventBus:
    """
    Lightweight event bus for JARVIS capabilities.

    Events are persisted to memory (and optionally to the database) for
    observability and recovery.

    Events MUST represent real operations - never synthetic display events.
    """

    def __init__(self, max_events: int = 50000):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._critical_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._async_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._events: List[Event] = []
        self._lock = threading.RLock()
        self._max_events = max_events
        self._db_persistence = None  # Optional DB persistence

    def set_db_persistence(self, db_func):
        """Set a function to persist events to the database."""
        self._db_persistence = db_func

    def subscribe(self, event_type: str, callback: Callable, priority: int = 0):
        """Subscribe a sync callback. Use '*' for all events."""
        self._subscribers[event_type].append(callback)

    def subscribe_critical(self, event_type: str, callback: Callable) -> None:
        """Register a durable projection that must succeed before publish returns."""
        self._critical_subscribers[event_type].append(callback)

    def subscribe_async(self, event_type: str, callback: Awaitable):
        """Subscribe an async callback. Use '*' for all events."""
        self._async_subscribers[event_type].append(callback)

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None,
             source: str = "system", capability: str = "",
             correlation_id: str = "", session_id: str = "",
             user_id: str = "", status: str = "started",
             metrics: Optional[Dict[str, Any]] = None,
             event: Optional[Event] = None):
        """
        Emit an event.

        Can be called with either:
        - A pre-built Event object
        - Individual parameters
        """
        if event is None:
            event = Event.create(
                event_type=event_type,
                source=source,
                capability=capability,
                correlation_id=correlation_id,
                session_id=session_id,
                user_id=user_id,
                status=status,
                payload=payload,
                metrics=metrics,
            )

        # Runtime truth belongs to the canonical SQL journal, not the fabric's
        # process-local replay buffer or optional legacy persistence hook.
        runtime_event = (
            isinstance(event.payload, dict)
            and event.payload.get("runtime_protocol") == "1.0"
        )
        if not runtime_event:
            with self._lock:
                self._events.append(event)
                if len(self._events) > self._max_events:
                    self._events = self._events[-self._max_events:]

        # Persist to DB if configured
        if self._db_persistence and not runtime_event:
            try:
                self._db_persistence(event.to_dict())
            except Exception:
                pass

        critical_results = []
        for cb in self._critical_subscribers.get('*', []):
            critical_results.append(cb(event))
        for cb in self._critical_subscribers.get(event_type, []):
            critical_results.append(cb(event))

        # Notify sync subscribers
        for cb in self._subscribers.get('*', []):
            try:
                cb(event)
            except Exception:
                pass
        for cb in self._subscribers.get(event_type, []):
            try:
                cb(event)
            except Exception:
                pass
        return critical_results

    async def emit_async(self, event_type: str, payload: Optional[Dict[str, Any]] = None,
                         source: str = "system", capability: str = "",
                         correlation_id: str = "", session_id: str = "",
                         user_id: str = "", status: str = "started",
                         metrics: Optional[Dict[str, Any]] = None,
                         event: Optional[Event] = None):
        """Emit an event asynchronously."""
        if event is None:
            event = Event.create(
                event_type=event_type,
                source=source,
                capability=capability,
                correlation_id=correlation_id,
                session_id=session_id,
                user_id=user_id,
                status=status,
                payload=payload,
                metrics=metrics,
            )

        self.emit(event_type=event_type, event=event)

        # Notify async subscribers
        for cb in self._async_subscribers.get('*', []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception:
                pass
        for cb in self._async_subscribers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception:
                pass

    def get_events(
        self,
        event_type: Optional[str] = None,
        capability: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve events with optional filtering."""
        with self._lock:
            events = list(self._events)

        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if capability:
            events = [e for e in events if e.capability == capability]
        if session_id:
            events = [e for e in events if e.session_id == session_id]
        if user_id:
            events = [e for e in events if e.user_id == user_id]

        return [e.to_dict() for e in events[-limit:]]

    def clear_old_events(self, max_age_seconds: int = 3600):
        """Clear events older than max_age_seconds."""
        now = time.time()
        with self._lock:
            self._events = [
                e for e in self._events
                if now - datetime.fromisoformat(e.timestamp.replace('Z', '+00:00')).timestamp() < max_age_seconds
            ]


# ============================================================================
# SINGLETON ACCESS
# ============================================================================

_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global JARVIS event bus."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


__all__ = [
    'Event',
    'EventBus',
    'get_event_bus',
    'STANDARD_EVENTS',
]
