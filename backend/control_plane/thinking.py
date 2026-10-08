"""
Think-Before-Act (Deliberative Reasoning) Engine.

Provides structured deliberation — a reasoning step that an agent takes
*before* acting — analogous to Claude Code thinking blocks and Codex planning.
The engine produces a :class:`DeliberationPlan` with explicit steps, constraints,
fallback strategies, and a reasoning trace (chain-of-thought record).

Design:
  * Pure-Python, in-memory by default — no external dependencies.
  * Produces serializable plans (each ``to_dict`` round-trips).
  * Integrates with :class:`~backend.control_plane.task_runtime.TaskManager`
    during the ``PLANNING`` state.
  * Honest degradation: when the provider backend is unavailable the engine
    still returns a bounded default plan rather than fabricating actions.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("control_plane.thinking")


class StepStatus(str, Enum):
    PENDING = "pending"
    REASONING = "reasoning"
    PLANNED = "planned"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class ConfidenceState(str, Enum):
    INSUFFICIENT_INFORMATION = "insufficient_information"
    LOW_CONFIDENCE = "low"
    MEDIUM_CONFIDENCE = "medium"
    HIGH_CONFIDENCE = "high"
    CERTAIN = "certain"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ReasoningBlock:
    """A single deliberative reasoning turn (chain-of-thought segment)."""

    thought: str
    confidence: ConfidenceState = ConfidenceState.MEDIUM_CONFIDENCE
    assumptions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    alternatives_considered: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thought": self.thought,
            "confidence": self.confidence.value,
            "assumptions": self.assumptions,
            "risks": self.risks,
            "alternatives_considered": self.alternatives_considered,
            "timestamp": self.timestamp,
        }


@dataclass
class PlanStep:
    """A single step in a deliberation plan."""

    id: str
    name: str
    description: str
    capability: str = ""
    risk: RiskLevel = RiskLevel.LOW
    required_approval: bool = False
    depends_on: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    tool_call: Optional[Dict[str, Any]] = None
    estimated_cost: Optional[float] = None
    timeout_sec: float = 60.0
    rationale: Optional[ReasoningBlock] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capability": self.capability,
            "risk": self.risk.value,
            "required_approval": self.required_approval,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "tool_call": self.tool_call,
            "estimated_cost": self.estimated_cost,
            "timeout_sec": self.timeout_sec,
            "rationale": self.rationale.to_dict() if self.rationale else None,
            "error": self.error,
        }


@dataclass
class Constraint:
    """A constraint the plan must respect."""

    name: str
    description: str
    enforceable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "enforceable": self.enforceable,
        }


@dataclass
class FallbackStrategy:
    """Fallback actions if the primary plan fails."""

    condition: str
    actions: List[str] = field(default_factory=list)
    escalate_to: Optional[str] = None
    ask_user: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition": self.condition,
            "actions": self.actions,
            "escalate_to": self.escalate_to,
            "ask_user": self.ask_user,
            "reason": self.reason,
        }


@dataclass
class DeliberationPlan:
    """A full deliberative plan produced by the Think-Before-Act engine."""

    plan_id: str
    goal: str
    reasoning_trace: List[ReasoningBlock] = field(default_factory=list)
    steps: List[PlanStep] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    fallback_strategies: List[FallbackStrategy] = field(default_factory=list)
    confidence: ConfidenceState = ConfidenceState.MEDIUM_CONFIDENCE
    overall_risk: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    max_retries: int = 3
    execution_timeout_sec: float = 300.0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    source: str = "think_before_act"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "reasoning_trace": [r.to_dict() for r in self.reasoning_trace],
            "steps": [s.to_dict() for s in self.steps],
            "constraints": [c.to_dict() for c in self.constraints],
            "fallback_strategies": [f.to_dict() for f in self.fallback_strategies],
            "confidence": self.confidence.value,
            "overall_risk": self.overall_risk.value,
            "requires_approval": self.requires_approval,
            "max_retries": self.max_retries,
            "execution_timeout_sec": self.execution_timeout_sec,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "source": self.source,
        }

    def step_ids(self) -> List[str]:
        return [s.id for s in self.steps]

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def remaining_steps(self) -> List[PlanStep]:
        terminal = {StepStatus.DONE, StepStatus.SKIPPED, StepStatus.FAILED}
        return [s for s in self.steps if s.status not in terminal]


@dataclass
class DeliberationResult:
    """Result of a deliberation session."""

    plan: DeliberationPlan
    thinking_time_ms: float
    provider_used: str
    honest: bool = True
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "thinking_time_ms": self.thinking_time_ms,
            "provider_used": self.provider_used,
            "honest": self.honest,
            "note": self.note,
        }


class ThinkBeforeActEngine:
    """
    Deliberative reasoning engine.

    Accepts a goal and produces a :class:`DeliberationPlan` by running
    an optional deliberation callback (which may call an LLM provider).
    When no provider is configured or the callback raises, the engine
    falls back to a bounded heuristic planner that never fabricates.
    """

    _instance: Optional["ThinkBeforeActEngine"] = None

    def __init__(
        self,
        deliberator: Optional[Callable[[str, Any], DeliberationPlan]] = None,
    ):
        self._deliberator = deliberator
        self._plans: Dict[str, DeliberationPlan] = {}

    @classmethod
    def get_instance(cls, **kwargs: Any) -> "ThinkBeforeActEngine":
        if cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def set_deliberator(
        self, deliberator: Callable[[str, Any], DeliberationPlan]
    ) -> None:
        """Register a custom deliberation callback (e.g. LLM-powered planner)."""
        self._deliberator = deliberator

    def deliberate(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        constraints: Optional[List[str]] = None,
        max_steps: int = 8,
        timeout_sec: float = 30.0,
    ) -> DeliberationResult:
        """
        Run deliberation for *goal* and return a :class:`DeliberationResult`.

        If a registered deliberator callback succeeds, its plan is used.
        Otherwise, the built-in heuristic planner produces a bounded plan.
        """
        start = time.time()
        context = context or {}
        del_start = time.time()

        plan: Optional[DeliberationPlan] = None
        provider_used = "none"
        honest = True
        note = ""

        if self._deliberator is not None:
            try:
                plan = self._deliberator(goal, context)
                provider_used = "deliberator_callback"
            except Exception as exc:
                logger.warning("Deliberator callback failed: %s", exc)
                note = f"deliberator callback failed: {exc}"
                plan = None

        if plan is None:
            plan = self._heuristic_plan(
                goal,
                context,
                constraints=constraints or [],
                max_steps=max_steps,
            )
            provider_used = "heuristic_fallback"
            honest = True
            if note:
                note = note + "; " + "used heuristic fallback (no provider)"
            else:
                note = "used heuristic fallback (no provider)"

        plan.plan_id = plan.plan_id or str(uuid.uuid4())
        plan.source = plan.source or "think_before_act"

        self._plans[plan.plan_id] = plan

        thinking_time_ms = (time.time() - del_start) * 1000.0
        total_time_ms = (time.time() - start) * 1000.0

        logger.info(
            "Deliberation for goal '%s': %d steps, provider=%s, honest=%s, %.1fms",
            goal[:60], len(plan.steps), provider_used, honest, total_time_ms,
        )

        return DeliberationResult(
            plan=plan,
            thinking_time_ms=thinking_time_ms,
            provider_used=provider_used,
            honest=honest,
            note=note,
        )

    def _heuristic_plan(
        self,
        goal: str,
        context: Dict[str, Any],
        *,
        constraints: List[str],
        max_steps: int,
    ) -> DeliberationPlan:
        """Produce a bounded, honest default plan without external calls."""
        plan_id = str(uuid.uuid4())

        reasoning = ReasoningBlock(
            thought=f"Goal received: '{goal}'. No external deliberator available; "
                    f"producing a bounded heuristic plan. The plan will decompose the "
                    f"goal into observable steps and request evidence at each stage.",
            confidence=ConfidenceState.LOW_CONFIDENCE,
            assumptions=[
                "The goal is achievable with available platform capabilities.",
                "Each step can be verified before proceeding.",
            ],
            risks=[
                "Heuristic plan may miss edge cases.",
                "No external reasoning provider was available.",
            ],
            alternatives_considered=[
                "Skip planning and execute immediately (risky, not chosen).",
            ],
        )

        constraint_objs = [
            Constraint(name=c, description=c, enforceable=True)
            for c in constraints
        ]

        if not constraint_objs:
            constraint_objs = [
                Constraint(
                    name="safety",
                    description="Do not fabricate results; require evidence.",
                    enforceable=True,
                ),
                Constraint(
                    name="approval_gate",
                    description="High-risk steps require human approval.",
                    enforceable=True,
                ),
            ]

        step1 = PlanStep(
            id="s1",
            name="assess",
            description=f"Assess the current state with respect to: {goal}",
            capability="research" if "research" in goal.lower() else "reasoning",
            risk=RiskLevel.LOW,
            required_approval=False,
            rationale=reasoning,
        )

        step2 = PlanStep(
            id="s2",
            name="execute",
            description=f"Execute the primary action for: {goal}",
            capability=context.get("capability", "tool_use"),
            risk=RiskLevel.MEDIUM,
            depends_on=["s1"],
            required_approval=True,
        )

        step3 = PlanStep(
            id="s3",
            name="verify",
            description="Verify the result against evidence before committing.",
            capability="verification",
            risk=RiskLevel.LOW,
            depends_on=["s2"],
        )

        steps = [step1, step2, step3][:max_steps]

        fallbacks = [
            FallbackStrategy(
                condition="step failed or timed out",
                actions=["retry with adjusted parameters"],
                escalate_to="human",
                ask_user=True,
                reason="Graceful degradation on failure.",
            ),
            FallbackStrategy(
                condition="capability unavailable",
                actions=["route to fallback provider"],
                reason="Provider fallback per policy.",
            ),
        ]

        overall_risk = RiskLevel.HIGH if any(
            s.risk == RiskLevel.HIGH for s in steps
        ) else RiskLevel.MEDIUM

        return DeliberationPlan(
            plan_id=plan_id,
            goal=goal,
            reasoning_trace=[reasoning],
            steps=steps,
            constraints=constraint_objs,
            fallback_strategies=fallbacks,
            confidence=ConfidenceState.LOW_CONFIDENCE,
            overall_risk=overall_risk,
            requires_approval=overall_risk in (RiskLevel.HIGH, RiskLevel.MEDIUM),
            max_retries=3,
            execution_timeout_sec=300.0,
            source="heuristic_fallback",
        )

    def get_plan(self, plan_id: str) -> Optional[DeliberationPlan]:
        return self._plans.get(plan_id)

    def update_step_status(
        self,
        plan_id: str,
        step_id: str,
        status: StepStatus,
        *,
        error: Optional[str] = None,
    ) -> bool:
        plan = self._plans.get(plan_id)
        if plan is None:
            return False
        step = plan.get_step(step_id)
        if step is None:
            return False
        step.status = status
        if error:
            step.error = error
        logger.debug("Plan %s step %s -> %s", plan_id, step_id, status.value)
        return True

    def next_runnable_steps(self, plan_id: str) -> List[PlanStep]:
        """Return ready steps (all dependencies DONE/SKIPPED/FAILED)."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return []
        terminal = {StepStatus.DONE, StepStatus.SKIPPED, StepStatus.FAILED}
        done_deps = {s.id for s in plan.steps if s.status in terminal}
        pending = [
            s for s in plan.steps
            if s.status == StepStatus.PENDING
            and all(d in done_deps for d in s.depends_on)
        ]
        # Promote to PLANNED
        for s in pending:
            s.status = StepStatus.PLANNED
        return pending

    def mark_plan_complete(
        self, plan_id: str, *, completed_at: Optional[float] = None
    ) -> bool:
        plan = self._plans.get(plan_id)
        if plan is None:
            return False
        plan.completed_at = completed_at or time.time()
        return True

    def reset(self) -> None:
        self._plans.clear()


think_engine = ThinkBeforeActEngine.get_instance()


def deliberate(
    goal: str,
    context: Optional[Dict[str, Any]] = None,
    *,
    constraints: Optional[List[str]] = None,
    max_steps: int = 8,
    timeout_sec: float = 30.0,
) -> DeliberationResult:
    """Module-level convenience: run deliberation on the global engine."""
    return think_engine.deliberate(
        goal, context, constraints=constraints, max_steps=max_steps,
        timeout_sec=timeout_sec,
    )
