"""
Observed State - The actual current state of the JARVIS platform.

Continuously updated from live health checks, process monitoring,
and capability probing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List
from enum import Enum
import time
import subprocess


class ProcessStatus(str, Enum):
    """Observed process status"""
    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    STOPPING = "stopping"
    CRASHED = "crashed"
    UNKNOWN = "unknown"


class ServiceHealthStatus(str, Enum):
    """Observed service health status"""
    HEALTHY = "healthy"
    NOT_CONFIGURED = "not_configured"
    AUTHENTICATION_FAILED = "authentication_failed"
    FORBIDDEN = "forbidden"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class ObservedProc:
    """Observed process state"""
    pid: Optional[int] = None
    status: ProcessStatus = ProcessStatus.UNKNOWN
    uptime_sec: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    restart_count: int = 0
    last_error: Optional[str] = None
    last_seen: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "status": self.status.value,
            "uptime_sec": self.uptime_sec,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "restart_count": self.restart_count,
            "last_error": self.last_error,
            "last_seen": self.last_seen,
        }


@dataclass
class ObservedService:
    """Observed state for a core service"""
    name: str
    health: ServiceHealthStatus
    endpoint: Optional[str] = None
    port: Optional[int] = None
    version: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    latency_ms: Optional[float] = None
    request_count: int = 0
    error_count: int = 0
    dependencies_status: Dict[str, ServiceHealthStatus] = field(default_factory=dict)
    last_checked: float = field(default_factory=time.time)
    observed_version: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "health": self.health.value,
            "endpoint": self.endpoint,
            "port": self.port,
            "version": self.version,
            "capabilities": self.capabilities,
            "latency_ms": self.latency_ms,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "dependencies_status": {k: v.value for k, v in self.dependencies_status.items()},
            "last_checked": self.last_checked,
            "observed_version": self.observed_version,
            "notes": self.notes,
        }


@dataclass
class ObservedProvider:
    """Observed state for an external provider"""
    name: str
    health: ServiceHealthStatus
    model: Optional[str] = None
    models: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    endpoint: Optional[str] = None
    latency_ms: Optional[float] = None
    errors: Optional[str] = None
    last_checked: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "health": self.health.value,
            "model": self.model,
            "models": self.models,
            "capabilities": self.capabilities,
            "endpoint": self.endpoint,
            "latency_ms": self.latency_ms,
            "errors": self.errors,
            "last_checked": self.last_checked,
        }


@dataclass
class ObservedState:
    """
    The actual observed state of the JARVIS platform.
    
    This is continuously updated from live health checks, process
    monitoring, and capability probing. It represents what the system
    ACTUALLY is, compared to the desired state.
    """
    
    timestamp: float = field(default_factory=time.time)
    services: Dict[str, ObservedService] = field(default_factory=dict)
    providers: Dict[str, ObservedProvider] = field(default_factory=dict)
    processes: Dict[str, ObservedProc] = field(default_factory=dict)
    
    # System-wide observations
    uptime_sec: float = 0.0
    total_requests: int = 0
    total_errors: int = 0
    
    # Drift tracking
    last_drift_check: float = 0.0
    current_drift: Optional[str] = None
    
    def update_service(self, name: str, service: ObservedService) -> None:
        """Update observed service state"""
        self.services[name] = service
        self.timestamp = time.time()
    
    def update_provider(self, name: str, provider: ObservedProvider) -> None:
        """Update observed provider state"""
        self.providers[name] = provider
        self.timestamp = time.time()
    
    def update_process(self, name: str, proc: ObservedProc) -> None:
        """Update observed process state"""
        self.processes[name] = proc
        self.timestamp = time.time()
    
    def get_service(self, name: str) -> Optional[ObservedService]:
        """Get observed state for a service"""
        return self.services.get(name)
    
    def get_provider(self, name: str) -> Optional[ObservedProvider]:
        """Get observed state for a provider"""
        return self.providers.get(name)
    
    def get_process(self, name: str) -> Optional[ObservedProc]:
        """Get observed state for a process"""
        return self.processes.get(name)
    
    def get_all_services(self) -> List[ObservedService]:
        """Get all observed services"""
        return list(self.services.values())
    
    def get_all_providers(self) -> List[ObservedProvider]:
        """Get all observed providers"""
        return list(self.providers.values())
    
    def get_health_summary(self) -> Dict[str, ServiceHealthStatus]:
        """Get health summary for all services"""
        return {name: svc.health for name, svc in self.services.items()}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp,
            "uptime_sec": self.uptime_sec,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "services": {name: svc.to_dict() for name, svc in self.services.items()},
            "providers": {name: prov.to_dict() for name, prov in self.providers.items()},
            "processes": {name: proc.to_dict() for name, proc in self.processes.items()},
            "drift": {
                "last_drift_check": self.last_drift_check,
                "current_drift": self.current_drift,
            },
        }


# Global observed state instance (singleton)
_observed_state_instance: Optional[ObservedState] = None


def get_observed_state() -> ObservedState:
    """Get the global observed state instance"""
    global _observed_state_instance
    if _observed_state_instance is None:
        _observed_state_instance = ObservedState()
    return _observed_state_instance


def set_observed_state(state: ObservedState) -> None:
    """Set the global observed state instance"""
    global _observed_state_instance
    _observed_state_instance = state


def refresh_from_endpoints() -> ObservedState:
    """
    Refresh observed state from live endpoint checks.
    
    This function makes HTTP requests to all services and providers
    to update the observed state.
    """
    import requests
    from .desired_state import get_desired_state
    
    state = ObservedState()
    desired = get_desired_state()
    
    # Check API backend
    try:
        r = requests.get("http://127.0.0.1:8000/health", timeout=5)
        state.update_service("api", ObservedService(
            name="api",
            health=ServiceHealthStatus.HEALTHY if r.status_code == 200 else ServiceHealthStatus.DEGRADED,
            endpoint="http://127.0.0.1:8000",
            port=8000,
            latency_ms=r.elapsed.total_seconds() * 1000,
        ))
    except Exception:
        state.update_service("api", ObservedService(
            name="api",
            health=ServiceHealthStatus.OFFLINE,
            endpoint="http://127.0.0.1:8000",
            port=8000,
        ))
    
    # Check Brain
    try:
        r = requests.get("http://127.0.0.1:8011/health", timeout=5)
        health = "healthy" if r.status_code == 200 else "degraded"
        state.update_service("brain", ObservedService(
            name="brain",
            health=ServiceHealthStatus.HEALTHY if r.status_code == 200 else ServiceHealthStatus.DEGRADED,
            endpoint="http://127.0.0.1:8011",
            port=8011,
        ))
    except Exception:
        state.update_service("brain", ObservedService(
            name="brain",
            health=ServiceHealthStatus.UNAVAILABLE,
            endpoint="http://127.0.0.1:8011",
            port=8011,
        ))
    
    # Check Sandbox
    try:
        r = requests.get("http://127.0.0.1:8000/api/v1/sandbox/policy", timeout=5)
        state.update_service("sandbox", ObservedService(
            name="sandbox",
            health=ServiceHealthStatus.HEALTHY if r.status_code == 200 else ServiceHealthStatus.DEGRADED,
        ))
    except Exception:
        state.update_service("sandbox", ObservedService(
            name="sandbox",
            health=ServiceHealthStatus.UNKNOWN,
        ))
    
    # Check Providers
    try:
        r = requests.get("http://127.0.0.1:8000/api/providers", timeout=10)
        if r.status_code == 200:
            data = r.json()
            for prov in data.get("providers", []):
                name = prov.get("provider", "unknown")
                state.update_provider(name, ObservedProvider(
                    name=name,
                    health=ServiceHealthStatus(prov.get("health_status", "unknown").upper()),
                    model=prov.get("model"),
                    models=prov.get("models", []),
                    capabilities=prov.get("capabilities", []),
                    endpoint=prov.get("endpoint"),
                    latency_ms=prov.get("latency_ms"),
                    errors=prov.get("errors"),
                ))
    except Exception:
        pass
    
    return state