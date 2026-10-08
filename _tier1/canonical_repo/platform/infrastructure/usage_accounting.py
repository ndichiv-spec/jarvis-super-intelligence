"""
Usage and Cost Accounting System for JARVIS Control Plane.

Provides durable tracking of resource usage and costs for:
- Inference requests (per provider, per model)
- Training jobs (CPU, GPU, memory hours)
- Artifact storage and access
- Job execution

Phase 2 compliance:
- PostgreSQL-backed accounting records
- Detailed usage tracking by provider, model, user
- Cost estimation and actual cost tracking
- Budget enforcement
- Usage aggregation and reporting
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    JSON,
    Index,
    func,
    text,
)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger("usage_accounting")

# --------------------------------------------------------------------------- #
# Usage types
# --------------------------------------------------------------------------- #

class UsageType(str, Enum):
    """Types of usage to track."""
    INFERENCE_INPUT_TOKENS = "inference_input_tokens"
    INFERENCE_OUTPUT_TOKENS = "inference_output_tokens"
    INFERENCE_COST = "inference_cost"
    TRAINING_CPU_HOURS = "training_cpu_hours"
    TRAINING_MEMORY_GB_HOURS = "training_memory_gb_hours"
    TRAINING_GPU_HOURS = "training_gpu_hours"
    TRAINING_COST = "training_cost"
    ARTIFACT_STORAGE_GB_DAYS = "artifact_storage_gb_days"
    ARTIFACT_ACCESS = "artifact_access"
    JOB_CPU_HOURS = "job_cpu_hours"
    JOB_MEMORY_GB_HOURS = "job_memory_gb_hours"
    JOB_GPU_HOURS = "job_gpu_hours"
    JOB_COST = "job_cost"


# --------------------------------------------------------------------------- #
# Cost entry SQLAlchemy model
# --------------------------------------------------------------------------- #

Base = declarative_base()


class CostRecord(Base):
    """SQLAlchemy model for cost and usage tracking."""
    __tablename__ = "usage_costs"
    
    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Identifier
    record_id = Column(String(64), nullable=False, unique=True, index=True)
    
    # Timestamps for time-series analysis
    timestamp = Column(Float, default=time.time, index=True)
    period_start = Column(Float, nullable=True, index=True)  # For aggregated periods
    period_end = Column(Float, nullable=True)
    
    # Usage type
    usage_type = Column(String(32), nullable=False, index=True)
    
    # Provider/model association
    provider_id = Column(String(64), nullable=True, index=True)
    model_id = Column(String(255), nullable=True, index=True)
    
    # Job association
    job_id = Column(String(64), nullable=True, index=True)
    
    # User association
    user_id = Column(String(64), nullable=True, index=True)
    request_id = Column(String(64), nullable=True)
    
    # Usage quantities
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cpu_hours = Column(Float, default=0.0)
    memory_gb_hours = Column(Float, default=0.0)
    gpu_hours = Column(Float, default=0.0)
    storage_gb_days = Column(Float, default=0.0)
    
    # Cost breakdown
    unit_cost_usd = Column(Float, default=0.0)  # Cost per unit (token, hour, etc.)
    total_cost_usd = Column(Float, default=0.0)
    currency = Column(String(8), default="USD")
    
    # Resource details
    cpu_cores = Column(Float, default=1.0)
    memory_gb = Column(Float, default=1.0)
    gpu_count = Column(Integer, default=0)
    
    # Metadata
    usage_metadata = Column(JSON, default={})
    tags = Column(JSON, default=[])
    
    # Status
    is_estimated = Column(Boolean, default=False)  # True if estimate, not actual
    
    # Indexing
    __table_args__ = (
        Index("idx_costs_timestamp", "timestamp"),
        Index("idx_costs_type_provider", "usage_type", "provider_id"),
        Index("idx_costs_user", "user_id"),
        Index("idx_costs_model", "model_id"),
        Index("idx_costs_job", "job_id"),
        Index("idx_costs_period", "period_start", "period_end"),
    )


# --------------------------------------------------------------------------- #
# Dataclass for API compatibility
# --------------------------------------------------------------------------- #

@dataclass
class CostRecordInfo:
    """Cost record information for API responses."""
    id: str
    record_id: str
    timestamp: float
    period_start: Optional[float] = None
    period_end: Optional[float] = None
    usage_type: str = ""
    provider_id: str = ""
    model_id: str = ""
    job_id: str = ""
    user_id: str = ""
    request_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cpu_hours: float = 0.0
    memory_gb_hours: float = 0.0
    gpu_hours: float = 0.0
    storage_gb_days: float = 0.0
    unit_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    currency: str = "USD"
    cpu_cores: float = 1.0
    memory_gb: float = 1.0
    gpu_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    usage_metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    is_estimated: bool = False
    
    @classmethod
    def from_record(cls, record: CostRecord) -> "CostRecordInfo":
        """Create CostRecordInfo from SQLAlchemy model record."""
        return cls(
            id=record.id,
            record_id=record.record_id,
            timestamp=record.timestamp or 0.0,
            period_start=record.period_start,
            period_end=record.period_end,
            usage_type=record.usage_type,
            provider_id=record.provider_id or "",
            model_id=record.model_id or "",
            job_id=record.job_id or "",
            user_id=record.user_id or "",
            request_id=record.request_id or "",
            input_tokens=record.input_tokens or 0,
            output_tokens=record.output_tokens or 0,
            cpu_hours=record.cpu_hours or 0.0,
            memory_gb_hours=record.memory_gb_hours or 0.0,
            gpu_hours=record.gpu_hours or 0.0,
            storage_gb_days=record.storage_gb_days or 0.0,
            unit_cost_usd=record.unit_cost_usd or 0.0,
            total_cost_usd=record.total_cost_usd or 0.0,
            currency=record.currency or "USD",
            cpu_cores=record.cpu_cores or 1.0,
            memory_gb=record.memory_gb or 1.0,
            gpu_count=record.gpu_count or 0,
            usage_metadata=record.usage_metadata or {},
            tags=record.tags or [],
            is_estimated=record.is_estimated or False,
        )


# --------------------------------------------------------------------------- #
# Usage and Cost Accounting Service
# --------------------------------------------------------------------------- #

class UsageAccountant:
    """
    Usage and cost accounting service backed by PostgreSQL.
    
    Tracks all usage across the platform for:
    - Budget enforcement
    - Cost allocation
    - Usage analytics
    - Audit trails
    """
    
    _instance: Optional["UsageAccountant"] = None
    
    # Default pricing (USD per 1M tokens for inference)
    DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
        "openai": {"input": 0.03, "output": 0.06},
        "anthropic": {"input": 0.015, "output": 0.03},
        "google": {"input": 0.0075, "output": 0.0001},
        "groq": {"input": 0.0005, "output": 0.0005},
        "deepseek": {"input": 0.00014, "output": 0.00014},
        "ollama": {"input": 0.0, "output": 0.0},
        "llamacpp": {"input": 0.0, "output": 0.0},
        "silverwing": {"input": 0.0, "output": 0.0},
        "vllm": {"input": 0.0, "output": 0.0},
        "local": {"input": 0.0, "output": 0.0},
    }
    
    def __init__(self, engine=None):
        """Initialize with optional SQLAlchemy engine."""
        self._engine = engine
        self._tables_created = False
    
    @classmethod
    def get_instance(cls, engine=None) -> "UsageAccountant":
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
        """Ensure cost tables exist."""
        if self._tables_created:
            return
        
        engine = self._get_engine()
        
        # Create tables if they don't exist
        with engine.begin() as conn:
            from sqlalchemy import inspect
            inspector = inspect(conn)
            if "usage_costs" not in inspector.get_table_names():
                Base.metadata.create_all(conn)
        
        self._tables_created = True
    
    # ----------------------------------------------------------------------- #
    # Cost Recording
    # ----------------------------------------------------------------------- #
    
    def record_inference(
        self,
        provider_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecordInfo:
        """Record inference usage and calculate cost."""
        self._ensure_tables()
        
        # Get pricing
        pricing = self.DEFAULT_PRICING.get(provider_id, {"input": 0.0, "output": 0.0})
        
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost
        
        from sqlalchemy import insert
        engine = self._get_engine()
        
        record_id = f"inf-{uuid.uuid4()}"
        
        with engine.begin() as conn:
            conn.execute(insert(CostRecord).values({
                "record_id": record_id,
                "timestamp": time.time(),
                "usage_type": "inference_input_tokens" if input_tokens > 0 else "inference_output_tokens",
                "provider_id": provider_id,
                "model_id": model_id,
                "user_id": user_id,
                "request_id": request_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "unit_cost_usd": pricing["input"] if input_tokens > 0 else pricing["output"],
                "total_cost_usd": total_cost,
                "usage_metadata": metadata or {},
            }))
        
        return CostRecordInfo(
            id=record_id,
            record_id=record_id,
            timestamp=time.time(),
            usage_type="inference_cost",
            provider_id=provider_id,
            model_id=model_id,
            user_id=user_id or "",
            request_id=request_id or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            unit_cost_usd=pricing["input"],
            total_cost_usd=total_cost,
            usage_metadata=metadata or {},
        )
    
    def record_training(
        self,
        job_id: str,
        cpu_hours: float = 0.0,
        memory_gb_hours: float = 0.0,
        gpu_hours: float = 0.0,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecordInfo:
        """Record training job usage and calculate cost."""
        self._ensure_tables()
        
        # Rough cost estimates (USD per GPU hour)
        # These should be configured per-cloud/provider
        gpu_cost_per_hour = 1.0  # Conservative estimate
        cpu_cost_per_hour = 0.05  # Server-grade CPU
        memory_cost_per_gb_hour = 0.005  # RAM cost
        
        gpu_cost = gpu_hours * gpu_cost_per_hour
        cpu_cost = cpu_hours * cpu_cost_per_hour
        memory_cost = memory_gb_hours * memory_cost_per_gb_hour
        total_cost = gpu_cost + cpu_cost + memory_cost
        
        from sqlalchemy import insert
        engine = self._get_engine()
        
        record_id = f"train-{uuid.uuid4()}"
        
        with engine.begin() as conn:
            conn.execute(insert(CostRecord).values({
                "record_id": record_id,
                "timestamp": time.time(),
                "usage_type": "training_cost",
                "provider_id": provider_id,
                "model_id": model_id,
                "job_id": job_id,
                "user_id": user_id,
                "cpu_hours": cpu_hours,
                "memory_gb_hours": memory_gb_hours,
                "gpu_hours": gpu_hours,
                "unit_cost_usd": gpu_cost_per_hour,
                "total_cost_usd": total_cost,
                "cpu_cores": cpu_hours / max(cpu_hours, 1),  # Assume 1 core per hour
                "memory_gb": memory_gb_hours / max(memory_gb_hours, 1),
                "usage_metadata": metadata or {},
            }))
        
        return CostRecordInfo(
            id=record_id,
            record_id=record_id,
            timestamp=time.time(),
            usage_type="training_cost",
            provider_id=provider_id or "",
            model_id=model_id or "",
            job_id=job_id,
            user_id=user_id or "",
            cpu_hours=cpu_hours,
            memory_gb_hours=memory_gb_hours,
            gpu_hours=gpu_hours,
            total_cost_usd=total_cost,
            usage_metadata=metadata or {},
        )
    
    def record_artifact_access(
        self,
        artifact_id: str,
        user_id: Optional[str] = None,
        access_type: str = "download",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecordInfo:
        """Record artifact access for storage accounting."""
        self._ensure_tables()
        
        from sqlalchemy import insert
        engine = self._get_engine()
        
        record_id = f"art-{uuid.uuid4()}"
        
        with engine.begin() as conn:
            conn.execute(insert(CostRecord).values({
                "record_id": record_id,
                "timestamp": time.time(),
                "usage_type": "artifact_access",
                "model_id": artifact_id,
                "user_id": user_id,
                "metadata": {"access_type": access_type, **(metadata or {})},
            }))
        
        return CostRecordInfo(
            id=record_id,
            record_id=record_id,
            timestamp=time.time(),
            usage_type="artifact_access",
            model_id=artifact_id,
            user_id=user_id or "",
            usage_metadata=metadata or {},
        )
    
    # ----------------------------------------------------------------------- #
    # Querying
    # ----------------------------------------------------------------------- #
    
    def get_total_cost(
        self,
        user_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> float:
        """Get total cost matching filters."""
        self._ensure_tables()
        
        from sqlalchemy import select, func, and_, or_
        engine = self._get_engine()
        
        query = select(func.sum(CostRecord.total_cost_usd))
        conditions = []
        
        if user_id:
            conditions.append(CostRecord.user_id == user_id)
        if provider_id:
            conditions.append(CostRecord.provider_id == provider_id)
        if model_id:
            conditions.append(CostRecord.model_id == model_id)
        if start_time:
            conditions.append(CostRecord.timestamp >= start_time)
        if end_time:
            conditions.append(CostRecord.timestamp <= end_time)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        with engine.connect() as conn:
            result = conn.execute(query).scalar_one_or_none()
            return result or 0.0
    
    def get_usage_by_provider(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Dict[str, Dict[str, float]]:
        """Get usage aggregated by provider."""
        self._ensure_tables()
        
        from sqlalchemy import select, func, and_
        engine = self._get_engine()
        
        conditions = []
        if start_time:
            conditions.append(CostRecord.timestamp >= start_time)
        if end_time:
            conditions.append(CostRecord.timestamp <= end_time)
        
        with engine.connect() as conn:
            result = conn.execute(
                select(
                    CostRecord.provider_id,
                    func.sum(CostRecord.input_tokens).label("input_tokens"),
                    func.sum(CostRecord.output_tokens).label("output_tokens"),
                    func.sum(CostRecord.total_cost_usd).label("total_cost"),
                )
                .where(conditions or [True])
                .group_by(CostRecord.provider_id)
            ).fetchall()
        
        return {
            row[0] or "unknown": {
                "input_tokens": row[1] or 0,
                "output_tokens": row[2] or 0,
                "total_cost_usd": row[3] or 0.0,
            }
            for row in result
        }
    
    def get_usage_by_user(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get usage aggregated by user."""
        self._ensure_tables()
        
        from sqlalchemy import select, func, and_
        engine = self._get_engine()
        
        conditions = []
        if start_time:
            conditions.append(CostRecord.timestamp >= start_time)
        if end_time:
            conditions.append(CostRecord.timestamp <= end_time)
        
        with engine.connect() as conn:
            result = conn.execute(
                select(
                    CostRecord.user_id,
                    func.sum(CostRecord.total_cost_usd).label("total_cost"),
                    func.sum(CostRecord.input_tokens).label("input_tokens"),
                    func.sum(CostRecord.output_tokens).label("output_tokens"),
                    func.count(CostRecord.id).label("request_count"),
                )
                .where(conditions or [True])
                .group_by(CostRecord.user_id)
                .order_by(text("total_cost DESC"))
                .limit(limit)
            ).fetchall()
        
        return [
            {
                "user_id": row[0] or "anonymous",
                "total_cost_usd": row[1] or 0.0,
                "input_tokens": row[2] or 0,
                "output_tokens": row[3] or 0,
                "request_count": row[4] or 0,
            }
            for row in result
        ]
    
    def get_budget_status(
        self,
        user_id: str,
        daily_budget_usd: float,
    ) -> Dict[str, Any]:
        """Get budget status for a user."""
        # Get today's start
        now = time.time()
        today_start = now - (now % 86400)
        
        today_cost = self.get_total_cost(
            user_id=user_id,
            start_time=today_start,
            end_time=now,
        )
        
        return {
            "user_id": user_id,
            "daily_budget_usd": daily_budget_usd,
            "today_cost_usd": today_cost,
            "remaining_budget_usd": max(0, daily_budget_usd - today_cost),
            "budget_utilization": (today_cost / daily_budget_usd) if daily_budget_usd > 0 else 0,
        }
    
    def list_records(
        self,
        user_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        usage_type: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CostRecordInfo]:
        """List cost records with filters."""
        self._ensure_tables()
        
        from sqlalchemy import select, and_
        engine = self._get_engine()
        
        query = select(CostRecord)
        conditions = []
        
        if user_id:
            conditions.append(CostRecord.user_id == user_id)
        if provider_id:
            conditions.append(CostRecord.provider_id == provider_id)
        if usage_type:
            conditions.append(CostRecord.usage_type == usage_type)
        if start_time:
            conditions.append(CostRecord.timestamp >= start_time)
        if end_time:
            conditions.append(CostRecord.timestamp <= end_time)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        with engine.connect() as conn:
            records = conn.execute(
                query.offset(offset).limit(limit).fetchall()
            )
        
        return [CostRecordInfo.from_record(r) for r in records]


