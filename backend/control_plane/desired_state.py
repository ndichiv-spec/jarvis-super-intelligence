"""
Desired State - The intended configuration of the JARVIS platform.

The Control Plane knows what the system SHOULD be, and continuously
reconciles toward that state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any
from enum import Enum
import hashlib
import json
import time


class ServiceStatus(str, Enum):
    """Desired service status"""
    RUNNING = "running"
    STOPPED = "stopped"
    DISABLED = "disabled"
    PENDING = "pending"


class AuthStatus(str, Enum):
    """Desired authentication status"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    NOT_READY = "not_ready"


@dataclass
class DesiredProvider:
    """Desired configuration for an AI provider"""
    name: str
    desired_model: str
    status: Literal["healthy", "degraded", "unavailable"] = "healthy"
    endpoint: Optional[str] = None
    capabilities: list[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "desired_model": self.desired_model,
            "status": self.status,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
        }


@dataclass
class DesiredAuth:
    """Desired authentication configuration"""
    enabled: bool = True
    oidc_enabled: bool = True
    api_key_auth: bool = True
    session_timeout_sec: int = 3600
    max_sessions: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "oidc_enabled": self.oidc_enabled,
            "api_key_auth": self.api_key_auth,
            "session_timeout_sec": self.session_timeout_sec,
            "max_sessions": self.max_sessions,
        }


@dataclass
class DesiredService:
    """Desired configuration for a core service"""
    name: str
    status: str  # running, stopped, degraded
    port: Optional[int] = None
    dependencies: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    restart_policy: Literal["always", "on-failure", "never"] = "on-failure"
    max_restarts: int = 3
    health_check_path: str = "/health"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "port": self.port,
            "dependencies": self.dependencies,
            "capabilities": self.capabilities,
            "restart_policy": self.restart_policy,
            "max_restarts": self.max_restarts,
            "health_check_path": self.health_check_path,
        }


@dataclass
class DesiredFeature:
    """Desired configuration for a platform feature"""
    name: str
    enabled: bool = True
    policy: Literal["auto", "approval", "readonly"] = "auto"
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "policy": self.policy,
            "description": self.description,
        }


@dataclass
class DesiredState:
    """
    The authoritative desired state of the JARVIS platform.
    
    This represents what the system SHOULD be, as configured by operators.
    The reconciliation engine continuously works to align observed state
    with desired state.
    """
    
    version: str = "1.0"
    updated_at: float = field(default_factory=time.time)
    updated_by: str = "system"
    
    # Core services desired state
    api: DesiredService = field(default_factory=lambda: DesiredService(
        name="api",
        status="running",
        port=8000,
        capabilities=["chat", "generate", "browse", "sandbox"],
    ))
    
    brain: DesiredService = field(default_factory=lambda: DesiredService(
        name="brain",
        status="running",
        capabilities=["inference", "reasoning"],
    ))
    
    browser: DesiredService = field(default_factory=lambda: DesiredService(
        name="browser",
        status="running",
        capabilities=["search", "navigate", "research"],
    ))
    
    sandbox: DesiredService = field(default_factory=lambda: DesiredService(
        name="sandbox",
        status="running",
        capabilities=["execute", "patch", "test"],
    ))
    
    research: DesiredService = field(default_factory=lambda: DesiredService(
        name="research",
        status="running",
        capabilities=["web_search", "evidence_capture"],
    ))
    
    knowledge: DesiredService = field(default_factory=lambda: DesiredService(
        name="knowledge",
        status="running",
        capabilities=["index", "search", "store"],
    ))
    
    memory: DesiredService = field(default_factory=lambda: DesiredService(
        name="memory",
        status="running",
        capabilities=["recall", "store", "consolidate"],
    ))
    
    learning: DesiredService = field(default_factory=lambda: DesiredService(
        name="learning",
        status="running",
        capabilities=["challenge", "lesson", "dataset", "training"],
    ))
    
    # Authentication
    auth: DesiredAuth = field(default_factory=DesiredAuth)
    
    # Providers (configured externally, this tracks desired state)
    providers: Dict[str, DesiredProvider] = field(default_factory=lambda: {
        "nvidia": DesiredProvider(
            name="nvidia",
            desired_model="nvidia/nemotron-3-ultra-550b-a55b",
            status="healthy",
            capabilities=["chat", "reasoning", "streaming"],
        ),
        "google": DesiredProvider(
            name="google",
            desired_model="gemini-2.5-pro",
            status="healthy",
            capabilities=["chat", "vision", "reasoning"],
        ),
        "openai": DesiredProvider(
            name="openai",
            desired_model="gpt-5",
            status="healthy",
            capabilities=["chat", "reasoning", "tool_calling"],
        ),
    })
    
    # Features with policy
    features: Dict[str, DesiredFeature] = field(default_factory=lambda: {
        "sandbox_immediate_effects": DesiredFeature(
            name="sandbox_immediate_effects",
            enabled=True,
            policy="auto",
            description="Allow sandbox to produce verified system changes",
        ),
        "automatic_restarts": DesiredFeature(
            name="automatic_restarts",
            enabled=True,
            policy="auto",
            description="Auto-restart recoverable service failures",
        ),
        "provider_fallback": DesiredFeature(
            name="provider_fallback",
            enabled=True,
            policy="auto",
            description="Auto-fallback to healthy providers",
        ),
    })
    
    def update(self, **kwargs) -> None:
        """Update desired state"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = time.time()
    
    def get_service(self, name: str) -> Optional[DesiredService]:
        """Get desired state for a service"""
        return getattr(self, name, None)
    
    def get_provider(self, name: str) -> Optional[DesiredProvider]:
        """Get desired state for a provider"""
        return self.providers.get(name)
    
    def get_feature(self, name: str) -> Optional[DesiredFeature]:
        """Get desired state for a feature"""
        return self.features.get(name)
    
    def compute_hash(self) -> str:
        """Compute hash of current desired state for drift detection"""
        state_dict = {
            "api": self.api.to_dict(),
            "brain": self.brain.to_dict(),
            "browser": self.browser.to_dict(),
            "sandbox": self.sandbox.to_dict(),
            "research": self.research.to_dict(),
            "knowledge": self.knowledge.to_dict(),
            "memory": self.memory.to_dict(),
            "learning": self.learning.to_dict(),
            "auth": self.auth.to_dict(),
            "providers": {k: v.to_dict() for k, v in self.providers.items()},
            "features": {k: v.to_dict() for k, v in self.features.items()},
        }
        return hashlib.sha256(
            json.dumps(state_dict, sort_keys=True).encode()
        ).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "version": self.version,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
            "hash": self.compute_hash(),
            "services": {
                "api": self.api.to_dict(),
                "brain": self.brain.to_dict(),
                "browser": self.browser.to_dict(),
                "sandbox": self.sandbox.to_dict(),
                "research": self.research.to_dict(),
                "knowledge": self.knowledge.to_dict(),
                "memory": self.memory.to_dict(),
                "learning": self.learning.to_dict(),
            },
            "auth": self.auth.to_dict(),
            "providers": {k: v.to_dict() for k, v in self.providers.items()},
            "features": {k: v.to_dict() for k, v in self.features.items()},
        }


# Global desired state instance (singleton)
_desired_state_instance: Optional[DesiredState] = None


def get_desired_state() -> DesiredState:
    """Get the global desired state instance"""
    global _desired_state_instance
    if _desired_state_instance is None:
        _desired_state_instance = DesiredState()
    return _desired_state_instance


def set_desired_state(state: DesiredState) -> None:
    """Set the global desired state instance"""
    global _desired_state_instance
    _desired_state_instance = state