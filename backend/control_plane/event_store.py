"""
Event Sourcing - Append-only event log for state reconstruction.

Every state mutation in the control plane is recorded as an immutable event.
Aggregates are reconstructed by replaying the event stream, providing:
  * Full audit trail
  * Temporal querying ("what was the state at time T?")
  * Deterministic replay for testing
  * Event-driven projections

Backends:
  * In-memory (default, thread-safe)
  * PostgreSQL (optional; uses JSON column if psycopg2 is available)

Design:
  * Events are immutable namedtuples/dataclass instances.
  * Each event has: id, aggregate_id, aggregate_type, version, type,
    timestamp, payload, metadata.
  * EventStore.append() returns the new version for optimistic concurrency.
  * Projections subscribe to events via callbacks.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

logger = logging.getLogger("control_plane.event_store")

T = TypeVar("T")


class EventType(str, Enum):
    """Standard event types for the JARVIS control plane."""

    STATE_SNAPSHOT = "state.snapshot"
    STATE_UPDATED = "state.updated"
    SERVICE_STARTED = "service.started"
    SERVICE_STOPPED = "service.stopped"
    SERVICE_RESTARTED = "service.restarted"
    SERVICE_HEALTH_CHANGED = "service.health_changed"
    PROVIDER_STATUS_CHANGED = "provider.status_changed"
    PROVIDER_CONFIG_UPDATED = "provider.config_updated"
    CAPABILITY_STATE_CHANGED = "capability.state_changed"
    CAPABILITY_REGISTERED = "capability.registered"
    TASK_CREATED = "task.created"
    TASK_STATE_CHANGED = "task.state_changed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    CHANGESET_CREATED = "changeset.created"
    CHANGESET_APPROVED = "changeset.approved"
    CHANGESET_APPLIED = "changeset.applied"
    CHANGESET_COMMITTED = "changeset.committed"
    CHANGESET_FAILED = "changeset.failed"
    CHANGESET_ROLLED_BACK = "changeset.rolled_back"
    KNOWLEDGE_ADDED = "knowledge.added"
    KNOWLEDGE_UPDATED = "knowledge.updated"
    KNOWLEDGE_REMOVED = "knowledge.removed"
    REASONING_PLANNED = "reasoning.planned"
    REASONING_STEP_EXECUTED = "reasoning.step_executed"
    REASONING_STEP_FAILED = "reasoning.step_failed"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_NODE_EXECUTED = "workflow.node_executed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    CIRCUIT_OPENED = "circuit.opened"
    CIRCUIT_CLOSED = "circuit.closed"
    CIRCUIT_HALF_OPEN = "circuit.half_open"
    RATE_LIMITED = "rate.limited"
    RECOVERY_ATTEMPTED = "recovery.attempted"
    RECOVERY_SUCCEEDED = "recovery.succeeded"
    RECOVERY_FAILED = "recovery.failed"


@dataclass
class Event:
    """An immutable domain event."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    aggregate_id: str = ""
    aggregate_type: str = ""
    version: int = 0
    event_type: str = ""
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "version": self.version,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "metadata": self.metadata,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        return cls(
            event_id=data["event_id"],
            aggregate_id=data["aggregate_id"],
            aggregate_type=data["aggregate_type"],
            version=data["version"],
            event_type=data["event_type"],
            timestamp=data["timestamp"],
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
        )


@dataclass
class EventStreamVersion:
    """Expected version for optimistic concurrency control."""

    expected_version: int
    actual_version: int


class ConcurrentModificationError(Exception):
    """Raised when a write conflicts with a newer version."""

    def __init__(self, aggregate_id: str, expected: int, actual: int):
        super().__init__(f"Optimistic concurrency: {aggregate_id} "
                         f"expected v{expected}, actual v{actual}")
        self.aggregate_id = aggregate_id
        self.expected_version = expected
        self.actual_version = actual


