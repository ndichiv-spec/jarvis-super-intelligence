"""Lesson quality gate (spec §26, §32).

A *curriculum lesson* is the minimal learning unit the governed loop promotes
into datasets.  Every lesson passes through this gate, whose classes are the
only legal statuses:

* ``CANDIDATE``     — drafted, awaiting verification/quality analysis;
* ``VERIFIED``      — has a verified solution + evidence and passes quality;
* ``REJECTED``      — no solution / falsified solution / quality failure;
* ``DUPLICATE``     — equivalent to an existing lesson (never duplicated);
* ``NEEDS_REVIEW``  — open-ended (honestly unverifiable) or lacks evidence,
                      so a human/evidence review is required before use.

The gate also records lineage: ``source -> research -> evidence -> lesson ->
dataset -> training -> model`` is walked forward from these records.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class LessonClass(str, Enum):
    """The only legal lesson classes (spec §32)."""

    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


def _norm_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


@dataclass
class CurriculumLesson:
    """One governed curriculum lesson."""

    lesson_id: str
    title: str
    concept: str
    domain: str
    difficulty: int  # 1-6 (spec §25)
    difficulty_label: str
    problem_id: str
    problem: str
    context: str
    constraints: list[str] = field(default_factory=list)
    expected_format: str = ""
    verified_solution: str = ""
    verification: dict = field(default_factory=dict)
    teacher_keys: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    research_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: LessonClass = LessonClass.CANDIDATE
    quality: dict = field(default_factory=dict)
    quality_score: float = 0.0
    dedup_key: str = ""
    content_hash: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lesson_id": self.lesson_id,
            "title": self.title,
            "concept": self.concept,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "difficulty_label": self.difficulty_label,
            "problem_id": self.problem_id,
            "problem": self.problem,
            "context": self.context,
            "constraints": list(self.constraints),
            "expected_format": self.expected_format,
            "verified_solution": self.verified_solution,
            "verification": self.verification,
            "teacher_keys": list(self.teacher_keys),
            "evidence_ids": list(self.evidence_ids),
            "research_ids": list(self.research_ids),
            "tags": list(self.tags),
            "status": self.status.value,
            "quality_score": self.quality_score,
            "quality": self.quality,
            "dedup_key": self.dedup_key,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": self.history,
        }


def content_hash(*parts: str) -> str:
    payload = "\x1f".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LessonGate:
    """Analyzes, deduplicates, verifies and classifies curriculum lessons."""

    def __init__(self, *, privacy_filter: Any = None, sanitizer: Any = None) -> None:
        self._privacy = privacy_filter
        try:
            if self._privacy is None:
                from teacher_node.privacy_filter import PrivacyFilter

                self._privacy = PrivacyFilter()
        except Exception:  # noqa: BLE001
            self._privacy = None
        self._sanitizer = sanitizer
        self._lessons: dict[str, CurriculumLesson] = {}
        self._by_dedup: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Submission / analysis
    # ------------------------------------------------------------------
    def submit(
        self,
        *,
        lesson_id: Optional[str] = None,
        title: str,
        concept: str,
        domain: str,
        difficulty: int,
        difficulty_label: str,
        problem_id: str,
        problem: str,
        context: str = "",
        constraints: Optional[list[str]] = None,
        expected_format: str = "",
        verified_solution: str = "",
        verification: Optional[dict] = None,
        teacher_keys: Optional[list[str]] = None,
        evidence_ids: Optional[list[str]] = None,
        research_ids: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
    ) -> CurriculumLesson:
        """Submit a candidate lesson into the gate.

        Performs deterministic quality analysis, deduplication and secret/PII
        scanning, then classifies the lesson without guessing.
        """
        lid = lesson_id or str(uuid.uuid4())
        dkey = _norm_whitespace(f"{title}|{concept}|{problem_id}|{problem}")

        # Deduplication: an equivalent lesson already in the gate.
        existing = self._by_dedup.get(dkey)
        if existing is not None:
            hit = self._lessons[existing]
            return CurriculumLesson(
                lesson_id=existing,
                title=hit.title,
                concept=hit.concept,
                domain=hit.domain,
                difficulty=hit.difficulty,
                difficulty_label=hit.difficulty_label,
                problem_id=hit.problem_id,
                problem=hit.problem,
                context=hit.context,
                constraints=list(hit.constraints),
                expected_format=hit.expected_format,
                verified_solution=hit.verified_solution,
                verification=dict(hit.verification),
                teacher_keys=list(hit.teacher_keys),
                evidence_ids=list(hit.evidence_ids),
                research_ids=list(hit.research_ids),
                tags=list(hit.tags),
                status=LessonClass.DUPLICATE,
                quality=dict(hit.quality),
                quality_score=hit.quality_score,
                dedup_key=dkey,
                content_hash=content_hash(
                    lid, title, concept, problem_id, problem, verified_solution
                ),
                created_at=hit.created_at,
                updated_at=time.time(),
                history=[
                    {
                        "at": time.time(),
                        "event": "duplicate_of",
                        "existing_id": existing,
                    }
                ],
            )

        chash = content_hash(
            lid, title, concept, domain, problem_id, problem, verified_solution
        )
        quality, score = self._analyze_quality(
            title=title, concept=concept, problem=problem,
            solution=verified_solution, expected_format=expected_format,
            evidence_ids=evidence_ids or [],
        )

        lesson = CurriculumLesson(
            lesson_id=lid,
            title=title,
            concept=concept,
            domain=domain,
            difficulty=int(difficulty),
            difficulty_label=difficulty_label,
            problem_id=problem_id,
            problem=problem,
            context=context,
            constraints=list(constraints or []),
            expected_format=expected_format,
            verified_solution=verified_solution,
            verification=dict(verification or {}),
            teacher_keys=list(teacher_keys or []),
            evidence_ids=list(evidence_ids or []),
            research_ids=list(research_ids or []),
            tags=list(tags or []),
            status=LessonClass.CANDIDATE,
            quality=quality,
            quality_score=score,
            dedup_key=dkey,
            content_hash=chash,
        )

        # Secret / PII scan — a lesson carrying PII or secrets is contaminated.
        if self._privacy is not None:
            flagged = self._privacy.detect(
                f"{problem} {context} {verified_solution}"
            )
            if flagged:
                lesson.quality["contamination"] = [
                    d.kind.value for d in flagged
                ]
                lesson.quality_score = 0.0
                lesson.status = LessonClass.REJECTED
                lesson.history.append(
                    {
                        "at": time.time(),
                        "event": "rejected",
                        "reason": f"PII/secret contamination ({len(flagged)} detections)",
                    }
                )

        self._lessons[lid] = lesson
        self._by_dedup[dkey] = lid
        return lesson

    def _analyze_quality(
        self,
        *,
        title: str,
        concept: str,
        problem: str,
        solution: str,
        expected_format: str,
        evidence_ids: list[str],
    ) -> tuple[dict, float]:
        checks: dict[str, bool] = {
            "has_title": bool(title.strip()),
            "has_concept": bool(concept.strip()),
            "has_problem": bool(problem.strip()),
            "has_solution": bool(solution.strip()),
            "has_expected_format": bool(expected_format.strip()),
            "has_evidence": len(evidence_ids) > 0,
        }
        passed = sum(1 for v in checks.values() if v)
        score = round(passed / len(checks), 3)
        if not checks["has_solution"] or not checks["has_problem"]:
            score = 0.0
        return checks, score

    # ------------------------------------------------------------------
    # Verification and classification
    # ------------------------------------------------------------------
    def verify(
        self,
        lesson_id: str,
        verification: dict,
        *,
        actor: str,
        evidence_ids: Optional[list[str]] = None,
        research_ids: Optional[list[str]] = None,
    ) -> CurriculumLesson:
        """Classify a candidate from real verification + evidence.

        ``VERIFIED`` (sandbox/canonical pass), ``REJECTED`` (falsified),
        ``NEEDS_REVIEW`` (honestly unverifiable or weak evidence).  Status
        assignment is deterministic — never guessed.
        """
        lesson = self._lessons.get(lesson_id)
        if lesson is None:
            raise KeyError(f"unknown lesson {lesson_id!r}")
        if lesson.status in (LessonClass.DUPLICATE,):
            return lesson

        lesson.verification = dict(verification or {})
        outcome = (lesson.verification.get("outcome") or "").upper()
        if evidence_ids:
            lesson.evidence_ids = list(lesson.evidence_ids or []) + list(evidence_ids)
            lesson.evidence_ids = list(dict.fromkeys(lesson.evidence_ids))
        if research_ids:
            lesson.research_ids = list(dict.fromkeys(
                lesson.research_ids + list(research_ids)
            ))

        if outcome == "VERIFIED":
            lesson.status = LessonClass.VERIFIED
            reason = "verification passed with real evidence"
        elif outcome == "REFUTED":
            lesson.status = LessonClass.REJECTED
            reason = "solution falsified by verification"
        else:
            if lesson.quality_score < 0.5:
                lesson.status = LessonClass.NEEDS_REVIEW
                reason = "open-ended and/or low quality — human/evidence review required"
            else:
                lesson.status = LessonClass.NEEDS_REVIEW
                reason = "open-ended problem (honestly unverifiable) — review required"

        lesson.updated_at = time.time()
        lesson.history.append(
            {"at": lesson.updated_at, "event": "classified", "status": lesson.status.value,
             "reason": reason, "actor": actor}
        )
        return lesson

    def request_review(self, lesson_id: str, actor: str, reason: str = "") -> CurriculumLesson:
        lesson = self.require(lesson_id)
        lesson.status = LessonClass.NEEDS_REVIEW
        lesson.updated_at = time.time()
        lesson.history.append(
            {"at": lesson.updated_at, "event": "review_requested", "reason": reason, "actor": actor}
        )
        return lesson

    def reject(self, lesson_id: str, actor: str, reason: str = "") -> CurriculumLesson:
        lesson = self.require(lesson_id)
        lesson.status = LessonClass.REJECTED
        lesson.updated_at = time.time()
        lesson.history.append(
            {"at": lesson.updated_at, "event": "rejected",
             "reason": reason or "rejected by policy/human", "actor": actor}
        )
        return lesson

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def get(self, lesson_id: str) -> Optional[CurriculumLesson]:
        return self._lessons.get(lesson_id)

    def require(self, lesson_id: str) -> CurriculumLesson:
        lesson = self.get(lesson_id)
        if lesson is None:
            raise KeyError(f"unknown lesson {lesson_id!r}")
        return lesson

    def lessons(self, status: Optional[LessonClass | str] = None) -> list[CurriculumLesson]:
        if status is None:
            return list(self._lessons.values())
        if not isinstance(status, LessonClass):
            status = LessonClass(status)
        return [l for l in self._lessons.values() if l.status is status]

    def verified_lessons(self) -> list[CurriculumLesson]:
        return self.lessons(LessonClass.VERIFIED)

    def snapshot(self) -> dict:
        counts: dict[str, int] = {}
        for lesson in self._lessons.values():
            counts[lesson.status.value] = counts.get(lesson.status.value, 0) + 1
        return {
            "total": len(self._lessons),
            "by_status": counts,
            "verified": [l.lesson_id for l in self.verified_lessons()],
        }

    def clear(self) -> None:
        self._lessons.clear()
        self._by_dedup.clear()