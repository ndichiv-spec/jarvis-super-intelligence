"""
Audit Events System for JARVIS Control Plane.

Provides durable, queryable audit logging for all control plane operations.

Phase 2 compliance:
- PostgreSQL-backed audit event storage
- Event categorization (auth, model, provider, job, cost, routing)
- Provenance tracking
- Queryable by user, resource, time range, event type
- Compliance-ready (GDPR, SOC2, etc.)
"""

from __future__ import annotations

import logging
import time
import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import (
    Column,
    String,
    Text,
    JSON,
    Float,
    Integer,
    Boolean,
    Index,
    func,
    text,
)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger("audit_events")

# --------------------------------------------------------------------------- #
# Event categories
# --------------------------------------------------------------------------- #

class EventCategory(str, Enum):
    """Categories of audit events."""
    AUTHENTICATION = "authentication"      # Login, logout, token issues
    AUTHORIZATION = "authorization"      # Access denied, role changes
    MODEL_REGISTRY = "model_registry"    # Model lifecycle, promotion
    PROVIDER_REGISTRY = "provider_registry"  # Provider health, verification
    ARTIFACT_REGISTRY = "artifact_registry"  # Artifact access, storage
    JOB_REGISTRY = "job_registry"        # Job creation, status changes
    COST_ACCOUNTING = "cost_accounting"  # Cost events, budget
    ROUTING = "routing"                  # Routing decisions, policy
    SYSTEM = "system"                    # System events, maintenance
    DATA_ACCESS = "data_access"          # Data reads, exports
    SECURITY = "security"              # Security events, breaches


# --------------------------------------------------------------------------- #
# Event severity
# --------------------------------------------------------------------------- #

class EventSeverity(str, Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# --------------------------------------------------------------------------- #
# Audit Event SQLAlchemy model
# --------------------------------------------------------------------------- #

Base = declarative_base()


class AuditEventRecord(Base):
    """SQLAlchemy model for audit events."""
    __tablename__ = "audit_events"
    
    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Event identifier
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    
    # Timestamp (indexed for time-range queries)
    timestamp = Column(Float, default=time.time, index=True)
    timestamp_iso = Column(String(64), nullable=False)  # ISO format for readability
    
    # Event categorization
    category = Column(String(32), nullable=False, index=True)
    severity = Column(String(32), default="info", index=True)
    event_type = Column(String(128), nullable=False, index=True)
    
    # Actor information
    user_id = Column(String(64), nullable=True, index=True)
    user_email = Column(String(255), nullable=True)
    user_roles = Column(JSON, default=[])
    actor_type = Column(String(32), default="user")  # user, system, api_key
    
    # Resource information
    resource_type = Column(String(64), nullable=True, index=True)
    resource_id = Column(String(255), nullable=True, index=True)
    resource_name = Column(String(255), nullable=True)
    
    # Action and result
    action = Column(String(128), nullable=False)
    result = Column(String(32), default="success")  # success, failure, denied
    message = Column(Text, nullable=True)
    
    # Provenance and context
    request_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(64), nullable=True)
    correlation_id = Column(String(64), nullable=True)  # For related events
    
    # Request context
    client_ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    path = Column(String(512), nullable=True)
    method = Column(String(16), nullable=True)
    
    # Before/after state for changes
    before_state = Column(JSON, default={})
    after_state = Column(JSON, default={})
    
    # Changes made (for diff tracking)
    changes = Column(JSON, default=[])
    
    # Metadata
    event_metadata = Column(JSON, default={})
    tags = Column(JSON, default=[])
    
    # Performance/usage info
    duration_ms = Column(Float, nullable=True)
    cost_usd = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    
    # Indexing
    __table_args__ = (
        Index("idx_events_category", "category"),
        Index("idx_events_user", "user_id"),
        Index("idx_events_resource", "resource_type", "resource_id"),
        Index("idx_events_time", "timestamp"),
        Index("idx_events_type", "event_type"),
    )


# --------------------------------------------------------------------------- #
# Dataclass for API compatibility
# --------------------------------------------------------------------------- #

