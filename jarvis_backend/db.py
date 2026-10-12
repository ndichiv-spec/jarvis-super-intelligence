"""JARVIS SQL persistence backend.

Replaces the ephemeral JSON-file ``Store`` (see :mod:`jarvis_backend.core`)
with a real SQLAlchemy backend so that sessions, messages, refresh-tokens and
user data survive process restarts.

Design
------
* **SQLite by default** (``jarvis_data/jarvis.db``), switchable to **Postgres**
  or any other DBAPI via the ``DATABASE_URL`` environment variable, and to a
  test-only in-memory database when ``JARVIS_TEST_MODE`` is set.
* A single generic key/value table (``jarvis_kv``) backs every logical
  collection (``users``, ``sessions``, ``refresh_tokens``, ``chat_sessions``
  ...).  **Dict** collections are stored row-per-key (queryable by id);
  **list** collections are stored as one ordered blob so index order is never
  silently corrupted by lexicographic key sorting.

This is an *intentional* drop-in: the :class:`~jarvis_backend.core.Store` API
(``load`` returns a mutable dict/list, ``save`` flushes it back) is preserved
verbatim, so the ~190 existing ``get_store(name)`` call-sites need no changes.

The table is created idempotently by :func:`create_db_and_tables` (the
"migration script" entry point lives in ``scripts/migrate_persistence.py``).
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Index,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "jarvis_data"

# Reserved key under which list-typed collections are stored as a single blob.
_LIST_ROOT_KEY = "__root__"

metadata = MetaData()

kv_store = Table(
    "jarvis_kv",
    metadata,
    Column("store_name", String(64), primary_key=True),
    Column("key", String(255), primary_key=True),
    Column("value", Text, nullable=False),
)

schema_migrations = Table(
    "jarvis_schema_migrations",
    metadata,
    Column("revision", String(128), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)

command_events = Table(
    "jarvis_command_events",
    metadata,
    Column("command_id", String(64), primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("event_id", String(64), nullable=False, unique=True),
    Column("created_at", String(40), nullable=False),
    Column("payload", Text, nullable=False),
)

runtime_streams = Table(
    "jarvis_runtime_streams",
    metadata,
    Column("owner_id", String(160), primary_key=True),
    Column("session_id", String(160), primary_key=True),
    Column("sequence", Integer, nullable=False, default=0),
    Column("retention_floor", Integer, nullable=False, default=0),
    Column("snapshot", Text, nullable=False),
    Column("updated_at", String(40), nullable=False),
)

runtime_events = Table(
    "jarvis_runtime_events",
    metadata,
    Column("owner_id", String(160), primary_key=True),
    Column("session_id", String(160), primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("event_id", String(128), nullable=False, unique=True),
    Column("created_at", String(40), nullable=False),
    Column("expires_at", String(40), nullable=True),
    Column("retention", String(16), nullable=False),
    Column("payload", Text, nullable=False),
)
Index("ix_jarvis_runtime_events_retention", runtime_events.c.retention, runtime_events.c.expires_at)

LATEST_SCHEMA_REVISION = "003_durable_runtime_event_journal"

# --------------------------------------------------------------------------- #
# Engine lifecycle (process-wide singleton)
# --------------------------------------------------------------------------- #
_engine: Optional[Engine] = None
_engine_lock = threading.Lock()
_ready = False
_ready_lock = threading.Lock()


def database_url() -> str:
    """Resolve the database URL from the environment.

    Priority:
      1. ``DATABASE_URL``         — explicit backend (e.g. Postgres).
      2. ``JARVIS_DB_PATH``       — explicit SQLite file path.
      3. ``JARVIS_TEST_MODE``     — in-memory SQLite (fast, isolated).
      4. default                  — ``sqlite:///jarvis_data/jarvis.db``.
    """
    url = os.environ.get("DATABASE_URL")
    if not url and os.environ.get("DATABASE_URL_FILE"):
        url = Path(os.environ["DATABASE_URL_FILE"]).read_text(
            encoding="utf-8"
        ).strip()
    if url:
        return url
    db_path = os.environ.get("JARVIS_DB_PATH")
    if db_path:
        p = Path(db_path)
        if p.suffix != ".db":
            p = p.with_suffix(".db")
        return f"sqlite:///{p.as_posix()}"
    if os.environ.get("JARVIS_TEST_MODE"):
        return "sqlite://"  # in-memory, paired with StaticPool below
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Use forward slashes (as_posix) so SQLAlchemy's sqlite URL parser is
    # happy on every platform (backslashes break path parsing on Windows).
    db_file = (DATA_DIR / "jarvis.db").as_posix()
    return f"sqlite:///{db_file}"


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def _postgres_engine_options() -> dict[str, Any]:
    """Bound and health-check pooled PostgreSQL connections."""
    def configured_int(name: str, default: int, minimum: int = 1) -> int:
        value = os.environ.get(name)
        if value is None:
            return default
        try:
            parsed = int(value)
        except ValueError as exc:
            raise RuntimeError(f"{name} must be an integer of at least {minimum}.") from exc
        if parsed < minimum:
            raise RuntimeError(f"{name} must be an integer of at least {minimum}.")
        return parsed

    return {
        "pool_pre_ping": True,
        "pool_size": configured_int("JARVIS_DB_POOL_SIZE", 5),
        "max_overflow": configured_int("JARVIS_DB_MAX_OVERFLOW", 5, minimum=0),
        "pool_timeout": configured_int("JARVIS_DB_POOL_TIMEOUT_SECONDS", 10),
        "pool_recycle": configured_int("JARVIS_DB_POOL_RECYCLE_SECONDS", 1800),
        "connect_args": {
            "connect_timeout": configured_int("JARVIS_DB_CONNECT_TIMEOUT_SECONDS", 10),
        },
    }


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine (created lazily)."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                url = database_url()
                if url == "sqlite://":
                    # In-memory SQLite needs a single shared connection.
                    _engine = create_engine(
                        url,
                        connect_args={"check_same_thread": False},
                        poolclass=StaticPool,
                    )
                elif _is_sqlite_url(url):
                    _engine = create_engine(
                        url, connect_args={"check_same_thread": False}
                    )
                else:
                    _engine = create_engine(url, **_postgres_engine_options())
    return _engine


def ensure_schema() -> None:
    """Initialize development schema or validate the explicitly migrated production schema."""
    global _ready
    if _ready:
        return
    with _ready_lock:
        if not _ready:
            engine = get_engine()
            require_migrations = (
                os.environ.get("JARVIS_REQUIRE_PREMIGRATED_SCHEMA") == "1"
                or (
                    os.environ.get("JARVIS_ENV", "").lower() == "production"
                    and os.environ.get("JARVIS_REQUIRE_PREMIGRATED_SCHEMA") != "0"
                )
            )
            if require_migrations:
                from sqlalchemy import inspect

                existing = set(inspect(engine).get_table_names())
                missing = set(metadata.tables) - existing
                if missing:
                    raise RuntimeError(
                        "Database schema is incomplete; run the controlled "
                        f"migration first. Missing tables: {', '.join(sorted(missing))}"
                    )
                revisions = _applied_migrations_unchecked()
                if LATEST_SCHEMA_REVISION not in revisions:
                    raise RuntimeError(
                        "Database migrations are incomplete; run the controlled "
                        f"migration first. Required revision: {LATEST_SCHEMA_REVISION}"
                    )
            else:
                metadata.create_all(engine)
            _ready = True


def create_db_and_tables() -> str:
    """Public migration entry point — create tables and return the DB URL."""
    ensure_schema()
    return database_url()


def reset_database() -> None:
    """Truncate all persisted collections.

    Used by the test harness to isolate test cases without restarting the
    process (simulating a clean DB while the engine/connection pool persists).
    """
    ensure_schema()
    with get_engine().begin() as conn:
        conn.execute(delete(runtime_events))
        conn.execute(delete(runtime_streams))
        conn.execute(delete(command_events))
        conn.execute(delete(kv_store))


def record_migration(revision: str) -> None:
    """Record an explicitly completed additive schema migration."""
    from datetime import datetime, timezone

    engine = get_engine()
    from sqlalchemy import inspect

    if "jarvis_schema_migrations" not in inspect(engine).get_table_names():
        schema_migrations.create(engine, checkfirst=True)
    values = {"revision": revision, "applied_at": datetime.now(timezone.utc)}
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            statement = postgres_insert(schema_migrations).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[schema_migrations.c.revision]
            )
            conn.execute(statement)
        elif engine.dialect.name == "sqlite":
            statement = sqlite_insert(schema_migrations).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[schema_migrations.c.revision]
            )
            conn.execute(statement)
        elif not conn.execute(
            select(schema_migrations.c.revision).where(
                schema_migrations.c.revision == revision
            )
        ).first():
            conn.execute(insert(schema_migrations).values(**values))


def applied_migrations() -> list[str]:
    """Return the installed migration revisions in application order."""
    return _applied_migrations_unchecked()


def _applied_migrations_unchecked() -> list[str]:
    from sqlalchemy import inspect

    engine = get_engine()
    if "jarvis_schema_migrations" not in inspect(engine).get_table_names():
        return []
    with get_engine().connect() as conn:
        revisions = conn.execute(
            select(schema_migrations.c.revision).order_by(
                schema_migrations.c.applied_at,
                schema_migrations.c.revision,
            )
        ).scalars()
        return list(revisions)


def append_command_event(command_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """Atomically persist an ordered event and the current command snapshot."""
    ensure_schema()
    with get_engine().begin() as conn:
        row = conn.execute(
            select(kv_store.c.value)
            .where(kv_store.c.store_name == "commands", kv_store.c.key == command_id)
            .with_for_update()
        ).first()
        if row is None:
            return event
        command = json.loads(row.value)
        sequence = int(command.get("event_seq", 0)) + 1
        persisted_event = {
            **event,
            "sequence": sequence,
            "command_id": command_id,
        }
        command["event_seq"] = sequence
        events = command.setdefault("events", [])
        events.append(persisted_event)
        command["events"] = events[-200:]
        conn.execute(
            update(kv_store)
            .where(kv_store.c.store_name == "commands", kv_store.c.key == command_id)
            .values(value=json.dumps(command, ensure_ascii=False, default=str))
        )
        conn.execute(
            insert(command_events).values(
                command_id=command_id,
                sequence=sequence,
                event_id=str(persisted_event["event_id"]),
                created_at=str(persisted_event["timestamp"]),
                payload=json.dumps(persisted_event, ensure_ascii=False, default=str),
            )
        )
    return persisted_event


def load_command_events(command_id: str) -> list[dict[str, Any]]:
    ensure_schema()
    with get_engine().connect() as conn:
        payloads = conn.execute(
            select(command_events.c.payload)
            .where(command_events.c.command_id == command_id)
            .order_by(command_events.c.sequence)
        ).scalars()
        return [json.loads(payload) for payload in payloads]


def append_runtime_event(
    owner_id: str,
    session_id: str,
    event_id: str,
    retention: str,
    build_event: Callable[[int, dict[str, Any] | None], tuple[dict[str, Any], dict[str, Any]]],
    *,
    session_retention_days: int = 30,
    audit_retention_days: int = 90,
    max_session_events: int = 5000,
) -> tuple[dict[str, Any], bool]:
    """Atomically assign a session sequence, append an event, and save its snapshot."""
    ensure_schema()
    engine = get_engine()
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    empty_snapshot = json.dumps({
        "sessionId": session_id,
        "activeRequests": {},
        "activeExecutions": {},
        "activePresentations": {},
        "assistantState": "idle",
        "activeMedia": {},
        "activeTasks": {},
        "sequence": 0,
    })

    with _runtime_write_transaction(engine) as conn:
        values = {
            "owner_id": owner_id,
            "session_id": session_id,
            "sequence": 0,
            "retention_floor": 0,
            "snapshot": empty_snapshot,
            "updated_at": now_text,
        }
        if engine.dialect.name == "postgresql":
            conn.execute(
                postgres_insert(runtime_streams)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[runtime_streams.c.owner_id, runtime_streams.c.session_id]
                )
            )
        elif engine.dialect.name == "sqlite":
            conn.execute(
                sqlite_insert(runtime_streams)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[runtime_streams.c.owner_id, runtime_streams.c.session_id]
                )
            )
        elif not conn.execute(
            select(runtime_streams.c.sequence).where(
                runtime_streams.c.owner_id == owner_id,
                runtime_streams.c.session_id == session_id,
            )
        ).first():
            conn.execute(insert(runtime_streams).values(**values))

        stream = conn.execute(
            select(
                runtime_streams.c.sequence,
                runtime_streams.c.retention_floor,
                runtime_streams.c.snapshot,
            )
            .where(
                runtime_streams.c.owner_id == owner_id,
                runtime_streams.c.session_id == session_id,
            )
            .with_for_update()
        ).one()
        existing = conn.execute(
            select(
                runtime_events.c.owner_id,
                runtime_events.c.session_id,
                runtime_events.c.payload,
            ).where(runtime_events.c.event_id == event_id)
        ).first()
        if existing is not None:
            if existing.owner_id != owner_id or existing.session_id != session_id:
                raise ValueError("Runtime event ID is already associated with another stream.")
            return json.loads(existing.payload), False

        sequence = int(stream.sequence) + 1
        retention_floor = int(stream.retention_floor)
        if retention == "ephemeral":
            retention_floor = max(retention_floor, sequence)
        current_snapshot = json.loads(stream.snapshot)
        event_payload, next_snapshot = build_event(sequence, current_snapshot)
        event_json = json.dumps(event_payload, ensure_ascii=False, default=str)
        snapshot_json = json.dumps(next_snapshot, ensure_ascii=False, default=str)

        conn.execute(
            update(runtime_streams)
            .where(
                runtime_streams.c.owner_id == owner_id,
                runtime_streams.c.session_id == session_id,
            )
            .values(
                sequence=sequence,
                retention_floor=retention_floor,
                snapshot=snapshot_json,
                updated_at=now_text,
            )
        )
        if retention != "ephemeral":
            expires_at = None
            if retention == "session":
                expires_at = (now + timedelta(days=session_retention_days)).isoformat()
            elif retention == "audit":
                expires_at = (now + timedelta(days=audit_retention_days)).isoformat()
            conn.execute(insert(runtime_events).values(
                owner_id=owner_id,
                session_id=session_id,
                sequence=sequence,
                event_id=event_id,
                created_at=now_text,
                expires_at=expires_at,
                retention=retention,
                payload=event_json,
            ))

        expired_sequences = conn.execute(
            select(runtime_events.c.sequence).where(
                runtime_events.c.owner_id == owner_id,
                runtime_events.c.session_id == session_id,
                runtime_events.c.expires_at.is_not(None),
                runtime_events.c.expires_at <= now_text,
            )
        ).scalars().all()
        excess_sequences = conn.execute(
            select(runtime_events.c.sequence)
            .where(
                runtime_events.c.owner_id == owner_id,
                runtime_events.c.session_id == session_id,
                runtime_events.c.retention == "session",
            )
            .order_by(runtime_events.c.sequence.desc())
            .offset(max_session_events)
        ).scalars().all()
        removed_sequences = set(expired_sequences) | set(excess_sequences)
        if removed_sequences:
            retention_floor = max(retention_floor, max(removed_sequences))
            conn.execute(
                delete(runtime_events).where(
                    runtime_events.c.owner_id == owner_id,
                    runtime_events.c.session_id == session_id,
                    runtime_events.c.sequence.in_(removed_sequences),
                )
            )
            conn.execute(
                update(runtime_streams)
                .where(
                    runtime_streams.c.owner_id == owner_id,
                    runtime_streams.c.session_id == session_id,
                )
                .values(retention_floor=retention_floor)
            )
        return event_payload, True


@contextmanager
def _runtime_write_transaction(engine: Engine):
    connection = engine.connect()
    if engine.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return
    try:
        with connection.begin():
            yield connection
    finally:
        connection.close()


def read_runtime_stream(
    owner_id: str,
    session_id: str,
    *,
    after: int = 0,
    limit: int = 500,
) -> dict[str, Any]:
    """Read a consistent snapshot and an ordered page of owner-scoped events."""
    ensure_schema()
    connection = get_engine().connect()
    with connection as conn:
        with conn.begin():
            stream = conn.execute(
                select(
                    runtime_streams.c.sequence,
                    runtime_streams.c.retention_floor,
                    runtime_streams.c.snapshot,
                ).where(
                    runtime_streams.c.owner_id == owner_id,
                    runtime_streams.c.session_id == session_id,
                ).with_for_update()
            ).first()
            if stream is None:
                sequence = 0
                retention_floor = 0
                snapshot = {
                    "sessionId": session_id,
                    "activeRequests": {},
                    "activeExecutions": {},
                    "activePresentations": {},
                    "assistantState": "idle",
                    "activeMedia": {},
                    "activeTasks": {},
                    "sequence": 0,
                }
            else:
                sequence = int(stream.sequence)
                retention_floor = int(stream.retention_floor)
                snapshot = json.loads(stream.snapshot)
                expired_sequences = conn.execute(
                    select(runtime_events.c.sequence).where(
                        runtime_events.c.owner_id == owner_id,
                        runtime_events.c.session_id == session_id,
                        runtime_events.c.expires_at.is_not(None),
                        runtime_events.c.expires_at <= datetime.now(timezone.utc).isoformat(),
                    )
                ).scalars().all()
                if expired_sequences:
                    retention_floor = max(retention_floor, max(expired_sequences))
                    conn.execute(
                        delete(runtime_events).where(
                            runtime_events.c.owner_id == owner_id,
                            runtime_events.c.session_id == session_id,
                            runtime_events.c.sequence.in_(expired_sequences),
                        )
                    )
                    conn.execute(
                        update(runtime_streams)
                        .where(
                            runtime_streams.c.owner_id == owner_id,
                            runtime_streams.c.session_id == session_id,
                        )
                        .values(retention_floor=retention_floor)
                    )
            rows = conn.execute(
                select(runtime_events.c.payload)
                .where(
                    runtime_events.c.owner_id == owner_id,
                    runtime_events.c.session_id == session_id,
                    runtime_events.c.sequence > after,
                    runtime_events.c.sequence <= sequence,
                )
                .order_by(runtime_events.c.sequence)
                .limit(limit)
            ).scalars().all()
            oldest = conn.execute(
                select(runtime_events.c.sequence)
                .where(
                    runtime_events.c.owner_id == owner_id,
                    runtime_events.c.session_id == session_id,
                )
                .order_by(runtime_events.c.sequence)
                .limit(1)
            ).scalar_one_or_none()
            events = [json.loads(payload) for payload in rows]
            has_more = bool(events and events[-1]["sequence"] < sequence)
            return {
                "sequence": sequence,
                "retention_floor": retention_floor,
                "oldest_available_sequence": int(oldest) if oldest is not None else sequence + 1,
                "snapshot": snapshot,
                "events": events,
                "has_more": has_more,
                "resync_required": after < retention_floor,
            }


def remove_migration(revision: str) -> None:
    """Remove one migration record after a supported downgrade completes."""
    with get_engine().begin() as conn:
        conn.execute(
            delete(schema_migrations).where(schema_migrations.c.revision == revision)
        )


# --------------------------------------------------------------------------- #
# Key/value access primitives
# --------------------------------------------------------------------------- #
def kv_load(
    store_name: str,
    default_factory: Callable[[], Any] = dict,
) -> Any:
    """Load a whole collection for ``store_name``.

    Dict collections are returned as ``{key: value}``; list collections as a
    list (insertion order preserved).  An empty store yields the empty
    instance produced by ``default_factory``.
    """
    ensure_schema()
    is_list = default_factory is list
    with get_engine().connect() as conn:
        if is_list:
            value = conn.execute(
                select(kv_store.c.value).where(
                    kv_store.c.store_name == store_name,
                    kv_store.c.key == _LIST_ROOT_KEY,
                )
            ).scalar_one_or_none()
            return json.loads(value) if value is not None else list()

        rows = conn.execute(
            select(kv_store.c.key, kv_store.c.value).where(
                kv_store.c.store_name == store_name
            )
        ).fetchall()
        return {r.key: json.loads(r.value) for r in rows}


def kv_save(store_name: str, data: Any) -> None:
    """Persist an entire collection (dict or list) for ``store_name``."""
    ensure_schema()
    with get_engine().begin() as conn:
        conn.execute(delete(kv_store).where(kv_store.c.store_name == store_name))
        if isinstance(data, list):
            conn.execute(
                insert(kv_store).values(
                    store_name=store_name,
                    key=_LIST_ROOT_KEY,
                    value=json.dumps(data, ensure_ascii=False, default=str),
                )
            )
        elif isinstance(data, dict):
            for k, v in data.items():
                conn.execute(
                    insert(kv_store).values(
                        store_name=store_name,
                        key=str(k),
                        value=json.dumps(v, ensure_ascii=False, default=str),
                    )
                )
        else:
            # Scalar fallback.
            conn.execute(
                insert(kv_store).values(
                    store_name=store_name,
                    key=_LIST_ROOT_KEY,
                    value=json.dumps(data, ensure_ascii=False, default=str),
                )
            )


def kv_get(store_name: str, key: str, default: Any = None) -> Any:
    """Fetch a single value from a dict collection by key."""
    ensure_schema()
    with get_engine().connect() as conn:
        value = conn.execute(
            select(kv_store.c.value).where(
                kv_store.c.store_name == store_name,
                kv_store.c.key == key,
            )
        ).scalar_one_or_none()
        return json.loads(value) if value is not None else default


def kv_delete(store_name: str, key: str) -> bool:
    """Remove a single value from a dict collection. Returns whether it existed."""
    ensure_schema()
    with get_engine().begin() as conn:
        result = conn.execute(
            delete(kv_store).where(
                kv_store.c.store_name == store_name,
                kv_store.c.key == key,
            )
        )
        return bool(result.rowcount > 0)


def kv_set(store_name: str, key: str, value: Any) -> None:
    """Atomically persist one record without replacing its collection."""
    ensure_schema()
    payload = json.dumps(value, ensure_ascii=False, default=str)
    engine = get_engine()
    values = {"store_name": store_name, "key": key, "value": payload}
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            statement = postgres_insert(kv_store).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[kv_store.c.store_name, kv_store.c.key],
                set_={"value": payload},
            )
            conn.execute(statement)
            return
        if engine.dialect.name == "sqlite":
            statement = sqlite_insert(kv_store).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[kv_store.c.store_name, kv_store.c.key],
                set_={"value": payload},
            )
            conn.execute(statement)
            return

        result = conn.execute(
            update(kv_store)
            .where(kv_store.c.store_name == store_name, kv_store.c.key == key)
            .values(value=payload)
        )
        if not result.rowcount:
            conn.execute(insert(kv_store).values(**values))


def kv_update(store_name: str, key: str, transform: Callable[[Any], Any]) -> Any:
    """Update one JSON record under a database row lock."""
    ensure_schema()
    engine = get_engine()
    with _runtime_write_transaction(engine) as conn:
        row = conn.execute(
            select(kv_store.c.value)
            .where(kv_store.c.store_name == store_name, kv_store.c.key == key)
            .with_for_update()
        ).first()
        if row is None:
            return None
        current = json.loads(row.value)
        updated_value = transform(current)
        if updated_value is None:
            return current
        conn.execute(
            update(kv_store)
            .where(kv_store.c.store_name == store_name, kv_store.c.key == key)
            .values(value=json.dumps(updated_value, ensure_ascii=False, default=str))
        )
    return updated_value


def kv_insert_if_absent(store_name: str, key: str, value: Any) -> bool:
    """Insert one record only if its primary key is absent."""
    ensure_schema()
    payload = json.dumps(value, ensure_ascii=False, default=str)
    engine = get_engine()
    values = {"store_name": store_name, "key": key, "value": payload}
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            statement = postgres_insert(kv_store).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[kv_store.c.store_name, kv_store.c.key]
            )
            return bool(conn.execute(statement).rowcount)
        if engine.dialect.name == "sqlite":
            statement = sqlite_insert(kv_store).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[kv_store.c.store_name, kv_store.c.key]
            )
            return bool(conn.execute(statement).rowcount)

        exists = conn.execute(
            select(kv_store.c.key).where(
                kv_store.c.store_name == store_name,
                kv_store.c.key == key,
            )
        ).first()
        if exists:
            return False
        conn.execute(insert(kv_store).values(**values))
        return True
