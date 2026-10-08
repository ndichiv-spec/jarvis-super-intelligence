"""Unit tests for the lesson gate (learning_arena.lesson_gate)."""
import pytest

from learning_arena.lesson_gate import CurriculumLesson, LessonClass, LessonGate


def _submit(gate, **over):
    defaults = dict(
        title="FizzBuzz",
        concept="Programming",
        domain="Programming",
        difficulty=2,
        difficulty_label="basic",
        problem_id="p-1",
        problem="Print FizzBuzz 1..100",
        context="",
        constraints=["loop"],
        expected_format="runnable python",
        verified_solution="for i in range(1,101):\n    print(...)",
        verification={"outcome": "VERIFIED", "method": "sandbox"},
        teacher_keys=["openai/gpt-5"],
        evidence_ids=["ev-1"],
    )
    defaults.update(over)
    return gate.submit(**defaults)


def test_submit_candidate_and_verify():
    gate = LessonGate()
    lesson = _submit(gate)
    assert lesson.status is LessonClass.CANDIDATE
    assert lesson.quality_score > 0.5
    out = gate.verify(lesson.lesson_id, {"outcome": "VERIFIED"}, actor="test")
    assert out.status is LessonClass.VERIFIED
    assert any(e["event"] == "classified" for e in out.history)


def test_refuted_lesson_rejected():
    gate = LessonGate()
    lesson = _submit(gate)
    out = gate.verify(
        lesson.lesson_id, {"outcome": "REFUTED", "evidence": "fails cases"}, actor="test"
    )
    assert out.status is LessonClass.REJECTED


def test_unverifiable_becomes_needs_review():
    gate = LessonGate()
    lesson = _submit(
        gate, verified_solution="A considered essay", expected_format="prose",
        verification={"outcome": "UNVERIFIABLE"},
    )
    out = gate.verify(lesson.lesson_id, {"outcome": "UNVERIFIABLE"}, actor="test")
    assert out.status is LessonClass.NEEDS_REVIEW


def test_dedup_returns_duplicate():
    gate = LessonGate()
    first = _submit(gate)
    dup = _submit(gate)
    assert dup.status is LessonClass.DUPLICATE
    assert dup.lesson_id == first.lesson_id  # identity of the stored lesson, not a new row
    assert gate.snapshot()["total"] == 1
    assert gate.snapshot()["by_status"]["CANDIDATE"] == 1


def test_pii_contamination_rejects():
    gate = LessonGate()  # real PrivacyFilter
    lesson = _submit(
        gate,
        problem="Please find the corpus for user mike@example.com",
        verified_solution="mike@example.com",
    )
    assert lesson.status is LessonClass.REJECTED
    assert lesson.quality_score == 0.0


def test_request_review_and_reject_paths():
    gate = LessonGate()
    lesson = _submit(gate)
    reviewed = gate.request_review(lesson.lesson_id, "human", reason="double-check")
    assert reviewed.status is LessonClass.NEEDS_REVIEW
    rejected = gate.reject(lesson.lesson_id, "human", reason="policy")
    assert rejected.status is LessonClass.REJECTED