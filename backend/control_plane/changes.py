"""
Change Set System - Typed, reversible descriptions of system mutations.

A ChangeSet represents an intentional, auditable, and reversible change
to the JARVIS platform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Union
from enum import Enum
import time
import json
import hashlib
import uuid
import logging

logger = logging.getLogger("control_plane.changes")


class ChangeType(str, Enum):
    """Types of changes that can be made"""
    KNOWLEDGE_UPDATE = "knowledge_update"
    MEMORY_UPDATE = "memory_update"
    PROCEDURE_UPDATE = "procedure_update"
    SKILL_UPDATE = "skill_update"
    CONFIG_CHANGE = "config_change"
    CODE_PATCH = "code_patch"
    TEST_PATCH = "test_patch"
    TOOL_REGISTRATION = "tool_registration"
    MODEL_REGISTRY_UPDATE = "model_registry_update"
    WORKFLOW_UPDATE = "workflow_update"
    SERVICE_RESTART = "service_restart"
    DATASET_UPDATE = "dataset_update"
    SECURITY_POLICY = "security_policy"
    AUTH_POLICY = "auth_policy"
    DATA_MIGRATION = "data_migration"
    ROLLBACK = "rollback"


class ChangeStatus(str, Enum):
    """Status of a change set"""
    PROPOSED = "proposed"
    VALIDATING = "validating"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLYING = "applying"
    VERIFYING = "verifying"
    COMMITTED = "committed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    """Risk level of a change"""
    LOW = "low"        # Knowledge indexing, metadata updates
    MEDIUM = "medium"  # Code patches, config changes
    HIGH = "high"      # Security, production deployment, credentials


@dataclass
class ChangeOperation:
    """A single operation within a ChangeSet"""
    op: str  # Operation type: add, remove, replace, move, test
    path: str  # JSON path or identifier
    value: Optional[Any] = None
    from_value: Optional[Any] = None
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"op": self.op, "path": self.path}
        if self.value is not None:
            result["value"] = self.value
        if self.from_value is not None:
            result["from"] = self.from_value
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class TestSpec:
    """Test specification for a change"""
    type: str  # unit, integration, health_check, smoke
    target: str  # Service name or test file
    expected: Any = None
    timeout_sec: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "expected": self.expected,
            "timeout_sec": self.timeout_sec,
        }


@dataclass
class ChangeSet:
    """
    A ChangeSet represents an intentional, testable, and reversible
    description of a system mutation.
    
    ChangeSets flow through stages:
    PROPOSED -> VALIDATING -> APPROVED -> APPLYING -> VERIFYING -> COMMITTED
                          \-> FAILED -> ROLLED_BACK
                          \-> REJECTED
                          \-> CANCELLED
    """
    
    change_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: ChangeType = ChangeType.CONFIG_CHANGE
    title: str = ""
    description: str = ""
    reason: str = ""
    
    # Core change data
    operations: List[ChangeOperation] = field(default_factory=list)
    tests: List[TestSpec] = field(default_factory=list)
    
    # Policy and approval
    risk: RiskLevel = RiskLevel.LOW
    policy: Literal["auto", "approval", "readonly"] = "auto"
    approvers: List[str] = field(default_factory=list)
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None
    
    # Status tracking
    status: ChangeStatus = ChangeStatus.PROPOSED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Results
    error: Optional[str] = None
    result_details: Dict[str, Any] = field(default_factory=dict)
    
    # Rollback support
    rollback_operations: List[ChangeOperation] = field(default_factory=list)
    checkpoint_created: bool = False
    checkpoint_path: Optional[str] = None
    
    # Provenance
    created_by: str = "system"
    source_task_id: Optional[str] = None
    parent_change_id: Optional[str] = None
    
    # Target
    target: str = ""  # Service name, component, or resource
    
    def compute_hash(self) -> str:
        """Compute hash of change content for integrity"""
        data = {
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "reason": self.reason,
            "operations": [op.to_dict() for op in self.operations],
            "tests": [t.to_dict() for t in self.tests],
            "risk": self.risk.value,
            "target": self.target,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "reason": self.reason,
            "operations": [op.to_dict() for op in self.operations],
            "tests": [t.to_dict() for t in self.tests],
            "risk": self.risk.value,
            "policy": self.policy,
            "approvers": self.approvers,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result_details": self.result_details,
            "rollback_operations": [op.to_dict() for op in self.rollback_operations],
            "checkpoint_created": self.checkpoint_created,
            "checkpoint_path": self.checkpoint_path,
            "created_by": self.created_by,
            "source_task_id": self.source_task_id,
            "parent_change_id": self.parent_change_id,
            "target": self.target,
            "hash": self.compute_hash(),
        }


class ChangeSetManager:
    """
    Manages ChangeSets - creation, validation, approval, execution, and rollback.
    """
    
    _instance: Optional["ChangeSetManager"] = None
    
    def __init__(self):
        self._changes: Dict[str, ChangeSet] = {}
        self._pending_approvals: List[str] = []
    
    @classmethod
    def get_instance(cls) -> "ChangeSetManager":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)"""
        cls._instance = None
    
    def create(self, change_type: str, title: str, **kwargs) -> ChangeSet:
        """Create a new ChangeSet"""
        change = ChangeSet(
            change_id=str(uuid.uuid4()),
            type=ChangeType(change_type),
            title=title,
            created_at=time.time(),
            **kwargs
        )
        self._changes[change.change_id] = change
        logger.info(f"Created ChangeSet: {change.change_id} ({change_type})")
        return change
    
    def get(self, change_id: str) -> Optional[ChangeSet]:
        """Get a ChangeSet by ID"""
        return self._changes.get(change_id)
    
    def get_all(self, status: Optional[ChangeStatus] = None) -> List[ChangeSet]:
        """Get all ChangeSets, optionally filtered by status"""
        if status:
            return [c for c in self._changes.values() if c.status == status]
        return list(self._changes.values())
    
    def get_pending_approvals(self) -> List[ChangeSet]:
        """Get ChangeSets awaiting approval"""
        return [
            self._changes[cid] for cid in self._pending_approvals
            if cid in self._changes
        ]
    
    def add_operation(self, change_id: str, operation: ChangeOperation) -> None:
        """Add an operation to a ChangeSet"""
        change = self.get(change_id)
        if change:
            change.operations.append(operation)
    
    def add_test(self, change_id: str, test: TestSpec) -> None:
        """Add a test to a ChangeSet"""
        change = self.get(change_id)
        if change:
            change.tests.append(test)
    
    def approve(self, change_id: str, approved_by: str) -> bool:
        """Approve a ChangeSet for execution"""
        change = self.get(change_id)
        if change and change.status == ChangeStatus.PROPOSED:
            change.approved_by = approved_by
            change.approved_at = time.time()
            change.status = ChangeStatus.APPROVED
            if change_id in self._pending_approvals:
                self._pending_approvals.remove(change_id)
            logger.info(f"ChangeSet {change_id} approved by {approved_by}")
            return True
        return False
    
    def propose(self, change: ChangeSet) -> None:
        """Propose a ChangeSet for approval"""
        change.status = ChangeStatus.PROPOSED
        if change.policy == "approval":
            self._pending_approvals.append(change.change_id)
        logger.info(f"ChangeSet {change.change_id} proposed")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            change_id: change.to_dict()
            for change_id, change in self._changes.items()
        }


