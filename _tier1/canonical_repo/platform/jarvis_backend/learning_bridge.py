"""JARVIS Learning Bridge — makes Learning Arena artifacts searchable (spec §41).

Global Search must be able to search across the learning lifecycle:
experiences, lessons, feedback, datasets, training runs, model revisions.

The Learning Arena arenas are in-memory objects.  This module holds shared,
lazily-instantiated arena singletons so that both the Search controller and any
orchestrator (e.g. Phase6Operations) can populate + query the same live state.
If the ``learning_arena`` / ``teacher_node`` packages are not importable, every
search degrades to "UNAVAILABLE" (spec §56) rather than fabricating results.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.learning_bridge")

_ARENAS: Optional[Dict[str, Any]] = None


def _safe_import():
    """Import learning arena classes; return None if unavailable."""
    try:
        from learning_arena.datasets import DatasetArena
        from learning_arena.training_runs import TrainingRunArena
        from learning_arena.model_revisions import ModelRevisionArena
        from learning_arena.evaluations import EvaluationArena
        from learning_arena.feedback import FeedbackArena
        from learning_arena.experiences import ExperienceArena
        from learning_arena.failures import FailureArena
        from learning_arena.rewards import RewardEngine
        return {
            "DatasetArena": DatasetArena,
            "TrainingRunArena": TrainingRunArena,
            "ModelRevisionArena": ModelRevisionArena,
            "EvaluationArena": EvaluationArena,
            "FeedbackArena": FeedbackArena,
            "ExperienceArena": ExperienceArena,
            "FailureArena": FailureArena,
            "RewardEngine": RewardEngine,
        }
    except Exception as exc:  # noqa: BLE001 — learning arena is optional
        logger.debug("learning_arena not importable: %s", exc)
        return None


class _StubRecorder:
    """Minimal stand-in for ExperienceRecorder used only for read-only search.

    The real :class:`teacher_node.experience_recorder.ExperienceRecorder` is
    injected by the orchestrator; for search we never record, only read.
    """

    def record(self, **kwargs: Any) -> None:
        pass

    def clear(self) -> None:
        pass


def get_learning_arenas() -> Dict[str, Any]:
    """Return the shared (singleton) learning arena instances.

    Self-contained arenas (DatasetArena, etc.) are instantiated directly.
    TrainingRunArena needs sub-arena dependencies, which are wired from the
    same shared set.  LessonArena requires teacher_node deps and is handled
    separately by :func:`get_lessons`.
    """
    global _ARENAS
    if _ARENAS is not None:
        return _ARENAS
    _ARENAS = {}
    deps = _safe_import()
    if deps is None:
        return _ARENAS
    # Self-contained arenas.
    _ARENAS["feedback"] = deps["FeedbackArena"]()
    _ARENAS["failures"] = deps["FailureArena"]()
    _ARENAS["evaluations"] = deps["EvaluationArena"]()
    _ARENAS["model_revisions"] = deps["ModelRevisionArena"]()
    _ARENAS["datasets"] = deps["DatasetArena"]()
    _ARENAS["experiences"] = deps["ExperienceArena"](_StubRecorder())
    # RewardEngine needs the feedback arena.
    _rewards = deps["RewardEngine"](feedback_arena=_ARENAS["feedback"])
    # TrainingRunArena depends on the above.
    try:
        _ARENAS["training_runs"] = deps["TrainingRunArena"](
            _ARENAS["experiences"], _ARENAS["feedback"],
            _ARENAS["failures"], _ARENAS["evaluations"], _rewards,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("TrainingRunArena init failed: %s", exc)
        _ARENAS["training_runs"] = None
    return _ARENAS


def reset_learning_arenas() -> None:
    """Drop the shared arena singletons (used by tests)."""
    global _ARENAS
    _ARENAS = None


def _as_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {"repr": str(obj)}


def get_learning_items() -> List[Dict[str, Any]]:
    """Flatten all learning artifacts into searchable item dicts.

    Each item carries a ``_learning_type`` (``lesson``, ``dataset``,
    ``training_run``, ``model_revision``, ``evaluation``, ``feedback``,
    ``experience``) plus the fields needed for text search.
    """
    items: List[Dict[str, Any]] = []
    arenas = get_learning_arenas()
    if not arenas:
        return items

    # Lessons (requires teacher_node lesson_builder)
    lessons = get_lessons()
    for lsn in lessons:
        items.append({**_as_dict(lsn), "_learning_type": "lesson",
                      "_learning_key": lsn.get("id", lsn.get("key", ""))})

    # Datasets
    arena = arenas.get("datasets")
    if arena is not None:
        for ds in arena.all():
            d = _as_dict(ds)
            items.append({**d, "_learning_type": "dataset", "_learning_key": d.get("id", "")})

    # Training runs
    arena = arenas.get("training_runs")
    if arena is not None:
        for tr in arena.all():
            d = _as_dict(tr)
            items.append({**d, "_learning_type": "training_run", "_learning_key": d.get("id", "")})

    # Model revisions
    arena = arenas.get("model_revisions")
    if arena is not None:
        for mr in arena.all():
            d = _as_dict(mr)
            items.append({**d, "_learning_type": "model_revision", "_learning_key": d.get("id", "")})

    # Evaluations
    arena = arenas.get("evaluations")
    if arena is not None:
        for ev in arena.all():
            d = _as_dict(ev)
            items.append({**d, "_learning_type": "evaluation", "_learning_key": d.get("id", "")})

    # Feedback
    arena = arenas.get("feedback")
    if arena is not None:
        for fb in arena.all():
            d = _as_dict(fb)
            items.append({**d, "_learning_type": "feedback", "_learning_key": d.get("id", "")})

    # Experiences
    arena = arenas.get("experiences")
    if arena is not None:
        for ex in arena.all():
            d = _as_dict(ex)
            items.append({**d, "_learning_type": "experience", "_learning_key": d.get("id", "")})

    return items


def get_lessons() -> List[Dict[str, Any]]:
    """Best-effort retrieval of lessons from the Teacher Node."""
    try:
        from teacher_node.lesson_builder import LessonBuilder
        from teacher_node.system_knowledge import SystemKnowledge
        from teacher_node.sanitizer import Sanitizer
        builder = LessonBuilder(knowledge=SystemKnowledge(sanitizer=Sanitizer()))
        out = []
        for lesson in builder.all():
            out.append({
                "id": getattr(lesson, "id", str(getattr(lesson, "confidence", ""))),
                "hypothesis": getattr(lesson, "hypothesis", ""),
                "action": getattr(lesson, "action", ""),
                "confidence": getattr(lesson, "confidence", 0.0),
                "evidence_count": getattr(lesson, "evidence_count", 0),
                "category": getattr(lesson, "category", ""),
                "tags": getattr(lesson, "tags", []),
            })
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("Lesson retrieval unavailable: %s", exc)
        return []


def get_learning_searchable_items(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return learning artifacts as searchable item dicts, filtered to ``user_id``.

    Thin wrapper over :func:`get_learning_items` that applies per-user filtering
    (spec §15) so the search endpoint only returns artifacts the caller is
    allowed to see.  Lessons are system-wide (not user-scoped) so they always
    pass the filter.
    """
    items = get_learning_items()
    if not user_id:
        return items
    visible: List[Dict[str, Any]] = []
    for item in items:
        # Lessons have no user_id (system-wide knowledge) — always visible.
        if item.get("_learning_type") == "lesson":
            visible.append(item)
            continue
        owner = item.get("user_id")
        if owner is None or owner == "system" or owner == user_id:
            visible.append(item)
    return visible
