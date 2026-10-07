"""Tests for the Advanced Problem-Solving Arena."""
import pytest

from learning_arena.arena import (
    AdversarialTester,
    ChallengeOrchestrator,
    ChallengeRun,
    DifficultyTracker,
    MultiDomainProblemGenerator,
    ResourceGovernor,
    WeaknessProfile,
)
from learning_arena.problem_generator import ProblemGenerator, DIFFICULTY_SCALE


class TestDifficultyTracker:
    def test_first_attempts_maintain_current_difficulty(self):
        tracker = DifficultyTracker()
        # Need at least 3 records for adaptation
        assert tracker.next_difficulty("test", 3) == 3

    def test_consistent_success_increases_difficulty(self):
        tracker = DifficultyTracker()
        tracker.record("test", True)
        tracker.record("test", True)
        tracker.record("test", True)
        result = tracker.next_difficulty("test", 3)
        assert result == 4  # Increased

    def test_consistent_failure_decreases_difficulty(self):
        tracker = DifficultyTracker()
        tracker.record("test", False)
        tracker.record("test", False)
        tracker.record("test", False)
        result = tracker.next_difficulty("test", 3)
        assert result == 2  # Decreased

    def test_profile_strong_after_good_performance(self):
        tracker = DifficultyTracker()
        for _ in range(5):
            tracker.record("algo", True)
        assert tracker.get_profile("algo") == "STRONG"

    def test_profile_weak_after_poor_performance(self):
        tracker = DifficultyTracker()
        for _ in range(5):
            tracker.record("algo", False)
        assert tracker.get_profile("algo") == "WEAK"


class TestWeaknessProfile:
    def test_to_dict_returns_all_fields(self):
        profile = WeaknessProfile(
            domain="Concurrency",
            status="WEAK",
            observed_failures=3,
            failed_problems=["p1", "p2"],
        )
        d = profile.to_dict()
        assert d["domain"] == "Concurrency"
        assert d["status"] == "WEAK"
        assert d["observed_failures"] == 3


class TestAdversarialTester:
    def test_generate_edge_cases_returns_list(self):
        cases = AdversarialTester.generate_edge_cases("Programming", "sort array", 3)
        assert isinstance(cases, list)
        assert len(cases) <= 3

    def test_generate_counterexample_race_condition(self):
        ce = AdversarialTester.generate_counterexample("race condition", "solution")
        assert ce is not None
        # Just check it returns something, not specific content
        assert len(ce) > 0


class TestMultiDomainProblemGenerator:
    def test_compound_problem_requires_multiple_domains(self):
        with pytest.raises(ValueError):
            MultiDomainProblemGenerator.generate_compound_problem(["Programming"], 3)

    def test_compound_problem_works_with_two_domains(self):
        problem = MultiDomainProblemGenerator.generate_compound_problem(
            ["Programming", "Algorithms"], 4
        )
        assert "Programming" in problem.title or "Algorithms" in problem.title
        assert "compound" in problem.tags
        assert "design" in problem.tags
        # Verify difficulty was converted correctly
        from learning_arena.problem_generator import DIFFICULTY_SCALE
        assert problem.difficulty.value == DIFFICULTY_SCALE[4].value


class TestResourceGovernor:
    def test_default_limits(self):
        gov = ResourceGovernor()
        assert gov.DEFAULT_LIMITS["max_problems"] == 100
        assert gov.DEFAULT_LIMITS["max_sandbox_runs"] == 50

    def test_check_prevents_exceedance(self):
        gov = ResourceGovernor(max_problems=5)
        for _ in range(5):
            assert gov.check("problems") is True
        # Next check should succeed (increments from 5 to 6) but return False
        assert gov.check("problems") is False

    def test_can_proceed(self):
        gov = ResourceGovernor()
        assert gov.can_proceed() is True


class TestChallengeOrchestrator:
    def test_start_challenge_returns_challenge_run(self):
        from learning_arena.arena import ChallengeOrchestrator
        orch = ChallengeOrchestrator()
        challenge = orch.start_challenge(count=5, difficulty=3)
        assert challenge.run_id.startswith("ch-")
        assert challenge.problems == 5
        assert challenge.state == "GENERATED"

    def test_complete_challenge(self):
        from learning_arena.arena import ChallengeOrchestrator
        orch = ChallengeOrchestrator()
        challenge = orch.start_challenge(count=5)
        result = orch.complete_challenge(challenge.run_id)
        assert "summary" in result
        assert "weakness_profiles" in result
        assert result["run_id"] == challenge.run_id


class TestChallengeRun:
    def test_to_dict(self):
        run = ChallengeRun(
            run_id="test-123",
            problems=5,
            difficulty=4,
            attempted=3,
            verified=3,
        )
        d = run.to_dict()
        assert d["run_id"] == "test-123"
        assert d["problems"] == 5
        assert d["state"] == "GENERATED"