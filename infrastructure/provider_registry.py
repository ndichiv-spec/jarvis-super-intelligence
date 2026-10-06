"""
Durable Provider Registry - PostgreSQL-backed provider metadata catalog.

Provides a canonical ProviderRegistry that persists provider metadata in PostgreSQL
while maintaining compatibility with existing routing and discovery patterns.

Phase 2 compliance:
- Persists NON-SECRET provider metadata only (endpoint metadata, capabilities, health state)
- Provider credentials continue through existing Secret Manager/Vault architecture
- Supports health state tracking and verification state
- Tracks supported models per provider
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
    cast,
)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger("provider_registry")

# --------------------------------------------------------------------------- #
# Provider health states
# --------------------------------------------------------------------------- #

class ProviderHealthState(str, Enum):
    """Provider health states for durable tracking."""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    TEMPORARILY_DISABLED = "temporarily_disabled"


# --------------------------------------------------------------------------- #
# Provider environments
# --------------------------------------------------------------------------- #

class ProviderEnvironment(str, Enum):
    """Provider deployment environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    LOCAL = "local"
    OFFLINE = "offline"


# --------------------------------------------------------------------------- #
# SQLAlchemy model
# --------------------------------------------------------------------------- #

Base = declarative_base()


class ProviderRecord(Base):
    """SQLAlchemy model for durable provider registry."""
    __tablename__ = "providers"
    
    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Provider identifier
    provider_id = Column(String(64), nullable=False, unique=True, index=True)
    provider_name = Column(String(128), nullable=False)
    
    # Adapter information
    adapter = Column(String(64), nullable=True)  # e.g., 'openai', 'anthropic', 'local'
    
    # Capabilities
    capabilities = Column(JSON, default=[])  # JSON for cross-db compatibility
    supported_modalities = Column(JSON, default=["text"])  # text, image, audio, video
    
    # Environment
    enabled = Column(Boolean, default=True)
    environment = Column(String(32), default="development")
    
    # Endpoint metadata (non-secret only)
    endpoint_type = Column(String(32), default="api")  # api, local, remote
    endpoint_url = Column(String(512), nullable=True)  # Only for non-sensitive endpoints
    region = Column(String(64), nullable=True)  # Cloud region
    version = Column(String(32), nullable=True)  # API version
    
    # Health state
    health_state = Column(String(32), default="unknown")
    last_health_check = Column(Float, default=0.0)
    health_check_message = Column(Text, nullable=True)
    
    # Inference verification
    verification_enabled = Column(Boolean, default=False)
    verification_state = Column(String(32), default="unverified")
    last_verification = Column(Float, default=0.0)
    verification_results = Column(JSON, default={})
    
    # Supported models (list of model IDs)
    supported_models = Column(JSON, default=[])
    
    # Additional metadata
    provider_data = Column(JSON, default={})
    
    # Timestamps
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    
    # Indexing
    __table_args__ = (
        Index("idx_providers_enabled", "enabled"),
        Index("idx_providers_health", "health_state"),
        Index("idx_providers_env", "environment"),
    )


# --------------------------------------------------------------------------- #
# Dataclass for API compatibility
# --------------------------------------------------------------------------- #

@dataclass
class ProviderInfo:
    """Provider information for API responses."""
    id: str
    provider_id: str
    provider_name: str
    adapter: str = ""
    capabilities: List[str] = field(default_factory=list)
    supported_modalities: List[str] = field(default_factory=lambda: ["text"])
    enabled: bool = True
    environment: str = "development"
    endpoint_type: str = "api"
    endpoint_url: str = ""
    region: str = ""
    version: str = ""
    health_state: str = "unknown"
    last_health_check: float = 0.0
    health_check_message: str = ""
    verification_enabled: bool = False
    verification_state: str = "unverified"
    last_verification: float = 0.0
    verification_results: Dict[str, Any] = field(default_factory=dict)
    supported_models: List[str] = field(default_factory=list)
    provider_data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    
    @classmethod
    def from_record(cls, record: ProviderRecord) -> "ProviderInfo":
        """Create ProviderInfo from SQLAlchemy model record."""
        return cls(
            id=record.id,
            provider_id=record.provider_id,
            provider_name=record.provider_name,
            adapter=record.adapter or "",
            capabilities=record.capabilities or [],
            supported_modalities=record.supported_modalities or ["text"],
            enabled=record.enabled if record.enabled is not None else True,
            environment=record.environment or "development",
            endpoint_type=record.endpoint_type or "api",
            endpoint_url=record.endpoint_url or "",
            region=record.region or "",
            version=record.version or "",
            health_state=record.health_state or "unknown",
            last_health_check=record.last_health_check or 0.0,
            health_check_message=record.health_check_message or "",
            verification_enabled=record.verification_enabled if record.verification_enabled is not None else False,
            verification_state=record.verification_state or "unverified",
            last_verification=record.last_verification or 0.0,
            verification_results=record.verification_results or {},
            supported_models=record.supported_models or [],
            provider_data=record.provider_data or {},
            created_at=record.created_at or 0.0,
            updated_at=record.updated_at or 0.0,
        )


