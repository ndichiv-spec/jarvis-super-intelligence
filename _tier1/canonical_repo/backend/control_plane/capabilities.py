"""
Capability Registry - Track platform capabilities and their states.

Each capability represents a distinct function the platform can perform,
tracked by which services provide it and its current availability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List
from enum import Enum
import time
import threading


class CapabilityState(str, Enum):
    """State of a capability"""
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN = "unknown"


@dataclass
class Capability:
    """A platform capability"""
    name: str
    description: str = ""
    provided_by: List[str] = field(default_factory=list)  # Service IDs
    required_by: List[str] = field(default_factory=list)  # Tasks/Features that need it
    state: CapabilityState = CapabilityState.UNKNOWN
    version: Optional[str] = None
    latency_ms: Optional[float] = None
    last_checked: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "provided_by": self.provided_by,
            "required_by": self.required_by,
            "state": self.state.value,
            "version": self.version,
            "latency_ms": self.latency_ms,
            "last_checked": self.last_checked,
        }


class CapabilityRegistry:
    """
    Registry of all platform capabilities.
    
    Tracks what the platform can do, by whom it's provided, and its current state.
    """
    
    _instance: Optional["CapabilityRegistry"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
    
    @classmethod
    def get_instance(cls) -> "CapabilityRegistry":
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)"""
        with cls._lock:
            cls._instance = None
    
    def register(self, capability: Capability) -> None:
        """Register a capability"""
        self._capabilities[capability.name] = capability
    
    def get(self, name: str) -> Optional[Capability]:
        """Get capability by name"""
        return self._capabilities.get(name)
    
    def get_all(self) -> List[Capability]:
        """Get all capabilities"""
        return list(self._capabilities.values())
    
    def get_by_state(self, state: CapabilityState) -> List[Capability]:
        """Get capabilities by state"""
        return [c for c in self._capabilities.values() if c.state == state]
    
    def get_available(self) -> List[Capability]:
        """Get all available capabilities"""
        return [c for c in self._capabilities.values() 
                if c.state in (CapabilityState.AVAILABLE, CapabilityState.DEGRADED)]
    
    def update_state(self, name: str, state: CapabilityState) -> None:
        """Update capability state"""
        cap = self.get(name)
        if cap:
            cap.state = state
            cap.last_checked = time.time()
    
    def update_latency(self, name: str, latency_ms: float) -> None:
        """Update capability latency"""
        cap = self.get(name)
        if cap:
            cap.latency_ms = latency_ms
            cap.last_checked = time.time()
    
    def list_for_provider(self, provider_id: str) -> List[Capability]:
        """List capabilities provided by a service"""
        return [
            c for c in self._capabilities.values()
            if provider_id in c.provided_by
        ]
    
    def services_for_capability(self, capability_name: str) -> List[str]:
        """Get all services that provide a capability"""
        cap = self.get(capability_name)
        return cap.provided_by if cap else []
    
    def register_core_capabilities(self) -> None:
        """Register the core JARVIS capabilities"""
        core_capabilities = [
            Capability(
                name="chat",
                description="Chat/inference capabilities",
                provided_by=["jarvis_api", "jarvis_brain", "silverwing", "nvidia", "openai", "google"],
                required_by=["autonomous_agents", "conversational_ai"],
            ),
            Capability(
                name="reasoning",
                description="Logical reasoning and analysis",
                provided_by=["jarvis_api", "jarvis_brain", "nvidia", "openai", "google"],
                required_by=["problem_solving", "research", "planning"],
            ),
            Capability(
                name="code_generation",
                description="Code generation and explanation",
                provided_by=["jarvis_api", "jarvis_brain", "nvidia", "google"],
                required_by=["coding_tasks", "sandbox"],
            ),
            Capability(
                name="browse",
                description="Web browsing and navigation",
                provided_by=["browser"],
                required_by=["research", "information_gathering"],
            ),
            Capability(
                name="research",
                description="Web research and evidence gathering",
                provided_by=["research", "browser"],
                required_by=["knowledge_creation", "analysis"],
            ),
            Capability(
                name="knowledge",
                description="Knowledge storage and retrieval",
                provided_by=["knowledge"],
                required_by=["memory", "learning", "research"],
            ),
            Capability(
                name="memory",
                description="Persistent memory and context",
                provided_by=["memory"],
                required_by=["all_tasks"],
            ),
            Capability(
                name="sandbox",
                description="Code execution and testing",
                provided_by=["sandbox"],
                required_by=["code_tasks", "testing", "patching"],
            ),
            Capability(
                name="tool_use",
                description="Tool registry and execution",
                provided_by=["sandbox", "browser"],
                required_by=["agents", "automated_tasks"],
            ),
            Capability(
                name="verification",
                description="Claim verification and fact checking",
                provided_by=["knowledge", "research", "sandbox"],
                required_by=["learning", "decision_making"],
            ),
            Capability(
                name="learning",
                description="Curriculum and lesson generation",
                provided_by=["learning"],
                required_by=["improvement", "skill_building"],
            ),
            Capability(
                name="model_routing",
                description="Intelligent model selection",
                provided_by=["model_gateway"],
                required_by=["all_ai_tasks"],
            ),
            Capability(
                name="authentication",
                description="User and service authentication",
                provided_by=["auth"],
                required_by=["access_control"],
            ),
            Capability(
                name="authorization",
                description="RBAC and permission checking",
                provided_by=["auth"],
                required_by=["all_protected_operations"],
            ),
        ]
        
        for cap in core_capabilities:
            self.register(cap)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            name: cap.to_dict()
            for name, cap in self._capabilities.items()
        }


# Global registry instance
capability_registry = CapabilityRegistry.get_instance()