class Projection:
    """
    A read-side projection that rebuilds a view from the event log.

    Subclasses override :meth:`apply_event` to fold events into the projection state.
    """

    def __init__(self):
        self._version: int = 0
        self._lock = threading.Lock()

    @property
    def version(self) -> int:
        return self._version

    def apply_event(self, event: Event) -> None:
        """Apply a single event to the projection. Override in subclasses."""
        raise NotImplementedError

    def project(self, events: List[Event]) -> None:
        """Replay a batch of events in order."""
        with self._lock:
            for event in events:
                self._version = max(self._version, event.version)
                self.apply_event(event)

    def reset(self) -> None:
        self._version = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"version": self._version}


class InMemoryEventStore:
    """
    Thread-safe in-memory event store.

    Events are stored per-aggregate as an ordered list.  Global append-only
    log is also kept for projection replay.
    """

    def __init__(self):
        self._streams: Dict[str, List[Event]] = {}
        self._global_log: List[Event] = []
        self._lock = threading.RLock()
        self._subscribers: List[Callable[[Event], None]] = []
        self._projection_subscribers: Dict[str, List[Callable[[Event], None]]] = {}

    def append(
        self,
        event: Event,
        expected_version: Optional[int] = None,
    ) -> Event:
        """
        Append an event to the store.

        If *expected_version* is provided, optimistically checks the aggregate's
        current version matches before appending.

        Returns a copy of the event with its version field populated.
        """
        with self._lock:
            stream = self._streams.setdefault(event.aggregate_id, [])

            if expected_version is not None:
                current = stream[-1].version if stream else 0
                if current != expected_version:
                    raise ConcurrentModificationError(
                        event.aggregate_id, expected_version, current
                    )

            event.version = len(stream) + 1
            event.event_id = event.event_id or str(uuid.uuid4())
            if event.timestamp == 0:
                event.timestamp = time.time()

            # Make a copy with the assigned version
            committed = Event(**event.to_dict())
            stream.append(committed)
            self._global_log.append(committed)

            self._notify_subscribers(committed)
            return committed

    def append_batch(
        self,
        events: List[Event],
        expected_version: Optional[int] = None,
    ) -> List[Event]:
        """Append multiple events atomically. All must target the same aggregate."""
        if not events:
            return []
        with self._lock:
            stream = self._streams.setdefault(events[0].aggregate_id, [])

            if expected_version is not None:
                current = stream[-1].version if stream else 0
                if current != expected_version:
                    raise ConcurrentModificationError(
                        events[0].aggregate_id, expected_version, current
                    )

            committed: List[Event] = []
            base_version = len(stream)
            for i, event in enumerate(events):
                event.version = base_version + i + 1
                event.event_id = event.event_id or str(uuid.uuid4())
                if event.timestamp == 0:
                    event.timestamp = time.time()
                copy = Event(**event.to_dict())
                stream.append(copy)
                self._global_log.append(copy)
                committed.append(copy)

            for copy in committed:
                self._notify_subscribers(copy)
            return committed

    def get_stream(
        self, aggregate_id: str, from_version: int = 0
    ) -> List[Event]:
        """Get all events for an aggregate (optionally from a version)."""
        with self._lock:
            stream = self._streams.get(aggregate_id, [])
            if from_version:
                return [e for e in stream if e.version >= from_version]
            return list(stream)

    def get_aggregate_version(self, aggregate_id: str) -> int:
        """Get the current version of an aggregate's event stream."""
        with self._lock:
            stream = self._streams.get(aggregate_id, [])
            return stream[-1].version if stream else 0

    def get_by_type(
        self,
        event_type: str,
        since: Optional[float] = None,
    ) -> List[Event]:
        """Get all events of a given type (optionally since timestamp)."""
        with self._lock:
            if since is not None:
                return [
                    e for e in self._global_log
                    if e.event_type == event_type and e.timestamp >= since
                ]
            return [e for e in self._global_log if e.event_type == event_type]

    def get_all(
        self,
        since_version: Optional[int] = None,
        since: Optional[float] = None,
        event_types: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Event]:
        """Get events from the global log with optional filters."""
        with self._lock:
            events = self._global_log
            if since:
                events = [e for e in events if e.timestamp >= since]
            if event_types:
                event_types_set = set(event_types)
                events = [e for e in events if e.event_type in event_types_set]
            if since_version is not None:
                events = [e for e in events if e.version >= since_version]
            if limit:
                events = events[-limit:]
            return list(events)

    def replay(
        self,
        aggregate_id: str,
        handler: Callable[[Any, Event], Any],
        initial_state: Optional[Any] = None,
    ) -> Any:
        """Replay all events for an aggregate into *handler*."""
        stream = self.get_stream(aggregate_id)
        state = initial_state
        for event in stream:
            state = handler(state, event)
        return state

    def replay_range(
        self,
        aggregate_id: str,
        from_version: int,
        to_version: Optional[int],
        handler: Callable[[Any, Event], Any],
        initial_state: Optional[Any] = None,
    ) -> Any:
        """Replay a range of versions for an aggregate."""
        stream = self.get_stream(aggregate_id, from_version)
        if to_version is not None:
            stream = [e for e in stream if e.version <= to_version]
        state = initial_state
        for event in stream:
            state = handler(state, event)
        return state

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        """Subscribe to all events (push model)."""
        with self._lock:
            self._subscribers.append(callback)

    def subscribe_to_type(
        self, event_type: str, callback: Callable[[Event], None]
    ) -> None:
        """Subscribe to events of a specific type."""
        with self._lock:
            self._projection_subscribers.setdefault(event_type, []).append(callback)

    def _notify_subscribers(self, event: Event) -> None:
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception as exc:
                logger.warning("Subscriber error for event %s: %s", event.event_id, exc)
        for callback in self._projection_subscribers.get(event.event_type, []):
            try:
                callback(event)
            except Exception as exc:
                logger.warning("Projection subscriber error: %s", exc)

    def subscribe_projection(self, projection: Projection) -> None:
        """Attach a projection that will be fed all events from this point."""
        self.subscribe(projection.apply_event)

    def project_from_start(self, projection: Projection) -> None:
        """Replay all historical events into the projection."""
        with self._lock:
            for event in self._global_log:
                projection._version = max(projection._version, event.version)
                projection.apply_event(event)

    def get_snapshot(self, aggregate_id: str) -> Optional[Event]:
        """Get the latest snapshot event for an aggregate (if any)."""
        stream = self._streams.get(aggregate_id, [])
        for event in reversed(stream):
            if event.event_type == EventType.STATE_SNAPSHOT.value:
                return event
        return None

    def create_snapshot(
        self,
        aggregate_id: str,
        state: Dict[str, Any],
        aggregate_type: str = "",
    ) -> Event:
        """Create and store a snapshot event for an aggregate."""
        snapshot = Event(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type or aggregate_id,
            version=0,
            event_type=EventType.STATE_SNAPSHOT.value,
            payload=state,
        )
        return self.append(snapshot)

    def clear(self) -> None:
        """Clear all events (testing only)."""
        with self._lock:
            self._streams.clear()
            self._global_log.clear()
            self._subscribers.clear()
            self._projection_subscribers.clear()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_events": len(self._global_log),
                "total_streams": len(self._streams),
                "subscribers": len(self._subscribers),
                "projection_subscribers": {
                    k: len(v) for k, v in self._projection_subscribers.items()
                },
            }


