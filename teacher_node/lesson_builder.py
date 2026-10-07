"""Lesson builder for the Teacher Node (spec §19, §20, §23).

Extracts actionable lessons from accumulated experience records.  A
``Lesson`` is a structured, confidence-weighted insight that the Teacher
Node can apply to future decisions — e.g., "training fails when VRAM > 90%"
or "model X times out on sequences > 2K tokens".

Process:
  1. **Collect** recent experiences from the recorder.
  2. **Pattern-match** — group by error category, resource delta, tags.
  3. **Extract** — produce candidate lessons with evidence (count, confidence).
  4. **Sanitize** — all lesson text is sanitized via the :class:`Sanitizer`.
  5. **Commit** — store in :class:`SystemKnowledge` as ``category="lesson"``.

Lessons are **actionable hypotheses**, not facts — each carries a confidence
score and an evidence count so the Teacher Node can decide when to trust them.
"""

from __future__ import annotations

import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from .experience_recorder import ExperienceRecord, TaskOutcome
from .resource_governor import GovernorState


@dataclass
class Lesson:
    """A structured, confidence-weighted lesson from experience."""

    id: str
    hypothesis: str           # human-readable, sanitized
    category: str             # e.g. "resource", "timeout", "validation"
    action: str               # recommended action
    confidence: float         # 0.0 — 1.0
    evidence_count: int       # number of supporting experiences
    evidence_ids: list[str]   # IDs of supporting ExperienceRecords
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    applied_count: int = 0    # how many times this lesson was applied

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hypothesis": self.hypothesis,
            "category": self.category,
            "action": self.action,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "tags": self.tags,
            "applied_count": self.applied_count,
        }


