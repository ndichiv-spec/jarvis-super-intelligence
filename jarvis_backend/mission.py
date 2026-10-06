"""Phase 10 — Mission abstraction.

A *Mission* is a durable, lifecycle-managed long-running objective.  It is the
**orchestration layer** above the existing Task/ExecutionGraph fabric (Phase 7)
and the Brain (Phase 8).  Mission does **not** replace JobRegistry (which
remains responsible for executable jobs) — Missions reference tasks and jobs
but operate at a higher level of abstraction.

Persistence uses the existing ``get_store("missions")`` pattern, mirroring
``Task.save()`` / ``Task.load()`` in ``execution_fabric.py``.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import get_store, now_iso

from .mission_lifecycle import (
    MissionStatus,
    MissionTransitionError,
    MissionLifecycle,
    validate_transition,
    is_terminal,
)


# ---------------------------------------------------------------------------
# Supporting enums
# ---------------------------------------------------------------------------
class AutonomyLevel(Enum):
    """How much the Cognitive Kernel can do without human intervention.

    * LEVEL_0 — fully manual: every kernel step must be approved.
    * LEVEL_1 — kernel can execute READ tasks; EXEC/WRITE/NETWORK require
      explicit human confirmation (delegated to ToolRegistry authorization).
    * LEVEL_2 — kernel can execute READ + low-risk WRITE; high-risk requires
      approval through PromotionGate.
    * LEVEL_3 — kernel can self-plan and execute within declared capability
      budget, but cannot approve its own promotion/deployment.
    """
    LEVEL_0 = 0
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3


class RiskLevel(str, Enum):
    """Risk tier for a mission (mission-level, not tool-level)."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MissionPriority(str, Enum):
    """Priority tiers for mission scheduling."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionMode(str, Enum):
    """Execution mode — online (live providers) or offline (degraded)."""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------
@dataclass
class MissionBudget:
    """Hard limits enforced by the Cognitive Kernel.

    Every cycle consumes a cognitive step.  When any limit is exhausted the
    Kernel must stop (hard stop, no infinite loops).
    """
    max_steps: int = 50           # maximum cognitive cycles
    max_tokens: int = 50_000      # max model tokens (if model is available)
    max_cost_usd: float = 10.0    # max USD spend across all providers
    max_seconds: int = 3_600      # max wall-clock seconds (1 hour)
    max_iterations: int = 20      # max inner-loop iterations per cycle
    max_cost_provider: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_seconds": self.max_seconds,
            "max_iterations": self.max_iterations,
            "max_cost_provider": dict(self.max_cost_provider),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionBudget":
        return cls(
            max_steps=data.get("max_steps", 50),
            max_tokens=data.get("max_tokens", 50_000),
            max_cost_usd=data.get("max_cost_usd", 10.0),
            max_seconds=data.get("max_seconds", 3_600),
            max_iterations=data.get("max_iterations", 20),
            max_cost_provider=dict(data.get("max_cost_provider", {})),
        )


# ---------------------------------------------------------------------------
# Mission Event Timeline
# ---------------------------------------------------------------------------
@dataclass
class MissionEvent:
    """One entry on the mission's event timeline."""

    event_id: str
    mission_id: str
    at: str          # ISO-8601 UTC
    kind: str        # e.g. "transition", "checkpoint", "hypothesis", "evidence",
                     #   "verification", "approval", "budget", "replan"
    status_from: Optional[str]
    status_to: Optional[str]
    detail: str
    actor: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "mission_id": self.mission_id,
            "at": self.at,
            "kind": self.kind,
            "from": self.status_from,
            "to": self.status_to,
            "detail": self.detail,
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionEvent":
        return cls(
            event_id=data["event_id"],
            mission_id=data["mission_id"],
            at=data["at"],
            kind=data["kind"],
            status_from=data.get("from"),
            status_to=data.get("to"),
            detail=data.get("detail", ""),
            actor=data.get("actor", "system"),
        )