# Global manager instance
change_manager = ChangeSetManager.get_instance()


def create_knowledge_update(
    title: str,
    path: str,
    value: Any,
    reason: str = "",
    source: str = "system"
) -> ChangeSet:
    """Create a knowledge update ChangeSet"""
    change = ChangeSet(
        type=ChangeType.KNOWLEDGE_UPDATE,
        title=title,
        reason=reason,
        target=path,
        created_by=source,
        risk=RiskLevel.LOW,
        policy="auto",
    )
    change.operations.append(ChangeOperation(
        op="add" if isinstance(value, dict) and "add" not in str(value).lower() else "replace",
        path=path,
        value=value,
    ))
    change_manager._changes[change.change_id] = change
    return change


def create_code_patch(
    title: str,
    target_file: str,
    patch: str,
    source: str = "system",
    auto_apply: bool = False,
) -> ChangeSet:
    """Create a code patch ChangeSet"""
    change = ChangeSet(
        type=ChangeType.CODE_PATCH,
        title=title,
        reason=f"Patch to {target_file}",
        target=target_file,
        created_by=source,
        risk=RiskLevel.MEDIUM,
        policy="auto" if auto_apply else "approval",
    )
    change.operations.append(ChangeOperation(
        op="patch",
        path=target_file,
        value=patch,
    ))
    change_manager._changes[change.change_id] = change
    return change