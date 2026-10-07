"""Reward computation for the Learning Arena (spec §26, §27).

Computes a scalar reward signal from feedback, experience outcomes, and
resource efficiency.  This reward drives task prioritization and lesson
trust in the arena.

Reward model (spec §27):
  * **Feedback** — primary signal from :class:`~learning_arena.feedback.FeedbackArena`.
  * **Outcome** — binary: +1.0 for success, -0.5 for failure, -0.25 for timeout.
  * **Efficiency** — resource cost vs. expected cost (efficiency bonus).
  * **Novelty** — bonus for tasks on untried model revisions.
  * **Trust decay** — lessons applied with low confidence have lower weight.

Final reward is a weighted combination, clamped to [-1, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .feedback import Feedback, FeedbackSource, FeedbackArena


@dataclass
class RewardComponents:
    """Breakdown of a computed reward for transparency."""

    total: float
    feedback: float = 0.0
    outcome: float = 0.0
    efficiency: float = 0.0
    novelty: float = 0.0
    trust: float = 0.0
    weights: dict[str, float] = None  # type: ignore[assignment]


# Default reward weights (spec §27).
DEFAULT_WEIGHTS = {
    "feedback": 0.5,
    "outcome": 0.3,
    "efficiency": 0.1,
    "novelty": 0.05,
    "trust": 0.05,
}

# Outcome → reward mapping.
OUTCOME_REWARDS = {
    "success": 1.0,
    "failure": -0.5,
    "timeout": -0.25,
    "cancelled": -0.1,
    "skipped": 0.0,
}


class RewardEngine:
    """Computes reward signals for learning tasks (spec §26, §27).

    Parameters
    ----------
    feedback_arena
        The :class:`FeedbackArena` that stores feedback signals.
    weights
        Custom reward component weights (defaults to DEFAULT_WEIGHTS).
    """

    def __init__(
        self,
        feedback_arena: FeedbackArena,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self._feedback_arena = feedback_arena
        self._weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    def compute(
        self,
        task_id: str,
        outcome: str,
        *,
        resource_cost: Optional[float] = None,
        expected_cost: Optional[float] = None,
        is_novel: bool = False,
        lesson_confidence: float = 1.0,
    ) -> RewardComponents:
        """Compute the reward for a completed task.

        Parameters
        ----------
        task_id
            The task to compute reward for.
        outcome
            Task outcome string: "success", "failure", "timeout", etc.
        resource_cost
            Actual resource cost (e.g. GPU-hours).  Lower is better.
        expected_cost
            Expected resource cost for this task type.
        is_novel
            Whether the task used a novel model/config (bonus).
        lesson_confidence
            Confidence of the lesson that spawned this task (trust weight).
        """
        # 1. Feedback component
        feedback_score = 0.0
        feedbacks = self._feedback_arena.for_task(task_id)
        if feedbacks:
            feedback_score = sum(f.score for f in feedbacks) / len(feedbacks)

        # 2. Outcome component
        outcome_reward = OUTCOME_REWARDS.get(outcome.lower(), 0.0)

        # 3. Efficiency component
        efficiency = 0.0
        if resource_cost is not None and expected_cost is not None and expected_cost > 0:
            # Under budget → positive; over budget → negative.
            ratio = resource_cost / expected_cost
            efficiency = max(-1.0, min(1.0, 1.0 - ratio))

        # 4. Novelty bonus
        novelty = 0.5 if is_novel else 0.0

        # 5. Trust weight (from lesson confidence)
        trust = lesson_confidence

        # Weighted total
        w = self._weights
        total = (
            w["feedback"] * feedback_score
            + w["outcome"] * outcome_reward
            + w["efficiency"] * efficiency
            + w["novelty"] * novelty
            + w["trust"] * trust
        )
        total = max(-1.0, min(1.0, total))

        return RewardComponents(
            total=total,
            feedback=round(feedback_score, 4),
            outcome=round(outcome_reward, 4),
            efficiency=round(efficiency, 4),
            novelty=round(novelty, 4),
            trust=round(trust, 4),
            weights=dict(w),
        )

    def rank_tasks(
        self,
        task_rewards: list[tuple[str, RewardComponents]],
    ) -> list[tuple[str, float]]:
        """Rank tasks by total reward (descending)."""
        return sorted(
            [(tid, r.total) for tid, r in task_rewards],
            key=lambda x: x[1],
            reverse=True,
        )

    def should_prune(self, reward: RewardComponents, *, threshold: float = -0.5) -> bool:
        """Decide whether to prune a task based on its reward (spec §27)."""
        return reward.total < threshold
