"""Unit tests for the governed learning loop orchestration."""
import pytest

from learning_arena.learning_loop import LearningLoop
from learning_arena.lesson_gate import LessonGate, LessonClass
from types import SimpleNamespace


class _Problem:
    def __init__(self, canonical_answer=None, expected_format="python code"):
        self.domain = "Programming"
        self.difficulty = None
        self.difficulty_rank = 2  # level 3
        self.id = "prob-1"
        self.question = "Print the numbers 1..5, one per line."
        self.context = "a programming exercise"
        self.expected_format = expected_format
        self.canonical_answer = canonical_answer
        self.metadata = {}
        self.title = "count to five"
        self.constraints = ["no imports"]
        self.tags = ["loops"]


class _Teacher:
    def __init__(self, key):
        self.key = key


class _Mesh:
    def __init__(self, solution='for i in range(1, 6): print(i)', error_on_solve=False):
        self.solution = solution
        self.error_on_solve = error_on_solve
        self.solved = 0
        self.compared = 0

    def select(self, capabilities=None):
        if capabilities:
            self.compared += 1
            return _Teacher("peer")
        return _Teacher("t1")

    def solve(self, problem, teacher_key=None):
        self.solved += 1
        if self.error_on_solve:
            raise RuntimeError("teacher crashed")
        return {"solution": self.solution}


class _DeadMesh:
    def select(self, capabilities=None):
        raise RuntimeError("no healthy teacher")


class _Builder:
    def __init__(self):
        self.calls = 0

    def build(self, name=None, min_quality_score=None, actor=None):
        self.calls += 1
        return SimpleNamespace(dataset_id="ds-1", version=1)


class _Generator:
    def __init__(self, problem):
        self.problem = problem

    def generate(self, domain=None, difficulty=3, count=1):
        return [self.problem]


def _loop(problem, mesh=None, builder=None, **kw):
    return LearningLoop(
        generator=_Generator(problem),
        mesh=mesh or _Mesh(),
        gate=LessonGate(),
        dataset_builder=builder or _Builder(),
        **kw,
    )


def test_no_healthy_teacher_is_honest():
    problem = _Problem()
    loop = _loop(problem, mesh=_DeadMesh())
    episode = loop.run_episode(domain="Programming", difficulty=3, publish_dataset=True)
    assert episode.status == "NO_HEALTHY_TEACHER"
    assert not episode.teacher_solution


def test_teacher_error_recorded():
    problem = _Problem()
    loop = _loop(problem, mesh=_Mesh(error_on_solve=True))
    episode = loop.run_episode(domain="Programming", difficulty=3)
    assert episode.status.startswith("TEACHER_ERROR:")
    assert episode.teacher_key == "t1"


def test_verified_code_lesson_publishes_dataset():
    problem = _Problem()
    builder = _Builder()
    loop = _loop(problem, builder=builder)
    episode = loop.run_episode(domain="Programming", difficulty=3, publish_dataset=True)
    assert episode.status == "COMPLETED"
    assert episode.teacher_verification["outcome"] == "VERIFIED"
    assert episode.teacher_verification["method"] == "sandbox"
    assert episode.lesson_status == LessonClass.VERIFIED.value
    assert episode.dataset_id == "ds-1"
    assert episode.dataset_version == 1
    assert builder.calls == 1


def test_publish_dataset_off_leaves_builder_untouched():
    problem = _Problem()
    builder = _Builder()
    loop = _loop(problem, builder=builder)
    episode = loop.run_episode(domain="Programming", difficulty=3, publish_dataset=False)
    assert episode.status == "COMPLETED"
    assert episode.lesson_status == LessonClass.VERIFIED.value
    assert episode.dataset_id == ""
    assert builder.calls == 0


def test_open_ended_problem_held_back_as_needs_review():
    problem = _Problem(expected_format="essay")
    builder = _Builder()
    loop = _loop(problem, builder=builder)
    episode = loop.run_episode(domain="Programming", difficulty=3, publish_dataset=True)
    assert episode.status == "COMPLETED"
    assert episode.teacher_verification["outcome"] == "UNVERIFIABLE"
    assert episode.lesson_status == LessonClass.NEEDS_REVIEW.value
    assert episode.dataset_id == ""
    assert builder.calls == 0  # ONLY verified lessons publish (spec §28)


def test_student_attempt_recorded_when_healthy():
    problem = _Problem()
    loop = _loop(problem)
    runner = lambda q: {"answer": "for i in range(1, 6): print(i)", "provider": "student"}
    episode = loop.run_episode(domain="Programming", difficulty=3, student_runner=runner)
    assert episode.status == "COMPLETED"
    assert episode.student_attempt
    assert episode.student_verification["outcome"] == "VERIFIED"


def test_episodes_are_recorded_and_snapshot_counts():
    problem = _Problem(expected_format="essay")
    loop = _loop(problem)
    loop.run_episode(domain="Programming", difficulty=3)
    loop.run_episode(domain="Programming", difficulty=4)
    assert len(loop.episodes()) == 2
    snap = loop.snapshot()
    assert snap["episodes"] == 2
    assert snap["by_status"].get("COMPLETED") == 2