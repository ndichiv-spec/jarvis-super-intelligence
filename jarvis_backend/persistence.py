"""
JARVIS PERSISTENCE LAYER
=========================

Central persistence for all JARVIS state using the EXISTING database
architecture (jarvis_backend/db.py - SQLAlchemy-based).

This layer extends the existing infrastructure WITHOUT creating new databases.
It uses the same engine/database URL resolution as db.py.

Persists:
- conversations
- messages
- capability state
- provider state
- tool executions
- memory entries
- tasks/jobs
- artifacts
- audit events
- learning lineage
- event log
- science solutions
- hypotheses
- learning episodes
- tech technologies
- tech frontiers
- tech predictions
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from sqlalchemy import (
    MetaData, Table, Column, String, Text, Integer, Float, DateTime,
    insert, select, update, delete, and_,
)
from sqlalchemy.engine import Engine

# Use the existing database engine
def get_engine() -> Engine:
    """Get the existing project SQLAlchemy engine."""
    from jarvis_backend.db import get_engine as _get_engine, ensure_schema
    ensure_schema()
    return _get_engine()


# Metadata for our new tables (separate from the existing kv_store)
_capability_metadata = MetaData()

# Table definitions
conversations_table = Table(
    "jarvis_conversations", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("session_id", String(255), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("title", String(500)),
    Column("modality", String(50), nullable=False, default="text"),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column("metadata_json", Text),
    Column("state", String(50), default="active"),
)

messages_table = Table(
    "jarvis_messages", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("conversation_id", String(64), nullable=False),
    Column("session_id", String(255), nullable=False),
    Column("role", String(50), nullable=False),
    Column("modality", String(50), nullable=False, default="text"),
    Column("content", Text),
    Column("content_type", String(50), default="text"),
    Column("timestamp", String(64), nullable=False),
    Column("correlation_id", String(64)),
    Column("parent_message_id", String(64)),
    Column("tool_calls_json", Text),
    Column("tool_results_json", Text),
    Column("provider_used", String(255)),
    Column("model_used", String(255)),
    Column("brain_decision", Text),
    Column("metadata_json", Text),
)

capability_state_table = Table(
    "jarvis_capability_state", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("capability", String(255), nullable=False),
    Column("category", String(255)),
    Column("status", String(50), nullable=False),
    Column("state_json", Text),
    Column("correlation_id", String(64)),
    Column("session_id", String(255)),
    Column("user_id", String(255)),
    Column("started_at", String(64)),
    Column("last_updated", String(64)),
    Column("error", Text),
    Column("metadata_json", Text),
)

provider_state_table = Table(
    "jarvis_provider_state", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("provider_name", String(255), nullable=False),
    Column("capability", String(255)),
    Column("status", String(50), nullable=False),
    Column("latency_ms", Float),
    Column("last_checked", String(64)),
    Column("error", Text),
    Column("metadata_json", Text),
    Column("config_snapshot", Text),
)

tool_executions_table = Table(
    "jarvis_tool_executions", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("capability", String(255), nullable=False),
    Column("tool_name", String(255), nullable=False),
    Column("session_id", String(255)),
    Column("user_id", String(255)),
    Column("correlation_id", String(64)),
    Column("request_json", Text),
    Column("response_json", Text),
    Column("success", Integer),
    Column("error", Text),
    Column("started_at", String(64)),
    Column("completed_at", String(64)),
    Column("duration_ms", Float),
    Column("metadata_json", Text),
)

memory_entries_table = Table(
    "jarvis_memory_entries", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("memory_type", String(50), nullable=False),
    Column("session_id", String(255)),
    Column("user_id", String(255)),
    Column("content", Text),
    Column("embedding_json", Text),
    Column("metadata_json", Text),
    Column("created_at", String(64)),
    Column("accessed_at", String(64)),
    Column("access_count", Integer, default=0),
    Column("provenance", Text),
    Column("expires_at", String(64)),
)

tasks_table = Table(
    "jarvis_tasks", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("user_id", String(255)),
    Column("capability", String(255)),
    Column("title", String(500)),
    Column("description", Text),
    Column("status", String(50), nullable=False, default="pending"),
    Column("priority", Integer, default=0),
    Column("input_json", Text),
    Column("output_json", Text),
    Column("error", Text),
    Column("scheduled_at", String(64)),
    Column("started_at", String(64)),
    Column("completed_at", String(64)),
    Column("retry_count", Integer, default=0),
    Column("max_retries", Integer, default=3),
    Column("parent_task_id", String(64)),
    Column("correlation_id", String(64)),
    Column("metadata_json", Text),
)

artifacts_table = Table(
    "jarvis_artifacts", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("capability", String(255), nullable=False),
    Column("artifact_type", String(255), nullable=False),
    Column("url", String(1000)),
    Column("file_path", String(1000)),
    Column("file_size", Integer),
    Column("mime_type", String(255)),
    Column("metadata_json", Text),
    Column("created_at", String(64)),
    Column("session_id", String(255)),
    Column("conversation_id", String(64)),
    Column("correlation_id", String(64)),
    Column("provenance", Text),
)

audit_events_table = Table(
    "jarvis_audit_events", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("event_type", String(255), nullable=False),
    Column("source", String(255)),
    Column("capability", String(255)),
    Column("user_id", String(255)),
    Column("session_id", String(255)),
    Column("action", String(500)),
    Column("resource", String(500)),
    Column("result", String(100)),
    Column("details", Text),
    Column("ip_address", String(100)),
    Column("timestamp", String(64)),
)

learning_lineage_table = Table(
    "jarvis_learning_lineage", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("stage", String(100), nullable=False),
    Column("parent_id", String(64)),
    Column("experiment_id", String(255)),
    Column("task_id", String(64)),
    Column("checkpoint_id", String(255)),
    Column("model_version", String(255)),
    Column("metrics_json", Text),
    Column("status", String(50)),
    Column("created_at", String(64)),
    Column("approved", Integer, default=0),
    Column("metadata_json", Text),
)

event_log_table = Table(
    "jarvis_event_log", _capability_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", String(128), nullable=False),
    Column("event_type", String(255), nullable=False),
    Column("source", String(255)),
    Column("capability", String(255)),
    Column("correlation_id", String(128)),
    Column("session_id", String(255)),
    Column("user_id", String(255)),
    Column("status", String(50)),
    Column("payload", Text),
    Column("metrics", Text),
    Column("timestamp", String(64)),
)

# ---------------------------------------------------------------------------
# Bio-growth research layer tables
# ---------------------------------------------------------------------------
science_solutions_table = Table(
    "jarvis_science_solutions", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("operation", String(100), nullable=False),
    Column("problem", Text),
    Column("solution_json", Text),
    Column("verified", Integer, default=0),
    Column("processing_time_ms", Float),
    Column("session_id", String(255)),
    Column("user_id", String(255)),
    Column("correlation_id", String(64)),
    Column("created_at", String(64)),
    Column("metadata_json", Text),
)

hypotheses_table = Table(
    "jarvis_hypotheses", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("domain", String(255), nullable=False),
    Column("statement", Text),
    Column("variables_json", Text),
    Column("confidence", Float),
    Column("status", String(50), default="proposed"),
    Column("evidence_json", Text),
    Column("created_at", String(64)),
    Column("evaluated_at", String(64)),
    Column("creator", String(255)),
    Column("metadata_json", Text),
)

learning_episodes_table = Table(
    "jarvis_learning_episodes", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("domain", String(255), nullable=False),
    Column("concept", String(500), nullable=False),
    Column("session_id", String(255)),
    Column("user_id", String(255)),
    Column("quality", Integer, default=0),
    Column("reviewed_at", String(64)),
    Column("next_review_at", String(64)),
    Column("repetitions", Integer, default=0),
    Column("ease_factor", Float, default=2.5),
    Column("interval", Float, default=1.0),
    Column("difficulty", Float, default=0.5),
    Column("mastery_level", Float, default=0.0),
    Column("created_at", String(64)),
    Column("metadata_json", Text),
)

tech_technologies_table = Table(
    "jarvis_tech_technologies", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(500), nullable=False),
    Column("category", String(255)),
    Column("description", Text),
    Column("stage", String(50), default="birth"),
    Column("source", String(255)),
    Column("source_url", String(1000)),
    Column("maturity_score", Float),
    Column("adoption_velocity", Float),
    Column("frontier_tags_json", Text),
    Column("discovered_at", String(64)),
    Column("last_seen", String(64)),
    Column("metadata_json", Text),
)

tech_frontiers_table = Table(
    "jarvis_tech_frontiers", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(500), nullable=False),
    Column("description", Text),
    Column("domains_json", Text),
    Column("technologies_json", Text),
    Column("emergence_score", Float),
    Column("cross_domain", Integer, default=0),
    Column("created_at", String(64)),
    Column("last_updated", String(64)),
    Column("metadata_json", Text),
)

tech_predictions_table = Table(
    "jarvis_tech_predictions", _capability_metadata,
    Column("id", String(64), primary_key=True),
    Column("tech_id", String(64), nullable=False),
    Column("model", String(255)),
    Column("prediction_type", String(100)),
    Column("predicted_value", Float),
    Column("confidence", Float),
    Column("time_horizon", String(100)),
    Column("model_version", String(255)),
    Column("created_at", String(64)),
    Column("metadata_json", Text),
)


def initialize_persistence() -> List[str]:
    """
    Create all capability persistence tables.
    Uses the existing project database engine.
    """
    engine = get_engine()
    _capability_metadata.create_all(engine)
    return [t.name for t in _capability_metadata.tables.values()]


@contextmanager
def db_session():
    """Get a database connection using the existing engine."""
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _json_dump(obj):
    return json.dumps(obj, ensure_ascii=False, default=str) if obj else None


# ============================================================================
# CONVERSATION REPOSITORY
# ============================================================================

class ConversationRepository:
    @staticmethod
    def create_session(session_id, user_id, title=None, modality="text", metadata=None):
        conv_id = f"conv-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(conversations_table).values(
                id=conv_id, session_id=session_id, user_id=user_id,
                title=title or f"Conversation {conv_id[:8]}",
                modality=modality, created_at=now, updated_at=now,
                metadata_json=_json_dump(metadata), state='active'
            ))
        return conv_id

    @staticmethod
    def get_session(session_id):
        with db_session() as conn:
            result = conn.execute(
                select(conversations_table).where(
                    conversations_table.c.session_id == session_id
                ).order_by(conversations_table.c.created_at.desc()).limit(1)
            ).fetchone()
            if result:
                return dict(result._mapping)
        return None

    @staticmethod
    def get_conversation_by_id(conv_id):
        with db_session() as conn:
            result = conn.execute(
                select(conversations_table).where(conversations_table.c.id == conv_id)
            ).fetchone()
            if result:
                return dict(result._mapping)
        return None

    @staticmethod
    def add_message(conversation_id, session_id, role, content, modality="text",
                    correlation_id="", tool_calls=None, tool_results=None,
                    provider_used=None, model_used=None, brain_decision=None,
                    metadata=None):
        msg_id = f"msg-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(messages_table).values(
                id=msg_id, conversation_id=conversation_id, session_id=session_id,
                role=role, modality=modality, content=content, content_type='text',
                timestamp=now, correlation_id=correlation_id,
                tool_calls_json=_json_dump(tool_calls),
                tool_results_json=_json_dump(tool_results),
                provider_used=provider_used, model_used=model_used,
                brain_decision=brain_decision, metadata_json=_json_dump(metadata)
            ))
            conn.execute(
                update(conversations_table).where(
                    conversations_table.c.id == conversation_id
                ).values(updated_at=now)
            )
        return msg_id

    @staticmethod
    def get_messages(conversation_id, limit=100):
        with db_session() as conn:
            result = conn.execute(
                select(messages_table).where(
                    messages_table.c.conversation_id == conversation_id
                ).order_by(messages_table.c.timestamp.asc()).limit(limit)
            ).fetchall()
            return [dict(r._mapping) for r in result]

    @staticmethod
    def update_session_state(conv_id, state, metadata=None):
        with db_session() as conn:
            stmt = update(conversations_table).where(
                conversations_table.c.id == conv_id
            ).values(state=state, updated_at=now_iso())
            if metadata:
                stmt = stmt.values(metadata_json=_json_dump(metadata))
            conn.execute(stmt)


# ============================================================================
# MEMORY REPOSITORY
# ============================================================================

class MemoryRepository:
    @staticmethod
    def store_memory(memory_type, content, session_id=None, user_id=None,
                     embedding=None, metadata=None, provenance=None,
                     expires_at=None):
        mem_id = f"mem-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(memory_entries_table).values(
                id=mem_id, memory_type=memory_type, session_id=session_id,
                user_id=user_id, content=content,
                embedding_json=_json_dump(embedding),
                metadata_json=_json_dump(metadata),
                created_at=now, accessed_at=now, access_count=0,
                provenance=provenance, expires_at=expires_at
            ))
        return mem_id

    @staticmethod
    def retrieve_memories(memory_type=None, session_id=None, user_id=None, limit=20):
        conditions = []
        params = {}
        if memory_type:
            conditions.append(memory_entries_table.c.memory_type == memory_type)
        if session_id:
            conditions.append(memory_entries_table.c.session_id == session_id)
        if user_id:
            conditions.append(memory_entries_table.c.user_id == user_id)

        where_clause = and_(*conditions) if conditions else None
        with db_session() as conn:
            query = select(memory_entries_table)
            if conditions:
                query = query.where(where_clause)
            query = query.order_by(memory_entries_table.c.created_at.desc()).limit(limit)
            result = conn.execute(query).fetchall()
            rows = [dict(r._mapping) for r in result]

            # Update access count
            for row in rows:
                conn.execute(
                    update(memory_entries_table).where(
                        memory_entries_table.c.id == row['id']
                    ).values(
                        accessed_at=now_iso(),
                        access_count=memory_entries_table.c.access_count + 1
                    )
                )
            return rows

    @staticmethod
    def get_episodic_memory(session_id, limit=50):
        """Get episodic memories for a session."""
        return MemoryRepository.retrieve_memories(
            memory_type='episodic', session_id=session_id, limit=limit
        )

    @staticmethod
    def get_working_memory(session_id, limit=20):
        """Get working memory for a session."""
        return MemoryRepository.retrieve_memories(
            memory_type='working', session_id=session_id, limit=limit
        )

    @staticmethod
    def store_working_memory(session_id, content, user_id=None, metadata=None):
        """Store a working memory entry (short-lived context)."""
        return MemoryRepository.store_memory(
            'working', content, session_id=session_id, user_id=user_id,
            metadata=metadata, provenance='conversation'
        )

    @staticmethod
    def store_episodic_memory(session_id, content, user_id=None, metadata=None):
        """Store an episodic memory entry."""
        return MemoryRepository.store_memory(
            'episodic', content, session_id=session_id, user_id=user_id,
            metadata=metadata, provenance='conversation'
        )


# ============================================================================
# TASK REPOSITORY
# ============================================================================

class TaskRepository:
    @staticmethod
    def create_task(user_id, capability, title, description=None, input_data=None,
                    priority=0, scheduled_at=None, max_retries=3,
                    parent_task_id=None, correlation_id="", metadata=None):
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(tasks_table).values(
                id=task_id, user_id=user_id, capability=capability,
                title=title, description=description, status='pending',
                priority=priority, input_json=_json_dump(input_data),
                error=None, scheduled_at=scheduled_at or now,
                started_at=None, completed_at=None,
                retry_count=0, max_retries=max_retries,
                parent_task_id=parent_task_id, correlation_id=correlation_id,
                metadata_json=_json_dump(metadata)
            ))
        return task_id

    @staticmethod
    def update_task(task_id, status, output_data=None, error=None,
                    started_at=None, completed_at=None, retry_count=None):
        updates = {'status': status}
        if output_data is not None:
            updates['output_json'] = _json_dump(output_data)
        if error is not None:
            updates['error'] = error
        if started_at is not None:
            updates['started_at'] = started_at
        if completed_at is not None:
            updates['completed_at'] = completed_at
        if retry_count is not None:
            updates['retry_count'] = retry_count

        with db_session() as conn:
            conn.execute(
                update(tasks_table).where(tasks_table.c.id == task_id).values(**updates)
            )
            return True

    @staticmethod
    def get_task(task_id):
        with db_session() as conn:
            result = conn.execute(
                select(tasks_table).where(tasks_table.c.id == task_id)
            ).fetchone()
            return dict(result._mapping) if result else None

    @staticmethod
    def get_by_status(status, capability=None, limit=100):
        conditions = [tasks_table.c.status == status]
        if capability:
            conditions.append(tasks_table.c.capability == capability)
        with db_session() as conn:
            result = conn.execute(
                select(tasks_table).where(
                    and_(*conditions)
                ).order_by(tasks_table.c.priority.desc(), tasks_table.c.scheduled_at.asc()).limit(limit)
            ).fetchall()
            return [dict(r._mapping) for r in result]

    @staticmethod
    def get_incomplete_tasks():
        """Get tasks that need recovery after restart."""
        with db_session() as conn:
            result = conn.execute(
                select(tasks_table).where(
                    and_(tasks_table.c.status.in_(['pending', 'running', 'paused']))
                ).order_by(tasks_table.c.scheduled_at.asc())
            ).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# ARTIFACT REPOSITORY
# ============================================================================

class ArtifactRepository:
    @staticmethod
    def store_artifact(capability, artifact_type, url=None, file_path=None,
                       file_size=None, mime_type=None, metadata=None,
                       session_id=None, conversation_id=None,
                       correlation_id="", provenance=None):
        art_id = f"art-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(artifacts_table).values(
                id=art_id, capability=capability, artifact_type=artifact_type,
                url=url, file_path=file_path, file_size=file_size,
                mime_type=mime_type, metadata_json=_json_dump(metadata),
                created_at=now, session_id=session_id, conversation_id=conversation_id,
                correlation_id=correlation_id, provenance=provenance
            ))
        return art_id

    @staticmethod
    def get_artifact(artifact_id):
        with db_session() as conn:
            result = conn.execute(
                select(artifacts_table).where(artifacts_table.c.id == artifact_id)
            ).fetchone()
            return dict(result._mapping) if result else None

    @staticmethod
    def get_for_conversation(conversation_id):
        with db_session() as conn:
            result = conn.execute(
                select(artifacts_table).where(
                    artifacts_table.c.conversation_id == conversation_id
                ).order_by(artifacts_table.c.created_at.desc())
            ).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# TOOL EXECUTION LOG REPOSITORY
# ============================================================================

class ToolExecutionLog:
    @staticmethod
    def log_execution(capability, tool_name, request, response, success,
                      error, started_at, completed_at, duration_ms,
                      session_id, user_id, correlation_id, metadata=None):
        exec_id = f"txn-{uuid.uuid4().hex[:12]}"
        with db_session() as conn:
            conn.execute(insert(tool_executions_table).values(
                id=exec_id, capability=capability, tool_name=tool_name,
                session_id=session_id, user_id=user_id, correlation_id=correlation_id,
                request_json=_json_dump(request), response_json=_json_dump(response),
                success=1 if success else 0, error=error,
                started_at=started_at, completed_at=completed_at,
                duration_ms=duration_ms, metadata_json=_json_dump(metadata)
            ))
        return exec_id


# ============================================================================
# PROVIDER STATE REPOSITORY
# ============================================================================

class ProviderStateRepository:
    @staticmethod
    def update_state(provider_name, capability, status, latency_ms=None,
                     error=None, metadata=None, config_snapshot=None):
        state_id = f"prov-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(provider_state_table).values(
                id=state_id, provider_name=provider_name, capability=capability,
                status=status, latency_ms=latency_ms, last_checked=now,
                error=error, metadata_json=_json_dump(metadata),
                config_snapshot=_json_dump(config_snapshot)
            ))
        return state_id

    @staticmethod
    def get_latest_state(provider_name):
        with db_session() as conn:
            result = conn.execute(
                select(provider_state_table).where(
                    provider_state_table.c.provider_name == provider_name
                ).order_by(provider_state_table.c.last_checked.desc()).limit(1)
            ).fetchone()
            return dict(result._mapping) if result else None

    @staticmethod
    def get_all_states():
        with db_session() as conn:
            result = conn.execute(
                select(provider_state_table).order_by(
                    provider_state_table.c.provider_name,
                    provider_state_table.c.last_checked.desc()
                )
            ).fetchall()
            # Get latest for each provider
            latest = {}
            for row in result:
                d = dict(row._mapping)
                if d['provider_name'] not in latest:
                    latest[d['provider_name']] = d
            return list(latest.values())


# ============================================================================
# CAPABILITY STATE REPOSITORY (for recovery)
# ============================================================================

class CapabilityStateRepository:
    @staticmethod
    def save_state(capability, category, status, state_json=None,
                   correlation_id="", session_id=None, user_id=None,
                   started_at=None, error=None, metadata=None):
        state_id = f"cap-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(capability_state_table).values(
                id=state_id, capability=capability, category=category,
                status=status, state_json=_json_dump(state_json),
                correlation_id=correlation_id, session_id=session_id,
                user_id=user_id, started_at=started_at or now,
                last_updated=now, error=error, metadata_json=_json_dump(metadata)
            ))
        return state_id

    @staticmethod
    def get_in_progress():
        """Get capabilities with in_progress status for recovery."""
        with db_session() as conn:
            result = conn.execute(
                select(capability_state_table).where(
                    capability_state_table.c.status == 'in_progress'
                ).order_by(capability_state_table.c.last_updated.desc())
            ).fetchall()
            return [dict(r._mapping) for r in result]

    @staticmethod
    def cleanup_old_snapshots(retention_hours=24):
        """Remove capability state snapshots older than retention period."""
        cutoff = datetime.now(timezone.utc).timestamp() - (retention_hours * 3600)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        with db_session() as conn:
            conn.execute(
                delete(capability_state_table).where(
                    capability_state_table.c.last_updated < cutoff_iso
                )
            )


# ============================================================================
# AUDIT LOG REPOSITORY
# ============================================================================

class AuditLog:
    @staticmethod
    def log(event_type, source="system", capability="", user_id="",
            session_id="", action="", resource="", result="success",
            details=None, ip_address=""):
        audit_id = f"audit-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(audit_events_table).values(
                id=audit_id, event_type=event_type, source=source,
                capability=capability, user_id=user_id, session_id=session_id,
                action=action, resource=resource, result=result,
                details=details, ip_address=ip_address, timestamp=now
            ))
        return audit_id

    @staticmethod
    def get_recent(limit=100):
        with db_session() as conn:
            result = conn.execute(
                select(audit_events_table).order_by(
                    audit_events_table.c.timestamp.desc()
                ).limit(limit)
            ).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# EVENT LOG REPOSITORY
# ============================================================================

class EventLog:
    @staticmethod
    def log_event(event_dict):
        with db_session() as conn:
            conn.execute(insert(event_log_table).values(
                event_id=event_dict.get('event_id', ''),
                event_type=event_dict.get('event_type', ''),
                source=event_dict.get('source', ''),
                capability=event_dict.get('capability', ''),
                correlation_id=event_dict.get('correlation_id', ''),
                session_id=event_dict.get('session_id', ''),
                user_id=event_dict.get('user_id', ''),
                status=event_dict.get('status', ''),
                payload=_json_dump(event_dict.get('payload', {})),
                metrics=_json_dump(event_dict.get('metrics', {})),
                timestamp=event_dict.get('timestamp', now_iso())
            ))

    @staticmethod
    def get_for_correlation(correlation_id):
        with db_session() as conn:
            result = conn.execute(
                select(event_log_table).where(
                    event_log_table.c.correlation_id == correlation_id
                ).order_by(event_log_table.c.timestamp.asc())
            ).fetchall()
            return [dict(r._mapping) for r in result]

    @staticmethod
    def get_recent(limit=100, capability=None):
        with db_session() as conn:
            query = select(event_log_table).order_by(event_log_table.c.id.desc()).limit(limit)
            if capability:
                query = query.where(event_log_table.c.capability == capability)
            result = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# LEARNING LINEAGE REPOSITORY
# ============================================================================

class LearningLineageRepository:
    @staticmethod
    def record_stage(stage, parent_id=None, experiment_id=None, task_id=None,
                     checkpoint_id=None, model_version=None, metrics=None,
                     status='pending', approved=False, metadata=None):
        lineage_id = f"learn-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(learning_lineage_table).values(
                id=lineage_id, stage=stage, parent_id=parent_id,
                experiment_id=experiment_id, task_id=task_id,
                checkpoint_id=checkpoint_id, model_version=model_version,
                metrics_json=_json_dump(metrics), status=status,
                created_at=now, approved=1 if approved else 0,
                metadata_json=_json_dump(metadata)
            ))
        return lineage_id

    @staticmethod
    def get_lineage(task_id):
        with db_session() as conn:
            result = conn.execute(
                select(learning_lineage_table).where(
                    learning_lineage_table.c.task_id == task_id
                ).order_by(learning_lineage_table.c.created_at.asc())
            ).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# SCIENCE SOLUTION REPOSITORY
# ============================================================================

class ScienceSolutionRepository:
    @staticmethod
    def log_solution(operation, problem, solution, verified=False,
                    processing_time_ms=0.0, session_id=None, user_id=None,
                    correlation_id="", metadata=None):
        sol_id = f"sol-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(science_solutions_table).values(
                id=sol_id, operation=operation, problem=problem,
                solution_json=_json_dump(solution), verified=1 if verified else 0,
                processing_time_ms=processing_time_ms, session_id=session_id,
                user_id=user_id, correlation_id=correlation_id,
                created_at=now, metadata_json=_json_dump(metadata)
            ))
        return sol_id

    @staticmethod
    def get_solutions(operation=None, session_id=None, user_id=None, limit=50):
        conditions = []
        if operation:
            conditions.append(science_solutions_table.c.operation == operation)
        if session_id:
            conditions.append(science_solutions_table.c.session_id == session_id)
        if user_id:
            conditions.append(science_solutions_table.c.user_id == user_id)
        where_clause = and_(*conditions) if conditions else None
        with db_session() as conn:
            query = select(science_solutions_table).order_by(
                science_solutions_table.c.created_at.desc()).limit(limit)
            if where_clause:
                query = query.where(where_clause)
            result = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# HYPOTHESIS REPOSITORY
# ============================================================================

class HypothesisRepository:
    @staticmethod
    def propose(domain, statement, variables=None, confidence=0.0, creator=None,
                metadata=None):
        hyp_id = f"hyp-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(hypotheses_table).values(
                id=hyp_id, domain=domain, statement=statement,
                variables_json=_json_dump(variables), confidence=confidence,
                status='proposed', created_at=now, creator=creator,
                metadata_json=_json_dump(metadata)
            ))
        return hyp_id

    @staticmethod
    def update_status(hyp_id, status, evidence=None, confidence=None,
                      evaluated_at=None):
        updates = {'status': status}
        if evidence is not None:
            updates['evidence_json'] = _json_dump(evidence)
        if confidence is not None:
            updates['confidence'] = confidence
        if evaluated_at is not None:
            updates['evaluated_at'] = evaluated_at
        with db_session() as conn:
            conn.execute(
                update(hypotheses_table).where(
                    hypotheses_table.c.id == hyp_id
                ).values(**updates)
            )

    @staticmethod
    def get_hypotheses(domain=None, status=None, limit=50):
        conditions = []
        if domain:
            conditions.append(hypotheses_table.c.domain == domain)
        if status:
            conditions.append(hypotheses_table.c.status == status)
        where_clause = and_(*conditions) if conditions else None
        with db_session() as conn:
            query = select(hypotheses_table).order_by(
                hypotheses_table.c.created_at.desc()).limit(limit)
            if where_clause:
                query = query.where(where_clause)
            result = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# LEARNING EPISODE REPOSITORY
# ============================================================================

class LearningEpisodeRepository:
    @staticmethod
    def record_episode(domain, concept, session_id=None, user_id=None,
                       quality=3, mastery_level=0.0, repetitions=0,
                       ease_factor=2.5, interval=1.0, difficulty=0.5,
                       reviewed_at=None, next_review_at=None, metadata=None):
        ep_id = f"learn-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(learning_episodes_table).values(
                id=ep_id, domain=domain, concept=concept,
                session_id=session_id, user_id=user_id, quality=quality,
                reviewed_at=reviewed_at or now, next_review_at=next_review_at,
                repetitions=repetitions, ease_factor=ease_factor,
                interval=interval, difficulty=difficulty,
                mastery_level=mastery_level, created_at=now,
                metadata_json=_json_dump(metadata)
            ))
        return ep_id

    @staticmethod
    def get_due_reviews(user_id=None, limit=50):
        now = now_iso()
        conditions = [learning_episodes_table.c.next_review_at <= now]
        if user_id:
            conditions.append(learning_episodes_table.c.user_id == user_id)
        with db_session() as conn:
            query = select(learning_episodes_table).where(and_(*conditions)).order_by(
                learning_episodes_table.c.next_review_at.asc()
            ).limit(limit)
            result = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# TECH TECHNOLOGY REPOSITORY
# ============================================================================

class TechTechnologyRepository:
    @staticmethod
    def upsert_technology(name, category=None, description=None, stage="birth",
                          source=None, source_url=None, maturity_score=0.0,
                          adoption_velocity=0.0, frontier_tags=None,
                          discovered_at=None, last_seen=None, metadata=None):
        tech_id = f"tech-{uuid.uuid4().hex[:8]}"
        now = now_iso()
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        with db_session() as conn:
            stmt = pg_insert(tech_technologies_table).values(
                id=tech_id, name=name, category=category, description=description,
                stage=stage, source=source, source_url=source_url,
                maturity_score=maturity_score, adoption_velocity=adoption_velocity,
                frontier_tags_json=_json_dump(frontier_tags),
                discovered_at=discovered_at or now, last_seen=last_seen or now,
                metadata_json=_json_dump(metadata)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['name'],
                set_={
                    'stage': stage, 'category': category,
                    'description': description, 'maturity_score': maturity_score,
                    'adoption_velocity': adoption_velocity,
                    'frontier_tags_json': _json_dump(frontier_tags),
                    'last_seen': last_seen or now,
                    'metadata_json': _json_dump(metadata),
                }
            )
            conn.execute(stmt)
        return tech_id

    @staticmethod
    def get_technologies(stage=None, category=None, limit=100):
        conditions = []
        if stage:
            conditions.append(tech_technologies_table.c.stage == stage)
        if category:
            conditions.append(tech_technologies_table.c.category == category)
        where_clause = and_(*conditions) if conditions else None
        with db_session() as conn:
            query = select(tech_technologies_table).order_by(
                tech_technologies_table.c.discovered_at.desc()
            ).limit(limit)
            if where_clause:
                query = query.where(where_clause)
            result = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# TECH FRONTIER REPOSITORY
# ============================================================================

class TechFrontierRepository:
    @staticmethod
    def upsert_frontier(name, description=None, domains=None, technologies=None,
                        emergence_score=0.0, cross_domain=False, metadata=None):
        frontier_id = f"front-{uuid.uuid4().hex[:8]}"
        now = now_iso()
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        with db_session() as conn:
            stmt = pg_insert(tech_frontiers_table).values(
                id=frontier_id, name=name, description=description,
                domains_json=_json_dump(domains), technologies_json=_json_dump(technologies),
                emergence_score=emergence_score, cross_domain=1 if cross_domain else 0,
                created_at=now, last_updated=now, metadata_json=_json_dump(metadata)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['name'],
                set_={
                    'description': description,
                    'domains_json': _json_dump(domains),
                    'technologies_json': _json_dump(technologies),
                    'emergence_score': emergence_score,
                    'cross_domain': 1 if cross_domain else 0,
                    'last_updated': now,
                    'metadata_json': _json_dump(metadata),
                }
            )
            conn.execute(stmt)
        return frontier_id

    @staticmethod
    def get_frontiers(cross_domain_only=False, limit=50):
        with db_session() as conn:
            query = select(tech_frontiers_table).order_by(
                tech_frontiers_table.c.emergence_score.desc()
            ).limit(limit)
            if cross_domain_only:
                query = query.where(tech_frontiers_table.c.cross_domain == 1)
            result = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in result]


# ============================================================================
# TECH PREDICTION REPOSITORY
# ============================================================================

class TechPredictionRepository:
    @staticmethod
    def record_prediction(tech_id, model, prediction_type, predicted_value,
                          confidence=0.0, time_horizon="1y",
                          model_version="1.0.0", metadata=None):
        pred_id = f"pred-{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with db_session() as conn:
            conn.execute(insert(tech_predictions_table).values(
                id=pred_id, tech_id=tech_id, model=model,
                prediction_type=prediction_type, predicted_value=predicted_value,
                confidence=confidence, time_horizon=time_horizon,
                model_version=model_version, created_at=now,
                metadata_json=_json_dump(metadata)
            ))
        return pred_id

    @staticmethod
    def get_predictions(tech_id=None, model=None, limit=50):
        conditions = []
        if tech_id:
            conditions.append(tech_predictions_table.c.tech_id == tech_id)
        if model:
            conditions.append(tech_predictions_table.c.model == model)
        where_clause = and_(*conditions) if conditions else None
        with db_session() as conn:
            query = select(tech_predictions_table).order_by(
                tech_predictions_table.c.created_at.desc()
            ).limit(limit)
            if where_clause:
                query = query.where(where_clause)
            result = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in result]


__all__ = [
    'initialize_persistence',
    'ConversationRepository',
    'MemoryRepository',
    'TaskRepository',
    'ArtifactRepository',
    'ToolExecutionLog',
    'ProviderStateRepository',
    'CapabilityStateRepository',
    'AuditLog',
    'EventLog',
    'LearningLineageRepository',
    'ScienceSolutionRepository',
    'HypothesisRepository',
    'LearningEpisodeRepository',
    'TechTechnologyRepository',
    'TechFrontierRepository',
    'TechPredictionRepository',
]
