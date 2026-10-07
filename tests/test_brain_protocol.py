"""Phase 8 tests: Brain ↔ Control Plane protocol state machine (Phase 8 §5)."""
from __future__ import annotations

import pytest

from jarvis_brain.audit import BrainAudit, EventType
from jarvis_brain.budget import TaskBudget
from jarvis_brain.protocol import (
    BrainControlProtocol, ProtocolViolationError, ProtocolState,
)

pytestmark = pytest.mark.brain


def _p(budget=None):
    return BrainControlProtocol("task-1", budget=budget or TaskBudget())


# ---- valid full happy path --------------------------------------------------
def test_full_protocol_sequence():
    proto = _p()
    for ev in (EventType.PLAN_CREATED, EventType.PLAN_VALIDATED,
               EventType.PLAN_AUTHORIZED, EventType.EXECUTION_STARTED,
               EventType.EXECUTION_RESULT, EventType.VERIFICATION_RESULT,
               EventType.TASK_COMPLETED):
        proto.emit(ev, detail="ok")
    assert proto.completed
    assert proto.phase == "TASK_COMPLETED"


# ---- out-of-order events are rejected --------------------------------------
def test_cannot_complete_before_execute():
    proto = _p()
    proto.emit(EventType.PLAN_CREATED)
    proto.emit(EventType.PLAN_VALIDATED)
    proto.emit(EventType.PLAN_AUTHORIZED)
    with pytest.raises(ProtocolViolationError):
        proto.emit(EventType.TASK_COMPLETED)  # jumped the execution phases


def test_cannot_re_emit_terminal():
    proto = _p()
    proto.emit(EventType.PLAN_CREATED)
    proto.emit(EventType.PLAN_VALIDATED)
    proto.emit(EventType.PLAN_AUTHORIZED)
    proto.emit(EventType.EXECUTION_STARTED)
    proto.emit(EventType.EXECUTION_RESULT)
    proto.emit(EventType.VERIFICATION_RESULT)
    proto.emit(EventType.TASK_COMPLETED)
    assert proto.completed
    with pytest.raises(ProtocolViolationError):
        proto.emit(EventType.PLAN_CREATED)


def test_cannot_start_execution_without_authorization():
    proto = _p()
    proto.emit(EventType.PLAN_CREATED)
    proto.emit(EventType.PLAN_VALIDATED)
    # Skip PLAN_AUTHORIZED
    with pytest.raises(ProtocolViolationError):
        proto.emit(EventType.EXECUTION_STARTED)


# ---- replan loop: EXECUTION_RESULT -> REASSESSMENT -> PLN/EXEC is allowed ---
def test_reassessment_returns_to_execution():
    proto = _p()
    proto.emit(EventType.PLAN_CREATED)
    proto.emit(EventType.PLAN_VALIDATED)
    proto.emit(EventType.PLAN_AUTHORIZED)
    proto.emit(EventType.EXECUTION_STARTED)
    proto.emit(EventType.EXECUTION_RESULT)
    proto.emit(EventType.REASSESSMENT)      # replan phase
    proto.emit(EventType.PLAN_VALIDATED)   # validated a new plan
    proto.emit(EventType.PLAN_AUTHORIZED)
    proto.emit(EventType.EXECUTION_STARTED)
    proto.emit(EventType.EXECUTION_RESULT)
    proto.emit(EventType.VERIFICATION_RESULT)
    proto.emit(EventType.TASK_COMPLETED)
    assert proto.completed


# ---- budget integration: reassessment enforces max_replans -----------------
def test_reassessment_enforces_max_replans():
    proto = _p(TaskBudget(max_replans=1, max_plan_iterations=10))
    proto.emit(EventType.PLAN_CREATED)
    proto.emit(EventType.PLAN_VALIDATED)
    proto.emit(EventType.PLAN_AUTHORIZED)
    proto.emit(EventType.EXECUTION_STARTED)
    proto.emit(EventType.EXECUTION_RESULT)
    proto.emit(EventType.REASSESSMENT)
    proto.emit(EventType.PLAN_VALIDATED)
    proto.emit(EventType.PLAN_AUTHORIZED)
    proto.emit(EventType.EXECUTION_STARTED)
    proto.emit(EventType.EXECUTION_RESULT)
    # replan 2 should exhaust the budget -> budget exceeded, terminal
    with pytest.raises(Exception):
        proto.emit(EventType.REASSESSMENT)
    assert proto.phase == "TASK_BUDGET_EXCEEDED"


def test_plan_validated_enforces_max_iterations():
    proto = _p(TaskBudget(max_plan_iterations=1))
    proto.emit(EventType.PLAN_CREATED)
    proto.emit(EventType.PLAN_VALIDATED)  # iteration 1
    proto.emit(EventType.PLAN_AUTHORIZED)
    proto.emit(EventType.EXECUTION_STARTED)
    proto.emit(EventType.EXECUTION_RESULT)
    proto.emit(EventType.REASSESSMENT)
    with pytest.raises(Exception):
        proto.emit(EventType.PLAN_VALIDATED)  # iteration 2 > 1
    assert proto.phase == "TASK_BUDGET_EXCEEDED"


# ---- audit linkage ----------------------------------------------------------
def test_protocol_records_all_events_in_audit():
    proto = _p()
    proto.emit(EventType.PLAN_CREATED, detail="d1", capability="static_search")
    proto.emit(EventType.PLAN_VALIDATED)
    proto.emit(EventType.PLAN_AUTHORIZED)
    proto.emit(EventType.EXECUTION_STARTED)
    proto.emit(EventType.EXECUTION_RESULT, detail="d2", capability="static_search",
               success=True)
    assert proto.audit.has_event(EventType.PLAN_CREATED)
    assert proto.audit.has_event(EventType.EXECUTION_RESULT)
    res_events = proto.audit.events_for("static_search")
    assert any(e.success is True for e in res_events)
