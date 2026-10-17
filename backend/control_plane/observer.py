"""
Observer - Health status tracking and monitoring.

Continuously monitors service health and provides status reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Callable
from enum import Enum
import time
import threading
import logging

from .service_registry import ServiceRegistry, ServiceState, ServiceEntry
from .observed_state import (
    ObservedState, ObservedService, ObservedProvider, ServiceHealthStatus,
    get_observed_state, ServiceHealthStatus as ObsHealth
)

logger = logging.getLogger("control_plane.observer")


class HealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    AUTHENTICATION_FAILED = "authentication_failed"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Health check result for a service"""
    service_id: str
    health: HealthStatus
    message: str = ""
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "health": self.health.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "timestamp": self.timestamp,
            "details": self.details,
        }


class Observer:
    """
    Monitors platform services and provides health status.
    
    Continuously checks service health endpoints and tracks
    status changes.
    """
    
    _instance: Optional["Observer"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._registry = ServiceRegistry.get_instance()
        self._observed_state = get_observed_state()
        self._health_checks: Dict[str, Callable[[], ServiceHealth]] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
    
    @classmethod
    def get_instance(cls) -> "Observer":
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def start_monitoring(self, interval_sec: int = 30) -> None:
        """Start background health monitoring"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval_sec,),
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("Started health monitoring")
    
    def stop_monitoring(self) -> None:
        """Stop background health monitoring"""
        self._running = False
        logger.info("Stopped health monitoring")
    
    def _monitor_loop(self, interval_sec: int) -> None:
        """Background monitoring loop"""
        while self._running:
            try:
                self._do_health_checks()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            
            time.sleep(interval_sec)
    
    def _do_health_checks(self) -> None:
        """Perform health checks on all services"""
        services = self._registry.get_all()
        
        for service in services:
            if not service.enabled:
                continue
            
            health = self.check_service_health(service)
            
            # Update observed state
            self._observed_state.update_service(
                service.name,
                ObservedService(
                    name=service.name,
                    health=self._health_status_to_observed(health.health),
                    endpoint=service.endpoint,
                    port=service.port,
                    latency_ms=health.latency_ms,
                )
            )
    
    def check_service_health(self, service: ServiceEntry) -> ServiceHealth:
        """Check health of a specific service"""
        # Check if we have a custom health checker
        if service.service_id in self._health_checks:
            return self._health_checks[service.service_id]()
        
        # Default HTTP health check
        if not service.endpoint:
            return ServiceHealth(
                service_id=service.service_id,
                health=HealthStatus.NOT_CONFIGURED,
                message="No endpoint configured",
            )

        try:
            import requests
        except ImportError:
            return ServiceHealth(
                service_id=service.service_id,
                health=HealthStatus.UNKNOWN,
                message="HTTP health check unavailable: 'requests' is not installed",
            )
        
        try:
            url = f"{service.endpoint}{service.health_endpoint}"
            start = time.time()
            response = requests.get(url, timeout=5)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                return ServiceHealth(
                    service_id=service.service_id,
                    health=HealthStatus.HEALTHY,
                    message="Service responding normally",
                    latency_ms=latency_ms,
                )
            elif response.status_code in (401, 403):
                return ServiceHealth(
                    service_id=service.service_id,
                    health=HealthStatus.AUTHENTICATION_FAILED,
                    message=f"Authentication failed: {response.status_code}",
                    latency_ms=latency_ms,
                )
            else:
                return ServiceHealth(
                    service_id=service.service_id,
                    health=HealthStatus.DEGRADED,
                    message=f"Unexpected status code: {response.status_code}",
                    latency_ms=latency_ms,
                    error=response.text[:200],
                )
        
        except requests.exceptions.Timeout:
            return ServiceHealth(
                service_id=service.service_id,
                health=HealthStatus.TIMEOUT,
                message="Health check timed out",
            )
        except requests.exceptions.ConnectionError:
            return ServiceHealth(
                service_id=service.service_id,
                health=HealthStatus.OFFLINE,
                message="Cannot connect to service",
            )
        except Exception as e:
            return ServiceHealth(
                service_id=service.service_id,
                health=HealthStatus.UNKNOWN,
                message=f"Health check error: {str(e)}",
            )
    
    def _health_status_to_observed(self, status: ServiceHealthStatus) -> ServiceHealthStatus:
        """Convert HealthStatus to ObservedService health status"""
        mapping = {
            HealthStatus.HEALTHY: ServiceHealthStatus.HEALTHY,
            HealthStatus.DEGRADED: ServiceHealthStatus.DEGRADED,
            HealthStatus.UNAVAILABLE: ServiceHealthStatus.UNAVAILABLE,
            HealthStatus.NOT_CONFIGURED: ServiceHealthStatus.NOT_CONFIGURED,
            HealthStatus.AUTHENTICATION_FAILED: ServiceHealthStatus.AUTHENTICATION_FAILED,
            HealthStatus.FORBIDDEN: ServiceHealthStatus.FORBIDDEN,
            HealthStatus.RATE_LIMITED: ServiceHealthStatus.RATE_LIMITED,
            HealthStatus.TIMEOUT: ServiceHealthStatus.TIMEOUT,
            HealthStatus.OFFLINE: ServiceHealthStatus.OFFLINE,
            HealthStatus.UNKNOWN: ServiceHealthStatus.UNKNOWN,
        }
        return mapping.get(status, ServiceHealthStatus.UNKNOWN)
    
    def register_health_checker(
        self,
        service_id: str,
        checker: Callable[[], ServiceHealth],
    ) -> None:
        """Register a custom health checker for a service"""
        self._health_checks[service_id] = checker
    
    def check_provider_health(self, provider_name: str) -> ServiceHealth:
        """Check health of an external provider"""
        try:
            import requests
        except ImportError:
            return ServiceHealth(
                service_id=f"provider_{provider_name}",
                health=HealthStatus.UNKNOWN,
                message="Provider health check unavailable: 'requests' is not installed",
            )

        # Use the provider API endpoint
        try:
            r = requests.get(f"http://127.0.0.1:8000/api/providers", timeout=10)
            if r.status_code == 200:
                providers = r.json().get("providers", [])
                for prov in providers:
                    if prov.get("provider") == provider_name:
                        health_status = prov.get("health_status", "unknown")
                        return ServiceHealth(
                            service_id=f"provider_{provider_name}",
                            health=self._map_provider_health(health_status),
                            message=prov.get("errors", "OK"),
                            latency_ms=prov.get("latency_ms"),
                        )
        except Exception as e:
            logger.error(f"Provider health check error for {provider_name}: {e}")
        
        return ServiceHealth(
            service_id=f"provider_{provider_name}",
            health=HealthStatus.UNKNOWN,
            message="Could not determine provider health",
        )
    
    def _map_provider_health(self, health: str) -> HealthStatus:
        """Map provider health string to HealthStatus"""
        mapping = {
            "healthy": HealthStatus.HEALTHY,
            "degraded": HealthStatus.DEGRADED,
            "unhealthy": HealthStatus.UNAVAILABLE,
            "authentication_failed": HealthStatus.AUTHENTICATION_FAILED,
            "offline": HealthStatus.OFFLINE,
            "unknown": HealthStatus.UNKNOWN,
        }
        return mapping.get(health.lower(), HealthStatus.UNKNOWN)
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health report"""
        services = self._registry.get_all()
        health_report = {}
        
        for service in services:
            health = self.check_service_health(service)
            health_report[service.name] = health.to_dict()
        
        # Add provider health
        from .observed_state import get_observed_state
        observed = get_observed_state()
        for prov_name, prov_info in observed.providers.items():
            health_report[f"provider_{prov_name}"] = {
                "health": prov_info.health.value,
                "model": prov_info.model,
                "latency_ms": prov_info.latency_ms,
            }
        
        # Calculate overall health
        healthy_count = sum(
            1 for h in health_report.values()
            if h.get("health") == "healthy"
        )
        degraded_count = sum(
            1 for h in health_report.values()
            if h.get("health") in ("degraded", "timeout")
        )
        
        return {
            "timestamp": time.time(),
            "overall": "healthy" if degraded_count == 0 else "degraded",
            "healthy_count": healthy_count,
            "degraded_count": degraded_count,
            "services": health_report,
        }
    
    def pause_monitoring(self) -> None:
        """Pause health monitoring"""
        self._running = False
        logger.info("Health monitoring paused")
    
    def resume_monitoring(self) -> None:
        """Resume health monitoring"""
        if not self._running:
            self._running = True
            logger.info("Health monitoring resumed")


# Global observer instance
observer = Observer.get_instance()


def check_system_health() -> Dict[str, Any]:
    """Get system health (convenience function)"""
    return observer.get_system_health()


def check_service_health(service_id: str) -> Optional[ServiceHealth]:
    """Check a specific service health"""
    registry = ServiceRegistry.get_instance()
    service = registry.get(service_id)
    if service:
        return observer.check_service_health(service)
    return None