class PostgresEventStore:
    """
    PostgreSQL-backed event store.

    Requires the ``events`` table::

        CREATE TABLE events (
            event_id UUID PRIMARY KEY,
            aggregate_id TEXT NOT NULL,
            aggregate_type TEXT,
            version INT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp DOUBLE PRECISION,
            payload JSONB,
            metadata JSONB,
            correlation_id UUID,
            causation_id UUID,
            created_at DOUBLE PRECISION DEFAULT extract(epoch FROM now())
        );
        CREATE INDEX idx_events_aggregate ON events (aggregate_id, version);
        CREATE INDEX idx_events_type ON events (event_type);
    """

    def __init__(self, dsn: str, table_name: str = "events"):
        self.dsn = dsn
        self.table_name = table_name
        self._conn = None
        self._lock = threading.Lock()
        self._connect()

    def _connect(self) -> None:
        try:
            import psycopg2
            self._conn = psycopg2.connect(self.dsn)
            self._conn.autocommit = True
        except ImportError:
            logger.warning("psycopg2 not installed; PostgresEventStore unavailable")
            self._conn = None
        except Exception as exc:
            logger.warning("Postgres connection failed: %s", exc)
            self._conn = None

    def append(
        self,
        event: Event,
        expected_version: Optional[int] = None,
    ) -> Event:
        if self._conn is None:
            raise RuntimeError("Postgres connection not available")

        with self._lock:
            # Check optimistic concurrency
            if expected_version is not None:
                with self._conn.cursor() as cur:
                    cur.execute(
                        f"SELECT COALESCE(MAX(version), 0) FROM {self.table_name} "
                        f"WHERE aggregate_id = %s",
                        (event.aggregate_id,),
                    )
                    row = cur.fetchone()
                    current = row[0] if row else 0
                    if current != expected_version:
                        raise ConcurrentModificationError(
                            event.aggregate_id, expected_version, current
                        )

            event.version = self._next_version(event.aggregate_id)
            event.event_id = event.event_id or str(uuid.uuid4())
            if event.timestamp == 0:
                event.timestamp = time.time()

            with self._conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {self.table_name} "
                    f"(event_id, aggregate_id, aggregate_type, version, event_type, "
                    f"timestamp, payload, metadata, correlation_id, causation_id) "
                    f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        event.event_id,
                        event.aggregate_id,
                        event.aggregate_type,
                        event.version,
                        event.event_type,
                        event.timestamp,
                        json.dumps(event.payload),
                        json.dumps(event.metadata),
                        event.correlation_id,
                        event.causation_id,
                    ),
                )

            return event

    def _next_version(self, aggregate_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT COALESCE(MAX(version), 0) + 1 FROM {self.table_name} "
                f"WHERE aggregate_id = %s",
                (aggregate_id,),
            )
            row = cur.fetchone()
            return row[0] if row else 1

    def get_stream(
        self, aggregate_id: str, from_version: int = 0
    ) -> List[Event]:
        if self._conn is None:
            raise RuntimeError("Postgres connection not available")

        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT event_id, aggregate_id, aggregate_type, version, "
                f"event_type, timestamp, payload, metadata, correlation_id, "
                f"causation_id FROM {self.table_name} "
                f"WHERE aggregate_id = %s AND version >= %s ORDER BY version",
                (aggregate_id, from_version),
            )
            rows = cur.fetchall()

        events: List[Event] = []
        for row in rows:
            events.append(Event(
                event_id=row[0],
                aggregate_id=row[1],
                aggregate_type=row[2],
                version=row[3],
                event_type=row[4],
                timestamp=row[5],
                payload=row[6] or {},
                metadata=row[7] or {},
                correlation_id=row[8],
                causation_id=row[9],
            ))
        return events

    def get_aggregate_version(self, aggregate_id: str) -> int:
        if self._conn is None:
            raise RuntimeError("Postgres connection not available")

        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT COALESCE(MAX(version), 0) FROM {self.table_name} "
                f"WHERE aggregate_id = %s",
                (aggregate_id,),
            )
            row = cur.fetchone()
            return row[0] if row else 0

    def get_by_type(
        self,
        event_type: str,
        since: Optional[float] = None,
    ) -> List[Event]:
        if self._conn is None:
            raise RuntimeError("Postgres connection not available")

        with self._conn.cursor() as cur:
            if since is not None:
                cur.execute(
                    f"SELECT event_id, aggregate_id, aggregate_type, version, "
                    f"event_type, timestamp, payload, metadata, correlation_id, "
                    f"causation_id FROM {self.table_name} "
                    f"WHERE event_type = %s AND timestamp >= %s ORDER BY version",
                    (event_type, since),
                )
            else:
                cur.execute(
                    f"SELECT event_id, aggregate_id, aggregate_type, version, "
                    f"event_type, timestamp, payload, metadata, correlation_id, "
                    f"causation_id FROM {self.table_name} "
                    f"WHERE event_type = %s ORDER BY version",
                    (event_type,),
                )
            rows = cur.fetchall()

        return [
            Event(
                event_id=row[0], aggregate_id=row[1], aggregate_type=row[2],
                version=row[3], event_type=row[4], timestamp=row[5],
                payload=row[6] or {}, metadata=row[7] or {},
                correlation_id=row[8], causation_id=row[9],
            )
            for row in rows
        ]


