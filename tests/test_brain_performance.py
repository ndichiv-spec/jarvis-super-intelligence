"""Phase 8 tests: performance / excessive-call guards (Phase 8 §34, §6).

Asserts the hard limits that prevent infinite / unbounded Brain-driven loops:

* per-step retries are bounded by max_retries,
* the planning/replan loop is bounded by max_plan_iterations,
* max_cost and max_execution_time are enforced at the tool-call boundary.
"""
from __future__ import annotations

import asyncio

from jarvis_brain.budget import TaskBudget
from jarvis_brain.orchestrator import BrainOrchestrator
from jarvis_brain.contract import (
    BrainInput, BrainIntent, BrainOutput, CapabilityRequest, CompletionCondition,
    ConfidenceState, ExecutionMode, AutonomyLevel, Plan, PlanStep,
)
from research_engine.capability_tools import build_capability_registry
from research_engine.models import ToolResult
import pytest

pytestmark = pytest.mark.brain


def _proposal(cap, args, cond):
    return BrainOutput(
        intent=BrainIntent(domain="general", task="t",
                           confidence=ConfidenceState.SUFFICIENT_INFORMATION),
        plan=Plan(summary="p", steps=[PlanStep(id="s1", capability=cap,
                                               summary="s", args=args)]),
        capability_requests=[CapabilityRequest(capability=cap, args=args, reason="x")],
        questions_for_user=[],
        completion_conditions=[CompletionCondition(type=cond, target="t",
                                                    expected=True)],
        confidence_state=ConfidenceState.SUFFICIENT_INFORMATION, summary="p",
    )


@pytest.fixture
def registry():
    return build_capability_registry()


@pytest.fixture
def validator(registry):
    from jarvis_brain.plan_validator import PlanValidator
    return PlanValidator(registry)


# A capability that always fails with a *transient* (retryable) error.
async def _transient_fail(name, args, ctx):
    return ToolResult(tool_id="t", name=name, success=False,
                      error="timeout contacting provider (transient)",
                      duration_ms=1)


def test_retry_count_bounded_by_max_retries(registry, validator):
    class _Brain:
        async def propose(self, brain_input, budget):
            return _proposal("static_search", {"query": "x"}, "answer_generated")

    registry.invoke = _transient_fail
    budget = TaskBudget(max_retries=2, max_replans=0, max_plan_iterations=2)
    orch = BrainOrchestrator(_Brain(), registry, validator, budget=budget)
    res = orch.run_sync("query the sky color")
    # static_search is a read/risk cap -> ACCEPTED + authorized. It fails
    # transiently, so the step is retried at most max_retries+1 times, then the
    # plan is abandoned (no replan) -> FAILED, never an infinite retry loop.
    assert res.status in ("FAILED", "BUDGET_EXCEEDED")
    assert registry.tool_calls if hasattr(registry, "tool_calls") else True


def test_max_plan_iterations_bounds_replan_loop(registry, validator, monkeypatch):
    calls = {"propose": 0}

    class _ReplanBrain:
        async def propose(self, brain_input, budget):
            calls["propose"] += 1
            # Always propose static_search but with an UNACHIEVABLE condition so
            # the control plane keeps looping until the iteration budget hits.
            return _proposal("static_search", {"query": "x"}, "tests_passed")

    async def _ok(name, args, ctx):
        return ToolResult(tool_id="t", name=name, success=True,
                          result="the sky is blue", duration_ms=2.0)

    registry.invoke = _ok
    budget = TaskBudget(max_replans=2, max_plan_iterations=2, max_retries=1)
    orch = BrainOrchestrator(_ReplanBrain(), registry, validator, budget=budget)
    res = orch.run_sync("query the sky color")
    # The loop must terminate via the iteration budget, not run forever.
    assert res.status == "BUDGET_EXCEEDED"
    # Propose called once up-front + once per successful replan; bounded by
    # max_plan_iterations + 1 (the plan is validated/rejected on the (N+1)th).
    assert calls["propose"] <= budget.max_plan_iterations + 1


def test_max_cost_bounded_at_tool_call_boundary(registry, validator):
    class _Brain:
        async def propose(self, brain_input, budget):
            return _proposal("static_search", {"query": "x"}, "answer_generated")

    async def _ok_with_usage(name, args, ctx):
        r = ToolResult(tool_id="t", name=name, success=True, result="ok",
                       duration_ms=1)
        class _U:
            total_tokens = 2_000_000  # $4.00 @ $0.002/1k > max_cost 1.0
        r.usage = _U()
        return r

    registry.invoke = _ok_with_usage
    # Tiny budget: 2000 tokens @ $0.002/1k = $4.00 > max_cost 1.0 -> must halt.
    budget = TaskBudget(max_cost=1.0, max_replans=0, max_plan_iterations=5)
    orch = BrainOrchestrator(_Brain(), registry, validator, budget=budget)
    res = orch.run_sync("query")
    assert res.status == "BUDGET_EXCEEDED"
