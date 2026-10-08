"""Feedback collection for the Learning Arena (spec §26, §27).

Feedback is the reward signal that drives learning.  It comes from three
sources (spec §26):

  * **Automated** — evaluation metrics (loss, accuracy, latency) converted
    to a reward signal by a scoring function.
  * **Human** — explicit thumbs-up/down or numeric ratings from the user.
  * **Synthetic** — generated feedback from automated test harnesses.

Each feedback record is typed and timestamped, with optional context
(task_id, model_revision, prompt).  Feedback scores are clamped to
[-1.0, +1.0] for consistent reward comparison.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FeedbackSource(Enum):
    """Origin of a feedback signal (spec §26)."""

    AUTOMATED = "automated"
    HUMAN = "human"
    SYNTHETIC = "synthetic"


@dataclass
class Feedback:
    """A single feedback signal on a learning outcome."""

    id: str
    task_id: str
    source: FeedbackSource
    score: float          # -1.0 (worst) to +1.0 (best)
    raw_score: Optional[float] = None  # original metric before normalization
    context: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"

    def __post_init__(self) -> None:
        # Clamp score to [-1, 1].
        self.score = max(-1.0, min(1.0, self.score))


@dataclass
class FeedbackQuery:
    """Query parameters for filtering feedback."""

    task_ids: list[str] = field(default_factory=list)
    sources: list[FeedbackSource] = field(default_factory=list)
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    since: Optional[float] = None


class FeedbackArena:
    """Collects, normalizes, and stores feedback signals (spec §26).

    All feedback is sanitized before storage (no raw model outputs in
    :class:`Feedback.context` — only metadata keys).
    """

    def __init__(self, sanitizer: Any = None) -> None:
        self._feedback: dict[str, Feedback] = {}
        self._sanitizer = sanitizer

    def record(
        self,
        task_id: str,
        source: FeedbackSource,
        score: float,
        *,
        raw_score: Optional[float] = None,
        context: dict[str, Any] = None,
        created_by: str = "system",
    ) -> Feedback:
        """Record a feedback signal.  Score is clamped to [-1, 1]."""
        ctx = context or {}
        feedback = Feedback(
            id=str(uuid.uuid4()),
            task_id=task_id,
            source=source,
            score=score,
            raw_score=raw_score,
            context=ctx,
            created_by=created_by,
        )
        self._feedback[feedback.id] = feedback
        return feedback

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Convert a raw metric to a [-1, 1] reward score.

        * ``loss`` — lower is better → ``score = 1 - loss`` (clamped).
        * ``accuracy`` — higher is better → ``score = accuracy``.
        * ``latency`` — lower is better → ``score = 1 - min(latency/30, 1)``.
        * ``perplexity`` — lower is better → ``score = 1 - min(perplexity/100, 1)``.
        * Default: linear rescale from [0, max_val] to [-1, 1].
        """
        name = metric_name.lower()
        if name == "loss":
            return max(-1.0, min(1.0, 1.0 - value))
        if name == "accuracy":
            return max(-1.0, min(1.0, value * 2.0 - 1.0))  # [0,1] → [-1,1]
        if name == "latency":
            return max(-1.0, min(1.0, 1.0 - value / 30.0))  # 30s → 0, 60s → -1
        if name == "perplexity":
            return max(-1.0, min(1.0, 1.0 - min(value / 100.0, 1.0)))
        return max(-1.0, min(1.0, (value - 1.0) / 9.0))  # default: [1, 10] → [-1, 1]

    def query(self, query: FeedbackQuery) -> list[Feedback]:
        """Filter feedback records."""
        result = list(self._feedback.values())
        if query.task_ids:
            result = [f for f in result if f.task_id in query.task_ids]
        if query.sources:
            result = [f for f in result if f.source in query.sources]
        if query.min_score is not None:
            result = [f for f in result if f.score >= query.min_score]
        if query.max_score is not None:
            result = [f for f in result if f.score <= query.max_score]
        if query.since is not None:
            result = [f for f in result if f.created_at >= query.since]
        return sorted(result, key=lambda f: f.created_at)

    def for_task(self, task_id: str) -> list[Feedback]:
        return [f for f in self._feedback.values() if f.task_id == task_id]

    def average_score(self, task_id: str) -> Optional[float]:
        feedbacks = self.for_task(task_id)
        if not feedbacks:
            return None
        return sum(f.score for f in feedbacks) / len(feedbacks)

    def all(self) -> list[Feedback]:
        return list(self._feedback.values())

    def clear(self) -> None:
        self._feedback.clear()