@dataclass
class AuditEvent:
    """Audit event for API responses."""
    id: str
    event_id: str
    timestamp: float
    timestamp_iso: str
    category: str
    severity: str
    event_type: str
    user_id: str = ""
    user_email: str = ""
    user_roles: List[str] = field(default_factory=list)
    actor_type: str = "user"
    resource_type: str = ""
    resource_id: str = ""
    resource_name: str = ""
    action: str = ""
    result: str = "success"
    message: str = ""
    request_id: str = ""
    session_id: str = ""
    correlation_id: str = ""
    client_ip: str = ""
    user_agent: str = ""
    path: str = ""
    method: str = ""
    before_state: Dict[str, Any] = field(default_factory=dict)
    after_state: Dict[str, Any] = field(default_factory=dict)
    changes: List[Dict[str, Any]] = field(default_factory=list)
    event_metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    duration_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    tokens_used: Optional[int] = None
    
    @classmethod
    def from_record(cls, record: AuditEventRecord) -> "AuditEvent":
        """Create AuditEvent from SQLAlchemy model record."""
        return cls(
            id=record.id,
            event_id=record.event_id,
            timestamp=record.timestamp or 0.0,
            timestamp_iso=record.timestamp_iso or "",
            category=record.category,
            severity=record.severity or "info",
            event_type=record.event_type,
            user_id=record.user_id or "",
            user_email=record.user_email or "",
            user_roles=record.user_roles or [],
            actor_type=record.actor_type or "user",
            resource_type=record.resource_type or "",
            resource_id=record.resource_id or "",
            resource_name=record.resource_name or "",
            action=record.action,
            result=record.result or "success",
            message=record.message or "",
            request_id=record.request_id or "",
            session_id=record.session_id or "",
            correlation_id=record.correlation_id or "",
            client_ip=record.client_ip or "",
            user_agent=record.user_agent or "",
            path=record.path or "",
            method=record.method or "",
            before_state=record.before_state or {},
            after_state=record.after_state or {},
            changes=record.changes or [],
            event_metadata=record.event_metadata or {},
            tags=record.tags or [],
            duration_ms=record.duration_ms,
            cost_usd=record.cost_usd,
            tokens_used=record.tokens_used,
        )


# --------------------------------------------------------------------------- #
# Audit Events Service
# --------------------------------------------------------------------------- #

