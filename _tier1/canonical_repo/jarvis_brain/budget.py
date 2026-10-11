"""Task budgets and hard limits (Phase 8 §6, §7, §26).

Enforces the *bounded autonomy* invariant: an autonomous Brain loop can never
run forever.  Every cycle is accounted against a :class:`TaskBudget`; the moment
any limit is crossed the control plane raises :class:`TaskBudgetExceeded` and
the task terminates in a terminal, auditable state rather than looping.

Limits (all configurable, all enforced):

    max_plan_iterations   total plan/iteration cycles (PLAN → ... → REPLAN)
    max_retries           per-step execution retries after a failure
    max_replans           replanning cycles allowed after an observed failure
    max_execution_time    wall-clock seconds for the whole task
    max_cost              abstract cost budget (tokens + provider usage)

This module owns no credentials, no secrets, no I/O — it is pure accounting.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CostKind(str, Enum):
    """Kinds of spend we account for (Phase 8 §23)."""

    TOKENS = "tokens"        # prompt+completion tokens consumed
    USDO = "usd"             # monetary spend (provider model calls)
    SECONDS = "seconds"      # wall-clock time
    PROVIDER_CALLS = "provider_calls"
    TOOL_CALLS = "tool_calls"
    REPLANS = "replans"
    ITERATIONS = "iterations"


# Approximate token→USD rates (per 1k tokens). These are *accounting* estimates
# used only for budget enforcement, never for billing.
_TOKEN_COSTS = {
    "llm_tokens": 0.002,     # mid-range provider rate ($/1k tokens)
    "provider": 0.01,
}


class TaskBudgetExceeded(Exception):
    """Raised when any hard limit is crossed (Phase 8 §6)."""

    def __init__(self, reason: str, *, spent: Optional[dict[str, float]] = None):
        super().__init__(reason)
        self.reason = reason
        self.spent = spent or {}


@dataclass
class TaskBudget:
    """Hard limits for a single task execution."""

    max_plan_iterations: int = 3
    max_retries: int = 3
    max_replans: int = 2
    max_execution_time: float = 300.0  # seconds
    max_cost: float = 1.0               # abstract USD budget
    # Per-capability cost multiplier override map (capability_id -> usd_per_call).
    capability_costs: dict[str, float] = field(default_factory=dict)

    # --- running counters (mutable) ---
    iterations: int = 0
    retries: int = 0
    replans: int = 0
    tokens_used: int = 0
    usd_spent: float = 0.0
    tool_calls: int = 0
    provider_calls: int = 0
    started_at: float = field(default_factory=time.monotonic)

    # ------------------------------------------------------------------ #
    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def exhausted_replans(self) -> bool:
        return self.replans >= self.max_replans

    @property
    def exhausted_retries(self) -> bool:
        return self.retries >= self.max_retries

    def spend_tokens(self, tokens: int, cost_model: str = "llm_tokens") -> None:
        self.tokens_used += max(0, int(tokens))
        self.usd_spent += max(0, int(tokens)) / 1000.0 * _TOKEN_COSTS.get(cost_model, _TOKEN_COSTS["llm_tokens"])
        self._check()

    def spend_call(self, cost_model: str = "provider", capability: Optional[str] = None) -> None:
        self.provider_calls += 1
        if capability and capability in self.capability_costs:
            unit = self.capability_costs[capability]
        else:
            unit = _TOKEN_COSTS.get(cost_model, 0.0)
        self.usd_spent += unit
        self._check()

    def spend_tool_call(self) -> None:
        self.tool_calls += 1
        self._check()

    def account_result(self, result: Any) -> None:
        """Account an execution result (tokens/time) without double counting.

        Accepts GatewayResponse / ToolResult-like objects that expose ``usage``
        or ``metrics`` with token counts — best-effort, never raises.
        """
        try:
            usage = getattr(result, "usage", None)
            if usage is not None:
                tok = getattr(usage, "total_tokens", 0) or 0
                if tok:
                    self.spend_tokens(int(tok))
            metrics = getattr(result, "metrics", None)
            if isinstance(metrics, dict):
                cm = metrics.get("cost_model")
                if cm:
                    call_count = metrics.get("provider_calls", 1)
                    if type(call_count) is not int or not 0 <= call_count <= 100:
                        call_count = 1
                    reported_cost = metrics.get("total_cost_usd")
                    if (
                        isinstance(reported_cost, (int, float))
                        and not isinstance(reported_cost, bool)
                        and math.isfinite(reported_cost)
                        and reported_cost >= 0
                    ):
                        self.provider_calls += call_count
                        self.usd_spent += float(reported_cost)
                        self._check()
                    else:
                        for _ in range(call_count):
                            self.spend_call(cm)
        except TaskBudgetExceeded:
            raise
        except Exception:
            pass
        self._check()

    # ------------------------------------------------------------------ #
    # Checkers — each increments its counter first, then enforces. The
    # caller increments, we only enforce. (See consume_* below.)
    # ------------------------------------------------------------------ #
    def begin_iteration(self) -> None:
        self.iterations += 1
        self._check()

    def note_retry(self) -> None:
        self.retries += 1
        if self.retries > self.max_retries:
            raise TaskBudgetExceeded(
                f"max_retries ({self.max_retries}) exceeded",
                spent=self.spent(),
            )

    def note_replan(self) -> None:
        self.replans += 1
        if self.replans > self.max_replans:
            raise TaskBudgetExceeded(
                f"max_replans ({self.max_replans}) exceeded",
                spent=self.spent(),
            )

    def _check(self) -> None:
        if self.iterations > self.max_plan_iterations:
            raise TaskBudgetExceeded(
                f"max_plan_iterations ({self.max_plan_iterations}) exceeded",
                spent=self.spent(),
            )
        if self.elapsed > self.max_execution_time:
            raise TaskBudgetExceeded(
                f"max_execution_time ({self.max_execution_time}s) exceeded "
                f"(elapsed {self.elapsed:.1f}s)",
                spent=self.spent(),
            )
        if self.usd_spent > self.max_cost:
            raise TaskBudgetExceeded(
                f"max_cost ({self.max_cost}) exceeded (spent {self.usd_spent:.6f})",
                spent=self.spent(),
            )

    def spent(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "retries": self.retries,
            "replans": self.replans,
            "tokens_used": self.tokens_used,
            "usd_spent": round(self.usd_spent, 8),
            "tool_calls": self.tool_calls,
            "provider_calls": self.provider_calls,
            "elapsed_sec": round(self.elapsed, 2),
        }
