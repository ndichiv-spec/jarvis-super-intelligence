"""
Durable Job Registry - PostgreSQL-backed job tracking for training/inference.

Provides a canonical JobRegistry that persists job metadata in PostgreSQL.

Phase 2 compliance:
- Tracks training jobs, inference jobs, and other job types
- Full job lifecycle state management (pending, running, completed, failed, cancelled)
- Resource allocation tracking (CPU, memory, GPU)
- Cost estimation and actual cost tracking
- Artifact association (input/output artifacts, model artifacts)
- User and audit information
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    JSON,
    Float,
    Boolean,
    Index,
    func,
    update,
    select,
    insert,
    or_,
)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger("job_registry")

# --------------------------------------------------------------------------- #
# Job types
# --------------------------------------------------------------------------- #

class JobType(str, Enum):
    """Types of jobs in the registry."""
    TRAINING = "training"
    FINE_TUNING = "fine_tuning"
    INFERENCE = "inference"
    EVALUATION = "evaluation"
    DEPLOYMENT = "deployment"
    MIGRATION = "migration"
    CLEANUP = "cleanup"
    OTHER = "other"


# --------------------------------------------------------------------------- #
# Job lifecycle states
# --------------------------------------------------------------------------- #

class JobStatus(str, Enum):
    """Job lifecycle states."""
    PENDING = "pending"       # Created, not yet started
    QUEUED = "queued"       # Waiting for resources
    RUNNING = "running"       # Active execution
    PAUSED = "paused"         # Temporarily stopped
    COMPLETED = "completed"   # Finished successfully
    FAILED = "failed"         # Error during execution
    CANCELLED = "cancelled"   # Request to stop
    TIMEOUT = "timeout"       # Exceeded time limit
    RETRYING = "retrying"     # Will retry
    ARCHIVED = "archived"     # Retired/preserved


# --------------------------------------------------------------------------- #
# SQLAlchemy model
# --------------------------------------------------------------------------- #

Base = declarative_base()


class JobRecord(Base):
    """SQLAlchemy model for durable job registry."""
    __tablename__ = "jobs"
    
    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Job identifier
    job_id = Column(String(255), nullable=False, unique=True, index=True)
    
    # Type and status
    job_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), default="pending", index=True)
    
    # User and ownership
    user_id = Column(String(64), nullable=True, index=True)  # Internal user ID
    user_email = Column(String(255), nullable=True, index=True)  # User email for audit
    requester = Column(String(128), nullable=True)  # Who requested the job
    
    # Parent/child relationships
    parent_job_id = Column(String(64), nullable=True, index=True)
    related_model_id = Column(String(255), nullable=True, index=True)
    
    # Model information
    model_id = Column(String(255), nullable=True, index=True)  # Model this job uses/trains
    model_version = Column(String(128), nullable=True)
    
    # Resource allocation
    resource_cpu = Column(Float, default=1.0)  # CPU cores
    resource_memory_gb = Column(Float, default=1.0)  # GB RAM
    resource_gpu = Column(Integer, default=0)  # Number of GPUs
    resource_gpu_type = Column(String(64), nullable=True)  # a100, h100, etc.
    resource_instance_type = Column(String(64), nullable=True)  # Cloud instance type
    
    # Timing
    scheduled_at = Column(Float, default=0.0)  # When scheduled
    started_at = Column(Float, nullable=True)  # When execution started
    completed_at = Column(Float, nullable=True)  # When finished
    duration_seconds = Column(Float, nullable=True)  # Actual duration
    
    # Cost tracking
    estimated_cost_usd = Column(Float, default=0.0)  # Estimated cost
    actual_cost_usd = Column(Float, nullable=True)  # Actual cost
    cost_currency = Column(String(8), default="USD")
    
    # Retry policy
    max_retries = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    retry_delay_seconds = Column(Float, default=60.0)
    
    # Configuration
    config = Column(JSON, default={})  # Job-specific configuration
    parameters = Column(JSON, default={})  # Hyperparameters, etc.
    
    # Artifact association
    input_artifacts = Column(JSON, default=[])  # Artifact IDs as input
    output_artifacts = Column(JSON, default=[])  # Artifact IDs as output
    
    # Results
    result = Column(JSON, default={})  # Output/results
    output_uri = Column(String(1024), nullable=True)  # Where results are stored
    
    # Error information
    error_message = Column(Text, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_traceback = Column(Text, nullable=True)
    
    # Priority and scheduling
    priority = Column(Integer, default=0)  # Higher = more important
    queue_position = Column(Integer, nullable=True)  # Current position in queue
    
    # Tags and metadata
    tags = Column(JSON, default=[])  # String tags for categorization
    job_data = Column(JSON, default={})
    
    # Audit information
    created_by = Column(String(64), nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    
    # Indexing
    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_type", "job_type"),
        Index("idx_jobs_user", "user_id"),
        Index("idx_jobs_model", "model_id"),
        Index("idx_jobs_scheduled", "scheduled_at"),
        Index("idx_jobs_priority", "priority"),
    )


# --------------------------------------------------------------------------- #
# Dataclass for API compatibility
# --------------------------------------------------------------------------- #

@dataclass
class JobInfo:
    """Job information for API responses."""
    id: str
    job_id: str
    job_type: str
    status: str = "pending"
    user_id: Optional[str] = None
    user_email: str = ""
    requester: str = ""
    parent_job_id: Optional[str] = None
    related_model_id: Optional[str] = None
    model_id: Optional[str] = None
    model_version: str = ""
    resource_cpu: float = 1.0
    resource_memory_gb: float = 1.0
    resource_gpu: int = 0
    resource_gpu_type: str = ""
    resource_instance_type: str = ""
    scheduled_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_seconds: Optional[float] = None
    estimated_cost_usd: float = 0.0
    actual_cost_usd: Optional[float] = None
    cost_currency: str = "USD"
    max_retries: int = 0
    retry_count: int = 0
    retry_delay_seconds: float = 60.0
    config: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    input_artifacts: List[str] = field(default_factory=list)
    output_artifacts: List[str] = field(default_factory=list)
    result: Dict[str, Any] = field(default_factory=dict)
    output_uri: str = ""
    error_message: str = ""
    error_code: str = ""
    error_traceback: str = ""
    priority: int = 0
    queue_position: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    job_data: Dict[str, Any] = field(default_factory=dict)
    created_by: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    
    @classmethod
    def from_record(cls, record: JobRecord) -> "JobInfo":
        """Create JobInfo from SQLAlchemy model record."""
        return cls(
            id=record.id,
            job_id=record.job_id,
            job_type=record.job_type,
            status=record.status or "pending",
            user_id=record.user_id,
            user_email=record.user_email or "",
            requester=record.requester or "",
            parent_job_id=record.parent_job_id,
            related_model_id=record.related_model_id,
            model_id=record.model_id,
            model_version=record.model_version or "",
            resource_cpu=record.resource_cpu or 1.0,
            resource_memory_gb=record.resource_memory_gb or 1.0,
            resource_gpu=record.resource_gpu or 0,
            resource_gpu_type=record.resource_gpu_type or "",
            resource_instance_type=record.resource_instance_type or "",
            scheduled_at=record.scheduled_at or 0.0,
            started_at=record.started_at,
            completed_at=record.completed_at,
            duration_seconds=record.duration_seconds,
            estimated_cost_usd=record.estimated_cost_usd or 0.0,
            actual_cost_usd=record.actual_cost_usd,
            cost_currency=record.cost_currency or "USD",
            max_retries=record.max_retries or 0,
            retry_count=record.retry_count or 0,
            retry_delay_seconds=record.retry_delay_seconds or 60.0,
            config=record.config or {},
            parameters=record.parameters or {},
            input_artifacts=record.input_artifacts or [],
            output_artifacts=record.output_artifacts or [],
            result=record.result or {},
            output_uri=record.output_uri or "",
            error_message=record.error_message or "",
            error_code=record.error_code or "",
            error_traceback=record.error_traceback or "",
            priority=record.priority or 0,
            queue_position=record.queue_position,
            tags=record.tags or [],
            job_data=record.job_data or {},
            created_by=record.created_by or "",
            created_at=record.created_at or 0.0,
            updated_at=record.updated_at or 0.0,
        )


# --------------------------------------------------------------------------- #
# Job Registry Service
# --------------------------------------------------------------------------- #

class JobRegistry:
    """
    Durable job registry backed by PostgreSQL.
    
    Provides CRUD operations for job tracking, status management,
    resource allocation, and cost tracking.
    """
    
    _instance: Optional["JobRegistry"] = None
    
    def __init__(self, engine=None):
        """Initialize with optional SQLAlchemy engine."""
        self._engine = engine
        self._tables_created = False
    
    @classmethod
    def get_instance(cls, engine=None) -> "JobRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(engine)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton and clear data (for testing)."""
        if cls._instance is not None:
            # Clear all records from the jobs table
            try:
                engine = cls._instance._get_engine()
                from sqlalchemy import delete
                with engine.begin() as conn:
                    conn.execute(delete(JobRecord))
            except Exception:
                pass  # Ignore if tables don't exist yet
        cls._instance = None
    
    def _get_engine(self):
        """Get SQLAlchemy engine, using existing db module."""
        if self._engine:
            return self._engine
        from jarvis_backend.db import get_engine
        return get_engine()
    
    def _ensure_tables(self) -> None:
        """Ensure job tables exist."""
        if self._tables_created:
            return
        
        engine = self._get_engine()
        
        # Create tables if they don't exist
        with engine.begin() as conn:
            from sqlalchemy import inspect
            inspector = inspect(conn)
            if "jobs" not in inspector.get_table_names():
                Base.metadata.create_all(conn)
        
        self._tables_created = True
    
    # ----------------------------------------------------------------------- #
    # CRUD Operations
    # ----------------------------------------------------------------------- #
    
    def create_job(self, job_info: JobInfo) -> JobInfo:
        """Create a new job."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.begin() as conn:
            conn.execute(insert(JobRecord).values({
                "id": job_info.id or str(uuid.uuid4()),
                "job_id": job_info.job_id,
                "job_type": job_info.job_type,
                "status": job_info.status,
                "user_id": job_info.user_id,
                "user_email": job_info.user_email,
                "requester": job_info.requester,
                "parent_job_id": job_info.parent_job_id,
                "related_model_id": job_info.related_model_id,
                "model_id": job_info.model_id,
                "model_version": job_info.model_version,
                "resource_cpu": job_info.resource_cpu,
                "resource_memory_gb": job_info.resource_memory_gb,
                "resource_gpu": job_info.resource_gpu,
                "resource_gpu_type": job_info.resource_gpu_type,
                "resource_instance_type": job_info.resource_instance_type,
                "scheduled_at": job_info.scheduled_at,
                "started_at": job_info.started_at,
                "completed_at": job_info.completed_at,
                "duration_seconds": job_info.duration_seconds,
                "estimated_cost_usd": job_info.estimated_cost_usd,
                "actual_cost_usd": job_info.actual_cost_usd,
                "cost_currency": job_info.cost_currency,
                "max_retries": job_info.max_retries,
                "retry_count": job_info.retry_count,
                "retry_delay_seconds": job_info.retry_delay_seconds,
                "config": job_info.config,
                "parameters": job_info.parameters,
                "input_artifacts": job_info.input_artifacts,
                "output_artifacts": job_info.output_artifacts,
                "result": job_info.result,
                "output_uri": job_info.output_uri,
                "error_message": job_info.error_message,
                "error_code": job_info.error_code,
                "error_traceback": job_info.error_traceback,
                "priority": job_info.priority,
                "queue_position": job_info.queue_position,
                "tags": job_info.tags,
                "job_data": job_info.job_data,
                "created_by": job_info.created_by,
                "created_at": job_info.created_at or time.time(),
                "updated_at": job_info.updated_at or time.time(),
            }))
        
        return job_info
    
    def get(self, job_id: str) -> Optional[JobInfo]:
        """Get job by job_id."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.connect() as conn:
            record = conn.execute(
                select(JobRecord).where(JobRecord.job_id == job_id)
            ).fetchone()
            
            return JobInfo.from_record(record) if record else None
    
    def get_by_id(self, internal_id: str) -> Optional[JobInfo]:
        """Get job by internal ID."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.connect() as conn:
            record = conn.execute(
                select(JobRecord).where(JobRecord.id == internal_id)
            ).fetchone()
            
            return JobInfo.from_record(record) if record else None
    
    def update_status(
        self,
        job_id: str,
        status: str,
        message: str = "",
        error: Optional[str] = None,
    ) -> bool:
        """Update job status."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.begin() as conn:
            # Get current record using fetchone() to get the full row
            record = conn.execute(
                select(JobRecord).where(JobRecord.job_id == job_id)
            ).fetchone()
            
            if not record:
                return False
            
            # Update based on status
            updates = {
                "status": status,
                "updated_at": time.time(),
            }
            
            if status == "running":
                updates["started_at"] = time.time()
            elif status in ("completed", "failed", "cancelled", "timeout"):
                updates["completed_at"] = time.time()
                if record.started_at:
                    updates["duration_seconds"] = updates["completed_at"] - record.started_at
            
            if message:
                if status == "failed":
                    updates["error_message"] = message
                else:
                    # Store in job_data as status messages can be large
                    job_data_update = dict(record.job_data) if record.job_data else {}
                    job_data_update["last_status_message"] = message
                    job_data_update["status_updated_at"] = time.time()
                    updates["job_data"] = job_data_update
            
            if error:
                updates["error_message"] = error
            
            stmt = (
                update(JobRecord)
                .where(JobRecord.job_id == job_id)
                .values(**updates)
            )
            conn.execute(stmt)
            return True
    
    def list_jobs(
        self,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        user_id: Optional[str] = None,
        model_id: Optional[str] = None,
        priority: Optional[int] = None,
        tag: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[JobInfo]:
        """List jobs with optional filters."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        query = select(JobRecord)
        
        if status:
            query = query.where(JobRecord.status == status)
        if job_type:
            query = query.where(JobRecord.job_type == job_type)
        if user_id:
            query = query.where(JobRecord.user_id == user_id)
        if model_id:
            query = query.where(JobRecord.model_id == model_id)
        if priority is not None:
            query = query.where(JobRecord.priority == priority)
        if tag:
            # Filter by tag (stored in JSON array)
            query = query.where(func.lower(JobRecord.tags.as_string()).like(f"%{tag.lower()}%"))
        
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        
        with engine.connect() as conn:
            records = conn.execute(query).fetchall()
            return [JobInfo.from_record(r) for r in records]
    
    def get_jobs_by_status(self, statuses: List[str], limit: int = 100) -> List[JobInfo]:
        """Get jobs with any of the specified statuses."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.connect() as conn:
            query = select(JobRecord).where(
                or_(*[JobRecord.status == s for s in statuses])
            ).limit(limit)
            
            records = conn.execute(query).fetchall()
            return [JobInfo.from_record(r) for r in records]
    
    # ----------------------------------------------------------------------- #
    # Resource and Cost Management
    # ----------------------------------------------------------------------- #
    
    def set_resource_allocation(
        self,
        job_id: str,
        cpu: float,
        memory_gb: float,
        gpu: int,
        gpu_type: Optional[str] = None,
    ) -> bool:
        """Set resource allocation for a job."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.begin() as conn:
            stmt = (
                update(JobRecord)
                .where(JobRecord.job_id == job_id)
                .values(
                    resource_cpu=cpu,
                    resource_memory_gb=memory_gb,
                    resource_gpu=gpu,
                    resource_gpu_type=gpu_type,
                    updated_at=time.time(),
                )
            )
            result = conn.execute(stmt)
            return result.rowcount > 0
    
    def set_cost(self, job_id: str, cost_usd: float) -> bool:
        """Set actual cost for a completed job."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.begin() as conn:
            stmt = (
                update(JobRecord)
                .where(JobRecord.job_id == job_id)
                .values(actual_cost_usd=cost_usd, updated_at=time.time())
            )
            result = conn.execute(stmt)
            return result.rowcount > 0
    
    # ----------------------------------------------------------------------- #
    # Artifact Association
    # ----------------------------------------------------------------------- #
    
    def add_artifact(self, job_id: str, artifact_id: str, artifact_type: str = "output") -> bool:
        """Add an artifact association to a job."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.begin() as conn:
            record = conn.execute(
                select(JobRecord).where(JobRecord.job_id == job_id)
            ).fetchone()
            
            if not record:
                return False
            
            # Get current artifacts list
            if artifact_type == "input":
                artifacts = list(record.input_artifacts or [])
            else:
                artifacts = list(record.output_artifacts or [])
            
            if artifact_id not in artifacts:
                artifacts.append(artifact_id)
            
            if artifact_type == "input":
                stmt = (
                    update(JobRecord)
                    .where(JobRecord.job_id == job_id)
                    .values(input_artifacts=artifacts, updated_at=time.time())
                )
            else:
                stmt = (
                    update(JobRecord)
                    .where(JobRecord.job_id == job_id)
                    .values(output_artifacts=artifacts, updated_at=time.time())
                )
            conn.execute(stmt)
            return True
    
    # ----------------------------------------------------------------------- #
    # Job Lifecycle Management
    # ----------------------------------------------------------------------- #
    
    def cancel_job(self, job_id: str, reason: str = "") -> bool:
        """Cancel a running job."""
        return self.update_status(job_id, "cancelled", reason=reason)
    
    def archive_job(self, job_id: str) -> bool:
        """Archive a completed job for long-term storage."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.begin() as conn:
            stmt = (
                update(JobRecord)
                .where(JobRecord.job_id == job_id)
                .values(status="archived", updated_at=time.time())
            )
            result = conn.execute(stmt)
            return result.rowcount > 0
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job from the registry."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.begin() as conn:
            stmt = (
                update(JobRecord)
                .where(JobRecord.job_id == job_id)
                .values(status="deleted", updated_at=time.time())
            )
            result = conn.execute(stmt)
            return result.rowcount > 0
    
    # ----------------------------------------------------------------------- #
    # Query Helpers
    # ----------------------------------------------------------------------- #
    
    def get_recent_jobs(self, limit: int = 100) -> List[JobInfo]:
        """Get recent jobs ordered by creation time."""
        self._ensure_tables()
        
        engine = self._get_engine()
        
        with engine.connect() as conn:
            records = conn.execute(
                select(JobRecord).order_by(JobRecord.created_at.desc()).limit(limit)
            ).fetchall()
            
            return [JobInfo.from_record(r) for r in records]
    
    def get_job_cost(self, job_id: str) -> float:
        """Get the actual cost of a job."""
        job = self.get(job_id)
        return job.actual_cost_usd if job else 0.0
    
    def get_upcoming_jobs(self, limit: int = 100) -> List[JobInfo]:
        """Get jobs scheduled to run in the future."""
        self._ensure_tables()
        
        now = time.time()
        engine = self._get_engine()
        
        with engine.connect() as conn:
            records = conn.execute(
                select(JobRecord)
                .where(JobRecord.scheduled_at > now)
                .where(JobRecord.status == "queued")
                .order_by(JobRecord.scheduled_at)
                .limit(limit)
            ).fetchall()
            return [JobInfo.from_record(r) for r in records]
    
    # ----------------------------------------------------------------------- #
    # Convenience functions for singleton access
    # ----------------------------------------------------------------------- #

def get_job_registry(engine=None) -> JobRegistry:
    """Get the global JobRegistry instance."""
    return JobRegistry.get_instance(engine)


def reset_job_registry() -> None:
    """Reset the JobRegistry singleton (testing)."""
    JobRegistry.reset_instance()