# --------------------------------------------------------------------------- #
# Provider Registry Service
# --------------------------------------------------------------------------- #

def bootstrap_providers() -> Dict[str, ProviderInfo]:
    """Create bootstrap providers for known adapters."""
    registry = ProviderRegistry.get_instance()
    providers = {}
    
    for adapter, capabilities in registry.DEFAULT_CAPABILITIES.items():
        provider = ProviderInfo(
            id=str(uuid.uuid4()),
            provider_id=adapter,
            provider_name=adapter.title(),
            adapter=adapter,
            capabilities=capabilities,
            endpoint_type=registry.ENDPOINT_TYPES.get(adapter, "api"),
            environment="development",
            health_state="unknown",
        )
        registry.register(provider)
        providers[adapter] = provider
    
    return providers


class ProviderRegistry:
    """
    Durable provider registry backed by PostgreSQL.
    
    Provides CRUD operations for provider metadata (non-secret only),
    health state tracking, and verification state. Provider credentials
    continue through the existing Secret Manager/Vault architecture.
    """
    
    _instance: Optional["ProviderRegistry"] = None
    
    # Default capabilities for common adapters
    DEFAULT_CAPABILITIES: Dict[str, List[str]] = {
        "openai": ["chat", "completion", "embedding", "image", "audio", "reasoning"],
        "anthropic": ["chat", "completion", "image"],
        "google": ["chat", "completion", "embedding", "image"],
        "groq": ["chat", "completion"],
        "deepseek": ["chat", "completion", "embedding"],
        "ollama": ["chat", "completion", "embedding"],
        "llamacpp": ["chat", "completion"],
        "bedrock": ["chat", "completion", "embedding"],
        "vertex": ["chat", "completion", "embedding"],
        "silverwing": ["chat", "completion", "embedding", "reasoning"],
        "vllm": ["chat", "completion", "embedding"],
        "local": ["chat", "completion"],
    }
    
    # Default endpoint types
    ENDPOINT_TYPES: Dict[str, str] = {
        "openai": "api",
        "anthropic": "api",
        "google": "api",
        "groq": "api",
        "deepseek": "api",
        "ollama": "local",
        "llamacpp": "local",
        "bedrock": "api",
        "vertex": "api",
        "silverwing": "local",
        "vllm": "local",
        "local": "local",
    }
    
    def __init__(self, engine=None):
        """Initialize with optional SQLAlchemy engine."""
        self._engine = engine
        self._tables_created = False
    
    @classmethod
    def get_instance(cls, engine=None) -> "ProviderRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(engine)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton and clear data (for testing)."""
        if cls._instance is not None:
            # Clear all records from the providers table
            try:
                engine = cls._instance._get_engine()
                from sqlalchemy import delete
                with engine.begin() as conn:
                    conn.execute(delete(ProviderRecord))
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
        """Ensure provider tables exist."""
        if self._tables_created:
            return
        
        engine = self._get_engine()
        
        # Create tables if they don't exist
        with engine.begin() as conn:
            from sqlalchemy import inspect
            inspector = inspect(conn)
            if "providers" not in inspector.get_table_names():
                Base.metadata.create_all(conn)
        
        self._tables_created = True
    
    # ----------------------------------------------------------------------- #
    # CRUD Operations
    # ----------------------------------------------------------------------- #
    
    def register(self, provider_info: ProviderInfo) -> ProviderInfo:
        """Register a new provider (or update existing by provider_id)."""
        self._ensure_tables()
        
        from sqlalchemy import insert, update, select
        
        engine = self._get_engine()
        
        # Check if provider exists
        with engine.begin() as conn:
            existing = conn.execute(
                select(ProviderRecord).where(ProviderRecord.provider_id == provider_info.provider_id)
            ).scalar_one_or_none()
            
            if existing:
                # Update existing
                stmt = (
                    update(ProviderRecord)
                    .where(ProviderRecord.provider_id == provider_info.provider_id)
                    .values(
                        provider_name=provider_info.provider_name,
                        adapter=provider_info.adapter,
                        capabilities=provider_info.capabilities,
                        supported_modalities=provider_info.supported_modalities,
                        enabled=provider_info.enabled,
                        environment=provider_info.environment,
                        endpoint_type=provider_info.endpoint_type,
                        endpoint_url=provider_info.endpoint_url,
                        region=provider_info.region,
                        version=provider_info.version,
                        health_state=provider_info.health_state,
                        last_health_check=provider_info.last_health_check,
                        health_check_message=provider_info.health_check_message,
                        verification_enabled=provider_info.verification_enabled,
                        verification_state=provider_info.verification_state,
                        last_verification=provider_info.last_verification,
                        verification_results=provider_info.verification_results,
                        supported_models=provider_info.supported_models,
                        provider_data=provider_info.provider_data,
                        updated_at=time.time(),
                    )
                )
                conn.execute(stmt)
                return provider_info
            else:
                # Insert new
                record = ProviderRecord(
                    id=provider_info.id or str(uuid.uuid4()),
                    provider_id=provider_info.provider_id,
                    provider_name=provider_info.provider_name,
                    adapter=provider_info.adapter,
                    capabilities=provider_info.capabilities,
                    supported_modalities=provider_info.supported_modalities,
                    enabled=provider_info.enabled,
                    environment=provider_info.environment,
                    endpoint_type=provider_info.endpoint_type,
                    endpoint_url=provider_info.endpoint_url,
                    region=provider_info.region,
                    version=provider_info.version,
                    health_state=provider_info.health_state,
                    last_health_check=provider_info.last_health_check,
                    health_check_message=provider_info.health_check_message,
                    verification_enabled=provider_info.verification_enabled,
                    verification_state=provider_info.verification_state,
                    last_verification=provider_info.last_verification,
                    verification_results=provider_info.verification_results,
                    supported_models=provider_info.supported_models,
                    provider_data=provider_info.provider_data,
                )
                conn.execute(insert(ProviderRecord).values({
                    "id": record.id,
                    "provider_id": record.provider_id,
                    "provider_name": record.provider_name,
                    "adapter": record.adapter,
                    "capabilities": record.capabilities,
                    "supported_modalities": record.supported_modalities,
                    "enabled": record.enabled,
                    "environment": record.environment,
                    "endpoint_type": record.endpoint_type,
                    "endpoint_url": record.endpoint_url,
                    "region": record.region,
                    "version": record.version,
                    "health_state": record.health_state,
                    "last_health_check": record.last_health_check,
                    "health_check_message": record.health_check_message,
                    "verification_enabled": record.verification_enabled,
                    "verification_state": record.verification_state,
                    "last_verification": record.last_verification,
                    "verification_results": record.verification_results,
                    "supported_models": record.supported_models,
                    "provider_data": record.provider_data,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }))
                return provider_info
    
    def get(self, provider_id: str) -> Optional[ProviderInfo]:
        """Get provider by provider_id."""
        self._ensure_tables()
        
        from sqlalchemy import select
        engine = self._get_engine()
        
        with engine.connect() as conn:
            record = conn.execute(
                select(ProviderRecord).where(ProviderRecord.provider_id == provider_id)
            ).fetchone()
            
            return ProviderInfo.from_record(record) if record else None
    
    def get_by_id(self, internal_id: str) -> Optional[ProviderInfo]:
        """Get provider by internal ID."""
        self._ensure_tables()
        
        from sqlalchemy import select
        engine = self._get_engine()
        
        with engine.connect() as conn:
            record = conn.execute(
                select(ProviderRecord).where(ProviderRecord.id == internal_id)
            ).fetchone()
            
            return ProviderInfo.from_record(record) if record else None
    
    def list_providers(
        self,
        enabled: Optional[bool] = None,
        health_state: Optional[str] = None,
        environment: Optional[str] = None,
        capability: Optional[str] = None,
        adapter: Optional[str] = None,
    ) -> List[ProviderInfo]:
        """List providers with optional filters."""
        self._ensure_tables()
        
        from sqlalchemy import select
        engine = self._get_engine()
        
        query = select(ProviderRecord)
        
        if enabled is not None:
            query = query.where(ProviderRecord.enabled == enabled)
        
        if health_state:
            query = query.where(ProviderRecord.health_state == health_state)
        
        if environment:
            query = query.where(ProviderRecord.environment == environment)
        
        if adapter:
            query = query.where(ProviderRecord.adapter == adapter)
        
        if capability:
            # Filter capabilities: check if capability is in the JSON array
            for cap in ([capability] if isinstance(capability, str) else capability):
                try:
                    # Try JSON array contains (PostgreSQL)
                    query = query.where(ProviderRecord.capabilities.contains([cap]))
                except Exception:
                    # Fallback for SQLite
                    from sqlalchemy import String
                    query = query.where(func.lower(
                        cast(ProviderRecord.capabilities, String)
                    ).like(f"%{cap.lower()}%"))
        
        with engine.connect() as conn:
            records = conn.execute(query).fetchall()
            return [ProviderInfo.from_record(r) for r in records]
    
    def update_health(
        self,
        provider_id: str,
        health_state: str,
        message: str = "",
        verification_results: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update provider health state."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            result = conn.execute(
                select(ProviderRecord).where(ProviderRecord.provider_id == provider_id)
            ).fetchone()
            
            if not result:
                return False
            
            stmt = (
                update(ProviderRecord)
                .where(ProviderRecord.provider_id == provider_id)
                .values(
                    health_state=health_state,
                    health_check_message=message,
                    last_health_check=time.time(),
                    verification_state="verified" if verification_results else "unverified",
                    verification_results=verification_results or result.verification_results,
                    updated_at=time.time(),
                )
            )
            conn.execute(stmt)
            return True
    
    def update_verification(
        self,
        provider_id: str,
        results: Dict[str, Any],
        enabled: bool = True,
    ) -> bool:
        """Update provider verification state with results."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            result = conn.execute(
                select(ProviderRecord).where(ProviderRecord.provider_id == provider_id)
            ).fetchone()
            
            if not result:
                return False
            
            stmt = (
                update(ProviderRecord)
                .where(ProviderRecord.provider_id == provider_id)
                .values(
                    verification_enabled=enabled,
                    verification_state="verified",
                    last_verification=time.time(),
                    verification_results=results,
                    updated_at=time.time(),
                )
            )
            conn.execute(stmt)
            return True
    
    def disable_provider(
        self,
        provider_id: str,
        reason: str,
    ) -> bool:
        """Disable a provider temporarily."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            result = conn.execute(
                select(ProviderRecord).where(ProviderRecord.provider_id == provider_id)
            ).fetchone()
            
            if not result:
                return False
            
            current_provider_data = result.provider_data or {}
            if "disabled_reason" not in current_provider_data:
                current_provider_data = dict(current_provider_data)
                current_provider_data["disabled_reason"] = reason
            
            stmt = (
                update(ProviderRecord)
                .where(ProviderRecord.provider_id == provider_id)
                .values(
                    enabled=False,
                    health_state="temporarily_disabled",
                    provider_data=current_provider_data,
                    updated_at=time.time(),
                )
            )
            conn.execute(stmt)
            return True
    
    def enable_provider(
        self,
        provider_id: str,
    ) -> bool:
        """Enable a disabled provider."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            result = conn.execute(
                select(ProviderRecord).where(ProviderRecord.provider_id == provider_id)
            ).fetchone()
            
            if not result:
                return False
            
            # Clear disabled_reason from provider_data
            current_provider_data = result.provider_data or {}
            if "disabled_reason" in current_provider_data:
                current_provider_data = {k: v for k, v in current_provider_data.items() 
                                       if k != "disabled_reason"}
            
            stmt = (
                update(ProviderRecord)
                .where(ProviderRecord.provider_id == provider_id)
                .values(
                    enabled=True,
                    health_state="healthy",
                    provider_data=current_provider_data,
                    updated_at=time.time(),
                )
            )
            conn.execute(stmt)
            return True
    
    def add_supported_model(
        self,
        provider_id: str,
        model_id: str,
    ) -> bool:
        """Add a model to the supported models list."""
        self._ensure_tables()
        
        from sqlalchemy import update, select
        engine = self._get_engine()
        
        with engine.begin() as conn:
            result = conn.execute(
                select(ProviderRecord).where(ProviderRecord.provider_id == provider_id)
            ).fetchone()
            
            if not result:
                return False
            
            supported_models = result.supported_models or []
            if model_id not in supported_models:
                supported_models = list(supported_models) + [model_id]
            
            stmt = (
                update(ProviderRecord)
                .where(ProviderRecord.provider_id == provider_id)
                .values(
                    supported_models=supported_models,
                    updated_at=time.time(),
                )
            )
            conn.execute(stmt)
            return True
    
    # ----------------------------------------------------------------------- #
    # Integration helpers
    # ----------------------------------------------------------------------- #
    
    def get_provider_defaults(self, adapter: str) -> Dict[str, Any]:
        """Get default settings for a provider adapter."""
        return {
            "capabilities": self.DEFAULT_CAPABILITIES.get(adapter, ["chat", "completion"]),
            "endpoint_type": self.ENDPOINT_TYPES.get(adapter, "api"),
        }
    
    def is_provider_enabled(self, provider_id: str) -> bool:
        """Check if a provider is enabled."""
        provider = self.get(provider_id)
        return provider is not None and provider.enabled


# --------------------------------------------------------------------------- #
# Convenience functions for singleton access
# --------------------------------------------------------------------------- #

def get_provider_registry(engine=None) -> ProviderRegistry:
    """Get the global ProviderRegistry instance."""
    return ProviderRegistry.get_instance(engine)


def reset_provider_registry() -> None:
    """Reset the ProviderRegistry singleton (testing)."""
    ProviderRegistry.reset_instance()