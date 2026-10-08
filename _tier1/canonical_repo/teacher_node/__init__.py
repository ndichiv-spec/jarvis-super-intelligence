"""JARVIS Teacher Node — automated learning from observation (spec §17-§30).

The Teacher Node is the metacognitive layer that watches the machine,
observes the repo, records experiences, and extracts actionable lessons.
It never trains models directly — it feeds intelligence to the Learning Arena
and the resource governor.

Components:
  * :mod:`privacy_filter`    — detects & redacts PII and secrets (spec §22)
  * :mod:`sanitizer`         — context-aware sanitization gatekeeper (spec §23)
  * :mod:`system_knowledge`  — append-only, indexed knowledge store (spec §18)
  * :mod:`machine_observer`  — samples system resources (CPU/mem/disk/GPU)
  * :mod:`repo_observer`     — watches git changes for learning signals
  * :mod:`experience_recorder` — captures task outcomes (spec §25)
  * :mod:`lesson_builder`    — extracts confidence-weighted lessons (spec §19)
  * :mod:`resource_governor` — enforces background-learning resource limits (spec §18)

Usage::

    from teacher_node import TeacherNode
    from teacher_node.resource_governor import ResourceGovernor

    governor = ResourceGovernor()
    teacher = TeacherNode(repo_path="/path/to/jarvis")
    teacher.start()  # begins background observation
    # ...
    teacher.stop()
"""

from __future__ import annotations

from .experience_recorder import (
    ExperienceRecord,
    ExperienceRecorder,
    TaskOutcome,
)
from .lesson_builder import Lesson, LessonBuilder
from .machine_observer import MachineObserver, SystemMetrics
from .privacy_filter import Detection, DetectionKind, PrivacyFilter, RedactionResult
from .repo_observer import RepoChange, RepoObserver
from .resource_governor import (
    GovernorConfig,
    GovernorState,
    ResourceGovernor,
    ResourceSnapshot,
)
from .sanitizer import SanitizationReport, Sanitizer
from .system_knowledge import KnowledgeEntry, SystemKnowledge

__version__ = "0.1.0"

__all__ = [
    "Detection",
    "DetectionKind",
    "ExperienceRecord",
    "ExperienceRecorder",
    "GovernorConfig",
    "GovernorState",
    "KnowledgeEntry",
    "Lesson",
    "LessonBuilder",
    "MachineObserver",
    "RedactionResult",
    "RepoChange",
    "RepoObserver",
    "ResourceGovernor",
    "ResourceSnapshot",
    "SanitizationReport",
    "Sanitizer",
    "SystemKnowledge",
    "SystemMetrics",
    "TaskOutcome",
]
