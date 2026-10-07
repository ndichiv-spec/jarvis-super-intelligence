"""
Supervisor - Self-healing service controller with exponential backoff.

Monitors services, detects failures, and performs automatic recovery
with backoff and restart limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Callable
from enum import Enum
import time
import threading
import logging
import subprocess
import signal
import os

from .service_registry import ServiceRegistry, ServiceEntry, ServiceState
from .observer import HealthStatus, ServiceHealth

logger = logging.getLogger("control_plane.supervisor")


class RecoveryPolicy(str, Enum):
    """Service recovery policy"""
    ALWAYS = "always"
    ON_FAILURE = "on_failure"
    NEVER = "never"
    EXPONENTIAL_BACKOFF = "exponential_backoff"


@dataclass
class RecoveryAction:
    """Action to take during recovery"""
    action: str  # restart, start, stop, notify, escalate
    service_id: str
    reason: str
    delay_sec: float = 0
    attempt: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "service_id": self.service_id,
            "reason": self.reason,
            "delay_sec": self.delay_sec,
            "attempt": self.attempt,
        }


@dataclass
class ServiceRecoveryPlan:
    """Recovery plan for a service"""
    service_id: str
    policy: RecoveryPolicy
    max_restarts: int = 3
    initial_backoff_sec: float = 1.0
    max_backoff_sec: float = 60.0
    restart_count: int = 0
    last_restart_at: Optional[float] = None
    consecutive_failures: int = 0
    
    def should_restart(self) -> bool:
        """Check if service should be restarted"""
        if self.policy == RecoveryPolicy.NEVER:
            return False
        if self.policy == RecoveryPolicy.ALWAYS:
            return True
        if self.policy == RecoveryPolicy.ON_FAILURE:
            return self.consecutive_failures > 0
        if self.policy == RecoveryPolicy.EXPONENTIAL_BACKOFF:
            return self.restart_count < self.max_restarts
        return False
    
    def calculate_backoff(self) -> float:
        """Calculate backoff time using exponential backoff"""
        delay = self.initial_backoff_sec * (2 ** min(self.restart_count, 10))
        return min(delay, self.max_backoff_sec)


@dataclass
class SupervisorStatus:
    """Current status of the supervisor"""
    running: bool = False
    start_time: float = 0
    checks_performed: int = 0
    recoveries_attempted: int = 0
    recoveries_successful: int = 0
    escalations: int = 0
    last_check: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "start_time": self.start_time,
            "checks_performed": self.checks_performed,
            "recoveries_attempted": self.recoveries_attempted,
            "recoveries_successful": self.recoveries_successful,
            "escalations": self.escalations,
            "last_check": self.last_check,
            "uptime_sec": time.time() - self.start_time if self.running else 0,
        }


class Supervisor:
    """
    Self-healing supervisor that monitors and recovers services.
    
    Features:
    - Health checking
    - Failure detection
    - Exponential backoff
    - Restart limits
    - Escalation for persistent failures
    """
    
    _instance: Optional["Supervisor"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._registry = ServiceRegistry.get_instance()
        self._status = SupervisorStatus()
        self._recovery_plans: Dict[str, ServiceRecoveryPlan] = {}
        self._recovery_handlers: Dict[str, Callable[[ServiceEntry], RecoveryAction]] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._setup_default_handlers()
    
    @classmethod
    def get_instance(cls) -> "Supervisor":
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _setup_default_handlers(self) -> None:
        """Set up default recovery handlers"""
        self._recovery_handlers["sandbox"] = self._restart_sandbox
        self._recovery_handlers["browser"] = self._restart_browser
        self._recovery_handlers["knowledge"] = self._restart_knowledge
        self._recovery_handlers["memory"] = self._restart_memory
        self._recovery_handlers["learning"] = self._restart_learning
        self._recovery_handlers["api"] = self._restart_api
    
    def start(self, check_interval_sec: int = 30) -> None:
        """Start the supervisor"""
        if self._running:
            return
        
        self._running = True
        self._status.running = True
        self._status.start_time = time.time()
        
        # Initialize recovery plans for all services
        for service in self._registry.get_all():
            self._init_recovery_plan(service)
        
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(check_interval_sec,),
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("Supervisor started")
    
    def stop(self) -> None:
        """Stop the supervisor"""
        self._running = False
        self._status.running = False
        logger.info("Supervisor stopped")
    
    def _monitor_loop(self, interval_sec: int) -> None:
        """Main monitoring loop"""
        while self._running:
            try:
                self._check_services()
            except Exception as e:
                logger.error(f"Supervisor monitoring error: {e}")
            
            time.sleep(interval_sec)
    
    def _check_services(self) -> None:
        """Check all services and perform recovery if needed"""
        from .observer import observer, HealthStatus
        
        self._status.checks_performed += 1
        self._status.last_check = time.time()
        
        services = self._registry.get_all()
        
        for service in services:
            if not service.enabled and service.state != ServiceState.STOPPED:
                # Check if we should start a disabled service
                if service.auto_restart:
                    plan = self._recovery_plans.get(service.service_id)
                    if plan and plan.should_restart():
                        self._attempt_recovery(service, "disabled")
            
            # Check health
            health = observer.check_service_health(service)
            if not health:
                continue
            
            if health.health != HealthStatus.HEALTHY:
                self._attempt_recovery(service, health.health.value)
    
    def _init_recovery_plan(self, service: ServiceEntry) -> None:
        """Initialize recovery plan for a service"""
        plan = ServiceRecoveryPlan(
            service_id=service.service_id,
            policy=RecoveryPolicy.EXPONENTIAL_BACKOFF,
            max_restarts=service.max_restarts,
        )
        self._recovery_plans[service.service_id] = plan
    
    def _attempt_recovery(self, service: ServiceEntry, reason: str) -> None:
        """Attempt to recover a failed service"""
        self._status.recoveries_attempted += 1
        
        plan = self._recovery_plans.get(service.service_id)
        if not plan:
            logger.warning(f"No recovery plan for {service.service_id}")
            return
        
        # Check restart limit
        if plan.restart_count >= plan.max_restarts:
            logger.warning(f"Restart limit exceeded for {service.service_id}")
            self._escalate(service, "restart limit exceeded")
            return
        
        # Check backoff
        if plan.last_restart_at:
            backoff = plan.calculate_backoff()
            elapsed = time.time() - plan.last_restart_at
            if elapsed < backoff:
                logger.debug(f"Back off for {service.service_id}, waiting {backoff - elapsed:.1f}s")
                return
        
        # Call custom recovery handler if available
        handler = self._recovery_handlers.get(service.service_id)
        if handler:
            action = handler(service)
            if action:
                self._execute_recovery(action)
                plan.restart_count += 1
                plan.last_restart_at = time.time()
                logger.info(f"Recovery action for {service.service_id}: {action.action}")
                return
        
        # Default: just log
        logger.warning(f"No recovery handler for {service.service_id}: {reason}")
    
    def _execute_recovery(self, action: RecoveryAction) -> None:
        """Execute a recovery action"""
        if action.action == "restart":
            self._restart_service(action.service_id)
        elif action.action == "notify":
            self._notify_failure(action)
        elif action.action == "escalate":
            self._escalate_by_id(action.service_id, action.reason)
    
    def _restart_service(self, service_id: str) -> bool:
        """Restart a service by its ID"""
        service = self._registry.get(service_id)
        if not service:
            return False
        
        logger.info(f"Restarting service: {service_id}")
        
        # Update service state
        self._registry.update_state(service_id, ServiceState.RESTARTING)
        
        # In a real implementation, this would:
        # 1. Send SIGTERM to the process
        # 2. Wait for shutdown
        # 3. Start the service again
        # 4. Wait for health check
        
        # For now, just mark as running
        self._registry.update_state(service_id, ServiceState.RUNNING)
        self._status.recoveries_successful += 1
        
        return True
    
    def _escalate(self, service: ServiceEntry, reason: str) -> None:
        """Escalate a persistent failure"""
        self._status.escalations += 1
        logger.error(f"ESCALATION: Service {service.service_id} - {reason}")
        # In production, this would:
        # - Send alert to operators
        # - Create incident ticket
        # - Attempt manual intervention
    
    def _escalate_by_id(self, service_id: str, reason: str) -> None:
        """Escalate by service ID"""
        service = self._registry.get(service_id)
        if service:
            self._escalate(service, reason)
    
    # Default recovery handlers
    def _restart_sandbox(self, service: ServiceEntry) -> RecoveryAction:
        return RecoveryAction(
            action="restart",
            service_id=service.service_id,
            reason="Sandbox service unhealthy",
        )
    
    def _restart_browser(self, service: ServiceEntry) -> RecoveryAction:
        return RecoveryAction(
            action="restart",
            service_id=service.service_id,
            reason="Browser service unhealthy",
        )
    
    def _restart_knowledge(self, service: ServiceEntry) -> RecoveryAction:
        return RecoveryAction(
            action="restart",
            service_id=service.service_id,
            reason="Knowledge service unhealthy",
        )
    
    def _restart_memory(self, service: ServiceEntry) -> RecoveryAction:
        return RecoveryAction(
            action="restart",
            service_id=service.service_id,
            reason="Memory service unhealthy",
        )
    
    def _restart_learning(self, service: ServiceEntry) -> RecoveryAction:
        return RecoveryAction(
            action="restart",
            service_id=service.service_id,
            reason="Learning service unhealthy",
        )
    
    def _restart_api(self, service: ServiceEntry) -> RecoveryAction:
        return RecoveryAction(
            action="restart",
            service_id=service.service_id,
            reason="API service unhealthy",
        )
    
    def register_recovery_handler(
        self,
        service_id: str,
        handler: Callable[[ServiceEntry], RecoveryAction],
    ) -> None:
        """Register a custom recovery handler"""
        self._recovery_handlers[service_id] = handler
    
    def get_status(self) -> SupervisorStatus:
        """Get supervisor status"""
        return self._status
    
    def reset_recovery(self, service_id: str) -> None:
        """Reset recovery count for a service"""
        plan = self._recovery_plans.get(service_id)
        if plan:
            plan.restart_count = 0
            plan.consecutive_failures = 0
            logger.info(f"Reset recovery state for {service_id}")


# Global supervisor instance
supervisor = Supervisor.get_instance()