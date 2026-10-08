"""Experience capture for the Learning Arena (spec §25, §26).

The ExperienceArena is the arena-side interface to the Teacher Node's
:class:`~teacher_node.experience_recorder.ExperienceRecorder`.  It captures
the outcome of every learning task — success or failure — and feeds it
back to the Teacher Node for lesson extraction.

An ``ArenaExperience`` adds arena-specific fields to the base experience
record:
  * ``task_id`` — links back to the originating :class:`Task`
  * ``model_revision`` — the model version that was tested/trained
  * ``metrics`` — structured evaluation metrics (loss, accuracy, etc.)
  * ``reward`` — the reward signal that was received (see rewards.py)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from teacher_node.experience_recorder import ExperienceRecord, TaskOutcome


@dataclass
class ArenaExperience:
    """A learning-task outcome captured in the arena."""

    id: str
    task_id: str
    category: str
    outcome: TaskOutcome
    started_at: float
    ended_at: float
    duration_seconds: float
    model_revision: Optional[str] = None
    metrics: dict[str, Any] = field(default_factory=dict)
    reward: Optional[float] = None
    error_category: str = ""
    error_sanitized: str = ""
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source: str = "arena"

    @property
    def resource_delta(self) -> dict[str, Any]:
        return {}


class ExperienceArena:
    """Captures and stores experiences from learning tasks.

    Thin adapter over the Teacher Node's experience recorder — adds arena
    metadata (model revision, metrics, reward) and delegates to the
    underlying recorder for storage and sanitization.
    """

    def __init__(self, experience_recorder: Any) -> None:
        self._recorder = experience_recorder
        self._arena_experiences: dict[str, ArenaExperience] = {}

    def capture(
        self,
        task_id: str,
        category: str,
        outcome: TaskOutcome,
        *,
        started_at: Optional[float] = None,
        ended_at: Optional[float] = None,
        model_revision: Optional[str] = None,
        metrics: dict[str, Any] = None,
        reward: Optional[float] = None,
        error_message: str = "",
        error_category: str = "",
        tags: list[str] = None,
        confidence: float = 0.5,
        source: str = "arena",
    ) -> ArenaExperience:
        """Capture a task outcome as an arena experience.

        Also delegates to the underlying :class:`ExperienceRecorder` so the
        Teacher Node can build lessons from it.
        """
        now = time.time()
        started_at = now if started_at is None else started_at
        ended_at = now if ended_at is None else ended_at

        # Delegate to the teacher node's recorder (for lesson extraction).
        self._recorder.record(
            task_id=task_id, category=category, outcome=outcome,
            started_at=started_at, ended_at=ended_at,
            error_message=error_message, error_category=error_category,
            tags=tags or [], confidence=confidence,
            source=source,
        )

        # Store arena-specific metadata.
        exp = ArenaExperience(
            id=str(uuid.uuid4()),
            task_id=task_id, category=category, outcome=outcome,
            started_at=started_at, ended_at=ended_at,
            duration_seconds=round(ended_at - started_at, 3),
            model_revision=model_revision,
            metrics=metrics or {}, reward=reward,
            error_category=error_category,
            error_sanitized=_safe_error(error_message),
            tags=tags or [], confidence=confidence, source=source,
        )
        self._arena_experiences[exp.id] = exp
        return exp

    def get(self, exp_id: str) -> Optional[ArenaExperience]:
        return self._arena_experiences.get(exp_id)

    def all(self) -> list[ArenaExperience]:
        return list(self._arena_experiences.values())

    def by_task(self, task_id: str) -> list[ArenaExperience]:
        return [e for e in self._arena_experiences.values() if e.task_id == task_id]

    def by_outcome(self, outcome: TaskOutcome) -> list[ArenaExperience]:
        return [e for e in self._arena_experiences.values() if e.outcome == outcome]

    def by_category(self, category: str) -> list[ArenaExperience]:
        return [e for e in self._arena_experiences.values() if e.category == category]

    def clear(self) -> None:
        self._arena_experiences.clear()
        self._recorder.clear()


def _safe_error(error: str) -> str:
    """Minimize error text — strip anything that looks like a secret (spec §23)."""
    if not error:
        return ""
    import re
    # Basic redaction of key-like patterns.
    redacted = re.sub(r"(?:sk-|hf_|gh[pousr]_)[A-Za-z0-9_\-]{8,}", "[REDACTED]", error)
    redacted = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "[REDACTED]", redacted)
    return redacted
