"""Lessons module for the Learning Arena (spec §19, §20).

Provides an arena-side view of lessons from the Teacher Node: querying,
applying, and tracking lesson effectiveness.  Lessons are the bridge
between observed experience (Teacher Node) and future task scheduling
(Learning Arena).

A lesson becomes actionable when:
  1. It has enough evidence (confidence ≥ threshold).
  2. Its category matches an upcoming task's category.
  3. The arena applies it — e.g., by adjusting resource specs, adding
     tags, or modifying task config.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from teacher_node.lesson_builder import Lesson


class LessonArena:
    """Manages lessons from the Teacher Node, applied to arena task scheduling.

    Parameters
    ----------
    lesson_builder
        The :class:`~teacher_node.lesson_builder.LessonBuilder` that
        produced the lessons we query.
    knowledge
        The :class:`~teacher_node.system_knowledge.SystemKnowledge` store
        (for re-reading committed lessons).
    """

    def __init__(self, lesson_builder: Any, knowledge: Any) -> None:
        self._builder = lesson_builder
        self._knowledge = knowledge
        self._applied: dict[str, dict[str, Any]] = {}  # lesson_id -> metadata

    def recommend(self, task_spec: Any, *, min_confidence: float = 0.3) -> list[dict[str, Any]]:
        """Return lessons relevant to a task spec, above a confidence threshold.

        A lesson is "relevant" if any of its tags match the task's category
        or tags.
        """
        relevant = []
        task_tags = set(getattr(task_spec, "tags", []) or [])
        task_tags.add(getattr(task_spec, "category", ""))
        for lesson in self._builder.all():
            if lesson.confidence < min_confidence:
                continue
            lesson_tags = set(lesson.tags)
            if lesson_tags & task_tags:
                relevant.append({
                    "lesson_id": lesson.id,
                    "hypothesis": lesson.hypothesis,
                    "action": lesson.action,
                    "confidence": lesson.confidence,
                    "evidence_count": lesson.evidence_count,
                    "tags": lesson.tags,
                })
        return sorted(relevant, key=lambda r: r["confidence"], reverse=True)

    def apply(self, lesson_id: str, task_id: str) -> bool:
        """Mark a lesson as applied to a task. Returns True if applied."""
        lesson = self._builder.get(lesson_id)
        if lesson is None:
            return False
        self._builder.apply(lesson_id)
        self._applied[lesson_id] = {
            "task_id": task_id,
            "applied_at": time.time(),
            "applied_count": self._applied.get(lesson_id, {}).get("applied_count", 0) + 1,
        }
        return True

    def track_effectiveness(self) -> dict[str, Any]:
        """Compute effectiveness metrics for applied lessons.

        Returns a summary of how many times each lesson was applied and
        whether subsequent tasks succeeded.
        """
        summary = {"total_applied": 0, "per_lesson": {}}
        for lid, meta in self._applied.items():
            entry = {
                "task_id": meta["task_id"],
                "applied_at": meta["applied_at"],
                "application_count": meta["applied_count"],
            }
            summary["per_lesson"][lid] = entry
            summary["total_applied"] += meta["applied_count"]
        return summary

    def all_applied(self) -> list[dict[str, Any]]:
        """Return all applied lesson records (for telemetry)."""
        return list(self._applied.values())

    def clear(self) -> None:
        self._applied.clear()
