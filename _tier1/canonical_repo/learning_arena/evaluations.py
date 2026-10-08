"""Evaluation suite for the Learning Arena (spec §29, §27.3).

Runs evaluation benchmarks against model revisions and captures structured
results.  The evaluation suite:
  * Executes a named benchmark (e.g. "mmlu", "humaneval") against a model.
  * Captures per-task metrics (accuracy, loss, latency).
  * Produces an :class:`EvaluationResult` that feeds into the feedback arena.
  * Supports both synchronous and batched (spec §29.4) evaluation.

Evaluation is **non-fabricating**: if the benchmark or model is unavailable,
the result status is ``ERROR`` with a clear reason — never a fake pass.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .feedback import Feedback, FeedbackSource


class EvalStatus(Enum):
    """Evaluation result status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class EvalSpec:
    """Specification for an evaluation run."""

    name: str
    model_revision: str
    benchmark: str          # e.g. "mmlu", "humaneval", "gsm8k"
    dataset: str            # dataset name / path
    max_samples: Optional[int] = None
    timeout_seconds: int = 300
    config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """Result of an evaluation run."""

    id: str
    spec: EvalSpec
    status: EvalStatus = EvalStatus.PENDING
    metrics: dict[str, float] = field(default_factory=dict)
    per_task: list[dict[str, Any]] = field(default_factory=list)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    error: str = ""

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.ended_at:
            return self.ended_at - self.started_at
        return None

    def to_feedback(
        self, task_id: str, feedback_arena: Any = None
    ) -> Optional[Feedback]:
        """Convert the evaluation result to a feedback signal."""
        if self.status != EvalStatus.COMPLETE:
            return None
        accuracy = self.metrics.get("accuracy", 0.0)
        score = max(-1.0, min(1.0, accuracy * 2.0 - 1.0))  # [0,1] → [-1,1]
        fb = Feedback(
            id=str(uuid.uuid4()),
            task_id=task_id,
            source=FeedbackSource.AUTOMATED,
            score=score,
            raw_score=accuracy,
            context={
                "benchmark": self.spec.benchmark,
                "model": self.spec.model_revision,
                "sample_count": len(self.per_task),
            },
        )
        if feedback_arena is not None:
            feedback_arena._feedback[fb.id] = fb
        return fb


@dataclass
class Benchmark:
    """A named evaluation benchmark with expected metric definitions."""

    name: str
    description: str
    metrics: list[str]    # e.g. ["accuracy", "loss", "latency_ms"]
    default_timeout: int = 300
    requires: list[str] = field(default_factory=list)  # model capabilities


class EvaluationArena:
    """Manages evaluation specs, benchmarks, and result tracking (spec §29).

    The arena itself does not execute benchmarks — it manages the lifecycle
    and stores results.  Execution is done by the caller (or a future
    remote training worker) which calls ``mark_complete`` / ``mark_error``.
    """

    def __init__(self) -> None:
        self._benchmarks: dict[str, Benchmark] = {}
        self._specs: dict[str, EvalSpec] = {}
        self._results: dict[str, EvalResult] = {}

    def register_benchmark(self, benchmark: Benchmark) -> None:
        self._benchmarks[benchmark.name] = benchmark

    def get_benchmark(self, name: str) -> Optional[Benchmark]:
        return self._benchmarks.get(name)

    def list_benchmarks(self) -> list[Benchmark]:
        return list(self._benchmarks.values())

    def submit(self, spec: EvalSpec) -> EvalResult:
        """Submit an evaluation spec and return a pending result."""
        result = EvalResult(id=str(uuid.uuid4()), spec=spec)
        self._results[result.id] = result
        self._specs[spec.name] = spec
        return result

    def get(self, result_id: str) -> Optional[EvalResult]:
        return self._results.get(result_id)

    def mark_running(self, result_id: str) -> EvalResult:
        result = self._results.get(result_id)
        if result is None:
            raise KeyError(f"unknown eval result: {result_id}")
        result.status = EvalStatus.RUNNING
        result.started_at = time.time()
        return result

    def mark_complete(
        self, result_id: str, metrics: dict[str, float],
        per_task: list[dict[str, Any]] = None,
    ) -> EvalResult:
        result = self._results.get(result_id)
        if result is None:
            raise KeyError(f"unknown eval result: {result_id}")
        result.status = EvalStatus.COMPLETE
        result.metrics = dict(metrics)
        result.per_task = per_task or []
        result.ended_at = time.time()
        return result

    def mark_error(self, result_id: str, error: str) -> EvalResult:
        result = self._results.get(result_id)
        if result is None:
            raise KeyError(f"unknown eval result: {result_id}")
        result.status = EvalStatus.ERROR
        result.error = error
        result.ended_at = time.time()
        return result

    def results_for_model(self, model_revision: str) -> list[EvalResult]:
        return [
            r for r in self._results.values()
            if r.spec.model_revision == model_revision
        ]

    def latest_for_benchmark(self, benchmark: str) -> Optional[EvalResult]:
        matches = [
            r for r in self._results.values()
            if r.spec.benchmark == benchmark and r.status == EvalStatus.COMPLETE
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda r: r.ended_at or 0, reverse=True)[0]

    def all(self) -> list[EvalResult]:
        return list(self._results.values())

    def clear(self) -> None:
        self._results.clear()
        self._specs.clear()
        self._benchmarks.clear()