# ---------------------------------------------------------------------------
# Mission Checkpoint
# ---------------------------------------------------------------------------
@dataclass
class MissionCheckpoint:
    """A durable snapshot of mission state for crash recovery."""

    checkpoint_id: str
    mission_id: str
    at: str          # ISO-8601 UTC
    cycle: int       # cognitive cycle at checkpoint time
    phase: str       # current cognitive phase
    cognitive_state: dict[str, Any]
    task_states: dict[str, Any]
    hypothesis_states: dict[str, Any]
    evidence_count: int
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "mission_id": self.mission_id,
            "at": self.at,
            "cycle": self.cycle,
            "phase": self.phase,
            "cognitive_state": dict(self.cognitive_state),
            "task_states": dict(self.task_states),
            "hypothesis_states": dict(self.hypothesis_states),
            "evidence_count": self.evidence_count,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionCheckpoint":
        return cls(
            checkpoint_id=data["checkpoint_id"],
            mission_id=data["mission_id"],
            at=data["at"],
            cycle=data["cycle"],
            phase=data["phase"],
            cognitive_state=dict(data.get("cognitive_state", {})),
            task_states=dict(data.get("task_states", {})),
            hypothesis_states=dict(data.get("hypothesis_states", {})),
            evidence_count=data.get("evidence_count", 0),
            notes=data.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# Decision log entry
# ---------------------------------------------------------------------------
@dataclass
class MissionDecision:
    """A recorded decision made during mission execution."""

    decision_id: str
    at: str
    kind: str          # e.g. "plan", "authorize", "replan", "critique", "verify"
    rationale: str
    outcome: str       # e.g. "approved", "rejected", "escalated"
    evidence_refs: list[str] = field(default_factory=list)
    actor: str = "cognitive_kernel"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "at": self.at,
            "kind": self.kind,
            "rationale": self.rationale,
            "outcome": self.outcome,
            "evidence_refs": list(self.evidence_refs),
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionDecision":
        return cls(
            decision_id=data["decision_id"],
            at=data["at"],
            kind=data["kind"],
            rationale=data["rationale"],
            outcome=data["outcome"],
            evidence_refs=list(data.get("evidence_refs", [])),
            actor=data.get("actor", "cognitive_kernel"),
        )


# Short UUID helper (mirrors research_engine models)
def _short_uuid() -> str:
    import uuid as _uuid
    return _uuid.uuid4().hex[:12]


def _utcnow() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Mission — the durable long-running objective
# ---------------------------------------------------------------------------
@dataclass
class Mission:
    """A durable, lifecycle-managed long-running objective.

    Missions are persisted via ``get_store("missions")`` using the same
    ``to_dict``/``from_dict``/``save``/``load`` pattern as Phase 7's Task.
    """

    mission_id: str
    title: str
    objective: str
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    failure_criteria: list[str] = field(default_factory=list)
    priority: str = MissionPriority.NORMAL.value
    autonomy_level: int = AutonomyLevel.LEVEL_1
    risk_level: str = RiskLevel.MEDIUM.value
    budget: MissionBudget = field(default_factory=MissionBudget)
    allowed_capabilities: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    execution_mode: str = ExecutionMode.ONLINE.value
    status: str = MissionStatus.DRAFT.value
    created_by: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    deadline: Optional[str] = None
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    current_phase: str = "understand"
    parent_mission: Optional[str] = None
    tasks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    # -- Lifecycle --
    def transition(
        self,
        target: MissionStatus,
        actor: str = "system",
        notes: str = "",
    ) -> None:
        """Validate and apply a state transition.

        Raises ``MissionTransitionError`` if the transition is illegal.
        Records an event on the mission timeline.
        """
        current = MissionStatus(self.status)
        # validate_transition checks preconditions (e.g. DRAFT→ACTIVE needs
        # objective + success_criteria, no active tasks for PAUSE/CANCEL,
        # COMPLETED only via VERIFYING).
        validate_transition(current, target, mission=self)

        prev = self.status
        self.status = target.value
        self.updated_at = now_iso()
        self._record_event(
            kind="transition",
            status_from=prev,
            status_to=target.value,
            detail=notes or f"mission transitioned {prev} → {target.value}",
            actor=actor,
        )

    @property
    def is_terminal(self) -> bool:
        return is_terminal(MissionStatus(self.status))

    @property
    def status_enum(self) -> MissionStatus:
        try:
            return MissionStatus(self.status)
        except ValueError:
            return MissionStatus.DRAFT

    # -- Event timeline --
    def _record_event(
        self,
        kind: str,
        detail: str,
        actor: str = "system",
        status_from: Optional[str] = None,
        status_to: Optional[str] = None,
    ) -> None:
        # Events are stored in metrics["event_timeline"] (a list of dicts).
        timeline = self.metrics.setdefault("event_timeline", [])
        if not isinstance(timeline, list):
            timeline = []
            self.metrics["event_timeline"] = timeline
        ev = MissionEvent(
            event_id=f"ev_{_short_uuid()}",
            mission_id=self.mission_id,
            at=now_iso(),
            kind=kind,
            status_from=status_from,
            status_to=status_to,
            detail=detail,
            actor=actor,
        )
        timeline.append(ev.to_dict())

    def event_timeline(self) -> list[dict[str, Any]]:
        """Return the mission's event timeline."""
        return self.metrics.get("event_timeline", [])

    # -- Checkpoints --
    def checkpoint(
        self,
        cycle: int,
        phase: str,
        cognitive_state: Optional[dict[str, Any]] = None,
        task_states: Optional[dict[str, Any]] = None,
        hypothesis_states: Optional[dict[str, Any]] = None,
        evidence_count: int = 0,
        notes: str = "",
    ) -> str:
        """Create a durable checkpoint for crash recovery.

        Returns the checkpoint_id.
        """
        ck = MissionCheckpoint(
            checkpoint_id=f"ckpt_{_short_uuid()}",
            mission_id=self.mission_id,
            at=now_iso(),
            cycle=cycle,
            phase=phase,
            cognitive_state=cognitive_state or {},
            task_states=task_states or {},
            hypothesis_states=hypothesis_states or {},
            evidence_count=evidence_count,
            notes=notes,
        )
        self.checkpoints.append(ck.to_dict())
        self.updated_at = now_iso()
        return ck.checkpoint_id

    def latest_checkpoint(self) -> Optional[dict[str, Any]]:
        """Return the most recent checkpoint, or None."""
        if not self.checkpoints:
            return None
        return sorted(self.checkpoints, key=lambda c: c.get("at", ""))[-1]

    # -- Serialization --
    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "objective": self.objective,
            "constraints": list(self.constraints),
            "success_criteria": list(self.success_criteria),
            "failure_criteria": list(self.failure_criteria),
            "priority": self.priority,
            "autonomy_level": self.autonomy_level,
            "risk_level": self.risk_level,
            "budget": self.budget.to_dict() if isinstance(self.budget, MissionBudget) else self.budget,
            "allowed_capabilities": list(self.allowed_capabilities),
            "required_capabilities": list(self.required_capabilities),
            "execution_mode": self.execution_mode,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deadline": self.deadline,
            "context_snapshot": dict(self.context_snapshot),
            "current_phase": self.current_phase,
            "parent_mission": self.parent_mission,
            "tasks": list(self.tasks),
            "artifacts": list(self.artifacts),
            "evidence": list(self.evidence),
            "decisions": list(self.decisions),
            "checkpoints": list(self.checkpoints),
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Mission":
        budget_val = data.get("budget", {})
        budget = (MissionBudget.from_dict(budget_val)
                  if isinstance(budget_val, dict) else budget_val)
        return cls(
            mission_id=data["mission_id"],
            title=data["title"],
            objective=data["objective"],
            constraints=list(data.get("constraints", [])),
            success_criteria=list(data.get("success_criteria", [])),
            failure_criteria=list(data.get("failure_criteria", [])),
            priority=data.get("priority", MissionPriority.NORMAL.value),
            autonomy_level=data.get("autonomy_level", AutonomyLevel.LEVEL_1),
            risk_level=data.get("risk_level", RiskLevel.MEDIUM.value),
            budget=budget if budget is not None else MissionBudget(),
            allowed_capabilities=list(data.get("allowed_capabilities", [])),
            required_capabilities=list(data.get("required_capabilities", [])),
            execution_mode=data.get("execution_mode", ExecutionMode.ONLINE.value),
            status=data.get("status", MissionStatus.DRAFT.value),
            created_by=data.get("created_by", ""),
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
            deadline=data.get("deadline"),
            context_snapshot=dict(data.get("context_snapshot", {})),
            current_phase=data.get("current_phase", "understand"),
            parent_mission=data.get("parent_mission"),
            tasks=list(data.get("tasks", [])),
            artifacts=list(data.get("artifacts", [])),
            evidence=list(data.get("evidence", [])),
            decisions=list(data.get("decisions", [])),
            checkpoints=list(data.get("checkpoints", [])),
            metrics=dict(data.get("metrics", {})),
        )

    # -- Persistence --
    def save(self) -> None:
        """Checkpoint this mission to the persistent mission store."""
        store = get_store("missions")
        missions = store.load()
        missions[self.mission_id] = self.to_dict()
        store.save()

    @staticmethod
    def load(mission_id: str) -> Optional["Mission"]:
        """Load a mission from the persistent store, or None if not found."""
        store = get_store("missions")
        missions = store.load()
        raw = missions.get(mission_id)
        if raw is None:
            return None
        return Mission.from_dict(raw)

    @staticmethod
    def list_all() -> list["Mission"]:
        """Return all saved missions."""
        store = get_store("missions")
        missions = store.load()
        return [Mission.from_dict(raw) for raw in missions.values()]

    @staticmethod
    def create(
        title: str,
        objective: str,
        created_by: str = "anonymous",
        success_criteria: Optional[list[str]] = None,
        constraints: Optional[list[str]] = None,
        failure_criteria: Optional[list[str]] = None,
        priority: str = MissionPriority.NORMAL.value,
        autonomy_level: int = AutonomyLevel.LEVEL_1,
        risk_level: str = RiskLevel.MEDIUM.value,
        budget: Optional[MissionBudget] = None,
        allowed_capabilities: Optional[list[str]] = None,
        required_capabilities: Optional[list[str]] = None,
        execution_mode: str = ExecutionMode.ONLINE.value,
        deadline: Optional[str] = None,
        parent_mission: Optional[str] = None,
    ) -> "Mission":
        """Factory: create a new DRAFT mission and persist it."""
        m = Mission(
            mission_id=f"mission_{_short_uuid()}",
            title=title,
            objective=objective,
            constraints=list(constraints or []),
            success_criteria=list(success_criteria or []),
            failure_criteria=list(failure_criteria or []),
            priority=priority,
            autonomy_level=autonomy_level,
            risk_level=risk_level,
            budget=budget or MissionBudget(),
            allowed_capabilities=list(allowed_capabilities or []),
            required_capabilities=list(required_capabilities or []),
            execution_mode=execution_mode,
            created_by=created_by,
            deadline=deadline,
            parent_mission=parent_mission,
        )
        m._record_event(
            kind="created",
            detail=f"mission '{title}' created",
            actor=created_by,
        )
        m.save()
        return m


__all__ = [
    "AutonomyLevel",
    "RiskLevel",
    "MissionPriority",
    "ExecutionMode",
    "MissionBudget",
    "MissionEvent",
    "MissionCheckpoint",
    "MissionDecision",
    "Mission",
]
