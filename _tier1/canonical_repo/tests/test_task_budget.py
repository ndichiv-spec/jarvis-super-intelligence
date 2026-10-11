"""Phase 8 tests: Task budgets and hard limits (Phase 8 §6, §26)."""
from __future__ import annotations

import time

import pytest

from jarvis_brain.budget import TaskBudget, TaskBudgetExceeded

pytestmark = pytest.mark.brain


def test_defaults():
    b = TaskBudget()
    assert b.max_plan_iterations == 3
    assert b.max_retries == 3
    assert b.max_replans == 2
    assert b.max_cost == 1.0


def test_begin_iteration_enforces_limit():
    b = TaskBudget(max_plan_iterations=2)
    b.begin_iteration()
    b.begin_iteration()
    with pytest.raises(TaskBudgetExceeded):
        b.begin_iteration()


def test_note_retry_enforces_limit():
    b = TaskBudget(max_retries=1)
    b.note_retry()
    with pytest.raises(TaskBudgetExceeded):
        b.note_retry()


def test_note_replan_enforces_limit():
    b = TaskBudget(max_replans=2)
    b.note_replan()
    b.note_replan()
    with pytest.raises(TaskBudgetExceeded):
        b.note_replan()


def test_spend_tokens_enforces_cost():
    b = TaskBudget(max_cost=0.01)  # $0.01
    # 5000 tokens * 0.002 / 1000 = $0.01 -> next spend exceeds
    b.spend_tokens(5000)
    with pytest.raises(TaskBudgetExceeded):
        b.spend_tokens(1)


def test_spend_call_enforces_cost():
    b = TaskBudget(max_cost=0.01)  # one provider call (0.01) is the limit
    b.spend_call("provider")  # spends exactly 0.01 -> still within budget
    with pytest.raises(TaskBudgetExceeded):
        b.spend_call("provider")  # 0.02 -> exceeds


def test_max_execution_time_enforced():
    b = TaskBudget(max_execution_time=0.05)
    time.sleep(0.06)
    with pytest.raises(TaskBudgetExceeded):
        b.spend_tool_call()  # _check fires on time


def test_account_result_best_effort():
    b = TaskBudget(max_cost=1.0, max_retries=5, max_replans=5, max_plan_iterations=5)

    class R:
        success = True
        error = ""
        duration_ms = 1
        metrics = {}
        artifacts = []
        result = "ok"

    class U:
        total_tokens = 10
    R2 = type("R", (), {"success": True, "error": "", "duration_ms": 1,
                        "metrics": {}, "artifacts": [], "result": "ok",
                        "usage": U()})
    b.account_result(R2())
    assert b.tokens_used == 10


def test_account_result_charges_each_provider_call():
    budget = TaskBudget(max_cost=0.02)
    result = type("R", (), {
        "metrics": {"cost_model": "provider", "provider_calls": 3},
    })()

    with pytest.raises(TaskBudgetExceeded):
        budget.account_result(result)
    assert budget.provider_calls == 3


def test_account_result_uses_provider_reported_cost_when_available():
    budget = TaskBudget(max_cost=0.05)
    result = type("R", (), {
        "metrics": {
            "cost_model": "provider",
            "provider_calls": 3,
            "total_cost_usd": 0.02,
        },
    })()

    budget.account_result(result)
    assert budget.provider_calls == 3
    assert budget.usd_spent == 0.02


def test_spent_snapshot():
    b = TaskBudget(max_plan_iterations=10, max_retries=10, max_replans=10,
                   max_cost=10.0, max_execution_time=60.0)
    b.spend_tokens(1000)
    snap = b.spent()
    assert snap["tokens_used"] == 1000
    assert snap["iterations"] == 0
    assert "usd_spent" in snap
    assert "elapsed_sec" in snap


def test_exhausted_flags():
    b = TaskBudget(max_replans=0, max_retries=0)
    assert b.exhausted_replans
    assert b.exhausted_retries
