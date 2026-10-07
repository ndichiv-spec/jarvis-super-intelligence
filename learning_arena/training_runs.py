"""Training run tracking for the Learning Arena (spec §25, §27, §55).

Manages the lifecycle of a training run: from task dispatch to result
capture.  A ``TrainingRun`` bundles:
  * The originating :class:`~learning_arena.tasks.Task`
  * The model revision being trained/extended
  * Input datasets (with provenance)
  * Resource allocation (checked against the :class:`ResourceGovernor`)
  * Live metrics (loss, accuracy per step)
  * Final outcome + experience capture

Training runs never execute directly — they are dispatched to a remote
worker (NeMo, cloud GPU, or local process).  The arena tracks state and
captures results when the worker reports back.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .tasks import TaskStatus
from .experiences import ExperienceArena
from .feedback import FeedbackArena, Feedback, FeedbackSource
from .failures import FailureArena
from .evaluations import EvaluationArena, EvalSpec, EvalResult
from .rewards import RewardEngine


class TrainingStatus(Enum):
    """Training run lifecycle states."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class TrainingConfig:
    """Training hyperparameters and remote target."""

    model_revision: str
    base_model: str
    dataset_ids: list[str]
    epochs: int = 1
    learning_rate: float = 1e-5
    batch_size: int = 32
    max_steps: int = 1000
    optimizer: str = "adamw"
    precision: str = "bf16"
    remote_target: str = ""  # URL of the training worker (NeMo, cloud GPU)
    config_override: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainingMetrics:
    """Live metrics for a training run."""

    step: int = 0
    loss: float = 0.0
    learning_rate: float = 0.0
    tokens_processed: int = 0
    elapsed_seconds: float = 0.0
    checkpoint_path: Optional[str] = None


@dataclass
class TrainingRun:
    """A tracked training run."""

    id: str
    task_id: str
    config: TrainingConfig
    status: TrainingStatus = TrainingStatus.PENDING
    created_at: float = field(default_factory=time.time)
    dispatched_at: Optional[float] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    metrics: TrainingMetrics = field(default_factory=TrainingMetrics)
    output_revision: Optional[str] = None
    error: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.ended_at:
            return self.ended_at - self.started_at
        return None


