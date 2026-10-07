"""Unit tests for the candidate-vs-baseline curriculum evaluator."""
from types import SimpleNamespace

from learning_arena.evaluator import CurriculumEvaluator
from learning_arena.verification import VerificationOutcome


def _example(pid, expect, answer=None):
    return SimpleNamespace(
        example_id=pid,
        domain="Programming",
        difficulty=3,
        difficulty_label="intermediate",
        problem="Print 1..5.",
        context="exercise",
        expected_format=expect,
        canonical_answer=None,
    )


def _revision(examples):
    return SimpleNamespace(dataset_id="ds-1", examples=examples)


def _good(q, *_a, **_k):
    return {"answer": "for i in range(1, 6): print(i)", "provider": "candidate"}


def _bad(q, *_a, **_k):
    return {"answer": "for i in range(1, 6): bogus(i)", "provider": "baseline"}


def test_needs_runtime_when_no_runners():
    rev = _revision([_example("p1", "python code")])
    result = CurriculumEvaluator().evaluate(
        rev, candidate_model="jarvis-cand", baseline_model="jarvis-base"
    )
    assert result.status == "NEEDS_RUNTIME"
    assert result.row_count == 0
    assert "no healthy chat runtime" in result.summary["note"]


def test_candidate_better_when_only_candidate_verifies():
    rev = _revision([_example("p1", "python code")])
    result = CurriculumEvaluator(max_problems=1).evaluate(
        rev, candidate_model="c", baseline_model="b",
        candidate_runner=_good, baseline_runner=_bad,
    )
    assert result.status == "COMPLETE"
    item = result.per_problem[0]
    assert item.outcome == "CANDIDATE_BETTER"
    assert result.summary["candidate_passed"] == 1
    assert result.summary["baseline_passed"] == 0
    assert result.summary["delta_pass_rate"] > 0


def test_tie_pass_records_both():
    rev = _revision([_example("p1", "python code")])
    result = CurriculumEvaluator(max_problems=1).evaluate(
        rev, candidate_model="c", baseline_model="b",
        candidate_runner=_good, baseline_runner=_good,
    )
    assert result.per_problem[0].outcome == "TIE_PASS"
    assert result.summary["outcomes"]["TIE_PASS"] == 1


def test_bad_runner_never_crashes_evaluation():
    def _throw(q, *_a, **_k):
        raise RuntimeError("runner offline")

    rev = _revision([_example("p1", "python code")])
    result = CurriculumEvaluator(max_problems=1).evaluate(
        rev, candidate_model="c", baseline_model="b",
        candidate_runner=_throw, baseline_runner=_throw,
    )
    assert result.status == "COMPLETE"
    assert result.per_problem[0].outcome == "BOTH_UNVERIFIED"
    assert result.per_problem[0].candidate["answer"] == ""


def test_runner_health_reported_in_result():
    def _errcall(q, *_a, **_k):
        return {"error": "429 quota", "answer": ""}

    rev = _revision([_example("p1", "python code")])
    result = CurriculumEvaluator(max_problems=1).evaluate(
        rev, candidate_model="c", baseline_model="b",
        candidate_runner=_errcall, baseline_runner=_bad,
    )
    assert result.status == "COMPLETE"
    assert result.per_problem[0].candidate["error"] == "429 quota"


def test_open_ended_examples_are_both_unverified():
    rev = _revision([_example("p1", "essay")])
    result = CurriculumEvaluator(max_problems=1).evaluate(
        rev, candidate_model="c", baseline_model="b",
        candidate_runner=_good, baseline_runner=_bad,
    )
    # Essay has no canonical answer and code is not expected -> UNVERIFIABLE,
    # so the evaluator reports both unverified rather than inventing a pass.
    assert result.per_problem[0].baseline_verification["outcome"] == VerificationOutcome.UNVERIFIABLE.value
    assert result.per_problem[0].outcome == "BOTH_UNVERIFIED"