# --------------------------------------------------------------------------- #
# Global instance
# --------------------------------------------------------------------------- #

usage_accountant = UsageAccountant()


# --------------------------------------------------------------------------- #
# Import hook for backward compatibility
# --------------------------------------------------------------------------- #

def get_usage_accountant() -> UsageAccountant:
    """Get the global usage accountant instance."""
    return UsageAccountant.get_instance()


# --------------------------------------------------------------------------- #
# Budget Manager
# --------------------------------------------------------------------------- #

@dataclass
class BudgetLimit:
    """Budget limit configuration."""
    user_id: str
    daily_usd: float = 0.0
    monthly_usd: float = 0.0
    provider_limits: Dict[str, float] = field(default_factory=dict)  # Per-provider daily limit


class BudgetManager:
    """Manages budget limits and enforcement."""
    
    def __init__(self):
        self._accountant = UsageAccountant.get_instance()
        self._limits: Dict[str, Dict[str, Any]] = {}
    
    def set_budget(self, user_id: str, daily_usd: float = 0.0, monthly_usd: float = 0.0,
                   provider_limits: Optional[Dict[str, float]] = None) -> None:
        """Set budget limits for a user."""
        self._limits[user_id] = {
            "daily_usd": daily_usd,
            "monthly_usd": monthly_usd,
            "provider_limits": provider_limits or {},
            "set_at": time.time(),
        }
    
    def check_budget(
        self,
        user_id: str,
        estimated_cost_usd: float,
        provider_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Check if estimated cost is within budget.
        
        Returns (is_allowed, message).
        """
        limit = self._limits.get(user_id)
        if not limit:
            return True, "No budget limit set"
        
        now = time.time()
        today_start = now - (now % 86400)
        month_start = now - (now % 2592000)  # Rough 30-day month
        
        # Get current usage
        daily_usage = self._accountant.get_total_cost(
            user_id=user_id,
            start_time=today_start,
            end_time=now,
        )
        
        monthly_usage = self._accountant.get_total_cost(
            user_id=user_id,
            start_time=month_start,
            end_time=now,
        )
        
        # Check daily limit
        if limit["daily_usd"] > 0:
            if daily_usage + estimated_cost_usd > limit["daily_usd"]:
                return False, (
                    f"Daily budget limit exceeded: ${daily_usage:.2f}/{limit['daily_usd']:.2f} USD "
                    f"for requested ${estimated_cost_usd:.2f} operation"
                )
        
        # Check monthly limit
        if limit["monthly_usd"] > 0:
            if monthly_usage + estimated_cost_usd > limit["monthly_usd"]:
                return False, (
                    f"Monthly budget limit exceeded: ${monthly_usage:.2f}/{limit['monthly_usd']:.2f} USD"
                )
        
        # Check provider-specific limit
        if provider_id and limit.get("provider_limits"):
            provider_limit = limit["provider_limits"].get(provider_id, float("inf"))
            if provider_limit > 0:
                provider_usage = self._accountant.get_total_cost(
                    user_id=user_id,
                    provider_id=provider_id,
                    start_time=today_start,
                    end_time=now,
                )
                if provider_usage + estimated_cost_usd > provider_limit:
                    return False, (
                        f"Provider {provider_id} daily limit exceeded: "
                        f"${provider_usage:.2f}/${provider_limit:.2f} USD"
                    )
        
        return True, "Within budget"
    
    def get_status(self, user_id: str) -> Dict[str, Any]:
        """Get budget status for a user."""
        return self._accountant.get_budget_status(
            user_id,
            self._limits.get(user_id, {}).get("daily_usd", 0.0),
        )