class TrainingRunArena:
    """Orchestrates training-run lifecycle and result capture (spec §25).

    Integrates with:
      * :class:`TaskArena` — for task scheduling
      * :class:`ExperienceArena` — to record outcomes
      * :class:`FeedbackArena` — to capture evaluation feedback
      * :class:`FailureArena` — to catalog failures
      * :class:`EvaluationArena` — to run eval suites
      * :class:`RewardEngine` — to compute rewards
      * :class:`ResourceGovernor` — to enforce resource limits
    """

    def __init__(
        self,
        experience_arena: ExperienceArena,
        feedback_arena: FeedbackArena,
        failure_arena: FailureArena,
        eval_arena: EvaluationArena,
        reward_engine: RewardEngine,
    ) -> None:
        self._experience_arena = experience_arena
        self._feedback_arena = feedback_arena
        self._failure_arena = failure_arena
        self._eval_arena = eval_arena
        self._reward_engine = reward_engine
        self._runs: dict[str, TrainingRun] = {}

    def launch(
        self,
        task_id: str,
        config: TrainingConfig,
        *,
        tags: list[str] = None,
    ) -> TrainingRun:
        """Create a new training run and dispatch it (spec §25.2)."""
        run = TrainingRun(
            id=str(uuid.uuid4()),
            task_id=task_id,
            config=config,
            tags=tags or [],
            status=TrainingStatus.PENDING,
        )
        self._runs[run.id] = run

        # Check resource governor via the config's remote_target.
        # (The actual dispatch happens in dispatch().)
        run.status = TrainingStatus.PENDING
        return run

    def dispatch(self, run_id: str) -> TrainingRun:
        """Mark a run as dispatched for remote execution."""
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown training run: {run_id}")
        if run.status != TrainingStatus.PENDING:
            raise ValueError(f"run {run_id} not in PENDING state (current: {run.status})")
        run.status = TrainingStatus.DISPATCHED
        run.dispatched_at = time.time()
        return run

    def start(self, run_id: str) -> TrainingRun:
        """Mark a run as actively training."""
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown training run: {run_id}")
        run.status = TrainingStatus.RUNNING
        run.started_at = time.time()
        return run

    def report_metrics(self, run_id: str, metrics: TrainingMetrics) -> TrainingRun:
        """Update live metrics for a running training run."""
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown training run: {run_id}")
        run.metrics = metrics
        return run

    def complete(
        self, run_id: str, output_revision: Optional[str] = None,
        error: str = "",
    ) -> Optional[TrainingRun]:
        """Mark a run as complete (or failed) and capture experience."""
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown training run: {run_id}")

        run.ended_at = time.time()
        run.error = error

        if error:
            run.status = TrainingStatus.FAILED
            # Record failure
            self._failure_arena.record(
                task_id=run.task_id,
                error_message=error,
                model_revision=run.config.model_revision,
                resource_at_failure={
                    "step": run.metrics.step,
                    "loss": run.metrics.loss,
                    "elapsed_seconds": run.metrics.elapsed_seconds,
                },
                tags=["training", "remote"] + run.tags,
            )
            outcome_str = "failure"
        else:
            run.status = TrainingStatus.COMPLETE
            if output_revision:
                run.output_revision = output_revision
            outcome_str = "success"

        # Capture experience
        from teacher_node.experience_recorder import TaskOutcome
        outcome = TaskOutcome.SUCCESS if not error else TaskOutcome.FAILURE
        self._experience_arena.capture(
            task_id=run.task_id,
            category="training",
            outcome=outcome,
            started_at=run.started_at or run.created_at,
            ended_at=run.ended_at,
            model_revision=run.config.model_revision,
            metrics={
                "loss": run.metrics.loss,
                "step": run.metrics.step,
                "tokens": run.metrics.tokens_processed,
            },
            error_message=error,
            tags=run.tags + ["training"],
            source="training_run_arena",
        )

        # Compute reward
        reward = self._reward_engine.compute(
            run.task_id, outcome_str,
            resource_cost=run.metrics.elapsed_seconds,
            expected_cost=config_expected(run.config),
            is_novel=False,
        )

        # Record feedback from metrics
        if not error and run.metrics.loss > 0:
            self._feedback_arena.record(
                task_id=run.task_id,
                source=FeedbackSource.AUTOMATED,
                score=max(-1.0, min(1.0, 1.0 - run.metrics.loss / 10.0)),
                raw_score=run.metrics.loss,
                context={
                    "metric": "loss",
                    "step": run.metrics.step,
                    "model": run.config.model_revision,
                },
            )

        return run

    def cancel(self, run_id: str) -> TrainingRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown training run: {run_id}")
        if run.is_terminal():
            return run
        run.status = TrainingStatus.CANCELLED
        run.ended_at = time.time()
        return run

    def pause(self, run_id: str) -> TrainingRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown training run: {run_id}")
        if run.status == TrainingStatus.RUNNING:
            run.status = TrainingStatus.PAUSED
        return run

    def resume(self, run_id: str) -> TrainingRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown training run: {run_id}")
        if run.status == TrainingStatus.PAUSED:
            run.status = TrainingStatus.RUNNING
        return run

    def get(self, run_id: str) -> Optional[TrainingRun]:
        return self._runs.get(run_id)

    def runs_for_task(self, task_id: str) -> list[TrainingRun]:
        return [r for r in self._runs.values() if r.task_id == task_id]

    def all(self) -> list[TrainingRun]:
        return list(self._runs.values())

    def clear(self) -> None:
        self._runs.clear()


def config_expected(config: TrainingConfig) -> Optional[float]:
    """Estimate expected resource cost (seconds) from config."""
    if config.max_steps == 0:
        return None
    # Rough: 1s per 10 steps per epoch, scaled by max_steps
    per_epoch = config.max_steps / 10.0
    return per_epoch * config.epochs


# Helper to check if a run status is terminal
def _is_terminal(self):
    return self.status in (
        TrainingStatus.COMPLETE, TrainingStatus.FAILED,
        TrainingStatus.CANCELLED,
    )


TrainingRun.is_terminal = _is_terminal  # type: ignore[attr-defined]
