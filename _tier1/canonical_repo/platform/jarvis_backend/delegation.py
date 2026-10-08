"""Phase 10 — Multi-Agent Delegation.

Enables the Cognitive Kernel to delegate sub-tasks to specialist roles with
different capability sets and risk tolerances.  Delegation is bounded by
``max_delegations`` per role and the mission's autonomy level.

The Kernel delegates to AgentExecutor (Phase 7) for actual execution; this
module manages *which* role handles *which* sub-task and tracks delegation
depth.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from jarvis_backend.core import now_iso
from jarvis_backend.execution_fabric import (
    AgentExecutor,
    Task,
    TaskStatus,
)

from .specialist_roles import RoleConfig, get_role, can_delegate_to

logger = logging.getLogger("jarvis_backend.mission_api")


@dataclass
class Delegation:
    """A delegation of a sub-task to a specialist role."""

    delegation_id: str
    mission_id: str
    parent_task_id: Optional[str]
    role_name: str
    sub_objective: str
    capabilities: list[str]
    delegated_at: str
    delegated_by: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    result: Optional[dict[str, Any]] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "mission_id": self.mission_id,
            "parent_task_id": self.parent_task_id,
            "role_name": self.role_name,
            "sub_objective": self.sub_objective,
            "capabilities": list(self.capabilities),
            "delegated_at": self.delegated_at,
            "delegated_by": self.delegated_by,
            "status": self.status,
            "result": self.result,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Delegation":
        return cls(
            delegation_id=data["delegation_id"],
            mission_id=data["mission_id"],
            parent_task_id=data.get("parent_task_id"),
            role_name=data["role_name"],
            sub_objective=data["sub_objective"],
            capabilities=list(data.get("capabilities", [])),
            delegated_at=data["delegated_at"],
            delegated_by=data["delegated_by"],
            status=data.get("status", "pending"),
            result=data.get("result"),
            completed_at=data.get("completed_at"),
        )


class DelegationManager:
    """Manages multi-agent delegation within a mission.

    The DelegationManager decides *which* specialist role should handle a
    sub-task, enforces the role hierarchy (a role can only delegate to its
    declared ``child_roles``), and tracks delegation depth to prevent
    infinite delegation chains.
    """

    def __init__(self, executor: Optional[AgentExecutor] = None) -> None:
        self._delegations: dict[str, Delegation] = {}
        self._executor = executor

    def plan_delegation(
        self,
        mission_id: str,
        role_name: str,
        sub_objective: str,
        capabilities: list[str],
        delegated_by: str = "cognitive_kernel",
        parent_task_id: Optional[str] = None,
        max_depth: int = 3,
    ) -> Optional[Delegation]:
        """Plan a delegation to a specialist role.

        Returns the Delegation if planning succeeds, None if the role cannot
        delegate (depth limit, role not found, or hierarchy violation).
        """
        role = get_role(role_name)
        if role is None:
            logger.warning("Cannot delegate to unknown role: %s", role_name)
            return None

        # Check delegation depth
        depth = self._delegation_depth(mission_id)
        if depth >= max_depth:
            logger.warning(
                "Delegation depth limit (%d) reached for mission %s",
                max_depth, mission_id,
            )
            return None

        if not role.can_delegate:
            logger.debug(
                "Role %s cannot delegate (can_delegate=False)", role_name,
            )
            return None

        # Filter capabilities to what the role prefers
        allowed = set(role.preferred_capabilities) if role.preferred_capabilities else set(capabilities)
        filtered_caps = [c for c in capabilities if c in allowed or not allowed]

        if not filtered_caps:
            filtered_caps = list(capabilities)  # fall back to all requested

        d = Delegation(
            delegation_id=f"del_{uuid.uuid4().hex[:12]}",
            mission_id=mission_id,
            parent_task_id=parent_task_id,
            role_name=role_name,
            sub_objective=sub_objective,
            capabilities=filtered_caps,
            delegated_at=now_iso(),
            delegated_by=delegated_by,
        )
        self._delegations[d.delegation_id] = d
        logger.info(
            "Delegated sub-task to role %s (mission %s, depth %d)",
            role_name, mission_id, depth + 1,
        )
        return d

    async def execute_delegation(
        self,
        delegation_id: str,
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Execute a delegated sub-task through the AgentExecutor.

        Returns the execution result, or None if the delegation was not found
        or the executor is not available.
        """
        d = self._delegations.get(delegation_id)
        if d is None:
            return None
        if self._executor is None:
            return None

        d.status = "running"

        from jarvis_backend.execution_fabric import TaskStatus

        task, graph = self._executor.build_execution_graph(
            intent=d.sub_objective,
            capabilities=d.capabilities,
            user_id=d.delegated_by,
        )

        result = await self._executor.execute_task(
            task, permissions=permissions, principal=principal,
        )

        d.result = result
        d.status = "completed" if result.get("success") else "failed"
        d.completed_at = now_iso()

        return result

    def get_role_for_capability(self, capability: str) -> Optional[str]:
        """Find the best role for a given capability.

        Returns the role name whose preferred_capabilities include the
        capability, or the closest match.
        """
        from .specialist_roles import get_all_roles

        best_role = None
        for role in get_all_roles():
            if capability in role.preferred_capabilities:
                return role.name
            if best_role is None:
                best_role = role.name
        return best_role

    def _delegation_depth(self, mission_id: str) -> int:
        """Count active (non-terminal) delegations for a mission."""
        return sum(
            1 for d in self._delegations.values()
            if d.mission_id == mission_id and d.status in ("pending", "running")
        )

    def get_delegations(self, mission_id: str) -> list[Delegation]:
        """Return all delegations for a mission."""
        return [d for d in self._delegations.values()
                if d.mission_id == mission_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegations": [d.to_dict() for d in self._delegations.values()],
            "active_count": self._delegation_depth(""),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], executor: Optional[AgentExecutor] = None) -> "DelegationManager":
        dm = cls(executor=executor)
        for dd in data.get("delegations", []):
            d = Delegation.from_dict(dd)
            dm._delegations[d.delegation_id] = d
        return dm


__all__ = [
    "Delegation",
    "DelegationManager",
]
