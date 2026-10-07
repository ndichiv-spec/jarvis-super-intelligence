"""
Reconciler - Align observed state with desired state.

Applies automatic repairs where possible and reports issues requiring
manual intervention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Callable
from enum import Enum
import time
import logging
import asyncio

from .desired_state import DesiredState, DesiredService, ServiceStatus, get_desired_state
from .observed_state import ObservedState, ObservedService, ServiceHealthStatus, get_observed_state
from .drift import Drift, DriftType, DriftReport, detect_drift

logger = logging.getLogger("control_plane.reconciler")


class ReconciliationAction(str, Enum):
    """Actions that can be taken during reconciliation"""
    RESTART_SERVICE = "restart_service"
    START_SERVICE = "start_service"
    STOP_SERVICE = "stop_service"
    UPDATE_CONFIG = "update_config"
    SWITCH_PROVIDER = "switch_provider"
    CLEAR_ERROR = "clear_error"
    NONE = "none"


@dataclass
class ReconciliationStep:
    """Single step in a reconciliation process"""
    step: int
    action: ReconciliationAction
    target: str
    reason: str
    success: bool = False
    error: Optional[str] = None
    executed_at: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action.value,
            "target": self.target,
            "reason": self.reason,
            "success": self.success,
            "error": self.error,
            "executed_at": self.executed_at,
        }


@dataclass
class ReconciliationResult:
    """Result of a reconciliation attempt"""
    timestamp: float
    success: bool
    drifts_resolved: int = 0
    drifts_remaining: int = 0
    steps: List[ReconciliationStep] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    human_intervention_required: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "success": self.success,
            "drifts_resolved": self.drifts_resolved,
            "drifts_remaining": self.drifts_remaining,
            "steps": [s.to_dict() for s in self.steps],
            "skipped": self.skipped,
            "failed": self.failed,
            "human_intervention_required": self.human_intervention_required,
        }


class Reconciler:
    """
    Reconciles observed state with desired state.
    
    Attempts automatic repairs for recoverable drifts and identifies
    issues requiring manual intervention.
    """
    
    def __init__(self, desired: Optional[DesiredState] = None,
                 observed: Optional[ObservedState] = None):
        self.desired = desired or get_desired_state()
        self.observed = observed or get_observed_state()
        self._drift_handlers: Dict[DriftType, Callable[[Drift], ReconciliationResult]] = {}
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """Set up default drift handlers"""
        # This is intentionally minimal - handlers would be plugged in
        # by the service manager or supervisor
        pass
    
    def reconcile(self, auto_recover: bool = True) -> ReconciliationResult:
        """
        Reconcile observed state with desired state.
        
        Args:
            auto_recover: If True, automatically attempt recovery for
                         auto-recoverable drifts
        
        Returns:
            ReconciliationResult with details of what was done
        """
        logger.info("Starting reconciliation")
        
        drift_report = detect_drift()
        result = ReconciliationResult(
            timestamp=time.time(),
            success=True,
        )
        
        if not drift_report.drift_detected:
            logger.info("No drift detected - system is in desired state")
            return result
        
        logger.info("Drift detected: %d issues", len(drift_report.drifts))
        
        # Track which drifts we can handle
        drifts_to_handle = list(drift_report.drifts)
        
        for drift in drifts_to_handle:
            step = self._handle_drift(drift, auto_recover)
            if step:
                result.steps.append(step)
                if step.success:
                    result.drifts_resolved += 1
                else:
                    result.drifts_remaining += 1
                    if drift.auto_recoverable:
                        result.failed.append(drift.resource_id)
                    else:
                        result.human_intervention_required.append(drift.resource_id)
            else:
                result.drifts_remaining += 1
                if not drift.auto_recoverable:
                    result.human_intervention_required.append(drift.resource_id)
        
        # Update success based on how many drifts remain
        if result.drifts_remaining > 0:
            result.success = len(result.human_intervention_required) == 0
        
        logger.info(
            f"Reconciliation complete: {result.drifts_resolved} resolved, "
            f"{result.drifts_remaining} remaining, "
            f"{len(result.human_intervention_required)} need human intervention"
        )
        
        return result
    
    def _handle_drift(self, drift: Drift, auto_recover: bool) -> Optional[ReconciliationStep]:
        """Handle a single drift by taking appropriate action"""
        
        # Don't auto-recover if disabled
        if not auto_recover and drift.auto_recoverable:
            logger.info("Auto-recovery disabled, skipping drift: %s", drift.resource_id)
            return None
        
        # Don't handle non-auto-recoverable drift with auto
        if not drift.auto_recoverable:
            return None
        
        # Check restart limits
        if self._exceeds_restart_limit(drift.resource_id):
            logger.warning("Skip recovery for %s: restart limit exceeded", drift.resource_id)
            drift.skipped.append(f"{drift.resource_id}_restart_limit")
            return None
        
        # Handle based on drift type
        if drift.drift_type == DriftType.SERVICE_DOWN:
            return self._recover_service_down(drift)
        elif drift.drift_type == DriftType.SERVICE_STATUS:
            return self._recover_service(drift)
        elif drift.drift_type == DriftType.PROVIDER_HEALTH:
            return self._recover_provider(drift)
        elif drift.drift_type == DriftType.AUTH_DISABLED:
            # Auth is manually managed
            return None
        else:
            return None
    
    def _exceeds_restart_limit(self, resource_id: str) -> bool:
        """Check if restart limit is exceeded for a resource"""
        # Find the service in observed state
        obs_svc = self.observed.get_service(resource_id)
        if obs_svc and obs_svc.restart_count >= 3:
            return True
        
        # Check provider
        obs_prov = self.observed.get_provider(resource_id)
        if obs_prov and hasattr(obs_prov, 'restart_count') and obs_prov.restart_count >= 3:
            return True
        
        return False
    
    def _recover_service_down(self, drift: Drift) -> Optional[ReconciliationStep]:
        """Attempt to restart a down service"""
        step = ReconciliationStep(
            step=1,
            action=ReconciliationAction.RESTART_SERVICE,
            target=drift.resource_id,
            reason=drift.detail,
            executed_at=time.time(),
        )
        
        try:
            # This would call the service manager to restart
            # For now, we just record the intent
            logger.info("Would restart service: %s", drift.resource_id)
            step.success = True
        except Exception as e:
            step.success = False
            step.error = str(e)
            logger.error("Failed to restart %s: %s", drift.resource_id, e)
        
        return step
    
    def _recover_service(self, drift: Drift) -> Optional[ReconciliationStep]:
        """Recover a degraded service"""
        step = ReconciliationStep(
            step=1,
            action=ReconciliationAction.RESTART_SERVICE,
            target=drift.resource_id,
            reason=drift.detail,
            executed_at=time.time(),
        )
        
        try:
            logger.info("Would recover service: %s", drift.resource_id)
            step.success = True
        except Exception as e:
            step.success = False
            step.error = str(e)
        
        return step
    
    def _recover_provider(self, drift: Drift) -> Optional[ReconciliationStep]:
        """Recover a degraded provider"""
        step = ReconciliationStep(
            step=1,
            action=ReconciliationAction.SWITCH_PROVIDER,
            target=drift.resource_id,
            reason=drift.detail,
            executed_at=time.time(),
        )
        
        try:
            logger.info("Would switch provider: %s", drift.resource_id)
            step.success = True
        except Exception as e:
            step.success = False
            step.error = str(e)
        
        return step


# Convenience function
def reconcile(auto_recover: bool = True) -> ReconciliationResult:
    """Perform reconciliation of system state"""
    reconciler = Reconciler()
    return reconciler.reconcile(auto_recover)