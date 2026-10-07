"""
Drift Detection - Compare desired state vs observed state.

Detects when the system is not in its desired configuration and
reports discrepancies for reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List
from enum import Enum
import time
import logging

from .desired_state import DesiredState, get_desired_state, ServiceStatus
from .observed_state import (
    ObservedState, ServiceHealthStatus,
    get_observed_state, ServiceHealthStatus as ObsHealth
)

logger = logging.getLogger("control_plane.drift")


class DriftType(str, Enum):
    """Types of drift detected"""
    SERVICE_STATUS = "service_status"
    SERVICE_PORT = "service_port"
    PROVIDER_HEALTH = "provider_health"
    PROVIDER_MODEL = "provider_model"
    AUTH_DISABLED = "auth_disabled"
    CAPABILITY_MISSING = "capability_missing"
    CONFIG_MISSING = "config_missing"
    SERVICE_DOWN = "service_down"
    UNKNOWN = "unknown"


@dataclass
class Drift:
    """Represents a detected drift between desired and observed state"""
    drift_type: DriftType
    resource_id: str  # Service name, provider name, etc.
    detail: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    detected_at: float = field(default_factory=time.time)
    auto_recoverable: bool = True
    suggested_action: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_type": self.drift_type.value,
            "resource_id": self.resource_id,
            "detail": self.detail,
            "severity": self.severity,
            "detected_at": self.detected_at,
            "auto_recoverable": self.auto_recoverable,
            "suggested_action": self.suggested_action,
        }


@dataclass
class DriftReport:
    """Complete drift report for the system"""
    timestamp: float
    drift_detected: bool
    drifts: List[Drift]
    summary: Dict[str, int]  # Count by severity
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "drift_detected": self.drift_detected,
            "drifts": [d.to_dict() for d in self.drifts],
            "summary": self.summary,
        }


class DriftDetector:
    """
    Detects drift between desired and observed state.
    
    Compares the DesiredState with the ObservedState and reports
    discrepancies that need reconciliation.
    """
    
    def __init__(self, desired: Optional[DesiredState] = None,
                 observed: Optional[ObservedState] = None):
        self.desired = desired or get_desired_state()
        self.observed = observed or get_observed_state()
    
    def detect_all(self) -> DriftReport:
        """Detect all drifts and return a report"""
        drifts: List[Drift] = []
        
        # Check service status drifts
        drifts.extend(self._check_service_status_drift())
        
        # Check service port drifts
        drifts.extend(self._check_service_port_drift())
        
        # Check provider health drifts
        drifts.extend(self._check_provider_health_drift())
        
        # Check auth status drift
        drifts.extend(self._check_auth_drift())
        
        # Check capability availability
        drifts.extend(self._check_capability_drift())
        
        # Calculate summary
        summary = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for d in drifts:
            summary[d.severity] += 1
        
        return DriftReport(
            timestamp=time.time(),
            drift_detected=len(drifts) > 0,
            drifts=drifts,
            summary=summary,
        )
    
    def _check_service_status_drift(self) -> List[Drift]:
        """Check for service status drifts"""
        drifts = []
        
        for service_name in ["api", "brain", "browser", "sandbox", 
                            "research", "knowledge", "memory", "learning"]:
            desired_svc = self.desired.get_service(service_name)
            observed_svc = self.observed.get_service(service_name)
            
            if desired_svc is None or observed_svc is None:
                continue
            
            desired_status = desired_svc.status
            observed_health = observed_svc.health
            
            # Map desired status to expected health
            expected_health = ObsHealth.HEALTHY if desired_status == "running" else ObsHealth.OFFLINE
            
            if desired_status == "running" and observed_health not in (ObsHealth.HEALTHY, ObsHealth.DEGRADED):
                drift = Drift(
                    drift_type=DriftType.SERVICE_STATUS,
                    resource_id=service_name,
                    detail=f"Service {desired_status} but observed as {observed_health.value}",
                    severity="high" if observed_health in (ObsHealth.OFFLINE, ObsHealth.UNAVAILABLE) else "medium",
                    auto_recoverable=observed_health in (ObsHealth.OFFLINE, ObsHealth.UNAVAILABLE),
                    suggested_action=f"Restart {service_name} service and verify health check",
                )
                drifts.append(drift)
        
        return drifts
    
    def _check_service_port_drift(self) -> List[Drift]:
        """Check for service port drifts"""
        drifts = []
        
        for service_name in ["api", "brain"]:
            desired_svc = self.desired.get_service(service_name)
            observed_svc = self.observed.get_service(service_name)
            
            if desired_svc and observed_svc:
                if desired_svc.port != observed_svc.port:
                    drifts.append(Drift(
                        drift_type=DriftType.SERVICE_PORT,
                        resource_id=service_name,
                        detail=f"Port mismatch: desired {desired_svc.port}, observed {observed_svc.port}",
                        severity="high",
                        auto_recoverable=False,
                        suggested_action=f"Update {service_name} port configuration",
                    ))
        
        return drifts
    
    def _check_provider_health_drift(self) -> List[Drift]:
        """Check for provider health drifts"""
        drifts = []
        
        for provider_name, desired_provider in self.desired.providers.items():
            observed_provider = self.observed.get_provider(provider_name)
            
            if observed_provider is None:
                # Provider not observed
                drift = Drift(
                    drift_type=DriftType.PROVIDER_HEALTH,
                    resource_id=provider_name,
                    detail="Provider not reachable or not configured",
                    severity="medium",
                    auto_recoverable=True,
                    suggested_action=f"Check {provider_name} connectivity and credentials",
                )
                drifts.append(drift)
                continue
            
            if desired_provider.status == "healthy" and observed_provider.health != ObsHealth.HEALTHY:
                drift = Drift(
                    drift_type=DriftType.PROVIDER_HEALTH,
                    resource_id=provider_name,
                    detail=f"Desired healthy but observed as {observed_provider.health.value}",
                    severity="medium" if observed_provider.health == ObsHealth.DEGRADED else "high",
                    auto_recoverable=True,
                    suggested_action=f"Check {provider_name} endpoint and credentials",
                )
                drifts.append(drift)
        
        return drifts
    
    def _check_auth_drift(self) -> List[Drift]:
        """Check for authentication drifts"""
        drifts = []
        
        desired_auth = self.desired.auth
        
        if desired_auth.enabled:
            # Check if auth is actually working
            auth_service = self.observed.get_service("auth")
            if auth_service is None or auth_service.health not in (
                ObsHealth.HEALTHY, ObsHealth.DEGRADED
            ):
                drifts.append(Drift(
                    drift_type=DriftType.AUTH_DISABLED,
                    resource_id="authentication",
                    detail="Authentication required but not functional",
                    severity="high",
                    auto_recoverable=False,
                    suggested_action="Check authentication service and OIDC configuration",
                ))
        
        return drifts
    
    def _check_capability_drift(self) -> List[Drift]:
        """Check for capability availability drifts"""
        from .capabilities import CapabilityState, capability_registry
        
        drifts = []
        registry = capability_registry
        
        # Check required capabilities based on desired state
        for service_name in ["sandbox", "knowledge", "memory", "learning"]:
            service = self.desired.get_service(service_name)
            if service and service.status == "running":
                for cap_name in service.capabilities:
                    cap = registry.get(cap_name)
                    if cap and cap.state == CapabilityState.UNAVAILABLE:
                        drifts.append(Drift(
                            drift_type=DriftType.CAPABILITY_MISSING,
                            resource_id=cap_name,
                            detail=f"Capability required by {service_name} is unavailable",
                            severity="high",
                            auto_recoverable=True,
                            suggested_action=f"Start service providing {cap_name}",
                        ))
        
        return drifts
    
    def get_healthy_summary(self) -> Dict[str, Any]:
        """Get a summary of system health"""
        report = self.detect_all()
        
        return {
            "healthy": not report.drift_detected,
            "drift_count": len(report.drifts),
            "by_severity": report.summary,
            "last_checked": time.time(),
            "drifts": [d.to_dict() for d in report.drifts],
        }


# Convenience function
def detect_drift() -> DriftReport:
    """Detect all drifts and return a report"""
    detector = DriftDetector()
    return detector.detect_all()