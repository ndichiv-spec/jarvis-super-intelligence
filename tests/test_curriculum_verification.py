"""Unit tests for deterministic problem verification (learning_arena.verification)."""
import pytest

from learning_arena.verification import VerificationOutcome, verify_problem


class _Problem:
    def __init__(self, **kw):
        self.question = kw.get("question", "")
        self.canonical_answer = kw.get("canonical_answer") or ""
        self.expected_format = kw.get("expected_format") or ""
        self.solution_path = kw.get("solution_path") or "/tmp/soln.py"
        self.id = "p-test"
        self.title = "test"
        self.domain = "Programming"
        self.difficulty = 1
        self.tags = []
        self.context = ""
        self.constraints = []


def test_canonical_numeric_answer_verifies():
    problem = _Problem(question="2 + 2", canonical_answer="4", expected_format="number")
    result = verify_problem(problem, "4")
    assert result.outcome is VerificationOutcome.VERIFIED
    assert result.method == "numeric"


def test_open_ended_no_canonical_is_unverifiable():
    problem = _Problem(question="Discuss the philosophy of time")
    result = verify_problem(problem, "A considered essay")
    assert result.outcome is VerificationOutcome.UNVERIFIABLE


def test_runnable_python_verifies_in_sandbox():
    problem = _Problem(
        question="Print the numbers 1 to 5",
        expected_format="python code",
        canonical_answer="",
    )
    result = verify_problem(problem, "for i in range(1, 6):\n    print(i)")
    assert result.outcome is VerificationOutcome.VERIFIED
    assert result.method == "sandbox"


def test_bad_python_refuted_by_sandbox():
    problem = _Problem(question="Print 1", expected_format="python code")
    result = verify_problem(problem, "for i in range(1")
    assert result.outcome is VerificationOutcome.REFUTED


def test_sandbox_rejects_network_imports():
    problem = _Problem(question="Fetch a URL", expected_format="python code")
    result = verify_problem(problem, "import urllib.request\nprint(urllib.request.urlopen('http://x'))")
    assert result.outcome is VerificationOutcome.REFUTED
    assert result.exit_code != 0