class LessonBuilder:
    """Extracts lessons from experience records (spec §19, §20).

    Parameters
    ----------
    knowledge
        The :class:`SystemKnowledge` store.
    sanitizer
        The :class:`Sanitizer` — all lesson text is sanitized before storage.
    """

    def __init__(self, knowledge: Any, sanitizer: Any) -> None:
        self._knowledge = knowledge
        self._sanitizer = sanitizer
        self._lessons: dict[str, Lesson] = {}

    # ------------------------------------------------------------------ #
    # Lesson extraction
    # ------------------------------------------------------------------ #
    def build_from_experiences(
        self,
        experiences: list[ExperienceRecord],
        *,
        min_evidence: int = 2,
    ) -> list[Lesson]:
        """Extract candidate lessons from a batch of experiences.

        Rules:
          * Group failures by ``error_category`` — if ≥ ``min_evidence`` share
            a category, emit a lesson.
          * Group by resource bottleneck (high CPU/memory/disk/vram) — if ≥
            ``min_evidence`` failures occurred under similar thresholds,
            emit a lesson.
          * Compute confidence as ``min(evidence_count / 10, 0.95)``.
        """
        lessons: list[Lesson] = []

        if not experiences:
            return lessons

        # 1. Error-category clustering.
        failures = [e for e in experiences if e.outcome == TaskOutcome.FAILURE]
        by_category: dict[str, list[ExperienceRecord]] = {}
        for f in failures:
            cat = f.error_category or "UnknownError"
            by_category.setdefault(cat, []).append(f)

        for cat, recs in by_category.items():
            if len(recs) >= min_evidence:
                lesson = self._make_lesson(
                    category="error",
                    hypothesis=(
                        f"Tasks in this category fail with {cat} "
                        f"({len(recs)} occurrences)."
                    ),
                    action=f"Investigate and mitigate {cat} before retrying.",
                    confidence=self._confidence(len(recs)),
                    evidence_ids=[r.id for r in recs],
                    tags=[cat, "failure"],
                )
                lessons.append(lesson)

        # 2. Resource-bottleneck clustering.
        for metric in ("cpu_percent", "memory_percent", "disk_percent", "gpu_percent"):
            bottlenecks = [
                e for e in failures
                if e.resource_after.get(metric, 0) > e.resource_before.get(metric, 0)
                and isinstance(e.resource_after.get(metric), (int, float))
            ]
            if len(bottlenecks) >= min_evidence:
                peak = max(e.resource_after.get(metric, 0) for e in bottlenecks)
                lesson = self._make_lesson(
                    category="resource",
                    hypothesis=(
                        f"Failures correlate with high {metric} "
                        f"(peak: {peak:.1f}%)."
                    ),
                    action=(
                        f"Throttle or pause when {metric} exceeds "
                        f"{peak * 0.8:.0f}%."
                    ),
                    confidence=self._confidence(len(bottlenecks)),
                    evidence_ids=[e.id for e in bottlenecks],
                    tags=[metric, "resource", "failure"],
                )
                lessons.append(lesson)

        # 3. Timeout pattern.
        timeouts = [e for e in experiences if e.outcome == TaskOutcome.TIMEOUT]
        if len(timeouts) >= min_evidence:
            avg_duration = sum(e.duration_seconds for e in timeouts) / len(timeouts)
            lesson = self._make_lesson(
                category="timeout",
                hypothesis=(
                    f"Tasks in this batch average {avg_duration:.1f}s before timing out."
                ),
                action="Reduce task scope or increase timeout budget.",
                confidence=self._confidence(len(timeouts)),
                evidence_ids=[e.id for e in timeouts],
                tags=["timeout", "performance"],
            )
            lessons.append(lesson)

        # 4. Success patterns.
        successes = [e for e in experiences if e.outcome == TaskOutcome.SUCCESS]
        if len(successes) >= min_evidence:
            avg_duration = sum(e.duration_seconds for e in successes) / len(successes)
            lesson = self._make_lesson(
                category="success",
                hypothesis=(
                    f"Successes average {avg_duration:.1f}s; "
                    f"resource usage stays within limits."
                ),
                action="Use these parameters as a baseline for future runs.",
                confidence=self._confidence(len(successes)),
                evidence_ids=[e.id for e in successes],
                tags=["success", "baseline"],
            )
            lessons.append(lesson)

        # Deduplicate + commit.
        seen_hypotheses: set[str] = set()
        committed: list[Lesson] = []
        for lesson in lessons:
            if lesson.hypothesis in seen_hypotheses:
                continue
            seen_hypotheses.add(lesson.hypothesis)
            self._commit(lesson)
            committed.append(lesson)
        return committed

    def _make_lesson(
        self,
        category: str,
        hypothesis: str,
        action: str,
        confidence: float,
        evidence_ids: list[str],
        tags: list[str],
    ) -> Lesson:
        lesson = Lesson(
            id=str(uuid.uuid4()),
            hypothesis=self._sanitizer.sanitize(hypothesis),
            category=category,
            action=self._sanitizer.sanitize(action),
            confidence=confidence,
            evidence_count=len(evidence_ids),
            evidence_ids=evidence_ids,
            tags=tags,
        )
        self._lessons[lesson.id] = lesson
        return lesson

    def _commit(self, lesson: Lesson) -> None:
        """Store the lesson in the knowledge base."""
        self._knowledge.add(
            category="lesson",
            key=lesson.id,
            value=lesson.to_dict(),
            confidence=lesson.confidence,
            tags=["lesson", lesson.category] + lesson.tags,
            source_ref="lesson_builder",
        )

    @staticmethod
    def _confidence(evidence_count: int) -> float:
        """Logistic-style confidence: saturates near 0.95 with enough evidence."""
        import math

        return min(0.95, 1.0 / (1.0 + math.exp(-(evidence_count - 3))))

    # ------------------------------------------------------------------ #
    # Lesson retrieval
    # ------------------------------------------------------------------ #
    def get(self, lesson_id: str) -> Optional[Lesson]:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    def by_category(self, category: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.category == category]

    def apply(self, lesson_id: str) -> bool:
        """Mark a lesson as applied (increment counter)."""
        lesson = self._lessons.get(lesson_id)
        if lesson is None:
            return False
        lesson.applied_count += 1
        return True

    def clear(self) -> None:
        self._lessons.clear()
