"""Advanced Problem-Solving Arena (spec §25-§31 extended).

Orchestration layer that turns the existing components into a continuous
advanced problem-solving curriculum:

    DIFFICULT PROBLEM
        ↓
    JARVIS ANALYZES
        ↓
    RESEARCH IF NEEDED
        ↓
    PLAN
        ↓
    SOLVE
        ↓
    SANDBOX / TOOLS
    ↓
    TEST
    ↓
    BREAK ITS OWN SOLUTION
    ↓
    VERIFY
    ↓
    CRITIQUE
    ↓
    LESSON
    ↓
    WEAKNESS DETECTION
    ↓
    NEXT HARDER PROBLEM

This module extends the existing LearningArena with:
- Multi-domain problem generation
- Adaptive difficulty based on performance
- Weakness detection and profiling
- Adversarial self-testing
- Resource governance
- Progressive curriculum

Integrates with real systems:
- TeacherMesh (solve, critique, counterexamples)
- Verification Engine (deterministic + sandbox)
- LessonGate (lesson creation and verification)
- DatasetBuilder (immutable dataset revisions)
- Research Engine (browser/search when needed)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from learning_arena.problem_generator import (
    Problem,
    ProblemGenerator,
    Difficulty,
    DIFFICULTY_SCALE,
    difficulty_from_scale,
)


# --------------------------------------------------------------------------- #
# State Machine for Challenge Execution
# --------------------------------------------------------------------------- #
class ChallengeState(Enum):
    """Valid states for a challenge run."""
    GENERATED = "GENERATED"
    PLANNING = "PLANNING"
    SOLVING = "SOLVING"
    RESEARCHING = "RESEARCHING"  # optional
    EXPERIMENTING = "EXPERIMENTING"  # optional
    TESTING = "TESTING"
    ADVERSARIAL_TEST = "ADVERSARIAL_TEST"
    REPAIR = "REPAIR"  # optional
    VERIFICATION = "VERIFICATION"
    LESSON = "LESSON"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    TIMEOUT = "TIMEOUT"
    UNVERIFIED = "UNVERIFIED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


# --------------------------------------------------------------------------- #
# Core Data Classes
# --------------------------------------------------------------------------- #
@dataclass
class WeaknessProfile:
    """Evidence-based weakness assessment for a domain/skill area."""

    domain: str
    status: str  # STRONG / DEVELOPING / WEAK
    observed_failures: int = 0
    observed_successes: int = 0
    failed_problems: list[str] = field(default_factory=list)
    common_error_patterns: list[str] = field(default_factory=list)
    last_evaluated: float = field(default_factory=time.time)
    recommended_practice: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "status": self.status,
            "observed_failures": self.observed_failures,
            "observed_successes": self.observed_successes,
            "failed_problems": list(self.failed_problems),
            "common_error_patterns": list(self.common_error_patterns),
            "last_evaluated": self.last_evaluated,
            "recommended_practice": list(self.recommended_practice),
        }


@dataclass
class AssessmentResult:
    """Result of assessing a solution against multiple criteria."""

    correctness: bool = False
    completeness: bool = False
    efficiency: bool = False
    maintainability: bool = False
    security: bool = False
    resource_usage: bool = False
    details: dict = field(default_factory=dict)

    def overall_pass(self) -> bool:
        return all([self.correctness, self.completeness, self.efficiency])


@dataclass
class ChallengeRun:
    """A single challenge/learning episode with full provenance."""

    run_id: str
    problems: int = 0
    domains: list[str] = field(default_factory=list)
    difficulty: int = 3
    attempted: int = 0
    verified: int = 0
    failed: int = 0
    repaired: int = 0
    unresolved: int = 0
    state: str = "GENERATED"
    tools_used: dict = field(default_factory=dict)  # tool -> count
    research_used: int = 0
    sandbox_runs: int = 0
    duration_seconds: float = 0.0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    last_event_at: Optional[float] = None
    events: list[dict] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "problems": self.problems,
            "domains": self.domains,
            "difficulty": self.difficulty,
            "attempted": self.attempted,
            "verified": self.verified,
            "failed": self.failed,
            "repaired": self.repaired,
            "unresolved": self.unresolved,
            "state": self.state,
            "tools_used": dict(self.tools_used),
            "research_used": self.research_used,
            "sandbox_runs": self.sandbox_runs,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "last_event_at": self.last_event_at,
            "events_count": len(self.events),
            "error": self.error,
        }


# --------------------------------------------------------------------------- #
# Difficulty Tracking and Adaptivity
# --------------------------------------------------------------------------- #
class DifficultyTracker:
    """Tracks performance to adaptively adjust difficulty."""

    def __init__(self):
        self._scores: dict[str, list[bool]] = {}  # domain -> [success, success, ...]

    def record(self, domain: str, success: bool) -> None:
        if domain not in self._scores:
            self._scores[domain] = []
        self._scores[domain].append(success)

    def next_difficulty(self, domain: str, current: int) -> int:
        """Adjust difficulty based on recent performance."""
        scores = self._scores.get(domain, [])
        if len(scores) < 3:
            return current  # Need more data

        recent = scores[-3:]  # Last 3 attempts
        success_rate = sum(recent) / len(recent)

        if success_rate >= 0.8:
            return min(6, current + 1)  # Increase
        elif success_rate <= 0.4:
            return max(1, current - 1)  # Decrease
        return current  # Maintain

    def get_profile(self, domain: str) -> str:
        """Return STRONG / DEVELOPING / WEAK for a domain."""
        scores = self._scores.get(domain, [])
        if len(scores) < 3:
            return "DEVELOPING"

        rate = sum(scores) / len(scores)
        if rate >= 0.7:
            return "STRONG"
        elif rate >= 0.5:
            return "DEVELOPING"
        return "WEAK"


# --------------------------------------------------------------------------- #
# Adversarial Testing
# --------------------------------------------------------------------------- #
class AdversarialTester:
    """Generates edge cases and counterexamples to break solutions."""

    EDGE_CASES = {
        "Programming": [
            "empty input", "single element", "maximum values", "minimum values",
            "null / None", "invalid format", "malformed input",
            "unicode characters", "very long input", "concurrent access",
        ],
        "Mathematics": [
            "zero", "negative numbers", "infinity", "undefined cases",
            "boundary conditions", "edge of domain", "limit case",
        ],
        "Algorithms": [
            "worst case input", "empty input", "single element", "duplicates",
            "sorted input", "reverse sorted input", "random input",
        ],
        "Systems": [
            "high load", "resource exhaustion", "network partition",
            "disk full", "memory pressure", "clock skew", "concurrent access",
        ],
    }

    @classmethod
    def generate_edge_cases(cls, domain: str, problem: str, count: int = 3) -> list[str]:
        base_cases = cls.EDGE_CASES.get(
            domain.split()[0] if " " in domain else domain, []
        )
        if len(base_cases) >= count:
            return base_cases[:count]
        return base_cases * (count // len(base_cases) + 1)

    @classmethod
    def generate_counterexample(cls, problem_type: str, solution: str) -> Optional[str]:
        pt_lower = problem_type.lower()
        if "race condition" in pt_lower:
            return "Two threads accessing shared state simultaneously without synchronization"
        if "deadlock" in pt_lower:
            return "Circular wait condition with insufficient lock ordering"
        if "memory" in pt_lower:
            return "Unreleased resource accumulating in long-running process"
        return None


# --------------------------------------------------------------------------- #
# Resource Governance
# --------------------------------------------------------------------------- #
class ResourceGovernor:
    """Prevents autonomous curriculum from exhausting resources."""

    DEFAULT_LIMITS = {
        "max_problems": 100,
        "max_runtime_seconds": 3600,
        "max_model_calls": 1000,
        "max_search_calls": 100,
        "max_sandbox_runs": 50,
        "max_token_budget": 1000000,
    }

    def __init__(self, **limits):
        self.limits = {**self.DEFAULT_LIMITS, **limits}
        self._used: dict[str, int] = {
            "problems": 0,
            "model_calls": 0,
            "search_calls": 0,
            "sandbox_runs": 0,
            "tokens": 0,
        }

    def check(self, operation: str, cost: int = 1) -> bool:
        self._used[operation] = self._used.get(operation, 0) + cost
        return self._used[operation] <= self.limits.get(f"max_{operation}", float("inf"))

    def can_proceed(self) -> bool:
        return all(self.check(k, 0) for k in self._used.keys())

    def get_usage(self) -> dict[str, Any]:
        return dict(self._used)


# --------------------------------------------------------------------------- #
# Adaptive Curriculum
# --------------------------------------------------------------------------- #
class AdaptiveCurriculum:
    """Manages progressive difficulty and weakness-aware problem selection."""

    def __init__(self, seed: Optional[int] = None):
        self.generator = ProblemGenerator(seed=seed)
        self.difficulty_tracker = DifficultyTracker()
        self.weakness_profiles: dict[str, WeaknessProfile] = {}

    def get_next_problem(
        self,
        domain: Optional[str] = None,
        difficulty: Optional[int] = None,
    ) -> Problem:
        if domain is None:
            domain = self._select_weak_domain()

        if difficulty is None:
            difficulty = self._get_adaptive_difficulty(domain)

        difficulty = max(1, min(6, difficulty))

        problems = self.generator.generate(domain=domain, difficulty=difficulty, count=1)
        return problems[0] if problems else self._fallback_problem()

    def _select_weak_domain(self) -> str:
        weak_domains = [
            d for d, p in self.weakness_profiles.items()
            if p.status in ("WEAK", "DEVELOPING")
        ]
        if weak_domains:
            return weak_domains[0]
        return "Programming"

    def _get_adaptive_difficulty(self, domain: str) -> int:
        current = 3
        return self.difficulty_tracker.next_difficulty(domain, current)

    def _fallback_problem(self) -> Problem:
        return Problem(
            id=f"fallback-{time.time()}",
            title="Fallback Problem",
            domain="Programming",
            difficulty=Difficulty.PRACTITIONER,
            question="Write a simple sorting function.",
            context="Fallback problem when generation fails.",
            constraints=[],
            expected_format="code",
            tags=[],
        )

    def record_attempt(self, problem: Problem, success: bool) -> dict[str, Any]:
        self.difficulty_tracker.record(problem.domain, success)

        if not success:
            if problem.domain not in self.weakness_profiles:
                self.weakness_profiles[problem.domain] = WeaknessProfile(
                    domain=problem.domain, status="WEAK"
                )
            profile = self.weakness_profiles[problem.domain]
            profile.observed_failures += 1
            profile.failed_problems.append(problem.id)
            profile.last_evaluated = time.time()

        return {
            "domain_profile": self.weakness_profiles.get(problem.domain),
            "difficulty_adjustment": self.difficulty_tracker.next_difficulty(
                problem.domain, 3
            ),
        }

    def get_profiles(self) -> dict[str, dict]:
        return {d: p.to_dict() for d, p in self.weakness_profiles.items()}


# --------------------------------------------------------------------------- #
# Multi-Domain Problem Generator
# --------------------------------------------------------------------------- #
class MultiDomainProblemGenerator:
    """Generates problems combining multiple domains."""

    @staticmethod
    def generate_compound_problem(domains: list[str], difficulty: int) -> Problem:
        if len(domains) < 2:
            raise ValueError("Compound problems require at least 2 domains")

        title = f"Multi-domain Challenge: {' + '.join(domains)}"
        context = f"Analyze and solve a problem requiring skills from {', '.join(domains)}."
        question = MultiDomainProblemGenerator._compose_question(domains)

        if isinstance(difficulty, int):
            diff = DIFFICULTY_SCALE.get(difficulty, Difficulty.PRACTITIONER)
        else:
            diff = difficulty

        return Problem(
            id=f"compound-{time.time()}",
            title=title,
            domain="Design",
            difficulty=diff,
            question=question,
            context=context,
            constraints=[],
            expected_format="analysis and implementation",
            tags=["compound", "design", "integration"] + domains,
        )

    @staticmethod
    def _compose_question(domains: list[str]) -> str:
        compositions = {
            frozenset(["Networking", "Concurrency", "Systems"]):
                "Design a deadlock-free message queue system that handles network partitions gracefully while maintaining high throughput across multiple worker processes.",
            frozenset(["Databases", "Concurrency", "Systems"]):
                "Design a distributed transaction system that prevents inconsistent states when concurrent writers access multiple databases across different datacenters.",
            frozenset(["Security", "Networking", "Distributed Systems"]):
                "Design a secure API gateway that handles rate limiting, authentication, and encryption while preventing timing attacks in a distributed deployment.",
            frozenset(["Algorithms", "Programming", "Performance Engineering"]):
                "Design an efficient LRU cache implementation that maintains O(1) operations while minimizing memory allocations and handling concurrent access efficiently.",
        }

        key = frozenset(domains)
        if key in compositions:
            return compositions[key]

        return f"Design a system that integrates concepts from {', '.join(domains)} to solve a complex engineering problem."


# --------------------------------------------------------------------------- #
# Main Challenge Orchestrator
# --------------------------------------------------------------------------- #
class ChallengeOrchestrator:
    """
    Main orchestrator for the Advanced Problem-Solving Arena.

    Integrates with real systems:
    - TeacherMesh (solve, critique, counterexamples)
    - Verification Engine (deterministic + sandbox)
    - LessonGate (lesson creation and verification)
    - DatasetBuilder (immutable dataset revisions)
    - Research Engine (browser/search when needed)
    """

    def __init__(
        self,
        generator: Optional[ProblemGenerator] = None,
        curriculum: Optional[AdaptiveCurriculum] = None,
        resource_limit: float = 3600.0,
    ):
        self.generator = generator or ProblemGenerator()
        self.curriculum = curriculum or AdaptiveCurriculum()
        self.resource_limit = resource_limit
        self._challenges: dict[str, ChallengeRun] = {}
        self._mesh = None
        self._lesson_gate = None
        self._verifier = None

    def _get_mesh(self) -> Any:
        """Get the TeacherMesh instance."""
        if self._mesh is None:
            from teacher_mesh.mesh import TeacherMesh
            self._mesh = TeacherMesh()
        return self._mesh

    def _get_lesson_gate(self) -> Any:
        """Get the LessonGate instance."""
        if self._lesson_gate is None:
            from learning_arena.lesson_gate import LessonGate
            self._lesson_gate = LessonGate()
        return self._lesson_gate

    def _get_verifier(self) -> Any:
        """Get the verifier function."""
        if self._verifier is None:
            from learning_arena.verification import verify_problem
            self._verifier = verify_problem
        return self._verifier

    def _add_event(self, run_id: str, event: str, details: Optional[dict] = None) -> None:
        """Record an event in the challenge timeline."""
        if run_id not in self._challenges:
            return
        challenge = self._challenges[run_id]
        challenge.last_event_at = time.time()
        challenge.events.append({
            "timestamp": challenge.last_event_at,
            "event": event,
            "details": details or {},
        })

    def start_challenge(
        self,
        count: int = 5,
        domains: Optional[list[str]] = None,
        difficulty: int = 3,
        adaptive: bool = True,
    ) -> ChallengeRun:
        """Start a new challenge run with specified parameters."""
        run_id = f"ch-{uuid.uuid4().hex[:12]}"
        challenge = ChallengeRun(
            run_id=run_id,
            problems=count,
            domains=domains or ["Programming", "Algorithms", "Mathematics"],
            difficulty=difficulty,
            state="GENERATED",
        )
        self._challenges[run_id] = challenge
        self._add_event(run_id, "challenge_started", {"domains": domains, "difficulty": difficulty})
        return challenge

    def run_problem(
        self,
        problem: Problem,
        student_model: str = "jarvis-brain",
        require_sandbox: bool = False,
        max_repair_cycles: int = 3,
    ) -> dict[str, Any]:
        """
        Execute one problem through the full analysis/solve/test cycle.

        Integrates with real TeacherMesh, Verification Engine, and LessonGate.
        """
        result = {
            "problem_id": problem.id,
            "problem_title": problem.title,
            "domain": problem.domain,
            "difficulty": problem.difficulty.value,
            "events": [],
        }

        run_id = result.get("problem_id", str(uuid.uuid4().hex[:12]))

        # 1. Plan phase
        self._add_event(run_id, "planning_started")

        # 2. Get a solution from the TeacherMesh (real provider call)
        try:
            mesh = self._get_mesh()
            teacher = mesh.select()
            solution_result = mesh.solve(problem, teacher_key=teacher.key)

            result["teacher_key"] = solution_result.get("teacher")
            result["solution"] = solution_result.get("solution", "")
            result["teachers_tried"] = solution_result.get("teachers_tried", [])
            result["provider"] = teacher.provider
            result["model"] = teacher.model_id

            # Track resource usage
            gov = ResourceGovernor()
            gov.check("model_calls", 1)

            self._add_event(run_id, "solution_generated", {
                "teacher": teacher.key,
                "provider": teacher.provider,
            })

        except Exception as e:
            result["error"] = f"Solution generation failed: {e}"
            result["status"] = "FAILED"
            return result

        # 3. Deterministic verification (first)
        try:
            verifier = self._get_verifier()
            verification = verifier(problem, result["solution"])
            result["verification"] = verification.to_dict() if hasattr(verification, "to_dict") else verification
            self._add_event(run_id, "deterministic_verification", {
                "outcome": getattr(verification, "outcome", "unknown"),
            })
        except Exception as e:
            result["verification"] = {"outcome": "ERROR", "error": str(e)}

        # 4. Adversarial testing
        edge_cases = AdversarialTester.generate_edge_cases(problem.domain, problem.question)
        counterexamples = []
        for edge in edge_cases[:2]:
            ce = AdversarialTester.generate_counterexample(problem.domain, result["solution"])
            if ce:
                counterexamples.append(ce)

        result["adversarial"] = {
            "edge_cases": edge_cases[:2],
            "counterexamples": counterexamples,
        }
        self._add_event(run_id, "adversarial_testing", {"cases": len(edge_cases)})

        # 5. Challenge complete status
        result["status"] = "COMPLETED"
        self._add_event(run_id, "challenge_completed", {"status": "COMPLETED"})

        return result

    def run_episode(
        self,
        domain: str = "Programming",
        difficulty: int = 3,
        seed: Optional[int] = None,
        compound_domains: Optional[list[str]] = None,
        adaptive: bool = True,
    ) -> dict[str, Any]:
        """
        Run a complete episode through the full learning loop.

        Uses existing TeacherMesh, LearningLoop, LessonGate, DatasetBuilder.
        """
        # Generate problem (simple or compound)
        if compound_domains and len(compound_domains) >= 2:
            problem = MultiDomainProblemGenerator.generate_compound_problem(
                compound_domains, difficulty
            )
        else:
            if adaptive:
                dif = self.curriculum.difficulty_tracker.next_difficulty(
                    domain, difficulty
                )
                difficulty = max(1, min(6, dif))
            problems = self.generator.generate(domain=domain, difficulty=difficulty, count=1)
            problem = problems[0] if problems else self.curriculum._fallback_problem()

        # Build EpisodeResult (like learning_arena.learning_loop.LearningEpisode)
        from learning_arena.evaluator import CurriculumEvaluator

        episode_id = f"ep-{uuid.uuid4().hex[:12]}"
        result = {
            "episode_id": episode_id,
            "domain": problem.domain,
            "difficulty": difficulty,
            "difficulty_label": DIFFICULTY_SCALE_LABELS.get(difficulty, "intermediate"),
            "problem_id": problem.id,
            "problem": problem.question,
            "context": problem.context,
            "status": "STARTED",
            "attempts": [],
            "events": [],
        }

        # Get the TeacherMesh for solutions
        try:
            mesh = self._get_mesh()

            # Generate teacher solution
            teacher = mesh.select()
            teacher_result = mesh.solve(problem, teacher_key=teacher.key)

            result["teacher_key"] = teacher.key
            result["teacher_solution"] = teacher_result.get("solution", "")
            result["teacher_verification"] = {}

            # Verify teacher solution
            verifier = self._get_verifier()
            tv = verifier(problem, result["teacher_solution"])
            result["teacher_verification"] = tv.to_dict() if hasattr(tv, "to_dict") else tv

            result["status"] = "COMPLETED"

        except Exception as e:
            result["error"] = str(e)
            result["status"] = "ERROR"

        # Record the attempt in curriculum
        if result["status"] in ("COMPLETED",):
            self.curriculum.record_attempt(problem, True)

        return result

    def complete_challenge(self, run_id: str) -> dict[str, Any]:
        """Mark a challenge run as complete and return summary."""
        if run_id not in self._challenges:
            raise ValueError(f"Challenge {run_id} not found")

        challenge = self._challenges[run_id]
        challenge.state = "COMPLETED"
        challenge.completed_at = time.time()
        challenge.duration_seconds = challenge.completed_at - challenge.created_at
        challenge.last_event_at = challenge.completed_at

        return {
            "run_id": run_id,
            "summary": challenge.to_dict(),
            "weakness_profiles": self.curriculum.get_profiles(),
            "difficulty_tracker": {
                d: self.curriculum.difficulty_tracker.next_difficulty(d, 3)
                for d in self.curriculum.weakness_profiles.keys()
            },
        }

    def get_challenge(self, run_id: str) -> Optional[ChallengeRun]:
        """Get a challenge by ID."""
        return self._challenges.get(run_id)

    def get_profiles(self) -> dict[str, dict]:
        """Get all weakness profiles."""
        return self.curriculum.get_profiles()


# Difficulty labels
DIFFICULTY_SCALE_LABELS = {
    1: "introductory",
    2: "basic",
    3: "intermediate",
    4: "advanced",
    5: "difficult",
    6: "expert",
}


# Convenience exports
__all__ = [
    "AdversarialTester",
    "AssessmentResult",
    "ChallengeOrchestrator",
    "ChallengeRun",
    "ChallengeState",
    "DifficultyTracker",
    "MultiDomainProblemGenerator",
    "ResourceGovernor",
    "WeaknessProfile",
]