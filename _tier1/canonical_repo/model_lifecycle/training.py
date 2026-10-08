"""Training lifecycle orchestration (spec §17, §29, §34).

The local machine is the *orchestrator*; heavy training runs on a remote
target (``remote_target`` required).  A launched run always produces a
lifecycle record; that record only moves to ``EVALUATION`` /
``PROMOTION_REVIEW`` after the candidate has real evaluation evidence, and
nothing becomes production without the human gate in
:class:`~model_lifecycle.registry.ModelRegistry`.

The regression policy is **config-driven** — never an invented threshold.
When no tolerances are configured, the policy refuses to auto-decide and asks
a human evaluator instead (no silent auto-promotion).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .registry import ModelRegistry
from .types import LifecycleStage, ModelLifecycleType, PromotionState


class TrainingPolicyError(RuntimeError):
    """A training lifecycle policy was violated (e.g. no remote target)."""


@dataclass
class RegressionPolicy:
    """Candidate-vs-baseline regression policy, fully config-driven.

    Attribute lookup is explicit config; ``None`` means *no tolerance has been
    declared*, in which case the policy **cannot decide** and reports
    ``needs_human`` instead of inventing limits (spec §29, "never pretend").
    """

    min_improvement: Optional[float] = None  # e.g. +0.02 on the primary metric
    max_regression: Optional[float] = None  # e.g. 0.02 per secondary metric
    metrics: list[str] = field(default_factory=lambda: ["accuracy", "safety"])
    primary_metric: str = "accuracy"

    def is_configured(self) -> bool:
        return self.min_improvement is not None or self.max_regression is not None

    def decide(self, baseline: dict, candidate: dict) -> dict:
        """Return an honest decision: ``approve`` | ``reject`` | ``needs_human``."""
        if not self.is_configured():
            return {
                "decision": "needs_human",
                "reason": "no regression tolerances configured; human evaluation required",
            }

        primary_c = candidate.get(self.primary_metric)
        primary_b = baseline.get(self.primary_metric)
        if primary_c is None or primary_b is None:
            return {
                "decision": "needs_human",
                "reason": f"primary metric {self.primary_metric!r} missing from evidence",
            }

        delta_primary = _delta(primary_c, primary_b)
        if self.min_improvement is not None and delta_primary < self.min_improvement:
            return {
                "decision": "needs_human",
                "reason": (
                    f"primary delta {delta_primary:+.4f} below required "
                    f"improvement {self.min_improvement:+.4f}"
                ),
            }

        if self.max_regression is not None:
            for metric in self.metrics:
                b = baseline.get(metric)
                c = candidate.get(metric)
                if b is None or c is None:
                    continue
                d = _delta(c, b)
                if d < -abs(self.max_regression):
                    return {
                        "decision": "reject",
                        "reason": (
                            f"{metric} regressed by {-d:+.4f} beyond allowed "
                            f"{self.max_regression:.4f}"
                        ),
                    }

        if self.min_improvement is not None and delta_primary < 0:
            return {
                "decision": "reject",
                "reason": f"primary metric regressed ({delta_primary:+.4f})",
            }

        return {
            "decision": "approve",
            "reason": (
                f"primary delta {delta_primary:+.4f} within configured tolerances"
            ),
            "delta": delta_primary,
        }


def _delta(new_value: float, old_value: float) -> float:
    single = None
    try:
        float(old_value)
    except (TypeError, ValueError):
        single = old_value
    if single is not None and isinstance(single, (dict, list)):
        return 0.0  # complex artifact — never fabricate a numeric delta
    old_f = float(old_value or 0.0)
    new_f = float(new_value or 0.0)
    if old_f == 0:
        return 0.0
    return (new_f - old_f) / abs(old_f)


@dataclass
class TrainingRunResult:
    """Outcome of one lifecycle training run."""

    run_id: str
    candidate_record_id: str
    status: str  # PENDING | COMPLETE | FAILED | CANCELLED
    metrics: dict = field(default_factory=dict)
    decision: dict = field(default_factory=dict)
    launched_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "candidate_record_id": self.candidate_record_id,
            "status": self.status,
            "metrics": self.metrics,
            "decision": self.decision,
            "launched_at": self.launched_at,
            "completed_at": self.completed_at,
        }


class TrainingLifecycle:
    """Orchestrates a governed training run against the lifecycle registry.

    Flow: attach datasets + base model -> create the JARVIS candidate record ->
    dispatch to the (mandatory) remote target -> on completion, run the
    candidate against evaluation evidence -> regression-policy gate ->
    ``EVALUATION`` / ``PROMOTION_REVIEW`` (human gate remains).
    """

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        regression: Optional[RegressionPolicy] = None,
        require_remote: bool = True,
    ) -> None:
        self.registry = registry
        self.regression = regression or RegressionPolicy()
        self.require_remote = require_remote
        self._runs: dict[str, TrainingRunResult] = {}

    # ------------------------------------------------------------------
    def launch(
        self,
        *,
        base_record_id: str,
        dataset_ids: list[str],
        remote_target: str,
        actor: str,
        model_name: Optional[str] = None,
        hyperparameters: Optional[dict] = None,
        lifecycle_type: ModelLifecycleType = ModelLifecycleType.JARVIS_CANDIDATE,
    ) -> TrainingRunResult:
        """Launch a training run; returns the candidate lifecycle record link.

        ``remote_target`` is mandatory when ``self.require_remote`` is set: the
        local PC is the orchestrator, not the trainer (spec §34).  Pass an empty
        string only when a local-only path is explicitly allowed.
        """
        if self.require_remote and not remote_target.strip():
            raise TrainingPolicyError(
                "training requires a remote target (local machine orchestrates; "
                "heavy runs happen remotely)"
            )
        if not dataset_ids:
            raise TrainingPolicyError("training requires at least one dataset revision")

        base = self.registry.require(base_record_id)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        candidate_name = model_name or f"{os_safe_name(base.model_id)}-sft-{run_id[-6:]}"

        candidate = self.registry.ensure(
            provider="jarvis",
            model_id=candidate_name,
            lifecycle_type=lifecycle_type,
            family=base.family,
            capabilities=list(base.capabilities),
            deployment="remote_endpoint",
            architecture=base.architecture,
            context_length=base.context_length,
            source="training_lifecycle",
            parent_model=base.record_id,
            training_run_id=run_id,
            metadata={
                "remote_target": remote_target,
                "hyperparameters": hyperparameters or {},
                "run_id": run_id,
            },
            actor=actor,
        )

        for ds_id in dataset_ids:
            self.registry.link_dataset(candidate.record_id, ds_id, actor)

        self.registry.set_stage(
            candidate.record_id, LifecycleStage.TRAINING, actor,
            detail=f"training launched to {remote_target}",
        )

        result = TrainingRunResult(
            run_id=run_id,
            candidate_record_id=candidate.record_id,
            status="PENDING",
            metrics=dict(hyperparameters or {}),
        )
        self._runs[run_id] = result
        return result

    # ------------------------------------------------------------------
    def complete(
        self,
        run_id: str,
        *,
        metrics: dict,
        baseline_record_id: str,
        actor: str,
        baseline_metrics: Optional[dict] = None,
    ) -> TrainingRunResult:
        """Attach evaluation evidence, run the regression gate, and advance the
        candidate to ``EVALUATION`` + ``PROMOTION_REVIEW`` when the policy
        allows (the human approval gate stays untouched)."""
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown lifecycle training run {run_id!r}")

        candidate = self.registry.require(run.candidate_record_id)
        run.metrics = dict(metrics)
        run.status = "COMPLETE"
        run.completed_at = time.time()

        self.registry.record_evaluation(
            run.candidate_record_id,
            "training_metrics",
            {"metrics": metrics, "status": "COMPLETE"},
            actor=actor,
        )

        decision = self.regression.decide(
            baseline_metrics or {},
            metrics,
        )
        run.decision = decision

        if decision["decision"] == "reject":
            self.registry.set_stage(
                run.candidate_record_id,
                LifecycleStage.REJECTED,
                actor,
                detail=f"regression policy rejected: {decision['reason']}",
            )
            self.registry.set_promotion(
                run.candidate_record_id,
                PromotionState.NONE,
                actor,
                detail="rejected at regression gate",
            )
            return run

        # approve or needs_human — either way we must NOT auto-promote; we move
        # to EVALUATION / PROMOTION_REVIEW and leave the human gate closed.
        self.registry.record_evaluation(
            run.candidate_record_id,
            "candidate_vs_baseline",
            {
                "decision": decision,
                "baseline_record_id": baseline_record_id,
                "metrics": metrics,
            },
            actor=actor,
        )
        self.registry.mark_evaluated(run.candidate_record_id, actor)
        return run

    # ------------------------------------------------------------------
    def fail(self, run_id: str, *, actor: str, reason: str = "") -> TrainingRunResult:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown lifecycle training run {run_id!r}")
        run.status = "FAILED"
        run.completed_at = time.time()
        run.decision = {"decision": "reject", "reason": reason or "training failed"}
        self.registry.set_stage(
            run.candidate_record_id,
            LifecycleStage.REJECTED,
            actor,
            detail=f"training failed: {reason}",
        )
        self.registry.set_promotion(
            run.candidate_record_id,
            PromotionState.NONE,
            actor,
            detail="training failed",
        )
        return run

    def get_run(self, run_id: str) -> Optional[TrainingRunResult]:
        return self._runs.get(run_id)

    def runs(self) -> list[TrainingRunResult]:
        return list(self._runs.values())


def os_safe_name(model_id: str) -> str:
    """Sanitize a model/repo id for use as a local artifact name."""
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in model_id).strip("-")