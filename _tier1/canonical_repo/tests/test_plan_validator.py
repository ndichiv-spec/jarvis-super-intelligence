"""Phase 8 tests: Plan Validation pipeline (Phase 8 §4).

Exercises all six stages of :class:`PlanValidator` against the REAL capability
catalogue (build_capability_registry) so availability/risk/permissions/offline
flags are the genuine, environment-honest values.
"""
from __future__ import annotations

import pytest

from jarvis_brain.contract import (
    BrainOutput, BrainIntent, Plan, PlanStep, CapabilityRequest,
    CompletionCondition, ConfidenceState, ExecutionMode, AutonomyLevel, PlanDecision,
)
from jarvis_brain.plan_validator import PlanValidator
from research_engine.capability_tools import build_capability_registry

pytestmark = pytest.mark.brain


# Schema-correct argument shapes for the real capabilities used below.
_ARGS = {
    "static_search": {"query": "x"},
    "search_web": {"query": "x"},
    "sandbox_run": {"code": "print(1)"},
    "model_consult": {"question": "hi", "provider": "auto"},
    "files.read": {"path": "README.md"},
    "github.inspect": {"repo": "org/repo"},
}


def _out(cap, cond="evidence_sufficient"):
    args = _ARGS.get(cap, {})
    return BrainOutput(
        intent=BrainIntent(domain="general", task="t",
                           confidence=ConfidenceState.SUFFICIENT_INFORMATION),
        plan=Plan(summary="p", steps=[PlanStep(id="s1", capability=cap,
                                               summary="s", args=args)]),
        capability_requests=[CapabilityRequest(capability=cap, args=args, reason="x")],
        completion_conditions=[CompletionCondition(type=cond)],
        confidence_state=ConfidenceState.SUFFICIENT_INFORMATION,
    )


@pytest.fixture(scope="module")
def validator():
    return PlanValidator(build_capability_registry())


# ---- Stage 1: schema --------------------------------------------------------
def test_malformed_output_is_plan_rejected(validator):
    res = validator.validate({"not": "a brain output"})
    assert res.decision == PlanDecision.PLAN_REJECTED
    assert res.authorized_capabilities == []


# ---- Stage 2: capability existence (spec §4: nonexistent -> REJECTED) --------
def test_nonexistent_capability_rejected(validator):
    res = validator.validate(_out("does.not.exist").to_dict(), user_id="alice")
    assert res.decision == PlanDecision.PLAN_REJECTED


# ---- Stage 2b: availability (spec §4: unavailable -> PLAN_BLOCKED) ---------
# github is NOT_CONFIGURED in this env (no token) -> blocked, not fabricated.
def test_not_configured_capability_blocked(validator):
    res = validator.validate(_out("github.inspect").to_dict(), user_id="alice")
    assert res.decision == PlanDecision.PLAN_BLOCKED
    assert "github.inspect" in res.denied_capabilities


# ---- Stage 3: input/output compatibility -----------------------------------
def test_missing_required_arg_rejected(validator):
    bo = _out("static_search")
    bo.capability_requests[0].args = {}  # query is required
    res = validator.validate(bo.to_dict(), user_id="alice")
    assert res.decision == PlanDecision.PLAN_REJECTED


def test_wrong_arg_type_rejected(validator):
    bo = _out("static_search")
    bo.capability_requests[0].args = {"query": 12345}
    res = validator.validate(bo.to_dict(), user_id="alice")
    assert res.decision == PlanDecision.PLAN_REJECTED


# ---- Stage 5/6: risk + execution-mode compatibility ------------------------
def test_destructive_capability_needs_human_approval(validator):
    # sandbox_run is destructive -> HUMAN_APPROVAL even in AUTONOMOUS.
    res = validator.validate(_out("sandbox_run").to_dict(), user_id="alice",
                             permissions={"sandbox:execute"},
                             autonomy=AutonomyLevel.AUTONOMOUS.value)
    assert res.decision == PlanDecision.HUMAN_APPROVAL
    assert "sandbox_run" in res.needs_approval_for


def test_network_capability_needs_confirmation(validator, monkeypatch):
    # search_web is network + confirmation-gated -> HUMAN_APPROVAL.
    # The intent of this test is policy, so isolate availability separately.
    from research_engine import capability_tools

    monkeypatch.setattr(
        capability_tools,
        "capability_inventory",
        lambda: {"search_web": {"state": "AVAILABLE"}},
    )
    res = validator.validate(_out("search_web").to_dict(), user_id="alice",
                             autonomy=AutonomyLevel.AUTONOMOUS.value)
    assert res.decision == PlanDecision.HUMAN_APPROVAL
    assert "search_web" in res.needs_approval_for


def test_offline_mode_blocks_non_offline_cap(validator):
    # sandbox_run is exec + not supports_offline -> PLAN_BLOCKED in OFFLINE.
    res = validator.validate(_out("sandbox_run").to_dict(), user_id="alice",
                             permissions={"sandbox:execute"},
                             execution_mode=ExecutionMode.OFFLINE.value,
                             autonomy=AutonomyLevel.AUTONOMOUS.value)
    assert res.decision == PlanDecision.PLAN_BLOCKED
    assert "sandbox_run" in res.denied_capabilities


def test_offline_read_cap_accepted_offline(validator):
    res = validator.validate(_out("static_search").to_dict(), user_id="alice",
                             execution_mode=ExecutionMode.OFFLINE.value)
    assert res.decision == PlanDecision.ACCEPTED
    assert "static_search" in res.authorized_capabilities


def test_read_capability_accepted_autonomous(validator):
    res = validator.validate(_out("files.read").to_dict(), user_id="alice")
    assert res.decision == PlanDecision.ACCEPTED
    assert "files.read" in res.authorized_capabilities


# ---- Stage 7: dependency validation ----------------------------------------
def test_dependency_on_unknown_step_rejected(validator):
    bo = _out("static_search")
    bo.capability_requests[0].depends_on = ["nope"]
    res = validator.validate(bo.to_dict(), user_id="alice")
    assert res.decision == PlanDecision.PLAN_REJECTED
    assert any(i.severity == "reject" and i.stage == "dependency" for i in res.issues)


def test_duplicate_capability_requests_rejected(validator):
    bo = _out("static_search")
    bo.capability_requests.append(
        CapabilityRequest(capability="static_search", args={"query": "y"}, reason="dup"))
    bo.plan.steps.append(PlanStep(id="s2", capability="static_search", summary="s",
                                  args={"query": "y"}))
    res = validator.validate(bo.to_dict(), user_id="alice")
    assert res.decision == PlanDecision.PLAN_REJECTED
    assert any("duplicate" in i.message.lower() for i in res.issues)
