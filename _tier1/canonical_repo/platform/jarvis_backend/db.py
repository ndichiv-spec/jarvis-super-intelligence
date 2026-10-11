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
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    inspect as sqlalchemy_inspect,
    insert,
    select,
)
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

# Additive runtime tables. Existing command and application data remains in
# jarvis_kv; these indexed tables provide atomic execution claims and replay.
runtime_executions = Table(
    "jarvis_runtime_executions",
    metadata,
    Column("execution_id", String(36), primary_key=True),
    Column("command_id", String(36), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("plan_id", String(36)),
    Column("step_id", String(255)),
    Column("attempt", Integer, nullable=False, default=1),
    Column("worker_id", String(128)),
    Column("status", String(32), nullable=False),
    Column("idempotency_key", String(255), unique=True),
    Column("lease_started", Float),
    Column("lease_expires", Float),
    Column("heartbeat_at", Float),
    Column("created_at", Float, nullable=False),
    Column("started_at", Float),
    Column("completed_at", Float),
    Column("result", Text),
    Column("error", Text),
    Column("metadata", Text, nullable=False, default="{}"),
)
Index("ix_jarvis_runtime_executions_command", runtime_executions.c.command_id)
Index("ix_jarvis_runtime_executions_user_status", runtime_executions.c.user_id,
      runtime_executions.c.status)

runtime_plans = Table(
    "jarvis_runtime_plans",
    metadata,
    Column("plan_id", String(36), primary_key=True),
    Column("command_id", String(36), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("objective", Text, nullable=False),
    Column("required_capabilities", Text, nullable=False, default="[]"),
    Column("required_permissions", Text, nullable=False, default="[]"),
    Column("estimated_complexity", String(32), nullable=False, default="unknown"),
    Column("status", String(32), nullable=False),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
)
Index("ix_jarvis_runtime_plans_command", runtime_plans.c.command_id)

runtime_plan_steps = Table(
    "jarvis_runtime_plan_steps",
    metadata,
    Column("plan_id", String(36), primary_key=True),
    Column("step_id", String(255), primary_key=True),
    Column("objective", Text, nullable=False),
    Column("capability", String(255), nullable=False),
    Column("input", Text, nullable=False, default="{}"),
    Column("dependencies", Text, nullable=False, default="[]"),
    Column("timeout", Integer),
    Column("retry_policy", Text, nullable=False, default="{}"),
    Column("authorization", Text, nullable=False, default="{}"),
    Column("verification", Text, nullable=False, default="{}"),
    Column("status", String(32), nullable=False),
    Column("result", Text),
)
Index("ix_jarvis_runtime_plan_steps_plan", runtime_plan_steps.c.plan_id)

runtime_events = Table(
    "jarvis_runtime_events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("command_id", String(36), nullable=False),
    Column("execution_id", String(36)),
    Column("step_id", String(255)),
    Column("sequence", Integer, nullable=False),
    Column("timestamp", Float, nullable=False),
    Column("type", String(128), nullable=False),
    Column("status", String(32)),
    Column("payload", Text, nullable=False, default="{}"),
    UniqueConstraint("command_id", "sequence", name="uq_runtime_event_command_sequence"),
)
Index("ix_jarvis_runtime_events_command", runtime_events.c.command_id,
      runtime_events.c.sequence)

runtime_event_sequences = Table(
    "jarvis_runtime_event_sequences",
    metadata,
    Column("command_id", String(36), primary_key=True),
    Column("last_sequence", Integer, nullable=False),
)

endpoints = Table(
    "jarvis_endpoints",
    metadata,
    Column("endpoint_id", String(36), primary_key=True),
    Column("owner_id", String(255), nullable=False),
    Column("status", String(32), nullable=False),
    Column("is_active", Boolean, nullable=False, default=False),
    Column("version", Integer, nullable=False, default=1),
    Column("payload", Text, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
)
Index("ix_jarvis_endpoints_owner", endpoints.c.owner_id, endpoints.c.status)

endpoint_audit_events = Table(
    "jarvis_endpoint_audit_events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("endpoint_id", String(36), nullable=False),
    Column("owner_id", String(255), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("timestamp", Float, nullable=False),
    Column("payload", Text, nullable=False, default="{}"),
)
Index("ix_jarvis_endpoint_audit_owner", endpoint_audit_events.c.owner_id,
      endpoint_audit_events.c.timestamp)

infrastructure_resources = Table(
    "jarvis_infrastructure_resources",
    metadata,
    Column("resource_id", String(36), primary_key=True),
    Column("owner_id", String(255), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("resource_type", String(64), nullable=False),
    Column("name", String(128), nullable=False),
    Column("base_url", String(2048), nullable=False),
    Column("hostname", String(253), nullable=False),
    Column("port", Integer, nullable=False),
    Column("api_version", String(32), nullable=False),
    Column("connection_method", String(64), nullable=False),
    Column("auth_mechanism", String(64), nullable=False),
    Column("allowed_operations", Text, nullable=False),
    Column("permission_scope", Text, nullable=False),
    Column("network_policy", Text, nullable=False),
    Column("timeout_seconds", Integer, nullable=False),
    Column("health_policy", Text, nullable=False),
    Column("credential_ref", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("last_verified_at", Float),
    Column("verified_identity", Text),
    Column("sanitized_error", String(256)),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
)
Index(
    "ix_jarvis_infrastructure_resources_owner",
    infrastructure_resources.c.owner_id,
    infrastructure_resources.c.provider,
    infrastructure_resources.c.status,
)

infrastructure_resource_audit_events = Table(
    "jarvis_infrastructure_resource_audit_events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("resource_id", String(36), nullable=False),
    Column("owner_id", String(255), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("timestamp", Float, nullable=False),
    Column("payload", Text, nullable=False, default="{}"),
)
Index(
    "ix_jarvis_infrastructure_resource_audit_owner",
    infrastructure_resource_audit_events.c.owner_id,
    infrastructure_resource_audit_events.c.timestamp,
)

presentation_revisions = Table(
    "jarvis_presentation_revisions",
    metadata,
    Column("revision_id", String(36), primary_key=True),
    Column("task_id", String(255), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("owner_id", String(255), nullable=False),
    Column("request_id", String(255), nullable=False),
    Column("conversation_id", String(255)),
    Column("command_id", String(255)),
    Column("execution_id", String(255)),
    Column("endpoint_id", String(36)),
    Column("contract_version", String(16), nullable=False),
    Column("presentation", Text, nullable=False),
    Column("compatibility", Text, nullable=False, default="{}"),
    Column("fallback_reason", Text),
    Column("idempotency_key", String(255), unique=True),
    Column("created_at", Float, nullable=False),
    UniqueConstraint("task_id", "revision", name="uq_jarvis_presentation_task_revision"),
)
Index("ix_jarvis_presentation_owner_task", presentation_revisions.c.owner_id,
      presentation_revisions.c.task_id, presentation_revisions.c.revision)

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
        url = Path(os.environ["DATABASE_URL_FILE"]).read_text(encoding="utf-8").strip()
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
                    _engine = create_engine(url)
    return _engine


def ensure_schema() -> None:
    """Create the persistence tables if they do not yet exist (idempotent)."""
    global _ready
    if _ready:
        return
    with _ready_lock:
        if not _ready:
            engine = get_engine()
            if os.environ.get("JARVIS_REQUIRE_PREMIGRATED_SCHEMA") == "1":
                existing = set(sqlalchemy_inspect(engine).get_table_names())
                missing = set(metadata.tables) - existing
                if missing:
                    raise RuntimeError(
                        "Database schema is incomplete; run the controlled "
                        f"migration before starting JARVIS. Missing tables: {', '.join(sorted(missing))}"
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
        conn.execute(delete(kv_store))
        conn.execute(delete(endpoint_audit_events))
        conn.execute(delete(endpoints))
        conn.execute(delete(presentation_revisions))


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
