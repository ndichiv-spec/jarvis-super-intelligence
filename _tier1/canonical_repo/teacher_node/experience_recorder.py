"""Experience recorder for the Teacher Node (spec §25, §55).

Captures task outcomes — successes and failures — as structured experience
records.  Each record is sanitized before storage (spec §23) so that
secrets/PII never reach the knowledge base or lessons.

An ``ExperienceRecord`` captures:
  * The task category and outcome (success/failure).
  * Resource deltas (CPU/memory/disk before → after).
  * Error category (not raw error text — that is stored sanitized).
  * A confidence-weighted tag set for lesson extraction.
  * Provenance: timestamps, source component, environment markers.

The recorder is the single ingestion point for the Teacher Node — all
observations, task results, and incident reports flow through here.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskOutcome(Enum):
    """High-level outcome of a learning task."""

    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ExperienceRecord:
    """A single captured experience (task outcome)."""

    id: str
    task_id: str
    category: str            # e.g. "training", "evaluation", "synthesis"
    outcome: TaskOutcome
    started_at: float
    ended_at: float
    duration_seconds: float
    resource_before: dict[str, Any] = field(default_factory=dict)
    resource_after: dict[str, Any] = field(default_factory=dict)
    error_category: str = ""  # e.g. "OOM", "NetworkError", "ValidationError"
    error_sanitized: str = ""  # redacted error message
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source: str = ""  # which component recorded this

    @property
    def resource_delta(self) -> dict[str, Any]:
        """Compute resource deltas (after - before)."""
        deltas = {}
        for key in set(self.resource_before) | set(self.resource_after):
            b = self.resource_before.get(key, 0)
            a = self.resource_after.get(key, 0)
            if isinstance(b, (int, float)) and isinstance(a, (int, float)):
                deltas[key] = round(a - b, 2)
        return deltas


class ExperienceRecorder:
    """Records task experiences into the knowledge store (spec §25).

    All text content is sanitized via the injected :class:`Sanitizer`
    before being stored (spec §23, §55).
    """

    def __init__(self, knowledge: Any, sanitizer: Any) -> None:
        self._knowledge = knowledge
        self._sanitizer = sanitizer
        self._records: dict[str, ExperienceRecord] = {}

    def record(
        self,
        task_id: str,
        category: str,
        outcome: TaskOutcome,
        *,
        started_at: Optional[float] = None,
        ended_at: Optional[float] = None,
        resource_before: dict[str, Any] = None,
        resource_after: dict[str, Any] = None,
        error_message: str = "",
        error_category: str = "",
        tags: list[str] = None,
        confidence: float = 0.5,
        source: str = "",
        raw_payload: dict[str, Any] = None,
    ) -> ExperienceRecord:
        """Record a task experience.

        Parameters
        ----------
        task_id
            Identifier of the task that was executed.
        category
            Learning category: ``training``, ``evaluation``, ``synthesis``,
            ``observation``, etc.
        outcome
            Success, failure, timeout, etc.
        error_message
            Raw (unredacted) error message — will be sanitized before storage.
        raw_payload
            Any additional raw context — will be sanitized before storage.
        """
        now = time.time()
        started_at = now if started_at is None else started_at
        ended_at = now if ended_at is None else ended_at

        # Sanitize all text content.
        sanitized_error = ""
        if error_message:
            sanitized_error = self._sanitizer.sanitize(error_message)
        if not error_category and error_message:
            error_category = self._categorize_error(error_message)

        record = ExperienceRecord(
            id=str(uuid.uuid4()),
            task_id=task_id,
            category=category,
            outcome=outcome,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=round(ended_at - started_at, 3),
            resource_before=resource_before or {},
            resource_after=resource_after or {},
            error_category=error_category,
            error_sanitized=sanitized_error,
            tags=tags or [],
            confidence=confidence,
            source=source,
        )
        self._records[record.id] = record

        # Store in the knowledge base (also sanitized).
        self._knowledge.add(
            category="experience",
            key=record.id,
            value={
                "task_id": task_id,
                "category": category,
                "outcome": outcome.value,
                "duration_seconds": record.duration_seconds,
                "resource_delta": record.resource_delta,
                "error_category": error_category,
                "tags": tags or [],
                "confidence": confidence,
            },
            confidence=confidence,
            tags=["experience", category, outcome.value] + (tags or []),
            source_ref=f"experience_recorder:{source or 'unknown'}",
        )

        return record

    def get(self, record_id: str) -> Optional[ExperienceRecord]:
        return self._records.get(record_id)

    def all(self) -> list[ExperienceRecord]:
        return list(self._records.values())

    def by_category(self, category: str) -> list[ExperienceRecord]:
        return [r for r in self._records.values() if r.category == category]

    def by_outcome(self, outcome: TaskOutcome) -> list[ExperienceRecord]:
        return [r for r in self._records.values() if r.outcome == outcome]

    def clear(self) -> None:
        self._records.clear()

    @staticmethod
    def _categorize_error(error: str) -> str:
        """Heuristic error categorisation (no PII leaked)."""
        e = error.lower()
        if any(w in e for w in ("memory", "oom", "out of memory", "allocate")):
            return "MemoryError"
        if any(w in e for w in ("timeout", "timed out", "deadline")):
            return "TimeoutError"
        if any(w in e for w in ("network", "connection", "refused", "unreachable")):
            return "NetworkError"
        if any(w in e for w in ("permission", "forbidden", "unauthorized", "403", "401")):
            return "AuthError"
        if any(w in e for w in ("validation", "schema", "parse", "invalid")):
            return "ValidationError"
        return "UnknownError"
