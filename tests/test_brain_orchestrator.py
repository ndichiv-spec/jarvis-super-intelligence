"""Phase 8 tests: BrainOrchestrator controlled loop (Phase 8 §5-6, §28-30).

These run the FULL orchestrator against the REAL capability registry with a
small fake brain adapter, asserting the spec invariants:
  * plans only execute after schema+capability+mode validation,
  * destructive caps require approval (never execute autonomously without a gate),
  * completion is decided by EVIDENCE, never by the model saying "done",
  * replanning is BOUNDED (no infinite loops),
  * a Brain that cannot proceed degrades honestly (ASK_USER, never fabricates),
  * cancel yields CANCELLED.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from jarvis_brain.adapters import DeterministicBrainAdapter
from jarvis_brain.audit import EventType
from jarvis_brain.budget import TaskBudget
from jarvis_brain.contract import (
    AutonomyLevel, BrainInput, BrainIntent, BrainOutput, CapabilityRequest,
    CompletionCondition, ConfidenceState, ExecutionMode, Plan, PlanStep,
)
from jarvis_brain.orchestrator import BrainOrchestrator
from jarvis_brain.plan_validator import PlanValidator
from research_engine.capability_tools import build_capability_registry

pytestmark = pytest.mark.brain


# ---------------------------------------------------------------------------
# Fake brain adapters
# ---------------------------------------------------------------------------
class _FakeBrain:
    """Returns a canned BrainOutput. ``plan_fn(output)`` can mutate it."""

    def __init__(self, output, *, plan_fn=None):
        self.output = output
        self.plan_fn = plan_fn or (lambda o: o)
        self.calls = 0

    async def propose(self, brain_input: BrainInput, budget) -> BrainOutput:
        self.calls += 1
        out = self.plan_fn(self.output)
        return out


def _make_output(cap="static_search", args=None, cond="evidence_sufficient",
                 conf=ConfidenceState.SUFFICIENT_INFORMATION, summary="lookup color"):
    args = args if args is not None else {"query": "color of the sky"}
    return BrainOutput(
        intent=BrainIntent(domain="general", task=summary,
                           confidence=conf),
        plan=Plan(summary=summary, steps=[PlanStep(id="s1", capability=cap,
                                                   summary="evidence step", args=args)]),
        capability_requests=[CapabilityRequest(capability=cap, args=args, reason="x")],
        questions_for_user=[],
        completion_conditions=[CompletionCondition(type=cond, target="color", expected=True)],
        confidence_state=conf,
        model_ref="fake-brain",
        provenance={"adapter": "fake"},
        summary=summary,
    )


@pytest.fixture(scope="module")
def registry():
    return build_capability_registry()


@pytest.fixture
def validator(registry):
    return PlanValidator(registry)


def _orch(brain, registry, validator, **kw):
    return BrainOrchestrator(brain, registry, validator, **kw)


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------
def test_success_path_completes_on_evidence(registry, validator):
    brain = _FakeBrain(_make_output("static_search",
                                    cond="evidence_sufficient"))
    orch = _orch(brain, registry, validator)
    res = orch.run_sync("look up the color of the sky")
    assert res.status == "COMPLETED"
    assert res.confidence_state == ConfidenceState.SUFFICIENT_INFORMATION
    assert res.completion_condition_met == "evidence_sufficient"
    # Exactly one terminal audit event.
    terminal = [e for e in res.audit if e["event"] in
                (EventType.TASK_COMPLETED.value, EventType.TASK_FAILED.value,
                 EventType.TASK_CANCELLED.value, EventType.BUDGET_EXCEEDED.value)]
    assert len(terminal) == 1
    assert terminal[0]["event"] == EventType.TASK_COMPLETED.value


# ---------------------------------------------------------------------------
# Validation gate: nonexistent cap -> FAILED before any execution
# ---------------------------------------------------------------------------
def test_bad_capability_rejected_no_execution(registry, validator):
    brain = _FakeBrain(_make_output("does.not.exist"))
    orch = _orch(brain, registry, validator)
    res = orch.run_sync("do the thing")
    assert res.status == "FAILED"
    assert res.confidence_state == ConfidenceState.ASK_USER
    # EXECUTION_STARTED must NEVER appear when the plan was invalid.
    assert not any(e["event"] == EventType.EXECUTION_STARTED.value for e in res.audit)


# ---------------------------------------------------------------------------
# Destructive capability: HUMAN_APPROVAL path, not auto-executed
# ---------------------------------------------------------------------------
def test_destructive_capability_requires_approval(registry, validator):
    brain = _FakeBrain(_make_output("sandbox_run", args={"code": "print(1)"}))
    orch = _orch(brain, registry, validator)  # no approval_gate
    res = orch.run_sync("run code", autonomy=AutonomyLevel.AUTONOMOUS.value)
    assert res.status == "FAILED"
    assert res.confidence_state == ConfidenceState.ASK_USER
    # The destructive tool must never be invoked.
    assert brain.calls == 1  # only the initial propose
    assert not any(e["event"] == EventType.EXECUTION_STARTED.value for e in res.audit)


def test_approval_gate_unblocks_when_approved(registry, validator):
    brain = _FakeBrain(_make_output("sandbox_run", args={"code": "print(1)"}))
    gate = lambda ids, aut: True
    orch = _orch(brain, registry, validator, approval_gate=gate)
    res = orch.run_sync("run code", autonomy=AutonomyLevel.AUTONOMOUS.value)
    # With approval granted AND sandbox_run succeeding, evidence_sufficient → COMPLETED.
    assert res.status == "COMPLETED"


def test_async_approval_gate_and_audit_callback(registry, validator):
    brain = _FakeBrain(_make_output("sandbox_run", args={"code": "print(1)"}))
    events = []

    async def approve(request, autonomy):
        assert request["capabilities"] == ["sandbox_run"]
        assert autonomy == AutonomyLevel.AUTONOMOUS.value
        return True

    orchestrator = _orch(
        brain,
        registry,
        validator,
        approval_gate=approve,
        audit_callback=lambda event: events.append(event.event),
    )
    result = asyncio.run(orchestrator.run(
        "run a safe code snippet",
        autonomy=AutonomyLevel.AUTONOMOUS.value,
    ))

    assert result.status == "COMPLETED"
    assert "HUMAN_APPROVAL" in events
    assert "BRAIN_PLAN_PROPOSED" in events
    assert "CAPABILITY_STARTED" in events
    assert "CAPABILITY_COMPLETED" in events


# ---------------------------------------------------------------------------
# Empty / cannot-proceed proposal -> honest ASK_USER, never fabricate
# ---------------------------------------------------------------------------
def test_empty_proposal_degrades_to_ask_user(registry, validator):
    empty = BrainOutput(
        intent=BrainIntent(domain="ONLINE", task="t",
                           confidence=ConfidenceState.ASK_USER),
        plan=Plan(summary="nothing"),
        capability_requests=[], questions_for_user=["?"],
        completion_conditions=[],
        confidence_state=ConfidenceState.ASK_USER,
        summary="I need a clarification",
    )
    brain = _FakeBrain(empty)
    orch = _orch(brain, registry, validator)
    res = orch.run_sync("some vague thing")
    assert res.status == "FAILED"
    assert res.confidence_state == ConfidenceState.ASK_USER
    assert orch_run_audit_has(res, EventType.QUESTION_ASKED.value)


def orch_run_audit_has(res, event_name):
    return any(e["event"] == event_name for e in res.audit)


# ---------------------------------------------------------------------------
# Bounded replanning: unsatisfiable condition + max_replans=0 -> FAILED, no loop
# ---------------------------------------------------------------------------
def test_replan_exhaustion_terminates(registry, validator):
    # static_search succeeds, but completion condition is "tests_passed" which a
    # successful search result will NOT satisfy -> replan requested.
    brain = _FakeBrain(_make_output("static_search", cond="tests_passed"))
    # max_replans=0 -> exhausted immediately -> single terminal event.
    budget = TaskBudget(max_replans=0, max_plan_iterations=5, max_retries=1,
                        max_cost=100.0, max_execution_time=60.0)
    orch = _orch(brain, registry, validator, budget=budget)
    res = orch.run_sync("lookup")
    assert res.status == "FAILED"
    assert res.confidence_state == ConfidenceState.CONFLICTING_EVIDENCE
    terminal = [e for e in res.audit if e["event"] in
                (EventType.TASK_COMPLETED.value, EventType.TASK_FAILED.value,
                 EventType.TASK_CANCELLED.value, EventType.BUDGET_EXCEEDED.value)]
    assert len(terminal) == 1


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------
def test_cancel_token_yields_cancelled(registry, validator):
    brain = _FakeBrain(_make_output("static_search", cond="evidence_sufficient"))
    token = asyncio.Event()
    token.set()  # pre-set -> interrupt before any step executes
    orch = _orch(brain, registry, validator, cancel_token=token)
    res = orch.run_sync("lookup color")
    assert res.status == "CANCELLED"
    assert orch_run_audit_has(res, EventType.TASK_CANCELLED.value)


# ---------------------------------------------------------------------------
# Conversation linkage
# ---------------------------------------------------------------------------
def test_conversation_id_linked_into_audit(registry, validator):
    brain = _FakeBrain(_make_output("static_search", cond="evidence_sufficient"))
    orch = _orch(brain, registry, validator, conversation_id="conv-123")
    assert orch.conversation_id == "conv-123"
    res = orch.run_sync("lookup color")
    assert res.status == "COMPLETED"
    linked = [e for e in res.audit
              if e.get("provenance", {}).get("conversation_id") == "conv-123"]
    assert linked


# ---------------------------------------------------------------------------
# Offline path: DeterministicBrainAdapter never claims completion
# ---------------------------------------------------------------------------
def test_deterministic_adapter_never_declares_completion():
    # Force honest offline brain availability (no endpoint configured).
    import os
    import contextlib
    keys = ["JARVIS_BRAIN_ENDPOINT", "JARVIS_BRAIN_BACKEND"]
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        adapter = DeterministicBrainAdapter(offline_mode=True)
        bi = BrainInput(
            request="what can you do",
            context={"environment": {"brain": "OFFLINE"}},
            available_capabilities=[],
            execution_mode=ExecutionMode.OFFLINE.value,
            user_id="anon", autonomy=AutonomyLevel.AUTONOMOUS.value, budget=TaskBudget(),
        )
        out = asyncio.run(adapter.propose(bi, TaskBudget()))
        # Offline adapter is honest: INSUFFICIENT_EVIDENCE, never a "done" claim.
        assert out.confidence_state == ConfidenceState.INSUFFICIENT_EVIDENCE
        assert out.provenance.get("offline") is True
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