class EventStore:
    """
    High-level event store that auto-selects the backend.

    Defaults to :class:`InMemoryEventStore`.  If a PostgreSQL DSN is provided
    and psycopg2 is importable, uses :class:`PostgresEventStore`.
    """

    _instance: Optional["EventStore"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        backend: Optional[str] = None,
        dsn: Optional[str] = None,
    ):
        if backend is None:
            if dsn:
                backend = "postgres"
            else:
                backend = "memory"

        self.backend_name = backend
        self._impl: Any
        if backend == "postgres":
            self._impl = PostgresEventStore(dsn=dsn or "")
        else:
            self._impl = InMemoryEventStore()

    @classmethod
    def get_instance(
        cls,
        backend: Optional[str] = None,
        dsn: Optional[str] = None,
    ) -> "EventStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(backend=backend, dsn=dsn)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    def append(
        self,
        event: Event,
        expected_version: Optional[int] = None,
    ) -> Event:
        return self._impl.append(event, expected_version)

    def append_batch(
        self,
        events: List[Event],
        expected_version: Optional[int] = None,
    ) -> List[Event]:
        if hasattr(self._impl, "append_batch"):
            return self._impl.append_batch(events, expected_version)
        # Fallback: append one at a time
        result: List[Event] = []
        for event in events:
            result.append(self._impl.append(event, expected_version))
            if expected_version is not None:
                expected_version = result[-1].version
        return result

    def get_stream(
        self, aggregate_id: str, from_version: int = 0
    ) -> List[Event]:
        return self._impl.get_stream(aggregate_id, from_version)

    def get_aggregate_version(self, aggregate_id: str) -> int:
        return self._impl.get_aggregate_version(aggregate_id)

    def get_by_type(
        self,
        event_type: str,
        since: Optional[float] = None,
    ) -> List[Event]:
        return self._impl.get_by_type(event_type, since)

    def get_all(
        self,
        **kwargs: Any,
    ) -> List[Event]:
        if hasattr(self._impl, "get_all"):
            return self._impl.get_all(**kwargs)
        return []

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        if hasattr(self._impl, "subscribe"):
            self._impl.subscribe(callback)

    def subscribe_to_type(
        self, event_type: str, callback: Callable[[Event], None]
    ) -> None:
        if hasattr(self._impl, "subscribe_to_type"):
            self._impl.subscribe_to_type(event_type, callback)

    def subscribe_projection(self, projection: Projection) -> None:
        if hasattr(self._impl, "subscribe_projection"):
            self._impl.subscribe_projection(projection)

    def project_from_start(self, projection: Projection) -> None:
        if hasattr(self._impl, "project_from_start"):
            self._impl.project_from_start(projection)

    def clear(self) -> None:
        if hasattr(self._impl, "clear"):
            self._impl.clear()

    def stats(self) -> Dict[str, Any]:
        if hasattr(self._impl, "stats"):
            return self._impl.stats()
        return {"backend": self.backend_name}

    @property
    def impl(self) -> Any:
        return self._impl


event_store = EventStore.get_instance()


def record_event(
    aggregate_id: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    aggregate_type: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> Event:
    """Convenience: create and append an event."""
    event = Event(
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        event_type=event_type,
        payload=payload or {},
        metadata=metadata or {},
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return event_store.append(event, expected_version)
