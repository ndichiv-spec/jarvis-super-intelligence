"""Brain ↔ Control Plane protocol state machine (Phase 8 §5).

A strict, ordered event protocol.  Each event is emitted by the control plane
exactly once per phase and advances an internal phase register; the machine
*rejects* out-of-order events so a misbehaving/lying model or component cannot
skip the PLAN→EXECUTE→OBSERVE→VERIFY→REASON→REPLAN loop.

Events (spec §5)::

    BRAIN_PLAN_CREATED        → plan proposed by the Brain
    BRAIN_PLAN_VALIDATED      → PlanValidator accepted the proposal
    PLAN_AUTHORIZED           → control plane authorized execution
    EXECUTION_STARTED         → capability dispatch begun
    EXECUTION_PROGRESS        → a step is observed running/finishing
    EXECUTION_RESULT          → a capability returned a (sanitized) result
    VERIFICATION_RESULT       → VerificationEngine verdict vs completion_conditions
    BRAIN_REASSESSMENT        → Brain re-observes sanitized results + proposes next step
    (loop back to EXECUTION_STARTED for the next step, or PLAN_VALIDATED to replan)
    TASK_COMPLETED            → a completion_condition satisfied with real evidence
    TASK_FAILED / TASK_CANCELLED / TASK_BUDGET_EXCEEDED (terminal)
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

from .audit import AuditEvent, BrainAudit, EventType
from .budget import TaskBudget, TaskBudgetExceeded


# Allowed phase transitions.  Phase -> set of phases reachable from it.
_PHASE_TRANSITIONS: "OrderedDict[str, frozenset[str]]" = OrderedDict([
    ("INIT", frozenset({"PLAN_CREATED"})),
    ("PLAN_CREATED", frozenset({"PLAN_VALIDATED", "AWAITING_USER_INPUT",
                                "TASK_CANCELLED", "TASK_FAILED"})),
    ("AWAITING_USER_INPUT", frozenset()),  # terminal in protocol; _terminal records the FAIL
    ("PLAN_VALIDATED", frozenset({"PLAN_AUTHORIZED", "PLAN_REJECTED", "PLAN_BLOCKED",
                                  "DENIED", "HUMAN_APPROVAL", "TASK_CANCELLED"})),
    ("PLAN_AUTHORIZED", frozenset({"EXECUTION_STARTED", "TASK_CANCELLED"})),
    ("EXECUTION_STARTED", frozenset({"EXECUTION_PROGRESS", "EXECUTION_RESULT",
                                     "TASK_CANCELLED", "PROVIDER_UNAVAILABLE"})),
    ("EXECUTION_PROGRESS", frozenset({"EXECUTION_RESULT", "EXECUTION_PROGRESS",
                                       "PROVIDER_UNAVAILABLE"})),
    ("EXECUTION_RESULT", frozenset({"VERIFICATION_RESULT", "BRAIN_REASSESSMENT",
                                    "EXECUTION_STARTED", "EXECUTION_PROGRESS",
                                    "PROVIDER_UNAVAILABLE", "TASK_BUDGET_EXCEEDED"})),
    ("VERIFICATION_RESULT", frozenset({"BRAIN_REASSESSMENT", "TASK_COMPLETED",
                                       "TASK_BUDGET_EXCEEDED", "TASK_FAILED"})),
    ("BRAIN_REASSESSMENT", frozenset({"PLAN_VALIDATED", "EXECUTION_STARTED",
                                      "TASK_COMPLETED", "TASK_FAILED",
                                      "TASK_BUDGET_EXCEEDED"})),
    ("TASK_COMPLETED", frozenset()),   # terminal
    ("TASK_FAILED", frozenset()),      # terminal
    ("TASK_CANCELLED", frozenset()),    # terminal
    ("TASK_BUDGET_EXCEEDED", frozenset()),  # terminal
    ("PLAN_REJECTED", frozenset({"PLAN_CREATED", "TASK_FAILED", "TASK_CANCELLED"})),
    ("PLAN_BLOCKED", frozenset({"PLAN_CREATED", "BRAIN_REASSESSMENT", "TASK_FAILED",
                                "TASK_CANCELLED"})),
    ("DENIED", frozenset({"PLAN_CREATED", "TASK_FAILED", "TASK_CANCELLED"})),
    ("HUMAN_APPROVAL", frozenset({"PLAN_AUTHORIZED", "PLAN_CREATED", "TASK_CANCELLED"})),
    ("PROVIDER_UNAVAILABLE", frozenset({"BRAIN_REASSESSMENT", "PLAN_CREATED",
                                        "EXECUTION_STARTED", "TASK_FAILED",
                                        "TASK_CANCELLED"})),
])

_TERMINAL = {"TASK_COMPLETED", "TASK_FAILED", "TASK_CANCELLED",
             "TASK_BUDGET_EXCEEDED", "AWAITING_USER_INPUT"}


@dataclass
class ProtocolState:
    """Mutable phase register for a single task."""

    task_id: str
    phase: str = "INIT"
    iteration: int = 0  # number of PLAN cycles observed
    completed: bool = False

    def can_transition(self, next_event: str) -> bool:
        if self.phase in _TERMINAL:
            return False
        allowed = _PHASE_TRANSITIONS.get(self.phase, frozenset())
        return next_event in allowed


@dataclass
class ProtocolTransition:
    event: str
    from_phase: str
    to_phase: str
    budget: Optional[dict[str, Any]] = None
    provenance: dict[str, Any] = field(default_factory=dict)


class ProtocolViolationError(Exception):
    """An event arrived out of protocol order."""


class BrainControlProtocol:
    """Enforces the strict Brain↔Control Plane event protocol.

    The state machine is the *only* path by which execution may advance.  The
    orchestrator emits events through :meth:`emit`; an out-of-order or terminal
    event raises :class:`ProtocolViolationError`.
    """

    def __init__(self, task_id: str, budget: Optional[TaskBudget] = None,
                 audit: Optional[BrainAudit] = None):
        self.state = ProtocolState(task_id=task_id)
        self.budget = budget
        self.audit = audit or BrainAudit(task_id=task_id)

    # ------------------------------------------------------------------ #
    @property
    def phase(self) -> str:
        return self.state.phase

    @property
    def completed(self) -> bool:
        return self.state.completed

    def emit(self, event: EventType | str, *, detail: str = "",
             capability: str = "", success: Optional[bool] = None,
             cost: Optional[dict[str, Any]] = None,
             provenance: Optional[dict[str, Any]] = None) -> ProtocolTransition:
        """Emit a protocol event, advancing the phase register.

        Raises ProtocolViolationError if the event is out of order.
        Raises TaskBudgetExceeded if a budget check fires on a budgeted event.
        """
        ev_name = event.value if isinstance(event, EventType) else event
        # Map event -> target phase.
        target = _EVENT_TO_PHASE.get(ev_name, ev_name)

        if not self.state.can_transition(target):
            self.audit.record(EventType.__members__.get(
                ev_name, EventType.EXECUTION_PROGRESS),
                detail=f"REJECTED out-of-order {ev_name} from {self.state.phase}")
            raise ProtocolViolationError(
                f"event {ev_name!r} not allowed in phase {self.state.phase!r}"
            )

        from_phase = self.state.phase
        self.state.phase = target
        if target == "BRAIN_REASSESSMENT":
            self.state.iteration += 1
        if target in _TERMINAL:
            self.state.completed = True

        transition = ProtocolTransition(
            event=ev_name, from_phase=from_phase, to_phase=target,
            budget=self.budget.spent() if self.budget else None,
            provenance=provenance or {},
        )

        # Budget enforcement on the meaningful planning/execution cycles.
        # Match on the *target phase*, not the raw event name, so event aliases
        # (BRAIN_PLAN_VALIDATED -> PLAN_VALIDATED) route correctly.
        if self.budget is not None and target in (
            "PLAN_VALIDATED", "EXECUTION_STARTED", "BRAIN_REASSESSMENT",
        ):
            try:
                if target == "BRAIN_REASSESSMENT":
                    self.budget.note_replan()
                elif target == "PLAN_VALIDATED":
                    self.budget.begin_iteration()
                # EXECUTION_STARTED: nothing to count here beyond time/cost.
            except TaskBudgetExceeded as e:
                self.state.phase = "TASK_BUDGET_EXCEEDED"
                self.state.completed = True
                self.audit.record(EventType.BUDGET_EXCEEDED,
                                  detail=str(e))
                raise
        # Audit every protocol event (observability, §22).
        audit_ev = (
            EventType.TASK_COMPLETED if ev_name == "TASK_COMPLETED"
            else EventType.__members__.get(ev_name, EventType.EXECUTION_PROGRESS)
        )
        # Map a few protocol-only phases to the closest auditable event.
        audit_ev = _AUDIT_EVENT.get(ev_name, audit_ev)
        self.audit.record(
            audit_ev, detail=detail, capability=capability,
            success=success, cost=cost or {}, provenance=provenance or {},
        )
        return transition

    def assert_not_terminal(self) -> None:
        if self.state.phase in _TERMINAL:
            raise ProtocolViolationError(
                f"protocol is terminal ({self.state.phase}); no further events")

    def budget_spent(self) -> dict[str, Any]:
        return self.budget.spent() if self.budget else {}


# Maps an event name to the phase it transitions INTO.
_EVENT_TO_PHASE = {
    "BRAIN_PLAN_CREATED": "PLAN_CREATED",
    "BRAIN_PLAN_VALIDATED": "PLAN_VALIDATED",
    "PLAN_AUTHORIZED": "PLAN_AUTHORIZED",
    "EXECUTION_STARTED": "EXECUTION_STARTED",
    "EXECUTION_PROGRESS": "EXECUTION_PROGRESS",
    "EXECUTION_RESULT": "EXECUTION_RESULT",
    "VERIFICATION_RESULT": "VERIFICATION_RESULT",
    "BRAIN_REASSESSMENT": "BRAIN_REASSESSMENT",
    "TASK_COMPLETED": "TASK_COMPLETED",
    "TASK_FAILED": "TASK_FAILED",
    "TASK_CANCELLED": "TASK_CANCELLED",
    "TASK_BUDGET_EXCEEDED": "TASK_BUDGET_EXCEEDED",
    "PROVIDER_UNAVAILABLE": "PROVIDER_UNAVAILABLE",
    "PLAN_REJECTED": "PLAN_REJECTED",
    "PLAN_BLOCKED": "PLAN_BLOCKED",
    "DENIED": "DENIED",
    "HUMAN_APPROVAL": "HUMAN_APPROVAL",
    "QUESTION_ASKED": "AWAITING_USER_INPUT",
}

# AuditEvent closest mapping for protocol-only phases.
_AUDIT_EVENT = {
    "BRAIN_PLAN_CREATED": EventType.PLAN_CREATED,
    "BRAIN_PLAN_VALIDATED": EventType.PLAN_VALIDATED,
    "PLAN_AUTHORIZED": EventType.PLAN_AUTHORIZED,
    "EXECUTION_STARTED": EventType.EXECUTION_STARTED,
    "EXECUTION_PROGRESS": EventType.EXECUTION_PROGRESS,
    "EXECUTION_RESULT": EventType.EXECUTION_RESULT,
    "VERIFICATION_RESULT": EventType.VERIFICATION_RESULT,
    "BRAIN_REASSESSMENT": EventType.REASSESSMENT,
    "TASK_COMPLETED": EventType.TASK_COMPLETED,
    "TASK_FAILED": EventType.TASK_FAILED,
    "TASK_CANCELLED": EventType.TASK_CANCELLED,
    "TASK_BUDGET_EXCEEDED": EventType.BUDGET_EXCEEDED,
    "PROVIDER_UNAVAILABLE": EventType.PROVIDER_UNAVAILABLE,
    "PLAN_REJECTED": EventType.PLAN_CREATED,  # rejected plan reuses plan-created audit
    "PLAN_BLOCKED": EventType.REASSESSMENT,
    "DENIED": EventType.PLAN_CREATED,
    "HUMAN_APPROVAL": EventType.HUMAN_APPROVAL,
    "QUESTION_ASKED": EventType.QUESTION_ASKED,
    "BRAIN_REPLAN": EventType.REPLAN,
}


__all__ = ["BrainControlProtocol", "ProtocolState", "ProtocolTransition",
           "ProtocolViolationError", "EventType"]
