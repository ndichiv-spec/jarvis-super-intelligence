"""Phase 8 tests: no-fabrication audit (Phase 8 §39).

Asserts the Brain may never claim completion by fiat: completion is decided
solely by the control plane matching *real* tool evidence against the
brain's completion_conditions.  Confidence is always a qualitative enum
member, never a fabricated float.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from jarvis_brain.adapters import ModelBrainAdapter
from jarvis_brain.budget import TaskBudget
from jarvis_brain.contract import (
    BrainInput, BrainOutput, ConfidenceState, ExecutionMode, AutonomyLevel,
    CompletionCondition, validate_brain_output, safe_parse_brain_json,
)
from jarvis_brain.orchestrator import BrainOrchestrator
from jarvis_brain.plan_validator import PlanValidator
from research_engine.capability_tools import build_capability_registry
from research_engine.models import ToolResult

pytestmark = pytest.mark.brain


@pytest.fixture
def registry():
    return build_capability_registry()


@pytest.fixture
def validator(registry):
    return PlanValidator(registry)


def _fake_brain_output(cap, args, cond_type):
    from jarvis_brain.contract import BrainIntent, Plan, PlanStep, CapabilityRequest
    return BrainOutput(
        intent=BrainIntent(domain="g", task="t",
                           confidence=ConfidenceState.SUFFICIENT_INFORMATION),
        plan=Plan(summary="p", steps=[PlanStep(id="s1", capability=cap,
                                               summary="s", args=args)]),
        capability_requests=[CapabilityRequest(capability=cap, args=args,
                                               reason="x")],
        questions_for_user=[],
        completion_conditions=[CompletionCondition(type=cond_type, target="t",
                                                    expected=True)],
        confidence_state=ConfidenceState.SUFFICIENT_INFORMATION,
        summary="p",
    )


# ---------------------------------------------------------------------------
# Confidence is always qualitative, never a fabricated float.
# ---------------------------------------------------------------------------
def test_brain_output_confidence_is_enum_not_float():
    """The contract must reject a fabricated float confidence."""
    bogus = {
        "intent": {"domain": "g", "task": "t", "confidence_state": "HIGH"},
        "plan": {"summary": "p", "steps": []},
        "capability_requests": [],
        "questions_for_user": [],
        "completion_conditions": [],
        "confidence_state": 0.97,  # fabricated probability — must be rejected
        "model_ref": "x",
        "summary": "p",
    }
    with pytest.raises(Exception):
        validate_brain_output(bogus)


def test_brain_output_accepts_every_qualitative_state():
    for cs in ConfidenceState:
        d = {
            "intent": {"domain": "g", "task": "t", "confidence_state": cs.value},
            "plan": {"summary": "p", "steps": []},
            "capability_requests": [],
            "questions_for_user": [],
            "completion_conditions": [],
            "confidence_state": cs.value,
            "model_ref": "x",
            "summary": "p",
        }
        out = validate_brain_output(d)
        assert out.confidence_state == cs


# ---------------------------------------------------------------------------
# Model prose / stub content is rejected, never parsed into a plan.
# ---------------------------------------------------------------------------
def test_safe_parse_rejects_prose():
    out = safe_parse_brain_json("Hello here is my plan and a conclusion")
    assert out is None


def test_model_adapter_rejects_stub_content(monkeypatch):
    monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://127.0.0.1:8099")
    monkeypatch.setenv("JARVIS_BRAIN_BACKEND", "stub")

    class _Client:
        def chat(self, messages, timeout=60):
            class R:
                content = "[brain-stub] i have no real opinions"
                usage = None
            return R()

    # Force reachable=True so the chat path is taken (stub content rejected).
    a = ModelBrainAdapter(_Client())
    a.availability.available = True
    a.availability.stub = False
    a.availability.production_health = True
    bi = BrainInput(request="hi", context={}, available_capabilities=[],
                    execution_mode=ExecutionMode.ONLINE.value, user_id="u",
                    autonomy=AutonomyLevel.AUTONOMOUS.value, budget=TaskBudget())
    out = asyncio.run(a.propose(bi, TaskBudget()))
    assert out.capability_requests == []
    assert out.confidence_state in (ConfidenceState.ASK_USER,
                                    ConfidenceState.INSUFFICIENT_EVIDENCE)


def test_model_adapter_awaits_async_brain_client(monkeypatch):
    monkeypatch.setenv("JARVIS_BRAIN_ENDPOINT", "http://127.0.0.1:8099")
    monkeypatch.setenv("JARVIS_BRAIN_BACKEND", "remote")
    expected = _fake_brain_output(
        "static_search", {"query": "latest runtime"}, "evidence_sufficient"
    )

    class _Client:
        called = False
        messages = None

        async def chat(self, messages, timeout=60):
            self.called = True
            self.messages = messages

            class R:
                content = json.dumps(expected.to_dict())
                usage = None

            return R()

    client = _Client()
    adapter = ModelBrainAdapter(client)
    adapter.availability.available = True
    adapter.availability.stub = False
    adapter.availability.production_health = True
    brain_input = BrainInput(
        request="research latest runtime, API_KEY=sk-sensitive-test-value",
        context={},
        available_capabilities=[],
        execution_mode=ExecutionMode.ONLINE.value,
        user_id="u",
        autonomy=AutonomyLevel.AUTONOMOUS.value,
        budget=TaskBudget(),
    )

    output = asyncio.run(adapter.propose(brain_input, TaskBudget()))

    assert client.called
    assert "sk-sensitive-test-value" not in json.dumps(client.messages)
    assert "[REDACTED:credential]" in json.dumps(client.messages)
    assert output.capability_requests[0].capability == "static_search"
    assert output.provenance["adapter"] == "ModelBrainAdapter"


# ---------------------------------------------------------------------------
# Completion is evidence-gated: an unknown/claimed condition cannot complete.
# ---------------------------------------------------------------------------
def test_unknown_completion_condition_cannot_complete(registry, validator, monkeypatch):
    """Brain claims an arbitrary condition type -> not matched -> no COMPLETED."""
    class _Brain:
        async def propose(self, brain_input, budget):
            return _fake_brain_output("static_search", {"query": "x"},
                                      "i_will_be_done_now")

    async def ok_invoke(name, args, ctx):
        return ToolResult(tool_id="t", name=name, success=True,
                          result="the sky is blue", duration_ms=2.0)

    registry.invoke = ok_invoke
    budget = TaskBudget(max_replans=0, max_retries=1, max_plan_iterations=2)
    orch = BrainOrchestrator(_Brain(), registry, validator, budget=budget)
    res = orch.run_sync("look up sky color")
    # An unrecognized completion-condition type is never satisfied by the
    # control plane, so the task must NOT self-close as COMPLETED.
    assert res.status != "COMPLETED"
    assert res.status in ("FAILED", "BUDGET_EXCEEDED")


def test_empty_completion_conditions_never_complete(registry, validator, monkeypatch):
    """Brain with zero completion_conditions -> control plane never completes."""
    class _Brain:
        async def propose(self, brain_input, budget):
            from jarvis_brain.contract import (BrainIntent, BrainOutput, Plan,
                                               PlanStep, CapabilityRequest)
            return BrainOutput(
                intent=BrainIntent(domain="g", task="t",
                                   confidence=ConfidenceState.SUFFICIENT_INFORMATION),
                plan=Plan(summary="p", steps=[PlanStep(id="s1",
                                                       capability="static_search",
                                                       summary="s", args={"query": "x"})]),
                capability_requests=[CapabilityRequest(capability="static_search",
                                                       args={"query": "x"}, reason="x")],
                questions_for_user=[],
                completion_conditions=[],  # brain omits completion -> no auto-done
                confidence_state=ConfidenceState.SUFFICIENT_INFORMATION,
                summary="p",
            )

    async def ok_invoke(name, args, ctx):
        return ToolResult(tool_id="t", name=name, success=True,
                          result="the sky is blue", duration_ms=2.0)

    registry.invoke = ok_invoke
    budget = TaskBudget(max_replans=0, max_retries=1)
    orch = BrainOrchestrator(_Brain(), registry, validator, budget=budget)
    res = orch.run_sync("look up sky color")
    # No completion_condition is ever matched -> cannot self-declare done.
    assert res.status != "COMPLETED"


def test_confidence_state_never_fabricated_float_in_evidence(registry, validator, monkeypatch):
    """Even on success, the orchestrator reports a qualitative state, not a float."""
    class _Brain:
        async def propose(self, brain_input, budget):
            return _fake_brain_output("static_search", {"query": "color of the sky"},
                                      "answer_generated")

    registry.invoke = _ok_static()
    budget = TaskBudget()
    orch = BrainOrchestrator(_Brain(), registry, validator, budget=budget)
    res = orch.run_sync("look up sky color")
    assert res.confidence_state in {
        ConfidenceState.SUFFICIENT_INFORMATION,
        ConfidenceState.INSUFFICIENT_EVIDENCE,
        ConfidenceState.ASK_USER,
        ConfidenceState.CONFLICTING_EVIDENCE,
    }
    assert res.status == "COMPLETED"


def _ok_static():
    async def _r(name, args, ctx):
        from research_engine.models import ToolResult
        return ToolResult(tool_id="t", name=name, success=True,
                          result="the sky is blue", duration_ms=2.0)
    return _r
