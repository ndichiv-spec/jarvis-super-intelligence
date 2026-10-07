"""
Service Registry - Unified registration for all platform services.

Tracks all services, their health, capabilities, and dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Callable
from enum import Enum
import time
import threading
import logging

logger = logging.getLogger("control_plane.service_registry")


class ServiceType(str, Enum):
    """Types of services in the platform"""
    API = "api"
    BRAIN = "brain"
    RUNTIME = "runtime"
    SANDBOX = "sandbox"
    BROWSER = "browser"
    RESEARCH = "research"
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    LEARNING = "learning"
    PROVIDER = "provider"
    OBSERVABILITY = "observability"
    AUTH = "auth"
    FRONTEND = "frontend"
    UNKNOWN = "unknown"


class ServiceState(str, Enum):
    """Current state of a service"""
    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"


@dataclass
class ServiceEntry:
    """Entry for a registered service"""
    service_id: str
    name: str
    type: ServiceType
    state: ServiceState = ServiceState.UNKNOWN
    
    # Process information
    pid: Optional[int] = None
    port: Optional[int] = None
    
    # Addresses
    endpoint: Optional[str] = None
    
    # Health
    health_endpoint: str = "/health"
    liveness_endpoint: str = "/health/live"
    readiness_endpoint: str = "/health/ready"
    
    # Capabilities
    capabilities: List[str] = field(default_factory=list)
    
    # Dependencies
    dependencies: List[str] = field(default_factory=list)  # Other service_ids this depends on
    
    # Health tracking
    last_seen: float = field(default_factory=time.time)
    last_failure: Optional[float] = None
    restart_count: int = 0
    consecutive_failures: int = 0
    error_message: Optional[str] = None
    
    # Version info
    version: Optional[str] = None
    observed_version: Optional[str] = None
    
    # Metadata
    description: str = ""
    enabled: bool = True
    auto_restart: bool = True
    max_restarts: int = 3
    restart_backoff_sec: float = 1.0
    
    # Status details
    status_details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "name": self.name,
            "type": self.type.value,
            "state": self.state.value,
            "pid": self.pid,
            "port": self.port,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "dependencies": self.dependencies,
            "last_seen": self.last_seen,
            "last_failure": self.last_failure,
            "restart_count": self.restart_count,
            "consecutive_failures": self.consecutive_failures,
            "error_message": self.error_message,
            "version": self.version,
            "observed_version": self.observed_version,
            "enabled": self.enabled,
            "auto_restart": self.auto_restart,
            "max_restarts": self.max_restarts,
            "status_details": self.status_details,
        }


class ServiceRegistry:
    """
    Unified registry for all platform services.
    
    Tracks service lifecycle, health, and dependencies.
    """
    
    _instance: Optional["ServiceRegistry"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._services: Dict[str, ServiceEntry] = {}
        self._health_checkers: Dict[str, Callable[[], Any]] = {}
        self._start_handlers: Dict[str, Callable[[], Any]] = {}
        self._stop_handlers: Dict[str, Callable[[], Any]] = {}
    
    @classmethod
    def get_instance(cls) -> "ServiceRegistry":
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
    
    def register(self, entry: ServiceEntry) -> None:
        """Register a new service"""
        self._services[entry.service_id] = entry
        logger.info(f"Registered service: {entry.service_id} ({entry.type.value})")
    
    def unregister(self, service_id: str) -> None:
        """Unregister a service"""
        if service_id in self._services:
            del self._services[service_id]
            logger.info(f"Unregistered service: {service_id}")
    
    def get(self, service_id: str) -> Optional[ServiceEntry]:
        """Get service by ID"""
        return self._services.get(service_id)
    
    def get_by_name(self, name: str) -> Optional[ServiceEntry]:
        """Get service by name"""
        for entry in self._services.values():
            if entry.name == name:
                return entry
        return None
    
    def get_by_type(self, type: ServiceType) -> List[ServiceEntry]:
        """Get all services of a given type"""
        return [e for e in self._services.values() if e.type == type]
    
    def get_all(self) -> List[ServiceEntry]:
        """Get all registered services"""
        return list(self._services.values())
    
    def get_healthy(self) -> List[ServiceEntry]:
        """Get all healthy services"""
        return [
            e for e in self._services.values()
            if e.state in (ServiceState.READY, ServiceState.RUNNING)
            and e.consecutive_failures == 0
        ]
    
    def get_enabled(self) -> List[ServiceEntry]:
        """Get all enabled services"""
        return [e for e in self._services.values() if e.enabled]
    
    def register_health_checker(self, service_id: str, checker: Callable[[], Any]) -> None:
        """Register a health checker for a service"""
        self._health_checkers[service_id] = checker
    
    def register_start_handler(self, service_id: str, handler: Callable[[], Any]) -> None:
        """Register a start handler for a service"""
        self._start_handlers[service_id] = handler
    
    def register_stop_handler(self, service_id: str, handler: Callable[[], Any]) -> None:
        """Register a stop handler for a service"""
        self._stop_handlers[service_id] = handler
    
    def update_health(self, service_id: str, **kwargs) -> None:
        """Update health status for a service"""
        entry = self.get(service_id)
        if entry:
            for key, value in kwargs.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)
            entry.last_seen = time.time()
    
    def update_state(self, service_id: str, state: ServiceState, error: Optional[str] = None) -> None:
        """Update state for a service"""
        entry = self.get(service_id)
        if entry:
            entry.state = state
            if error:
                entry.error_message = error
                entry.last_failure = time.time()
                entry.consecutive_failures += 1
            else:
                entry.consecutive_failures = 0
            entry.last_seen = time.time()
    
    def register_service(self, data: Dict[str, Any]) -> ServiceEntry:
        """Register a new service from a dictionary"""
        entry = ServiceEntry(
            service_id=data.get("service_id", data.get("name")),
            name=data.get("name"),
            type=ServiceType(data.get("type", "unknown")),
            state=ServiceState(data.get("state", "unknown")),
            port=data.get("port"),
            endpoint=data.get("endpoint"),
            capabilities=data.get("capabilities", []),
            dependencies=data.get("dependencies", []),
            health_endpoint=data.get("health_endpoint", "/health"),
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            auto_restart=data.get("auto_restart", True),
            max_restarts=data.get("max_restarts", 3),
        )
        self.register(entry)
        return entry
    
    def register_core_services(self) -> None:
        """Register the core JARVIS services"""
        self.register(ServiceEntry(
            service_id="jarvis_api",
            name="api",
            type=ServiceType.API,
            port=8000,
            endpoint="http://127.0.0.1:8000",
            capabilities=["chat", "generate", "browse", "sandbox", "knowledge", "memory"],
            dependencies=[],
            health_endpoint="/health",
            description="JARVIS Unified API Backend",
        ))
        
        self.register(ServiceEntry(
            service_id="jarvis_brain",
            name="brain",
            type=ServiceType.BRAIN,
            port=8011,
            endpoint="http://127.0.0.1:8011",
            capabilities=["inference", "reasoning"],
            dependencies=["jarvis_api"],
            health_endpoint="/health",
            description="JARVIS Brain inference runtime",
        ))
        
        self.register(ServiceEntry(
            service_id="silverwing",
            name="silverwing",
            type=ServiceType.RUNTIME,
            port=8010,
            endpoint="http://127.0.0.1:8010",
            capabilities=["inference", "chat"],
            dependencies=[],
            health_endpoint="/v1/health",
            description="Silverwing AI runtime",
        ))
        
        self.register(ServiceEntry(
            service_id="sandbox",
            name="sandbox",
            type=ServiceType.SANDBOX,
            capabilities=["execute", "patch", "test", "artifact"],
            dependencies=["jarvis_api"],
            description="Code execution sandbox",
        ))
        
        self.register(ServiceEntry(
            service_id="browser",
            name="browser",
            type=ServiceType.BROWSER,
            capabilities=["search", "navigate", "research", "evidence"],
            dependencies=["jarvis_api"],
            description="Browser automation service",
        ))
        
        self.register(ServiceEntry(
            service_id="knowledge",
            name="knowledge",
            type=ServiceType.KNOWLEDGE,
            capabilities=["index", "search", "store"],
            dependencies=["jarvis_api"],
            description="Knowledge storage and retrieval",
        ))
        
        self.register(ServiceEntry(
            service_id="memory",
            name="memory",
            type=ServiceType.MEMORY,
            capabilities=["recall", "store", "consolidate"],
            dependencies=["jarvis_api"],
            description="Memory system for context and facts",
        ))
        
        self.register(ServiceEntry(
            service_id="learning",
            name="learning",
            type=ServiceType.LEARNING,
            capabilities=["challenge", "lesson", "dataset", "training"],
            dependencies=["jarvis_api", "sandbox", "knowledge"],
            description="Learning and curriculum system",
        ))
        
        self.register(ServiceEntry(
            service_id="frontend",
            name="frontend",
            type=ServiceType.FRONTEND,
            port=3000,
            endpoint="http://127.0.0.1:3000",
            dependencies=["jarvis_api"],
            description="Next.js web frontend",
        ))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert registry to dictionary"""
        return {
            service_id: entry.to_dict()
            for service_id, entry in self._services.items()
        }


# Global registry instance
service_registry = ServiceRegistry.get_instance()

# Alias for convenience
registry = service_registry