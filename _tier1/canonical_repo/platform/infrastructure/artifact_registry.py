"""
Durable Artifact Registry - PostgreSQL-backed artifact catalog.

Provides a canonical ArtifactRegistry that persists artifact metadata in PostgreSQL.

Phase 2 compliance:
- Tracks model weights, LoRA adapters, and other training artifacts
- Full provenance chain support (training run, dataset, parent/base model)
- Checksum verification for integrity
- Artifact storage locations (local paths, S3 URIs, etc.)
- Usage tracking for cost accounting
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
)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger("artifact_registry")

# --------------------------------------------------------------------------- #
# Artifact types
# --------------------------------------------------------------------------- #

class ArtifactType(str, Enum):
    """Types of artifacts in the registry."""
    MODEL_WEIGHTS = "model_weights"      # Base model weights
    LORA_ADAPTER = "lora_adapter"      # LoRA adapter
    CHECKPOINT = "checkpoint"            # Training checkpoint
    EVALUATION_DATASET = "eval_dataset"  # Evaluation dataset
    TRAINING_DATASET = "train_dataset"   # Training dataset
    CONFIG = "config"                    # Model/training config
    TOKENIZER = "tokenizer"              # Tokenizer files
    EMBEDDING = "embedding"              # Embedding model
    OTHER = "other"                      # Other artifacts


# --------------------------------------------------------------------------- #
# Artifact status
# --------------------------------------------------------------------------- #

class ArtifactStatus(str, Enum):
    """Artifact lifecycle status."""
    UPLOADING = "uploading"
    AVAILABLE = "available"
    VERIFIED = "verified"
    ARCHIVED = "archived"
    FAILED = "failed"
    DELETED = "deleted"


# --------------------------------------------------------------------------- #
# SQLAlchemy model
# --------------------------------------------------------------------------- #

Base = declarative_base()


class ArtifactRecord(Base):
    """SQLAlchemy model for durable artifact registry."""
    __tablename__ = "artifacts"
    
    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Artifact identifier
    artifact_id = Column(String(255), nullable=False, unique=True, index=True)
    
    # Type and status
    artifact_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), default="available", index=True)
    
    # Parent/child relationships (provenance)
    parent_artifact_id = Column(String(64), nullable=True, index=True)
    base_model_id = Column(String(64), nullable=True, index=True)
    
    # Source/model association
    source_model_id = Column(String(255), nullable=True, index=True)  # model_id this artifact belongs to
    training_run_id = Column(String(64), nullable=True, index=True)
    dataset_id = Column(String(64), nullable=True, index=True)
    
    # Location and storage info
    storage_uri = Column(String(1024), nullable=False)  # s3://, local://, etc.
    storage_type = Column(String(32), default="local")   # local, s3, gcs, azure
    size_bytes = Column(Integer, default=0)
    checksum_sha256 = Column(String(128), nullable=True)
    checksum_type = Column(String(32), default="sha256")
    
    # Metadata
    name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    version = Column(String(64), nullable=True)
    revision = Column(String(128), nullable=True)
    
    # Extractable info
    architecture = Column(String(64), nullable=True)
    parameters = Column(Integer, nullable=True)
    context_window = Column(Integer, nullable=True)
    open_weights = Column(Boolean, default=False)
    
    # Training provenance
    training_args = Column(JSON, default={})  # Training hyperparameters
    training_output = Column(JSON, default={})  # Training results
    
    # Evaluation provenance
    evaluation_results = Column(JSON, default={})
    
    # Usage tracking
    access_count = Column(Integer, default=0)
    first_accessed = Column(Float, nullable=True)
    last_accessed = Column(Float, nullable=True)
    
    # Deployment info
    deployed_model_id = Column(String(255), nullable=True, index=True)
    deployment_time = Column(Float, nullable=True)
    
    # Extended metadata
    artifact_data = Column(JSON, default={})
    provenance_chain = Column(JSON, default=[])
    
    # Timestamps
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    
    # Indexing
    __table_args__ = (
        Index("idx_artifacts_type", "artifact_type"),
        Index("idx_artifacts_status", "status"),
        Index("idx_artifacts_parent", "parent_artifact_id"),
        Index("idx_artifacts_model", "source_model_id"),
        Index("idx_artifacts_training", "training_run_id"),
        Index("idx_artifacts_deployed", "deployed_model_id"),
    )


# --------------------------------------------------------------------------- #
# Dataclass for API compatibility
# --------------------------------------------------------------------------- #

@dataclass
class ArtifactInfo:
    """Artifact information for API responses."""
    id: str
    artifact_id: str
    artifact_type: str
    status: str = "available"
    parent_artifact_id: Optional[str] = None
    base_model_id: Optional[str] = None
    source_model_id: Optional[str] = None
    training_run_id: str = ""
    dataset_id: str = ""
    storage_uri: str = ""
    storage_type: str = "local"
    size_bytes: int = 0
    checksum_sha256: str = ""
    checksum_type: str = "sha256"
    name: str = ""
    description: str = ""
    version: str = ""
    revision: str = ""
    architecture: str = ""
    parameters: Optional[int] = None
    context_window: int = 0
    open_weights: bool = False
    training_args: Dict[str, Any] = field(default_factory=dict)
    training_output: Dict[str, Any] = field(default_factory=dict)
    evaluation_results: Dict[str, Any] = field(default_factory=dict)
    access_count: int = 0
    first_accessed: Optional[float] = None
    last_accessed: Optional[float] = None
    deployed_model_id: str = ""
    deployment_time: Optional[float] = None
    artifact_data: Dict[str, Any] = field(default_factory=dict)
    provenance_chain: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    
    @classmethod
    def from_record(cls, record: ArtifactRecord) -> "ArtifactInfo":
        """Create ArtifactInfo from SQLAlchemy model record."""
        return cls(
            id=record.id,
            artifact_id=record.artifact_id,
            artifact_type=record.artifact_type,
            status=record.status or "available",
            parent_artifact_id=record.parent_artifact_id,
            base_model_id=record.base_model_id,
            source_model_id=record.source_model_id,
            training_run_id=record.training_run_id or "",
            dataset_id=record.dataset_id or "",
            storage_uri=record.storage_uri,
            storage_type=record.storage_type or "local",
            size_bytes=record.size_bytes or 0,
            checksum_sha256=record.checksum_sha256 or "",
            checksum_type=record.checksum_type or "sha256",
            name=record.name or "",
            description=record.description or "",
            version=record.version or "",
            revision=record.revision or "",
            architecture=record.architecture or "",
            parameters=record.parameters,
            context_window=record.context_window or 0,
            open_weights=record.open_weights if record.open_weights is not None else False,
            training_args=record.training_args or {},
            training_output=record.training_output or {},
            evaluation_results=record.evaluation_results or {},
            access_count=record.access_count or 0,
            first_accessed=record.first_accessed,
            last_accessed=record.last_accessed,
            deployed_model_id=record.deployed_model_id or "",
            deployment_time=record.deployment_time,
            artifact_data=record.artifact_data or {},
            provenance_chain=record.provenance_chain or [],
            created_at=record.created_at or 0.0,
            updated_at=record.updated_at or 0.0,
        )


# --------------------------------------------------------------------------- #
# Artifact Registry Service
# --------------------------------------------------------------------------- #

class ArtifactRegistry:
    """
    Durable artifact registry backed by PostgreSQL.
    
    Provides CRUD operations for artifact metadata, provenance tracking,
    and usage analytics for cost accounting.
    """
    
    _instance: Optional["ArtifactRegistry"] = None
    
    def __init__(self, engine=None):
        """Initialize with optional SQLAlchemy engine."""
        self._engine = engine
        self._tables_created = False
    
    @classmethod
    def get_instance(cls, engine=None) -> "ArtifactRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(engine)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton and clear data (for testing)."""
        if cls._instance is not None:
            # Clear all records from the artifacts table
            try:
                engine = cls._instance._get_engine()
                from sqlalchemy import delete
                with engine.begin() as conn:
                    conn.execute(delete(ArtifactRecord))
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
        """Ensure artifact tables exist."""
        if self._tables_created:
            return
        
        engine = self._get_engine()
        
        # Create tables if they don't exist
        with engine.begin() as conn:
            from sqlalchemy import inspect
            inspector = inspect(conn)
            if "artifacts" not in inspector.get_table_names():
                Base.metadata.create_all(conn)
        
        self._tables_created = True
    
    # ----------------------------------------------------------------------- #
    # CRUD Operations
    # ----------------------------------------------------------------------- #
    
    def register(self, artifact_info: ArtifactInfo) -> ArtifactInfo:
        """Register a new artifact (or update existing by artifact_id)."""
        self._ensure_tables()
        
        from sqlalchemy import insert, update, select
        
        engine = self._get_engine()
        
        # Check if artifact exists
        with engine.begin() as conn:
            existing = conn.execute(
                select(ArtifactRecord).where(ArtifactRecord.artifact_id == artifact_info.artifact_id)
            ).scalar_one_or_none()
            
            if existing:
                # Update existing
                stmt = (
                    update(ArtifactRecord)
                    .where(ArtifactRecord.artifact_id == artifact_info.artifact_id)
                    .values(
                        artifact_type=artifact_info.artifact_type,
                        status=artifact_info.status,
                        parent_artifact_id=artifact_info.parent_artifact_id,
                        base_model_id=artifact_info.base_model_id,
                        source_model_id=artifact_info.source_model_id,
                        training_run_id=artifact_info.training_run_id,
                        dataset_id=artifact_info.dataset_id,
                        storage_uri=artifact_info.storage_uri,
                        storage_type=artifact_info.storage_type,
                        size_bytes=artifact_info.size_bytes,
                        checksum_sha256=artifact_info.checksum_sha256,
                        checksum_type=artifact_info.checksum_type,
                        name=artifact_info.name,
                        description=artifact_info.description,
                        version=artifact_info.version,
                        revision=artifact_info.revision,
                        architecture=artifact_info.architecture,
                        parameters=artifact_info.parameters,
                        context_window=artifact_info.context_window,
                        open_weights=artifact_info.open_weights,
                        training_args=artifact_info.training_args,
                        training_output=artifact_info.training_output,
                        evaluation_results=artifact_info.evaluation_results,
                        access_count=artifact_info.access_count,
                        first_accessed=artifact_info.first_accessed,
                        last_accessed=artifact_info.last_accessed,
                        deployed_model_id=artifact_info.deployed_model_id,
                        deployment_time=artifact_info.deployment_time,
                        artifact_data=artifact_info.artifact_data,
                        provenance_chain=artifact_info.provenance_chain,
                        updated_at=time.time(),
                    )
                )
                conn.execute(stmt)
                return artifact_info
            else:
                # Insert new
                conn.execute(insert(ArtifactRecord).values({
                    "id": artifact_info.id or str(uuid.uuid4()),
                    "artifact_id": artifact_info.artifact_id,
                    "artifact_type": artifact_info.artifact_type,
                    "status": artifact_info.status,
                    "parent_artifact_id": artifact_info.parent_artifact_id,
                    "base_model_id": artifact_info.base_model_id,
                    "source_model_id": artifact_info.source_model_id,
                    "training_run_id": artifact_info.training_run_id,
                    "dataset_id": artifact_info.dataset_id,
                    "storage_uri": artifact_info.storage_uri,
                    "storage_type": artifact_info.storage_type,
                    "size_bytes": artifact_info.size_bytes,
                    "checksum_sha256": artifact_info.checksum_sha256,
                    "checksum_type": artifact_info.checksum_type,
                    "name": artifact_info.name,
                    "description": artifact_info.description,
                    "version": artifact_info.version,
                    "revision": artifact_info.revision,
                    "architecture": artifact_info.architecture,
                    "parameters": artifact_info.parameters,
                    "context_window": artifact_info.context_window,
                    "open_weights": artifact_info.open_weights,
                    "training_args": artifact_info.training_args,
                    "training_output": artifact_info.training_output,
                    "evaluation_results": artifact_info.evaluation_results,
                    "access_count": artifact_info.access_count,
                    "first_accessed": artifact_info.first_accessed,
                    "last_accessed": artifact_info.last_accessed,
                    "deployed_model_id": artifact_info.deployed_model_id,
                    "deployment_time": artifact_info.deployment_time,
                    "artifact_data": artifact_info.artifact_data,
                    "provenance_chain": artifact_info.provenance_chain,
                    "created_at": artifact_info.created_at or time.time(),
                    "updated_at": artifact_info.updated_at or time.time(),
                }))
                return artifact_info
    
    def get(self, artifact_id: str) -> Optional[ArtifactInfo]:
        """Get artifact by artifact_id."""
        self._ensure_tables()
        
        from sqlalchemy import select
        engine = self._get_engine()
        
        with engine.connect() as conn:
            record = conn.execute(
                select(ArtifactRecord).where(ArtifactRecord.artifact_id == artifact_id)
            ).fetchone()
            
            return ArtifactInfo.from_record(record) if record else None
    
    def get_by_id(self, internal_id: str) -> Optional[ArtifactInfo]:
        """Get artifact by internal ID."""
        self._ensure_tables()
        
        from sqlalchemy import select
        engine = self._get_engine()
        
        with engine.connect() as conn:
            record = conn.execute(
                select(ArtifactRecord).where(ArtifactRecord.id == internal_id)
            ).fetchone()
            
            return ArtifactInfo.from_record(record) if record else None
    
    def list_artifacts(
        self,
        artifact_type: Optional[str] = None,
        status: Optional[str] = None,
        source_model_id: Optional[str] = None,
        parent_artifact_id: Optional[str] = None,
        training_run_id: Optional[str] = None,
        base_model_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ArtifactInfo]:
        """List artifacts with optional filters."""
        self._ensure_tables()
        
        from sqlalchemy import select
        engine = self._get_engine()
        
        query = select(ArtifactRecord)
        
        if artifact_type:
            query = query.where(ArtifactRecord.artifact_type == artifact_type)
        if status:
            query = query.where(ArtifactRecord.status == status)
        if source_model_id:
            query = query.where(ArtifactRecord.source_model_id == source_model_id)
        if parent_artifact_id:
            query = query.where(ArtifactRecord.parent_artifact_id == parent_artifact_id)
        if training_run_id:
            query = query.where(ArtifactRecord.training_run_id == training_run_id)
        if base_model_id:
            query = query.where(ArtifactRecord.base_model_id == base_model_id)
        
        with engine.connect() as conn:
            records = conn.execute(query.limit(limit)).fetchall()
            return [ArtifactInfo.from_record(r) for r in records]
    
    def update_status(self, artifact_id: str, status: str) -> bool:
        """Update artifact status."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            stmt = (
                update(ArtifactRecord)
                .where(ArtifactRecord.artifact_id == artifact_id)
                .values(status=status, updated_at=time.time())
            )
            result = conn.execute(stmt)
            return result.rowcount > 0
    
    def record_access(self, artifact_id: str) -> bool:
        """Record an artifact access for usage tracking."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        now = time.time()
        
        with engine.begin() as conn:
            record = conn.execute(
                select(ArtifactRecord).where(ArtifactRecord.artifact_id == artifact_id)
            ).fetchone()
            
            if not record:
                return False
            
            stmt = (
                update(ArtifactRecord)
                .where(ArtifactRecord.artifact_id == artifact_id)
                .values(
                    access_count=(record.access_count or 0) + 1,
                    first_accessed=record.first_accessed or now,
                    last_accessed=now,
                    updated_at=now,
                )
            )
            conn.execute(stmt)
            return True
    
    def link_to_model(self, artifact_id: str, model_id: str) -> bool:
        """Link an artifact to a model deployment."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            record = conn.execute(
                select(ArtifactRecord).where(ArtifactRecord.artifact_id == artifact_id)
            ).scalar_one_or_none()
            
            if not record:
                return False
            
            stmt = (
                update(ArtifactRecord)
                .where(ArtifactRecord.artifact_id == artifact_id)
                .values(
                    deployed_model_id=model_id,
                    deployment_time=time.time(),
                    status="available",
                    updated_at=time.time(),
                )
            )
            conn.execute(stmt)
            return True
    
    def get_artifacts_by_model(self, model_id: str) -> List[ArtifactInfo]:
        """Get all artifacts associated with a model."""
        return self.list_artifacts(source_model_id=model_id)
    
    def get_artifacts_by_training_run(self, run_id: str) -> List[ArtifactInfo]:
        """Get all artifacts from a training run."""
        return self.list_artifacts(training_run_id=run_id)
    
    def get_parent_chain(self, artifact_id: str) -> List[ArtifactInfo]:
        """Get the parent chain for an artifact."""
        chain = []
        current_id = artifact_id
        
        while current_id:
            artifact = self.get(current_id)
            if not artifact:
                break
            chain.append(artifact)
            current_id = artifact.parent_artifact_id
        
        return chain
    
    def compute_checksum(self, data: bytes) -> str:
        """Compute SHA256 checksum for artifact data."""
        import hashlib
        return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Global instance
# --------------------------------------------------------------------------- #

artifact_registry = ArtifactRegistry()


# --------------------------------------------------------------------------- #
# Import hook for backward compatibility
# --------------------------------------------------------------------------- #

def get_artifact_registry() -> ArtifactRegistry:
    """Get the global artifact registry instance."""
    return ArtifactRegistry.get_instance()