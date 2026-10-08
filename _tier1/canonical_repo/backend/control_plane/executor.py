"""
Change Executor - Apply Verified Changes with Rollback Support.

Executes ChangeSets through the pipeline:
PROPOSED -> APPLYING -> VERIFYING -> COMMITTED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Callable
from enum import Enum
import time
import logging
import traceback

from .changes import ChangeSet, ChangeStatus, ChangeType, RiskLevel, ChangeOperation, change_manager

logger = logging.getLogger("control_plane.executor")


@dataclass
class ExecutorResult:
    """Result of a ChangeSet execution attempt"""
    change_id: str
    success: bool
    verified: bool = False
    error: Optional[str] = None
    error_trace: Optional[str] = None
    pre_state: Optional[Dict[str, Any]] = None
    post_state: Optional[Dict[str, Any]] = None
    tests_passed: int = 0
    tests_failed: int = 0
    rollback_performed: bool = False
    took_sec: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "success": self.success,
            "verified": self.verified,
            "error": self.error,
            "error_trace": self.error_trace,
            "pre_state": self.pre_state,
            "post_state": self.post_state,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "rollback_performed": self.rollback_performed,
            "took_sec": self.took_sec,
        }


class ChangeExecutor:
    """
    Executes ChangeSets with verification and rollback support.
    
    The executor follows the pipeline:
    1. Capture checkpoint (pre_state)
    2. Apply operations
    3. Run verification tests
    4. Verify system health
    5. If verification fails: initiate rollback
    6. Mark as committed
    """
    
    def __init__(self, change_manager_instance=None):
        self.change_manager = change_manager_instance or change_manager
        self._execution_handlers: Dict[ChangeType, Callable[[ChangeSet], ExecutorResult]] = {}
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """Set up default execution handlers for change types"""
        self._execution_handlers[ChangeType.KNOWLEDGE_UPDATE] = self._execute_knowledge_update
        self._execution_handlers[ChangeType.CONFIG_CHANGE] = self._execute_config_change
        self._execution_handlers[ChangeType.CODE_PATCH] = self._execute_code_patch
        self._execution_handlers[ChangeType.SERVICE_RESTART] = self._execute_service_restart
    
    def execute(self, change: ChangeSet) -> ExecutorResult:
        """
        Execute a ChangeSet through the full pipeline.
        
        Steps:
        1. Validate change is approved
        2. Capture checkpoint
        3. Apply operations
        4. Run tests
        5. Verify health
        6. Return result (or rollback if needed)
        """
        start_time = time.time()
        result = ExecutorResult(
            change_id=change.change_id,
            success=False,
        )
        
        try:
            # Validate
            if change.status != ChangeStatus.APPROVED:
                result.error = f"Change not approved (status: {change.status.value})"
                return result
            
            # Update status
            change.status = ChangeStatus.APPLYING
            change.started_at = time.time()
            
            # Capture pre-state checkpoint
            result.pre_state = self._capture_checkpoint(change)
            change.checkpoint_created = True
            change.checkpoint_path = f"/checkpoints/{change.change_id}"
            
            # Apply operations
            logger.info(f"Applying ChangeSet {change.change_id}")
            result = self._apply_operations(change)
            
            if not result.success:
                # Apply failed
                change.status = ChangeStatus.FAILED
                change.error = result.error
                self._attempt_rollback(change, result)
                return result
            
            # Run tests
            logger.info(f"Running verification tests for ChangeSet {change.change_id}")
            change.status = ChangeStatus.VERIFYING
            test_result = self._run_tests(change)
            result.tests_passed = test_result.get("passed", 0)
            result.tests_failed = test_result.get("failed", 0)
            
            if test_result.get("failed", 0) > 0:
                logger.warning(f"Tests failed for ChangeSet {change.change_id}")
                result.error = "Verification tests failed"
                change.status = ChangeStatus.FAILED
                self._attempt_rollback(change, result)
                return result
            
            # Verify system health
            health_ok = self._verify_system_health(change)
            if not health_ok:
                logger.warning(f"Health check failed for ChangeSet {change.change_id}")
                result.error = "Post-change health check failed"
                change.status = ChangeStatus.FAILED
                self._attempt_rollback(change, result)
                return result
            
            # Commit
            change.status = ChangeStatus.COMMITTED
            change.completed_at = time.time()
            result.success = True
            result.verified = True
            result.took_sec = time.time() - start_time
            
            logger.info(f"ChangeSet {change.change_id} successfully committed")
            
        except Exception as e:
            logger.error(f"Exception during execution of {change.change_id}: {e}")
            result.error = str(e)
            result.error_trace = traceback.format_exc()
            change.status = ChangeStatus.FAILED
            change.error = str(e)
            self._attempt_rollback(change, result)
        
        return result
    
    def _capture_checkpoint(self, change: ChangeSet) -> Dict[str, Any]:
        """Capture system state before applying changes"""
        # This would integrate with actual state capture
        return {
            "timestamp": time.time(),
            "change_id": change.change_id,
            "target": change.target,
        }
    
    def _apply_operations(self, change: ChangeSet) -> ExecutorResult:
        """Apply all operations in the ChangeSet"""
        handler = self._execution_handlers.get(change.type)
        if not handler:
            # Use default handler
            return self._apply_operations_default(change)
        
        return handler(change)
    
    def _apply_operations_default(self, change: ChangeSet) -> ExecutorResult:
        """Default operation handler"""
        result = ExecutorResult(change_id=change.change_id, success=True)
        
        for op in change.operations:
            logger.debug(f"Applying operation: {op.op} {op.path}")
            # In a real implementation, this would:
            # - Apply knowledge updates to knowledge store
            # - Write memory updates
            # - Patch code files
            # - Update configurations
            # - Restart services
            
            # For now, record the operation as applied
            logger.info(f"Would execute: {op.op} on {op.path}")
        
        return result
    
    def _execute_knowledge_update(self, change: ChangeSet) -> ExecutorResult:
        """Execute a knowledge update"""
        result = ExecutorResult(change_id=change.change_id, success=True)
        
        for op in change.operations:
            if op.path.startswith("/knowledge/"):
                # Apply knowledge update
                logger.info(f"Knowledge update: {op.path}")
                # This would write to the knowledge store
        
        return result
    
    def _execute_config_change(self, change: ChangeSet) -> ExecutorResult:
        """Execute a configuration change"""
        result = ExecutorResult(change_id=change.change_id, success=True)
        
        for op in change.operations:
            logger.info(f"Config change: {op.op} {op.path} = {op.value}")
            # Would update configuration store
        
        return result
    
    def _execute_code_patch(self, change: ChangeSet) -> ExecutorResult:
        """Execute a code patch"""
        result = ExecutorResult(change_id=change.change_id, success=True)
        
        for op in change.operations:
            if op.op == "patch":
                logger.info(f"Code patch: {op.path}")
                # Would apply patch to file, run tests
        
        return result
    
    def _execute_service_restart(self, change: ChangeSet) -> ExecutorResult:
        """Execute a service restart"""
        result = ExecutorResult(change_id=change.change_id, success=True)
        
        service_name = change.target
        logger.info(f"Restarting service: {service_name}")
        # Would call service manager to restart
        
        return result
    
    def _run_tests(self, change: ChangeSet) -> Dict[str, int]:
        """Run verification tests for a ChangeSet"""
        passed = 0
        failed = 0
        
        for test in change.tests:
            try:
                logger.debug(f"Running test: {test.type} -> {test.target}")
                # In production, would run actual tests
                if test.type == "smoke":
                    # Quick health check
                    passed += 1
                elif test.type == "health_check":
                    # Check endpoint health
                    passed += 1
                else:
                    # For demo, assume tests pass
                    passed += 1
            except Exception as e:
                logger.warning(f"Test failed: {test.type} -> {e}")
                failed += 1
        
        return {"passed": passed, "failed": failed}
    
    def _verify_system_health(self, change: ChangeSet) -> bool:
        """Verify system health after changes"""
        # Would check service health endpoints
        # For now, assume OK
        return True
    
    def _attempt_rollback(self, change: ChangeSet, result: ExecutorResult) -> None:
        """Attempt to rollback a failed change"""
        if not change.rollback_operations:
            logger.warning(f"No rollback operations for {change.change_id}")
            return
        
        logger.info(f"Attempting rollback for {change.change_id}")
        result.rollback_performed = True
        result.verified = False
        
        try:
            for op in change.rollback_operations:
                logger.debug(f"Rollback: {op.op} {op.path}")
                # Would apply rollback operations
        except Exception as e:
            logger.error(f"Rollback failed for {change.change_id}: {e}")


# Global executor instance
executor = ChangeExecutor()