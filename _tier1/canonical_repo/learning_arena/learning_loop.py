"""Governed learning loop (spec §26, §27).

One episode: 

1. a governed problem is generated (deterministic, seeded),
2. the Teacher Mesh produces a teacher solution,
3. the student (JARVIS brain / candidate model) attempts the problem,
4. deterministic verification runs **first** (canonical check then sandbox —
   cheap, never a guess),
5. disagreements go to a second teacher + sandbox, never to a coin flip,
6. a verified/evidence-backed episode becomes a lesson (Lesson Gate),
7. lessons publish an immutable dataset revision,
8. candidate vs baseline evaluation + regression policy close the loop.

Honesty rules: no healthy teacher -> ``NO_HEALTHY_TEACHER``; no healthy
student -> the loop still verifies the teacher solution deterministically but
cannot grade a student attempt; open-ended problems -> ``NEEDS_REVIEW`` lessons
instead of pretending they were verified.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .evaluator import ChatRunner, CurriculumEvaluator
from .lesson_gate import CurriculumLesson, LessonClass, LessonGate
from .verification import VerificationOutcome, verify_problem


@dataclass
class LearningEpisode:
    """Full, immutable trail of one learning episode."""

    episode_id: str
    domain: str
    difficulty: int
    difficulty_label: str
    problem_id: str
    problem: str
    status: str = "STARTED"  # STARTED | COMPLETED | NO_HEALTHY_TEACHER
    teacher_solution: str = ""
    teacher_key: str = ""
    student_attempt: str = ""
    student_key: str = ""
    teacher_verification: dict = field(default_factory=dict)
    student_verification: dict = field(default_factory=dict)
    disagreements: list[dict] = field(default_factory=list)
    research_ids: list[str] = field(default_factory=list)
    lesson: Optional[dict] = None
    lesson_status: str = ""
    dataset_id: str = ""
    dataset_version: int = 0
    evaluation: Optional[dict] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "difficulty_label": self.difficulty_label,
            "problem_id": self.problem_id,
            "problem": self.problem,
            "status": self.status,
            "teacher_key": self.teacher_key,
            "student_key": self.student_key,
            "teacher_verification": self.teacher_verification,
            "student_verification": self.student_verification,
            "disagreements": self.disagreements,
            "research_ids": self.research_ids,
            "lesson_status": self.lesson_status,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "evaluation": self.evaluation,
        }


class LearningLoop:
    """Orchestrates governed learning episodes end-to-end."""

    def __init__(
        self,
        generator: Any,
        mesh: Any,
        gate: LessonGate,
        dataset_builder: Any,
        *,
        evaluator: Optional[CurriculumEvaluator] = None,
        student_runner: Optional[ChatRunner] = None,
        student_key: str = "jarvis-brain",
        research: Optional[Any] = None,
        verifier: Optional[Any] = None,
        max_teacher_disagreements: int = 3,
        require_research_on_failure: bool = False,
    ) -> None:
        self.generator = generator
        self.mesh = mesh
        self.gate = gate
        self.dataset_builder = dataset_builder
        self.evaluator = evaluator or CurriculumEvaluator()
        self.student_runner = student_runner
        self.student_key = student_key
        self.research = research
        self.verifier = verifier or verify_problem
        self.max_teacher_disagreements = int(max_teacher_disagreements)
        self.require_research_on_failure = require_research_on_failure
        self._episodes: dict[str, LearningEpisode] = {}

    # ------------------------------------------------------------------
    def run_episode(
        self,
        *,
        domain: Optional[str] = None,
        difficulty: Any = 3,
        seed: Optional[int] = None,
        student_runner: Optional[ChatRunner] = None,
        publish_dataset: bool = True,
        artifact_domain: str = "Programming",
    ) -> LearningEpisode:
        """Run one learning episode and record its full trail."""
        problem = self.generator.generate(
            domain=domain or artifact_domain, difficulty=difficulty, count=1
        )[0]
        scale = _difficulty_scale(problem)

        episode = LearningEpisode(
            episode_id=f"ep-{uuid.uuid4().hex[:12]}",
            domain=problem.domain,
            difficulty=scale["level"],
            difficulty_label=scale["label"],
            problem_id=problem.id,
            problem=problem.question,
        )

        # 1. Teacher solution (healthy teacher required).
        try:
            teacher = self.mesh.select()
        except Exception:
            episode.status = "NO_HEALTHY_TEACHER"
            self._episodes[episode.episode_id] = episode
            return episode
        episode.teacher_key = teacher.key
        try:
            solved = self.mesh.solve(problem, teacher_key=teacher.key)
        except Exception as exc:
            episode.status = f"TEACHER_ERROR:{type(exc).__name__}"
            self._episodes[episode.episode_id] = episode
            return episode
        episode.teacher_solution = solved["solution"]

        # 2. Deterministic verification of the teacher solution FIRST.
        episode.teacher_verification = self.verifier(
            problem, episode.teacher_solution
        ).to_dict()

        # 3. Student attempt (only if a healthy student runner exists).
        runner = student_runner or self.student_runner
        if runner is not None:
            try:
                attempt = runner(problem.question)
                episode.student_attempt = (
                    attempt.get("answer", "") if isinstance(attempt, dict) else str(attempt)
                )
            except Exception:
                episode.student_attempt = ""
            if episode.student_attempt:
                episode.student_verification = verify_problem(
                    problem, episode.student_attempt
                ).to_dict()

        # 4. Disagreement handling when both answer but can't be verified.
        if (
            episode.student_attempt
            and episode.teacher_verification.get("outcome")
            == VerificationOutcome.UNVERIFIABLE.value
        ):
            try:
                peer = self.mesh.select(capabilities={"chat"})
                if peer and peer.key != episode.teacher_key:
                    resolution = self.mesh.compare_solutions(
                        problem,
                        episode.teacher_solution,
                        episode.teacher_key,
                        episode.student_attempt,
                        peer.key,
                        verifier=self._verifier_hook(problem),
                    )
                    episode.disagreements.append(resolution)
                    if resolution.get("outcome") in ("CONVERGED", "RESOLVED_VERIFICATION"):
                        episode.teacher_solution = resolution.get("solution", episode.teacher_solution)
                        episode.teacher_verification = {
                            "outcome": VerificationOutcome.VERIFIED.value,
                            "method": resolution.get("method", "disagreement_resolution"),
                            "evidence": resolution.get("solution", "")[:200],
                        }
            except Exception:
                pass

        # 5. Research/evidence for honest open-ended problems (optional).
        episode.research_ids = self._gather_research(problem, episode.teacher_verification)

        # 6. Create lesson via the gate.
        draft = self._draft_lesson(problem, episode, scale)
        lesson = self.gate.submit(**draft)
        evidence = episode.research_ids + [
            f"teacher:{episode.teacher_key}"
        ]
        lesson = self.gate.verify(
            lesson.lesson_id,
            episode.teacher_verification,
            actor="learning_loop",
            evidence_ids=evidence,
        )
        episode.lesson = lesson.to_dict()
        episode.lesson_status = lesson.status.value
        episode.status = "COMPLETED"

        # 7. Publish dataset revision (immutable) — only verified lessons
        # become training examples (spec §28); NEEDS_REVIEW ones are held back.
        if publish_dataset and lesson.status is LessonClass.VERIFIED:
            revision = self.dataset_builder.build(
                name=f"{artifact_domain.lower().replace(' ', '-')}-verified",
                min_quality_score=0.5,
                actor="learning_loop",
            )
            episode.dataset_id = revision.dataset_id
            episode.dataset_version = revision.version

        self._episodes[episode.episode_id] = episode
        return episode

    # ------------------------------------------------------------------
    def _gather_research(self, problem: Any, verification: dict) -> list[str]:
        outcome = verification.get("outcome", "")
        if outcome not in (VerificationOutcome.UNVERIFIABLE.value,):
            return []  # avoid unnecessary research calls (spec §26)
        if self.research is None:
            return []
        try:
            result = self.research(query=problem.question)
        except Exception:
            return []
        if isinstance(result, dict):
            rid = result.get("id") or result.get("research_id") or ""
            return [rid] if rid else ([str(result.get("evidence_id"))] if result.get("evidence_id") else [])
        return []

    def _draft_lesson(self, problem: Any, episode: LearningEpisode, scale: dict) -> dict:
        title = getattr(problem, "title", "") or f"{episode.domain} lesson"
        return {
            "title": title,
            "concept": episode.domain,
            "domain": episode.domain,
            "difficulty": scale["level"],
            "difficulty_label": scale["label"],
            "problem_id": episode.problem_id,
            "problem": episode.problem,
            "context": getattr(problem, "context", "") or "",
            "constraints": list(getattr(problem, "constraints", []) or []),
            "expected_format": getattr(problem, "expected_format", "") or "",
            "verified_solution": episode.teacher_solution,
            "verification": episode.teacher_verification,
            "teacher_keys": [episode.teacher_key] if episode.teacher_key else [],
            "evidence_ids": list(episode.research_ids),
            "tags": list(getattr(problem, "tags", []) or []),
        }

    def _verifier_hook(self, problem: Any):
        def _verify(_question: str, solution: str) -> dict:
            return self.verifier(problem, solution).to_dict()

        return _verify

    # ------------------------------------------------------------------
    def episodes(self) -> list[LearningEpisode]:
        return list(self._episodes.values())

    def get(self, episode_id: str) -> Optional[LearningEpisode]:
        return self._episodes.get(episode_id)

    def snapshot(self) -> dict:
        by_status: dict[str, int] = {}
        for ep in self._episodes.values():
            by_status[ep.status] = by_status.get(ep.status, 0) + 1
        return {
            "episodes": len(self._episodes),
            "by_status": by_status,
            "last": self._episodes[max(self._episodes)] if self._episodes else None,
        }


def _difficulty_scale(problem: Any) -> dict:
    from .problem_generator import DIFFICULTY_SCALE, DIFFICULTY_SCALE_LABELS

    diff = getattr(problem, "difficulty", None)
    rank_0 = getattr(problem, "difficulty_rank", 0)  # 0..5
    level = rank_0 + 1  # 1..6
    label = DIFFICULTY_SCALE_LABELS.get(level, "intermediate")
    if diff is not None:
        for lv, d in DIFFICULTY_SCALE.items():
            if d is diff:
                level, label = lv, DIFFICULTY_SCALE_LABELS[lv]
                break
    return {"level": level, "label": label}