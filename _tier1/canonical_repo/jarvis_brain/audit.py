"""Brain observability: audit events, cost/usage accounting, user-facing
explanation (Phase 8 §22-24).

All events are *descriptive* — they record what happened, with provenance, and
explicitly never echo secrets (results arriving here have already passed
through :func:`research_engine.tool_registry.scrub_secrets`).  The
user-facing surface exposes only ``summary`` + ``confidence_state`` and an
optional, scrubbed evidence digest — never a chain-of-thought dump.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .contract import ConfidenceState


class EventType(str, Enum):
    """Observable events on the Brain↔Control Plane protocol timeline."""

    PLAN_CREATED = "BRAIN_PLAN_CREATED"
    PLAN_VALIDATED = "BRAIN_PLAN_VALIDATED"
    PLAN_AUTHORIZED = "PLAN_AUTHORIZED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_PROGRESS = "EXECUTION_PROGRESS"
    EXECUTION_RESULT = "EXECUTION_RESULT"
    VERIFICATION_RESULT = "VERIFICATION_RESULT"
    REASSESSMENT = "BRAIN_REASSESSMENT"
    REPLAN = "BRAIN_REPLAN"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    BUDGET_EXCEEDED = "TASK_BUDGET_EXCEEDED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    QUESTION_ASKED = "QUESTION_ASKED"
    DEGRADED = "BRAIN_DEGRADED"
    OFFLINE = "BRAIN_OFFLINE"


@dataclass
class AuditEvent:
    at: str
    event: str
    detail: str = ""
    task_id: str = ""
    capability: str = ""
    success: Optional[bool] = None
    cost: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "event": self.event,
            "detail": self.detail,
            "task_id": self.task_id,
            "capability": self.capability,
            "success": self.success,
            "cost": dict(self.cost),
            "provenance": dict(self.provenance),
        }


@dataclass
class BrainAudit:
    """Append-only, in-memory audit log for a single task run.

    In production this is the source for the observability surface; tests use
    it to assert the controlled loop behaved correctly.
    """

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    events: list[AuditEvent] = field(default_factory=list)
    _spend: dict[str, float] = field(default_factory=dict)
    on_record: Optional[Callable[[AuditEvent], None]] = field(
        default=None, repr=False, compare=False
    )

    def record(
        self,
        event: EventType | str,
        *,
        detail: str = "",
        capability: str = "",
        success: Optional[bool] = None,
        cost: Optional[dict[str, Any]] = None,
        provenance: Optional[dict[str, Any]] = None,
        at: Optional[str] = None,
    ) -> AuditEvent:
        ev = AuditEvent(
            at=at or _now_iso(),
            event=event if isinstance(event, str) else event.value,
            detail=detail,
            task_id=self.task_id,
            capability=capability,
            success=success,
            cost=dict(cost or {}),
            provenance=dict(provenance or {}),
        )
        self.events.append(ev)
        if self.on_record is not None:
            self.on_record(ev)
        return ev

    def add_spend(self, **units: float) -> None:
        for k, v in units.items():
            self._spend[k] = self._spend.get(k, 0.0) + v

    def total_cost(self) -> dict[str, float]:
        return dict(self._spend)

    def has_event(self, event: EventType | str) -> bool:
        name = event if isinstance(event, str) else event.value
        return any(e.event == name for e in self.events)

    def events_for(self, capability: str) -> list[AuditEvent]:
        return [e for e in self.events if e.capability == capability]

    def timeline(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]

    def explanation(self, confidence: ConfidenceState) -> str:
        """Build the honest, user-facing summary (Phase 8 §24 — no CoT).

        Only surfaces high-level provenance + the confidence qualifier. Chain
        of thought / internal reasoning never leaves the control plane.
        """
        n_tools = sum(1 for e in self.events if e.event == EventType.EXECUTION_RESULT and e.success)
        n_fail = sum(1 for e in self.events if e.event == EventType.EXECUTION_RESULT and e.success is False)
        return (
            f"Task {_safe_task(self.task_id)}: "
            f"{'completed' if self.has_event(EventType.TASK_COMPLETED) else 'in progress'} "
            f"({n_tools} capability call(s) succeeded, {n_fail} failed). "
            f"Confidence: {confidence.value}."
        )


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_task(tid: str) -> str:
    return tid or "—"


__all__ = ["EventType", "AuditEvent", "BrainAudit"]
