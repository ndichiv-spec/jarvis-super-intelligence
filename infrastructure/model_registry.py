"""
Durable Model Registry - PostgreSQL-backed model catalog.

Provides a canonical ModelRegistry that persists model metadata in PostgreSQL
while maintaining compatibility with existing routing and discovery patterns.

Extends the existing jarvis_backend.db persistence layer with a dedicated
models table for proper querying, indexing, and state management.

Phase 2 compliance:
- Full lifecycle state support (discovered, registered, evaluating, candidate, approved, blocked, deprecated, retired)
- Provenance tracking (source provider, repository revision, parent/base model, training run, dataset, evaluation results)
- Artifact reference/checksum support
- Migration path from JSONL lifecycle records
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
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

logger = logging.getLogger("model_registry")

# --------------------------------------------------------------------------- #
# Model lifecycle states (Phase 2 specification)
# --------------------------------------------------------------------------- #

class ModelLifecycleState(str, Enum):
    """Canonical model lifecycle states as defined in Phase 2.

    The lifecycle supports concepts such as:
    - discovered: Found but not yet registered
    - registered: In registry, not yet evaluated
    - evaluating: Undergoing evaluation
    - candidate: Ready for evaluation/promotion
    - approved: Passed evaluation, approved for deployment
    - blocked: Evaluation failed, not usable
    - deprecated: Superseded, keep for backwards compat
    - retired: End of life, no longer usable
    """
    DISCOVERED = "discovered"       # Found but not yet registered
    REGISTERED = "registered"       # In registry, not yet evaluated
    EVALUATING = "evaluating"       # Undergoing evaluation
    CANDIDATE = "candidate"         # Ready for evaluation
    APPROVED = "approved"           # Passed evaluation, approved for deployment
    BLOCKED = "blocked"             # Evaluation failed, not usable
    DEPLOYED = "deployed"           # Active/used in production
    DEPRECATED = "deprecated"       # Superseded, keep for backwards compat
    RETIRED = "retired"             # End of life, no longer usable


# --------------------------------------------------------------------------- #
# SQLAlchemy model
# --------------------------------------------------------------------------- #

Base = declarative_base()


class ModelRecord(Base):
    """SQLAlchemy model for durable model registry."""
    __tablename__ = "models"
    
    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Core identifiers
    model_id = Column(String(255), nullable=False, unique=True)
    provider_id = Column(String(64), nullable=False, index=True)
    
    # Display and description
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    model_family = Column(String(128), nullable=True, index=True)
    
    # Lifecycle and provenance
    lifecycle_type = Column(String(32), default="discovered", index=True)
    lifecycle_status = Column(String(32), default="discovered", index=True)
    
    # Lineage / parent relationships
    parent_model_id = Column(String(64), nullable=True, index=True)
    revision = Column(String(128), nullable=True)
    
    # Capabilities and specs
    capabilities = Column(JSON, default=[])  # JSON for cross-db compatibility
    modalities = Column(JSON, default=[])      # text, image, audio, video
    context_window = Column(Integer, default=0)
    max_output_tokens = Column(Integer, default=0)
    
    # Architecture info
    architecture = Column(String(64), nullable=True)
    parameters = Column(Integer, nullable=True)
    open_weights = Column(Boolean, default=False)
    
    # Deployment info
    deployment_type = Column(String(32), default="local")  # local, remote_endpoint, cloud_api
    endpoint_reference = Column(String(512), nullable=True)  # URL or reference
    
    # Artifact and provenance
    artifact_reference = Column(String(512), nullable=True)
    checksum = Column(String(128), nullable=True)
    source = Column(String(64), nullable=True, index=True)  # provider, repository, etc.
    
    # Training/evaluation provenance
    training_run_id = Column(String(64), nullable=True)
    dataset_id = Column(String(64), nullable=True)
    evaluation_results = Column(JSON, default={})  # Detailed evaluation data
    
    # Metadata stored as JSON (JSONB for PostgreSQL, JSON for SQLite)
    model_data = Column(JSON, default={})  # Model-specific metadata
    provenance_chain = Column(JSON, default={})  # Full provenance chain
    history = Column(JSON, default=[])      # Lifecycle history
    
    # Timestamps
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    
    # Indexing
    __table_args__ = (
        Index("idx_models_provider", "provider_id"),
        Index("idx_models_lifecycle", "lifecycle_status"),
        Index("idx_models_parent", "parent_model_id"),
        Index("idx_models_family", "model_family"),
        Index("idx_models_source", "source"),
    )


# --------------------------------------------------------------------------- #
# Mapping functions for JSONL migration
# --------------------------------------------------------------------------- #

_JSONL_LIFECYCLE_TYPE_MAP = {
    'jarvis_base': 'discovered',
    'jarvis_candidate': 'candidate',
    'jarvis_sft': 'candidate',
    'local_model': 'discovered',
}

_JSONL_LIFECYCLE_STAGE_MAP = {
    'base': 'registered',
    'candidate': 'candidate',
    'evaluating': 'evaluating',
    'approved': 'approved',
    'deployed': 'deployed',
    'deprecated': 'deprecated',
    'retired': 'retired',
}


def jsonl_to_lifecycle_status(record: Dict[str, Any]) -> str:
    """Convert JSONL lifecycle_type/stage to Phase 2 lifecycle_status."""
    jsonl_type = record.get('lifecycle_type', 'discovered')
    jsonl_stage = record.get('lifecycle_stage', 'base')
    
    # Try stage map first, then type map
    if jsonl_stage in _JSONL_LIFECYCLE_STAGE_MAP:
        return _JSONL_LIFECYCLE_STAGE_MAP[jsonl_stage]
    if jsonl_type in _JSONL_LIFECYCLE_TYPE_MAP:
        return _JSONL_LIFECYCLE_TYPE_MAP[jsonl_type]
    return 'registered'  # Default fallback


# --------------------------------------------------------------------------- #
# Dataclass for API compatibility
# --------------------------------------------------------------------------- #

@dataclass
class ModelInfo:
    """Model information for API responses."""
    id: str
    model_id: str
    provider_id: str
    display_name: str = ""
    description: str = ""
    model_family: str = ""
    lifecycle_type: str = "discovered"
    lifecycle_status: str = "discovered"
    parent_model_id: Optional[str] = None
    revision: str = ""
    capabilities: List[str] = field(default_factory=list)
    modalities: List[str] = field(default_factory=lambda: ["text"])
    context_window: int = 0
    max_output_tokens: int = 0
    architecture: str = ""
    parameters: Optional[int] = None
    open_weights: bool = False
    deployment_type: str = "local"
    endpoint_reference: str = ""
    artifact_reference: str = ""
    checksum: str = ""
    source: str = ""
    training_run_id: str = ""
    dataset_id: str = ""
    evaluation_results: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    
    @classmethod
    def from_record(cls, record: ModelRecord) -> "ModelInfo":
        """Create ModelInfo from SQLAlchemy model record."""
        return cls(
            id=record.id,
            model_id=record.model_id,
            provider_id=record.provider_id,
            display_name=record.display_name or "",
            description=record.description or "",
            model_family=record.model_family or "",
            lifecycle_type=record.lifecycle_type or "discovered",
            lifecycle_status=record.lifecycle_status or "discovered",
            parent_model_id=record.parent_model_id,
            revision=record.revision or "",
            capabilities=record.capabilities or [],
            modalities=record.modalities or ["text"],
            context_window=record.context_window or 0,
            max_output_tokens=record.max_output_tokens or 0,
            architecture=record.architecture or "",
            parameters=record.parameters,
            open_weights=record.open_weights or False,
            deployment_type=record.deployment_type or "local",
            endpoint_reference=record.endpoint_reference or "",
            artifact_reference=record.artifact_reference or "",
            checksum=record.checksum or "",
            source=record.source or "",
            training_run_id=record.training_run_id or "",
            dataset_id=record.dataset_id or "",
            evaluation_results=record.evaluation_results or {},
            metadata=record.model_data or {},
            provenance=record.provenance_chain or {},
            history=record.history or [],
            created_at=record.created_at or 0.0,
            updated_at=record.updated_at or 0.0,
        )


# --------------------------------------------------------------------------- #
# Model Registry Service
# --------------------------------------------------------------------------- #

class ModelRegistry:
    """
    Durable model registry backed by PostgreSQL.
    
    Provides CRUD operations for model metadata, lifecycle management,
    and query capabilities. Uses the existing jarvis_backend.db engine.
    """
    
    _instance: Optional["ModelRegistry"] = None
    
    def __init__(self, engine=None):
        """Initialize with optional SQLAlchemy engine."""
        self._engine = engine
        self._tables_created = False
    
    @classmethod
    def get_instance(cls, engine=None) -> "ModelRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(engine)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton and clear data (for testing)."""
        if cls._instance is not None:
            # Clear all records from the models table
            try:
                engine = cls._instance._get_engine()
                from sqlalchemy import delete
                with engine.begin() as conn:
                    conn.execute(delete(ModelRecord))
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
        """Ensure model tables exist."""
        if self._tables_created:
            return
        
        engine = self._get_engine()
        
        # Create tables if they don't exist
        with engine.begin() as conn:
            from sqlalchemy import inspect
            inspector = inspect(conn)
            if "models" not in inspector.get_table_names():
                Base.metadata.create_all(conn)
        
        self._tables_created = True
    
    # ----------------------------------------------------------------------- #
    # CRUD Operations
    # ----------------------------------------------------------------------- #
    
    def register(self, model_info: ModelInfo) -> ModelInfo:
        """Register a new model (or update existing by model_id)."""
        self._ensure_tables()
        
        from sqlalchemy import insert, update, select
        
        engine = self._get_engine()
        
        # Check if model exists
        with engine.begin() as conn:
            existing = conn.execute(
                select(ModelRecord).where(ModelRecord.model_id == model_info.model_id)
            ).scalar_one_or_none()
            
            if existing:
                # Update existing
                stmt = (
                    update(ModelRecord)
                    .where(ModelRecord.model_id == model_info.model_id)
                    .values(
                        display_name=model_info.display_name,
                        description=model_info.description,
                        model_family=model_info.model_family,
                        capabilities=model_info.capabilities,
                        modalities=model_info.modalities,
                        context_window=model_info.context_window,
                        max_output_tokens=model_info.max_output_tokens,
                        architecture=model_info.architecture,
                        parameters=model_info.parameters,
                        open_weights=model_info.open_weights,
                        deployment_type=model_info.deployment_type,
                        endpoint_reference=model_info.endpoint_reference,
                        artifact_reference=model_info.artifact_reference,
                        checksum=model_info.checksum,
                        source=model_info.source,
                        training_run_id=model_info.training_run_id,
                        dataset_id=model_info.dataset_id,
                        model_data=model_info.metadata,
                        provenance_chain=model_info.provenance,
                        evaluation_results=model_info.evaluation_results,
                        history=model_info.history,
                        lifecycle_type=model_info.lifecycle_type,
                        lifecycle_status=model_info.lifecycle_status,
                        parent_model_id=model_info.parent_model_id,
                        revision=model_info.revision,
                        updated_at=time.time(),
                    )
                )
                conn.execute(stmt)
                return model_info
            else:
                # Insert new
                conn.execute(insert(ModelRecord).values({
                    "id": model_info.id or str(uuid.uuid4()),
                    "model_id": model_info.model_id,
                    "provider_id": model_info.provider_id,
                    "display_name": model_info.display_name,
                    "description": model_info.description,
                    "model_family": model_info.model_family,
                    "lifecycle_type": model_info.lifecycle_type,
                    "lifecycle_status": model_info.lifecycle_status,
                    "parent_model_id": model_info.parent_model_id,
                    "revision": model_info.revision,
                    "capabilities": model_info.capabilities,
                    "modalities": model_info.modalities,
                    "context_window": model_info.context_window,
                    "max_output_tokens": model_info.max_output_tokens,
                    "architecture": model_info.architecture,
                    "parameters": model_info.parameters,
                    "open_weights": model_info.open_weights,
                    "deployment_type": model_info.deployment_type,
                    "endpoint_reference": model_info.endpoint_reference,
                    "artifact_reference": model_info.artifact_reference,
                    "checksum": model_info.checksum,
                    "source": model_info.source,
                    "training_run_id": model_info.training_run_id,
                    "dataset_id": model_info.dataset_id,
                    "model_data": model_info.metadata,
                    "provenance_chain": model_info.provenance,
                    "evaluation_results": model_info.evaluation_results,
                    "history": model_info.history,
                    "created_at": model_info.created_at or time.time(),
                    "updated_at": model_info.updated_at or time.time(),
                }))
                return model_info
    
    def get(self, model_id: str) -> Optional[ModelInfo]:
        """Get model by ID."""
        self._ensure_tables()
        
        from sqlalchemy import select
        engine = self._get_engine()
        
        with engine.connect() as conn:
            record = conn.execute(
                select(ModelRecord).where(ModelRecord.model_id == model_id)
            ).fetchone()
            
            return ModelInfo.from_record(record) if record else None
    
    def get_by_id(self, internal_id: str) -> Optional[ModelInfo]:
        """Get model by internal ID."""
        self._ensure_tables()
        
        from sqlalchemy import select
        engine = self._get_engine()
        
        with engine.connect() as conn:
            record = conn.execute(
                select(ModelRecord).where(ModelRecord.id == internal_id)
            ).fetchone()
            
            return ModelInfo.from_record(record) if record else None
    
    def list_models(
        self,
        provider_id: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        lifecycle_type: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[ModelInfo]:
        """List models with optional filters."""
        self._ensure_tables()
        
        from sqlalchemy import select, and_, or_, cast, String
        from sqlalchemy import func
        engine = self._get_engine()
        
        query = select(ModelRecord)
        
        if provider_id:
            query = query.where(ModelRecord.provider_id == provider_id)
        
        if lifecycle_status:
            query = query.where(ModelRecord.lifecycle_status == lifecycle_status)
        
        if lifecycle_type:
            query = query.where(ModelRecord.lifecycle_type == lifecycle_type)
        
        if source:
            query = query.where(ModelRecord.source == source)
        
        if capabilities:
            # Filter capabilities: check if any capability is in the JSON array
            for cap in capabilities:
                # Use JSON array contains or simple ILIKE for SQLite/PostgreSQL compatibility
                try:
                    # Try JSON array contains (PostgreSQL)
                    query = query.where(ModelRecord.capabilities.contains([cap]))
                except Exception:
                    # Fallback to ILIKE for SQLite
                    query = query.where(func.lower(ModelRecord.capabilities.cast(String)).like(f"%{cap.lower()}%"))
        
        with engine.connect() as conn:
            records = conn.execute(query).fetchall()
            return [ModelInfo.from_record(r) for r in records]
    
    def update_lifecycle(
        self,
        model_id: str,
        status: str,
        reason: str = "",
        actor: str = "system",
    ) -> bool:
        """Update model lifecycle status."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            # Get current history
            record = conn.execute(
                select(ModelRecord).where(ModelRecord.model_id == model_id)
            ).fetchone()
            
            if not record:
                return False
            
            # Append to history
            new_history = (record.history or []) + [{
                "at": time.time(),
                "status": status,
                "reason": reason,
                "actor": actor,
            }]
            
            stmt = (
                update(ModelRecord)
                .where(ModelRecord.model_id == model_id)
                .values(
                    lifecycle_status=status,
                    history=new_history,
                    updated_at=time.time(),
                )
            )
            conn.execute(stmt)
            return True
    
    def record_evaluation(
        self,
        model_id: str,
        results: Dict[str, Any],
        evaluator: str = "",
        metrics: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record evaluation results for a model."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            record = conn.execute(
                select(ModelRecord).where(ModelRecord.model_id == model_id)
            ).fetchone()
            
            if not record:
                return False
            
            current_eval = record.evaluation_results or {}
            current_eval[evaluator] = {
                "at": time.time(),
                "results": results,
                "metrics": metrics or {},
            }
            
            stmt = (
                update(ModelRecord)
                .where(ModelRecord.model_id == model_id)
                .values(
                    evaluation_results=current_eval,
                    updated_at=time.time(),
                )
            )
            conn.execute(stmt)
            return True
    
    def search(
        self,
        query: str,
        limit: int = 50,
    ) -> List[ModelInfo]:
        """Search models by model_id or display_name."""
        self._ensure_tables()
        
        from sqlalchemy import select, or_
        engine = self._get_engine()
        
        search_pattern = f"%{query}%"
        
        with engine.connect() as conn:
            records = conn.execute(
                select(ModelRecord).where(
                    or_(
                        ModelRecord.model_id.ilike(search_pattern),
                        ModelRecord.display_name.ilike(search_pattern),
                    )
                ).limit(limit)
            ).fetchall()
            
            return [ModelInfo.from_record(r) for r in records]
    
    def promote_model(
        self,
        model_id: str,
        current_status: str,
        target_status: str,
        reason: str = "",
        evidence: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Promote a model through the lifecycle gate.
        
        Valid transitions:
        - registered -> evaluating
        - evaluating -> candidate
        - candidate -> approved
        - approved -> deployed
        - approved -> blocked (if evaluation fails)
        - deployed -> deprecated
        - deprecated -> retired
        """
        self._ensure_tables()
        
        valid_transitions = {
            "registered": ["evaluating", "blocked", "retired"],
            "evaluating": ["candidate", "blocked", "retired"],
            "candidate": ["approved", "blocked", "retired"],
            "approved": ["deployed", "blocked", "deprecated", "retired"],
            "deployed": ["deprecated", "retired"],
            "deprecated": ["retired"],
            "blocked": ["retired"],
            "evaluating": ["approved"],  # Direct eval -> approved
        }
        
        if current_status not in valid_transitions:
            logger.warning(f"Invalid current status '{current_status}' for promotion")
            return False
        
        if target_status not in valid_transitions.get(current_status, []):
            logger.warning(f"Invalid transition from '{current_status}' to '{target_status}'")
            return False
        
        return self.update_lifecycle(
            model_id, 
            target_status, 
            reason=f"Promotion: {reason}",
            actor="promotion_gate" if evidence else "system"
        )


# --------------------------------------------------------------------------- #
# Global instance
# --------------------------------------------------------------------------- #

model_registry = ModelRegistry()


# --------------------------------------------------------------------------- #
# Import hook for backward compatibility
# --------------------------------------------------------------------------- #

def get_model_registry() -> ModelRegistry:
    """Get the global model registry instance."""
    return ModelRegistry.get_instance()