class AuditEventService:
    """
    Audit event logging service backed by PostgreSQL.
    
    Provides secure, durable logging of all audit-relevant events
    for compliance and operational visibility.
    """
    
    _instance: Optional["AuditEventService"] = None
    
    def __init__(self, engine=None):
        """Initialize with optional SQLAlchemy engine."""
        self._engine = engine
        self._tables_created = False
        self._enabled = True
    
    @classmethod
    def get_instance(cls, engine=None) -> "AuditEventService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(engine)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None
    
    def _get_engine(self):
        """Get SQLAlchemy engine, using existing db module."""
        if self._engine:
            return self._engine
        from jarvis_backend.db import get_engine
        return get_engine()
    
    def _ensure_tables(self) -> None:
        """Ensure audit tables exist."""
        if self._tables_created:
            return
        
        engine = self._engine or self._get_engine()
        
        # Create tables if they don't exist
        with engine.begin() as conn:
            from sqlalchemy import inspect
            inspector = inspect(conn)
            if "audit_events" not in inspector.get_table_names():
                Base.metadata.create_all(conn)
        
        self._tables_created = True
    
    # ----------------------------------------------------------------------- #
    # Event Logging
    # ----------------------------------------------------------------------- #
    
    def log_event(self, event: AuditEvent) -> bool:
        """Log an audit event."""
        if not self._enabled:
            return False
        
        self._ensure_tables()
        
        from sqlalchemy import insert
        engine = self._get_engine()
        
        try:
            with engine.begin() as conn:
                conn.execute(insert(AuditEventRecord).values({
                    "event_id": event.event_id,
                    "timestamp": event.timestamp,
                    "timestamp_iso": event.timestamp_iso,
                    "category": event.category,
                    "severity": event.severity,
                    "event_type": event.event_type,
                    "user_id": event.user_id,
                    "user_email": event.user_email,
                    "user_roles": event.user_roles,
                    "actor_type": event.actor_type,
                    "resource_type": event.resource_type,
                    "resource_id": event.resource_id,
                    "resource_name": event.resource_name,
                    "action": event.action,
                    "result": event.result,
                    "message": event.message,
                    "request_id": event.request_id,
                    "session_id": event.session_id,
                    "correlation_id": event.correlation_id,
                    "client_ip": event.client_ip,
                    "user_agent": event.user_agent,
                    "path": event.path,
                    "method": event.method,
                    "before_state": event.before_state,
                    "after_state": event.after_state,
                    "changes": event.changes,
                    "event_metadata": event.event_metadata,
                    "tags": event.tags,
                    "duration_ms": event.duration_ms,
                    "cost_usd": event.cost_usd,
                    "tokens_used": event.tokens_used,
                }))
            return True
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            return False
    
    def record(
        self,
        event_type: str,
        category: str = "system",
        severity: str = "info",
        action: str = "",
        result: str = "success",
        message: str = "",
        user_id: str = "",
        user_email: str = "",
        user_roles: Optional[List[str]] = None,
        resource_type: str = "",
        resource_id: str = "",
        request_id: str = "",
        session_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        changes: Optional[List[Dict[str, Any]]] = None,
        duration_ms: Optional[float] = None,
        cost_usd: Optional[float] = None,
    ) -> str:
        """
        Record an audit event with convenience parameters.
        
        Returns the event_id.
        """
        now = time.time()
        event_id = str(uuid.uuid4())
        
        event = AuditEvent(
            id=event_id,
            event_id=event_id,
            timestamp=now,
            timestamp_iso=datetime.utcfromtimestamp(now).isoformat() + "Z",
            category=category,
            severity=severity,
            event_type=event_type,
            user_id=user_id,
            user_email=user_email,
            user_roles=user_roles or [],
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            result=result,
            message=message,
            request_id=request_id,
            session_id=session_id,
            event_metadata=metadata or {},
            before_state=before_state or {},
            after_state=after_state or {},
            changes=changes or [],
            duration_ms=duration_ms,
            cost_usd=cost_usd,
        )
        
        self.log_event(event)
        return event_id
    
    # ----------------------------------------------------------------------- #
    # Event Queries
    # ----------------------------------------------------------------------- #
    
    def query_events(
        self,
        category: Optional[str] = None,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        severity: Optional[str] = None,
        result: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events with filters."""
        self._ensure_tables()
        
        from sqlalchemy import select, and_, or_
        engine = self._get_engine()
        
        query = select(AuditEventRecord)
        conditions = []
        
        if category:
            conditions.append(AuditEventRecord.category == category)
        if event_type:
            conditions.append(AuditEventRecord.event_type == event_type)
        if user_id:
            conditions.append(AuditEventRecord.user_id == user_id)
        if resource_type:
            conditions.append(AuditEventRecord.resource_type == resource_type)
        if resource_id:
            conditions.append(AuditEventRecord.resource_id == resource_id)
        if start_time:
            conditions.append(AuditEventRecord.timestamp >= start_time)
        if end_time:
            conditions.append(AuditEventRecord.timestamp <= end_time)
        if severity:
            conditions.append(AuditEventRecord.severity == severity)
        if result:
            conditions.append(AuditEventRecord.result == result)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        with engine.connect() as conn:
            records = conn.execute(
                query.offset(offset).limit(limit).fetchall()
            )
        
        return [AuditEvent.from_record(r) for r in records]
    
    def get_user_activity(
        self,
        user_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Get activity history for a user."""
        return self.query_events(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    
    def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Get change history for a resource."""
        return self.query_events(
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
        )
    
    def get_security_events(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Get security-related events."""
        return self.query_events(
            category="security",
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    
    def count_events(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> int:
        """Count events matching filters."""
        self._ensure_tables()
        
        from sqlalchemy import select, func, and_
        engine = self._get_engine()
        
        conditions = []
        
        if category:
            conditions.append(AuditEventRecord.category == category)
        if severity:
            conditions.append(AuditEventRecord.severity == severity)
        if start_time:
            conditions.append(AuditEventRecord.timestamp >= start_time)
        if end_time:
            conditions.append(AuditEventRecord.timestamp <= end_time)
        
        query = select(func.count(AuditEventRecord.id))
        if conditions:
            query = query.where(and_(*conditions))
        
        with engine.connect() as conn:
            return conn.execute(query).scalar_one_or_none() or 0
    
    def enable(self) -> None:
        """Enable audit logging."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable audit logging."""
        self._enabled = False
    
    def cleanup_old_events(
        self,
        retention_days: int = 90,
        dry_run: bool = False,
    ) -> int:
        """
        Remove events older than retention period.
        
        Returns count of deleted events.
        """
        self._ensure_tables()
        
        from sqlalchemy import text
        engine = self._get_engine()
        
        cutoff = time.time() - (retention_days * 86400)
        
        with engine.begin() as conn:
            if dry_run:
                result = conn.execute(
                    select(func.count(AuditEventRecord.id)).where(
                        AuditEventRecord.timestamp < cutoff
                    )
                )
                return result.scalar_one_or_none() or 0
            else:
                result = conn.execute(
                    text("DELETE FROM audit_events WHERE timestamp < :cutoff"),
                    {"cutoff": cutoff}
                )
                return result.rowcount


# --------------------------------------------------------------------------- #
# Convenience logging functions
# --------------------------------------------------------------------------- #

_audit_service: Optional[AuditEventService] = None


def get_audit_service() -> AuditEventService:
    """Get the global audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditEventService()
    return _audit_service


def audit_event(
    event_type: str,
    category: str = "system",
    severity: str = "info",
    **kwargs: Any,
) -> str:
    """Convenience function to log an audit event."""
    return get_audit_service().record(
        event_type=event_type,
        category=category,
        severity=severity,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Pre-defined event loggers for common patterns
# --------------------------------------------------------------------------- #

def audit_model_promotion(
    model_id: str,
    from_status: str,
    to_status: str,
    reason: str,
    user_id: str = "",
    user_email: str = "",
) -> str:
    """Log model promotion event."""
    return get_audit_service().record(
        event_type="model.promotion",
        category="model_registry",
        severity="info",
        action=f"promote_model_{from_status}_to_{to_status}",
        result="success",
        resource_type="model",
        resource_id=model_id,
        user_id=user_id,
        user_email=user_email,
        message=reason,
        before_state={"lifecycle_status": from_status},
        after_state={"lifecycle_status": to_status},
        changes=[{
            "field": "lifecycle_status",
            "from": from_status,
            "to": to_status,
        }],
    )


def audit_provider_health_change(
    provider_id: str,
    from_state: str,
    to_state: str,
    message: str = "",
) -> str:
    """Log provider health change event."""
    return get_audit_service().record(
        event_type="provider.health_change",
        category="provider_registry",
        severity="warning" if to_state in ("offline", "auth_error") else "info",
        action=f"health_change_{from_state}_to_{to_state}",
        result="success",
        resource_type="provider",
        resource_id=provider_id,
        message=message,
        before_state={"health_state": from_state},
        after_state={"health_state": to_state},
    )


def audit_job_creation(
    job_id: str,
    job_type: str,
    user_id: str = "",
    user_email: str = "",
    model_id: str = "",
) -> str:
    """Log job creation event."""
    return get_audit_service().record(
        event_type="job.created",
        category="job_registry",
        severity="info",
        action="create_job",
        result="success",
        resource_type="job",
        resource_id=job_id,
        user_id=user_id,
        user_email=user_email,
        metadata={"job_type": job_type, "model_id": model_id},
    )


def audit_cost_event(
    provider_id: str,
    model_id: str,
    cost_usd: float,
    user_id: str = "",
    request_id: str = "",
) -> str:
    """Log cost event."""
    return get_audit_service().record(
        event_type="cost.incurred",
        category="cost_accounting",
        severity="info",
        action="record_cost",
        result="success",
        resource_type="billing",
        user_id=user_id,
        request_id=request_id,
        cost_usd=cost_usd,
        metadata={
            "provider_id": provider_id,
            "model_id": model_id,
        },
    )


def audit_routing_decision(
    selected_provider: str,
    selected_model: str,
    capability: str,
    user_id: str = "",
    cost_estimate: Optional[float] = None,
    fallback_used: bool = False,
) -> str:
    """Log routing decision event."""
    return get_audit_service().record(
        event_type="routing.decision",
        category="routing",
        severity="info",
        action="route",
        result="success",
        resource_type="routing",
        user_id=user_id,
        metadata={
            "selected_provider": selected_provider,
            "selected_model": selected_model,
            "capability": capability,
            "cost_estimate": cost_estimate,
            "fallback_used": fallback_used,
        },
    )