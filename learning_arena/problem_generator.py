"""Curriculum problem generator for the JARVIS learning loop (Learning Arena spec §25-§26).

Generates domain-specific problems at six difficulty levels, forming a
curriculum that the Teacher Node can schedule as learning tasks.  Each
domain has its own generator method so that question phrasing, context
and constraints stay faithful to the discipline.

The generator is deterministic when a ``seed`` is supplied, which makes
curriculum generation reproducible across runs — essential for tracking model
revisions against a fixed problem set (spec §31).
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


#: Schema / library version baked into every generated problem's metadata.
__version__ = "1.0.0"


class Difficulty(Enum):
    """Problem difficulty levels (NOVICE -> GRANDMASTER).

    The ordering is significant: :class:`ProblemGenerator` uses the ordinal
    position to scale question complexity.
    """

    NOVICE = "NOVICE"
    APPRENTICE = "APPRENTICE"
    PRACTITIONER = "PRACTITIONER"
    EXPERT = "EXPERT"
    MASTER = "MASTER"
    GRANDMASTER = "GRANDMASTER"

    @classmethod
    def from_value(cls, value: Any) -> Optional["Difficulty"]:
        """Coerce a string or numeric value to a Difficulty.

        Accepts ``'APPRENTICE'``/``Difficulty.APPRENTICE`` and the numeric
        scale ``1..6`` (1 = NOVICE/``introductory`` .. 6 =
        GRANDMASTER/``expert``) defined by spec §25.
        """
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, Difficulty):
            return value
        if isinstance(value, int):
            return DIFFICULTY_SCALE.get(value)
        try:
            return cls(str(value).upper())
        except ValueError:
            return None


# Canonical ordering of difficulties — index 0 is NOVICE, 5 is GRANDMASTER.
DIFFICULTY_ORDER: list[Difficulty] = [
    Difficulty.NOVICE,
    Difficulty.APPRENTICE,
    Difficulty.PRACTITIONER,
    Difficulty.EXPERT,
    Difficulty.MASTER,
    Difficulty.GRANDMASTER,
]


#: Numeric 1-6 difficulty scale (spec §25). 1 = most basic, 6 = most difficult.
DIFFICULTY_SCALE: dict[int, Difficulty] = {
    1: Difficulty.NOVICE,
    2: Difficulty.APPRENTICE,
    3: Difficulty.PRACTITIONER,
    4: Difficulty.EXPERT,
    5: Difficulty.MASTER,
    6: Difficulty.GRANDMASTER,
}

#: Numeric 1-6 scale -> human-facing label (spec §25).
DIFFICULTY_SCALE_LABELS: dict[int, str] = {
    1: "introductory",
    2: "basic",
    3: "intermediate",
    4: "advanced",
    5: "difficult",
    6: "expert",
}


def difficulty_from_scale(level: int) -> Difficulty:
    """Resolve the canonical :class:`Difficulty` for a 1-6 scale level."""
    try:
        return DIFFICULTY_SCALE[int(level)]
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            f"difficulty scale must be an integer 1..6, got {level!r}"
        ) from None


def scale_of(difficulty: Difficulty) -> int:
    """Return the 1-6 scale level for a :class:`Difficulty`."""
    for level, diff in DIFFICULTY_SCALE.items():
        if diff is difficulty:
            return level
    raise ValueError(f"{difficulty!r} is not on the 1-6 scale")


@dataclass(frozen=True)
class DomainInfo:
    """Static metadata describing a learning domain."""

    name: str
    category: str
    description: str = ""


@dataclass
class ProblemMetadata:
    """Metadata attached to every generated problem."""

    timestamp: float = field(default_factory=time.time)
    version: str = __version__


@dataclass
class Problem:
    """A single curriculum problem.

    Attributes:
        id: Unique identifier (UUID4).
        title: Short human-readable title.
        domain: Name of the domain the problem belongs to.
        difficulty: :class:`Difficulty` level.
        question: The problem statement the learner must solve.
        context: Background / scenario framing the question.
        constraints: Rules the solver must respect.
        expected_format: Description of the expected output format.
        tags: Topical tags for filtering / search.
        metadata: :class:`ProblemMetadata` (timestamp, version).
    """

    id: str
    title: str
    domain: str
    difficulty: Difficulty
    question: str
    context: str
    constraints: list[str]
    expected_format: str
    tags: list[str]
    metadata: ProblemMetadata = field(default_factory=ProblemMetadata)

    @property
    def difficulty_rank(self) -> int:
        """Numeric rank of the difficulty (0 = NOVICE)."""
        return DIFFICULTY_ORDER.index(self.difficulty)


# ---------------------------------------------------------------------------
# Domain registry — 36 domains organized into five categories (the twelve
# JARVIS Core disciplines are the applied remainder of the spec §25 set).
# ---------------------------------------------------------------------------
DOMAIN_CATEGORIES: dict[str, list[str]] = {
    "STEM": [
        "Mathematics",
        "Physics",
        "Chemistry",
        "Biology",
        "Computer Science",
        "Engineering",
    ],
    "Humanities": [
        "History",
        "Literature",
        "Philosophy",
        "Languages",
        "Art History",
        "Geography",
    ],
    "Creative": [
        "Music",
        "Visual Arts",
        "Creative Writing",
        "Design",
        "Film Studies",
        "Theater",
    ],
    "Practical": [
        "Business",
        "Economics",
        "Law",
        "Medicine",
        "Cooking",
        "Personal Finance",
    ],
    "JARVIS Core": [
        "Programming",
        "Software Architecture",
        "Security",
        "Databases",
        "Networks",
        "Systems",
        "Machine Learning",
        "Research",
        "Reasoning",
        "Planning",
        "Tool Use",
        "Debugging",
    ],
}


def _build_domain_index() -> dict[str, DomainInfo]:
    """Flatten the category map into a name -> DomainInfo lookup."""
    index: dict[str, DomainInfo] = {}
    for category, names in DOMAIN_CATEGORIES.items():
        for name in names:
            index[name] = DomainInfo(name=name, category=category)
    return index


DOMAINS: list[DomainInfo] = [
    DomainInfo(name=name, category=category)
    for category, names in DOMAIN_CATEGORIES.items()
    for name in names
]


# Shared template element: per-domain tags.
_DOMAIN_TAGS: dict[str, list[str]] = {
    "Mathematics": ["algebra", "proof", "computation"],
    "Physics": ["mechanics", "thermodynamics", "modern-physics"],
    "Chemistry": ["stoichiometry", "organic", "equilibrium"],
    "Biology": ["genetics", "physiology", "ecology"],
    "Computer Science": ["algorithms", "complexity", "systems"],
    "Engineering": ["design", "materials", "controls"],
    "History": ["primary-sources", "chronology", "causation"],
    "Literature": ["analysis", "genre", "themes"],
    "Philosophy": ["logic", "ethics", "metaphysics"],
    "Languages": ["linguistics", "grammar", "translation"],
    "Art History": ["iconography", "periods", "technique"],
    "Geography": ["cartography", "regions", "demographics"],
    "Music": ["theory", "composition", "performance"],
    "Visual Arts": ["drawing", "color-theory", "media"],
    "Creative Writing": ["narrative", "character", "worldbuilding"],
    "Design": ["aesthetics", "usability", "layout"],
    "Film Studies": ["cinematography", "narrative", "genre"],
    "Theater": ["drama", "performance", "text"],
    "Business": ["strategy", "operations", "entrepreneurship"],
    "Economics": ["micro", "macro", "policy"],
    "Law": ["constitutions", "contracts", "precedent"],
    "Medicine": ["diagnosis", "pathophysiology", "treatment"],
    "Cooking": ["technique", "flavor", "nutrition"],
    "Personal Finance": ["budgeting", "investing", "taxation"],
    "Programming": ["python", "algorithms", "code"],
    "Software Architecture": ["design", "patterns", "scaling"],
    "Security": ["authentication", "threat-model", "crypto"],
    "Databases": ["sql", "transactions", "consistency"],
    "Networks": ["tcpip", "latency", "topology"],
    "Systems": ["operating-systems", "concurrency", "memory"],
    "Machine Learning": ["training", "evaluation", "overfitting"],
    "Research": ["methodology", "evidence", "reproducibility"],
    "Reasoning": ["logic", "inference", "decision"],
    "Planning": ["goals", "scheduling", "resources"],
    "Tool Use": ["api", "sandbox", "function-calling"],
    "Debugging": ["diagnosis", "root-cause", "regression"],
}

#: Difficulty level -> human-facing label and intensity marker.
_DIFFICULTY_LABELS: dict[Difficulty, str] = {
    Difficulty.NOVICE: "introductory",
    Difficulty.APPRENTICE: "foundational",
    Difficulty.PRACTITIONER: "intermediate",
    Difficulty.EXPERT: "advanced",
    Difficulty.MASTER: "specialist",
    Difficulty.GRANDMASTER: "research-level",
}


# ---------------------------------------------------------------------------
# JARVIS Core domains (spec §25 — the fifteen required disciplines).
# Mathematics / Physics / Computer Science already live in "STEM"; the twelve
# below are the applied / engineering-facing remainder.  Each entry maps
# difficulty index (0..5) -> (title, question, context, constraints, format).
# ---------------------------------------------------------------------------
_JARVIS_CORE_TEMPLATES: dict[str, list[tuple[str, str, str, list[str], str]]] = {
    "Programming": [
        ("Print a Name", "Write a function that prints 'hello' to stdout.",
         "First program exercise.", ["any language"], "code"),
        ("FizzBuzz", "Print 1..100 replacing multiples of 3 with Fizz, of 5 with Buzz, of both with FizzBuzz.",
         "Classic loop/condition exercise.", ["no external libraries"], "program output"),
        ("Reverse a String", "Reverse a string without using the built-in reverse.",
         "In-place / two-pointer technique.", ["O(n) time", "U(1) extra space"], "code + complexity"),
        ("LRU Cache", "Implement an LRU cache with get/put in O(1).",
         "Hash map + doubly-linked list design.", ["get and put both O(1)"], "pseudocode"),
        ("Concurrent Counter", "Design a lock-free bounded counter safe for many producers.",
         "Atomicity and ordering under contention.", ["no data races", "bounded memory"], "design + reasoning"),
        ("Parallel Scheduler", "Design a dependency-aware scheduler for a DAG of tasks over a thread pool.",
         "Topological scheduling, backpressure, cancellation.", ["deadlock-free", "bounded queues"], "design"),
    ],
    "Software Architecture": [
        ("Layered Design", "Name three classic layers of a web application.",
         "High-level architecture.", ["three layers"], "list"),
        ("Monolith vs Microservices", "Compare monolith and microservice deployment.",
         "Trade-off of deployment units.", ["one paragraph each"], "comparison"),
        ("REST Design", "Design a REST API for a book inventory with stock levels.",
         "Resource modeling and status codes.", ["idempotent updates"], "endpoint list"),
        ("Event-Driven Refactor", "Refactor a synchronous order pipeline into an event-driven flow.",
         "Events, queues, sagas, at-least-once delivery.", ["duplicate processing avoided"], "architecture description"),
        ("Scaling a Service", "Design the scaling story (caching, sharding, queues) for a read-heavy feed service.",
         "Capacity planning under growth.", ["consistency trade-offs stated"], "architecture description"),
        ("Distributed Consistency", "Compare consensus and CRDT approaches for multi-region wallet balances.",
         "CAP trade-offs, protocol selection, partial failure.", ["correctness argument"], "design analysis"),
    ],
    "Security": [
        ("Password Storing", "What is the wrong way to store passwords?",
         "Secure credential storage basics.", ["one sentence"], "answer"),
        ("SQL Injection", "Why is string-concatenated SQL unsafe?",
         "Query injection attack.", ["example"], "explanation"),
        ("Authentication Flows", "Compare session cookies with bearer tokens.",
         "Authn state and CSRF/XSS trade-offs.", ["both mechanisms"], "comparison"),
        ("Threat Modeling", "Produce a STRIDE threat model for an upload endpoint.",
         "Systematic threat enumeration.", ["all six STRIDE categories"], "threat list"),
        ("Cryptographic Design", "Design an end-to-end encrypted chat using public-key cryptography.",
         "Key exchange, forward secrecy, PFS trade-offs.", ["no plaintext at server"], "design"),
        ("Formal Verification", "Argue how to reduce memory-unsafety risk in a C library at scale.",
         "Fuzzing, sanitizers, proof-based mitigations.", ["defense in depth"], "security analysis"),
    ],
    "Databases": [
        ("Primary Key", "What is a primary key?",
         "Relational basics.", ["one sentence"], "answer"),
        ("Normal Forms", "What does 3NF require beyond 2NF?",
         "Database normalization.", ["key/transitive dependencies"], "definition"),
        ("Index Design", "Which index helps a WHERE clause on user_id and created_at?",
         "Composite index ordering.", ["explain why"], "index + rationale"),
        ("Transactions", "Explain ACID and choose an isolation level for a balance transfer.",
         "Concurrency and durability.", ["two levels compared"], "isolation description"),
        ("Consistency Trade-offs", "Design a system for globally replicated product reviews that must never lose writes.",
         "Consistency vs. availability, replication topology.", ["failure modes listed"], "design"),
        ("Query Optimization", "Analyze a slow JOIN across billion-row tables and propose storage/query changes.",
         "Cost-based planning, sharding, denormalization.", ["ordering of optimizations"], "analysis"),
    ],
    "Networks": [
        ("Port 443", "Which protocol typically runs on port 443?",
         "Transport basics.", ["one answer"], "protocol"),
        ("DNS Lookup", "Describe what happens when you type a URL in a browser.",
         "DNS, TCP, HTTP flow.", ["ordered steps"], "steps"),
        ("TCP vs UDP", "Compare TCP and UDP for a video call.",
         "Reliability vs. latency.", ["one use case each"], "comparison"),
        ("Latency Bridge", "A 100ms-then-500ms latency change breaks your service. Trace where frames are lost.",
         "Congestion, backpressure, TCP windowing.", ["measurement plan"], "diagnosis"),
        ("Network Partition", "Design messaging that behaves safely when two datacenters partition.",
         "Replication, quorum, split-brain control.", ["availability stated"], "design"),
        ("Networking Architecture", "Design a multi-region edge architecture for a latency-sensitive global API.",
         "Anycast, CDN, TLS termination, failover.", ["cost/latency trade-offs"], "architecture"),
    ],
    "Systems": [
        ("Memory Types", "Difference between stack and heap memory?",
         "Runtime memory layout.", ["two differences"], "answer"),
        ("Process vs Thread", "How do processes and threads differ?",
         "Concurrency fundamentals.", ["sharing model"], "comparison"),
        ("Deadlocks", "Give the four Coffman conditions for deadlock.",
         "System concurrency.", ["all four"], "list"),
        ("Memory Allocation", "How would you implement malloc for small objects?",
         "Free lists, fragmentation, coalescing.", ["amortized bounds"], "design"),
        ("Highly Concurrent Server", "Design a state machine to handle a million WebSocket clients on one box.",
         "Event loops, backpressure, memory limits.", ["per-client budget"], "design"),
        ("OS Scheduling", "Compare CFS, priority, and deadline schedulers under mixed latency-sensitive workloads.",
         "Fairness vs. latency guarantees.", ["workload example"], "analysis"),
    ],
    "Machine Learning": [
        ("Overfitting", "What does it mean for a model to overfit?",
         "Generalization basics.", ["one sentence"], "answer"),
        ("Precision Recall", "When is precision more important than recall?",
         "Classification metrics.", ["example"], "answer"),
        ("Evaluation Split", "Why separate train/validation/test sets and when to add a hold-out?",
         "Selection bias and leakage.", ["both cases"], "explanation"),
        ("Regularization", "Explain L1 vs L2 regularization and their effect on weights.",
         "Bias-variance trade-off.", ["sparsity difference"], "explanation"),
        ("Adversarial Robustness", "Design an evaluation harness for adversarial image robustness.",
         "Threat model and metrics.", ["baseline comparison"], "design"),
        ("Model Deployments", "Design a canary / shadow deployment policy for a ranking model.",
         "Regression detection, metrics, rollback.", ["decision thresholds"], "policy"),
    ],
    "Research": [
        ("Citation Purpose", "Why do we cite sources in research?",
         "Research integrity basics.", ["one reason"], "answer"),
        ("Hypothesis", "Write a testable hypothesis for a system slowdown.",
         "Empirical method.", ["falsifiable"], "hypothesis"),
        ("Control Groups", "Why compare against a control/baseline in experiments?",
         "Attribution of effect.", ["example"], "explanation"),
        ("Reproducible Setup", "List the artifacts needed to reproduce a model result.",
         "Rigorous methodology.", ["complete list"], "checklist"),
        ("Bias in Evidence", "Identify survivorship bias in a dataset of success stories.",
         "Evidence quality review.", ["example"], "analysis"),
        ("Experimental Design", "Design an A/B experiment with guardrail metrics for a ranking change.",
         "Power, novelty effects, monitoring.", ["minimum viable scale"], "design"),
    ],
    "Reasoning": [
        ("Two Truths", "Given two facts, derive one reliable conclusion.",
         "Deductive basics.", ["no new facts"], "conclusion"),
        ("Syllogism", "All A are B, some B are C. What follows?",
         "Quantified logic.", ["valid inference only"], "answer"),
        ("Abductive Choice", "Given noisy evidence, rank the two most plausible explanations.",
         "Inference under uncertainty.", ["rank and justify"], "ranking"),
        ("Contradiction Detection", "Find the contradiction in an argument set.",
         "Logical consistency.", ["name the contradiction"], "answer"),
        ("Decision under Uncertainty", "Weigh expected value vs. worst-case risk for a deployment choice.",
         "Decision theory.", ["explicit probabilities"], "analysis"),
        ("Causal Reasoning", "Distinguish correlation from causation given an observational study.",
         "Confounding, counterfactuals, interventions.", ["threats to validity"], "analysis"),
    ],
    "Planning": [
        ("Today's Plan", "Order three steps to ship a fix.",
         "Simple sequencing.", ["safe order"], "steps"),
        ("Dependency Order", "Which build steps must precede a release?",
         "Task dependencies.", ["topological order"], "list"),
        ("Risk Plan", "For a two-week feature, list the top three risks and mitigations.",
         "Planning under uncertainty.", ["one mitigation each"], "plan"),
        ("Resource Scheduling", "Schedule three engineers against a milestone with a critical path.",
         "Dependency and capacity constraints.", ["critical path marked"], "schedule"),
        ("Contingency Evolution", "Replan a launch when a dependency is delayed a week.",
         "Dynamic re-planning, re-scoping.", ["impact assessment"], "revised plan"),
        ("Long-Horizon Plan", "Given an AGI-alignment research program, structure a multi-year plan with review gates.",
         "Goal decomposition, checkpoints, reversibility.", ["review gates"], "plan"),
    ],
    "Tool Use": [
        ("Find a File", "Which command lists files in a directory?",
         "CLI basics.", ["no flags required"], "command"),
        ("Search Output", "Which command filters a log for lines containing 'error'?",
         "Text filtering.", ["single pipeline"], "command"),
        ("Sandbox Safety", "Why run untrusted code in a sandbox?",
         "Isolation rationale.", ["two reasons"], "answer"),
        ("API Call Design", "Design a retry/backoff policy for a flaky HTTP API.",
         "Timeout, retry, jitter, idempotency.", ["idempotency key"], "policy"),
        ("Function Calling", "Design a tool-calling loop where a model may issue several tool calls.",
         "Schema, validation, loop-bounds, error handling.", ["loop bound"], "design"),
        ("Toolchain Automation", "Design an agent harness that safely composes sandboxed tools for a build task.",
         "Permission model, capability grants, audit.", ["least privilege"], "design"),
    ],
    "Debugging": [
        ("First Steps", "What do you check first when a program crashes?",
         "Debugging basics.", ["two steps"], "answer"),
        ("Reproduce", "How do you reproduce an intermittent failure?",
         "Flaky bug isolation.", ["conditions to vary"], "plan"),
        ("Divide and Conquer", "Binary-search a failing commit across 100 changes.",
         "Efficient isolation.", ["log2 bound"], "procedure"),
        ("Root Cause", "A service fails only at peak load. Trace likely root causes in order.",
         "Anecdotal vs. systematic diagnosis.", ["evidence first"], "analysis"),
        ("Concurrency Bug", "An assertion fires rarely under contention. Design a reproduction strategy.",
         "Heisenbugs, stress, race detection.", ["exhaustive? no — systematic"], "strategy"),
        ("Regression Hunt", "Build a formal regression-search workflow across a long release history.",
         "Bisect, auto-flag, resource limits.", ["blame + evidence"], "workflow"),
    ],
}


class ProblemGenerator:
    """Curriculum problem generator for the JARVIS learning loop.

    Each of the 36 supported domains has a dedicated generator method
    (``_generate_<domain>``) so that problem phrasing is discipline-aware.
    Passing a ``seed`` makes generation reproducible.

    Typical usage::

        pg = ProblemGenerator(seed=42)
        problem = pg.generate(domain="Mathematics", difficulty="EXPERT")[0]
        curriculum = pg.generate_curriculum()
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)
        self._domain_index: dict[str, DomainInfo] = _build_domain_index()

        # Dispatch table: domain name -> bound generator method.
        self._generators: dict[str, Any] = {
            "Mathematics": self._generate_mathematics,
            "Physics": self._generate_physics,
            "Chemistry": self._generate_chemistry,
            "Biology": self._generate_biology,
            "Computer Science": self._generate_computer_science,
            "Engineering": self._generate_engineering,
            "History": self._generate_history,
            "Literature": self._generate_literature,
            "Philosophy": self._generate_philosophy,
            "Languages": self._generate_languages,
            "Art History": self._generate_art_history,
            "Geography": self._generate_geography,
            "Music": self._generate_music,
            "Visual Arts": self._generate_visual_arts,
            "Creative Writing": self._generate_creative_writing,
            "Design": self._generate_design,
            "Film Studies": self._generate_film_studies,
            "Theater": self._generate_theater,
            "Business": self._generate_business,
            "Economics": self._generate_economics,
            "Law": self._generate_law,
            "Medicine": self._generate_medicine,
            "Cooking": self._generate_cooking,
            "Personal Finance": self._generate_personal_finance,
            "Programming": self._generate_programming,
            "Software Architecture": self._generate_software_architecture,
            "Security": self._generate_security,
            "Databases": self._generate_databases,
            "Networks": self._generate_networks,
            "Systems": self._generate_systems,
            "Machine Learning": self._generate_machine_learning,
            "Research": self._generate_research,
            "Reasoning": self._generate_reasoning,
            "Planning": self._generate_planning,
            "Tool Use": self._generate_tool_use,
            "Debugging": self._generate_debugging,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_domains(self) -> list[str]:
        """Return the list of all supported domain names."""
        return list(self._domain_index.keys())

    def get_difficulties(self) -> list[str]:
        """Return the list of difficulty level names."""
        return [d.value for d in DIFFICULTY_ORDER]

    def generate(
        self,
        domain: Optional[str] = None,
        difficulty: Any = None,
        count: int = 1,
    ) -> list[Problem]:
        """Generate one or more problems, optionally filtered.

        Args:
            domain: Restrict generation to this domain (name must be valid).
            difficulty: Restrict to this level (string or :class:`Difficulty`).
            count: Number of problems to generate.

        Returns:
            List of :class:`Problem` objects (length == ``count``).
        """
        domain_names = self._select_domains(domain, count)
        difficulties = self._select_difficulties(difficulty, count)

        problems: list[Problem] = []
        for i in range(count):
            dom = domain_names[i]
            diff = difficulties[i]
            gen = self._generators[dom]
            problems.append(gen(diff))
        return problems

    def generate_curriculum(
        self,
        domains: Optional[list[str]] = None,
        difficulties: Optional[list[Any]] = None,
    ) -> dict[tuple[str, Difficulty], Problem]:
        """Build a full curriculum mapping of domain/difficulty -> Problem.

        Args:
            domains: Subset of domain names (defaults to all 24).
            difficulties: Subset of difficulty levels (defaults to all six).

        Returns:
            Dict keyed by ``(domain, difficulty)`` covering the Cartesian
            product of the given domains and difficulties.
        """
        domain_names = domains if domains is not None else self.get_domains()
        diff_levels = self._normalize_difficulties(difficulties)

        missing = [d for d in domain_names if d not in self._domain_index]
        if missing:
            raise ValueError(f"unknown domain(s): {missing}")

        curriculum: dict[tuple[str, Difficulty], Problem] = {}
        for dom in domain_names:
            for diff in diff_levels:
                curriculum[(dom, diff)] = self._generators[dom](diff)
        return curriculum

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _normalize_difficulties(
        self, values: Optional[list[Any]]
    ) -> list[Difficulty]:
        if values is None:
            return list(DIFFICULTY_ORDER)
        normalized: list[Difficulty] = []
        for v in values:
            d = Difficulty.from_value(v)
            if d is None:
                raise ValueError(f"unknown difficulty: {v!r}")
            normalized.append(d)
        return normalized

    def _select_domains(self, domain: Optional[str], count: int) -> list[str]:
        if domain is not None:
            name = self._resolve_domain(domain)
            return [name] * count
        return [self._rng.choice(self.get_domains()) for _ in range(count)]

    def _select_difficulties(
        self, difficulty: Any, count: int
    ) -> list[Difficulty]:
        target = Difficulty.from_value(difficulty)
        if target is not None:
            return [target] * count
        return [
            self._rng.choice(DIFFICULTY_ORDER) for _ in range(count)
        ]

    def _resolve_domain(self, name: str) -> str:
        normalized = name.strip()
        if normalized not in self._domain_index:
            raise ValueError(
                f"unknown domain {name!r}; use one of {self.get_domains()}"
            )
        return normalized

    def _level(self, difficulty: Difficulty) -> int:
        """Ordinal position of a difficulty (0 = NOVICE)."""
        return DIFFICULTY_ORDER.index(difficulty)

    def _make_problem(
        self,
        domain: str,
        difficulty: Difficulty,
        title: str,
        question: str,
        context: str = "",
        constraints: Optional[list[str]] = None,
        expected_format: str = "Free-form text response",
        tags: Optional[list[str]] = None,
    ) -> Problem:
        """Assemble a :class:`Problem` with standard id/metadata."""
        return Problem(
            id=str(uuid.uuid4()),
            title=title,
            domain=domain,
            difficulty=difficulty,
            question=question,
            context=context,
            constraints=list(constraints or []),
            expected_format=expected_format,
            tags=list(tags or []),
            metadata=ProblemMetadata(),
        )

    def _templates(
        self, domain: str
    ) -> list[tuple[str, str, str, list[str], str]]:
        """Return difficulty-indexed templates for a domain.

        Each difficulty index (0-5) yields one template tuple:
        ``(title, question, context, constraints, expected_format)``.
        Domain generators override :meth:`_domain_templates` instead.
        """
        raise NotImplementedError

    def _generate_jarvis_core(self, domain: str, difficulty: Difficulty) -> Problem:
        """Generate a problem for one of the twelve JARVIS Core domains.

        Driven by the :data:`_JARVIS_CORE_TEMPLATES` pool so questions stay
        discipline-faithful and scale from NOVICE to GRANDMASTER (spec §25).
        """
        level = self._level(difficulty)
        pool = _JARVIS_CORE_TEMPLATES[domain]
        idx = min(level, len(pool) - 1)
        title, question, context, constraints, out_fmt = pool[idx]
        return self._make_problem(
            domain, difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS[domain],
        )

    def _generate_programming(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Programming", difficulty)

    def _generate_software_architecture(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Software Architecture", difficulty)

    def _generate_security(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Security", difficulty)

    def _generate_databases(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Databases", difficulty)

    def _generate_networks(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Networks", difficulty)

    def _generate_systems(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Systems", difficulty)

    def _generate_machine_learning(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Machine Learning", difficulty)

    def _generate_research(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Research", difficulty)

    def _generate_reasoning(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Reasoning", difficulty)

    def _generate_planning(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Planning", difficulty)

    def _generate_tool_use(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Tool Use", difficulty)

    def _generate_debugging(self, difficulty: Difficulty) -> Problem:
        return self._generate_jarvis_core("Debugging", difficulty)

    # ------------------------------------------------------------------
    # Domain generators
    #
    # Each generator holds a small, difficulty-indexed template pool so that
    # questions legitimately scale from NOVICE to GRANDMASTER.
    # ------------------------------------------------------------------
    def _generate_mathematics(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Sum of a Kind", "Add the integers 23 + 47 + 89.",
             "A mental-arithmetic warm-up.", ["no calculator"], "integer"),
            ("Linear Balance", "Solve for x: 3x + 7 = 2x + 15.",
             "Basic linear equation.", ["show steps"], "x = <value>"),
            ("System of Equations", "Solve: 2a + 3b = 12; a - b = 1.",
             "Two-variable linear system.", ["exact fractions"], "a,b = <values>"),
            ("Quadratic Roots", "Find the roots of x^2 - 5x + 6 = 0.",
             "Factorable quadratic equation.", ["factor or quadratic formula"], "roots = <set>"),
            ("Calculus Optimization", "Minimize x^2 + (4/x) for x>0.",
             "Single-variable optimization via derivatives.", ["symbolic answer"], "minimum value = <number>"),
            ("Real Analysis Proof", "Prove that every Cauchy sequence converges in R.",
             "Metric-space completeness of the reals.", ["epsilon-delta arguments"], "proof"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Mathematics", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Mathematics"],
        )

    def _generate_physics(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Speed Distance Time", "A car travels 60 km in 30 minutes. What is its speed in km/h?",
             "Uniform motion in one dimension.", ["km/h"], "speed = <number> km/h"),
            ("Newton's Second Law", "A 5 kg mass accelerates at 2 m/s^2. Find the net force.",
             "Applying F = ma.", ["newtons"], "force = <number> N"),
            ("Energy Conservation", "A 2 kg block falls from 10 m. Find its speed at impact. (g=9.8)",
             "Converting potential to kinetic energy.", ["ignore air resistance"], "speed = <number> m/s"),
            ("Electric Field", "Find the field 0.1 m from a +1 uC point charge.",
             "Coulomb's law for point charges.", ["Coulomb constant k_e"], "field = <number> N/C"),
            ("Special Relativity", "A spaceship travels at 0.8c. What is the Lorentz factor?",
             "Time dilation and length contraction.", ["gamma notation"], "gamma = <number>"),
            ("Quantum Harmonic Oscillator", "Derive the ladder operator algebra for SHO.",
             "Second-quantized formalism.", ["commutator relations"], "operator algebra / energy spectrum"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Physics", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Physics"],
        )

    def _generate_chemistry(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Atomic Count", "How many atoms are in 2 H2O molecules?",
             "Molecular composition.", ["count all atoms"], "integer"),
            ("Stoichiometry", "Balance: Fe + O2 -> Fe2O3.",
             "Conservation of mass.", ["smallest whole coefficients"], "coefficients"),
            ("Gas Law", "1 mol of ideal gas at 273 K and 1 atm occupies how many liters?",
             "Ideal gas equation of state.", ["R = 0.0821"], "volume = <number> L"),
            ("Equilibrium Constant", "For aA + bB <-> cC, write K_c expression.",
             "Chemical equilibrium.", ["activities/concentrations"], "K_c = <expression>"),
            ("Organic Reaction", "Draw the major product of esterification between acetic acid and ethanol.",
             "Carboxylic acid + alcohol -> ester.", ["condensed or drawn formula"], "ester structure"),
            ("Statistical Thermodynamics", "Derive the partition function for a diatomic ideal gas.",
             "Translational, rotational, vibrational contributions.", ["Boltzmann statistics"], "Z = <expression>"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Chemistry", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Chemistry"],
        )

    def _generate_biology(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Cell Parts", "What organelle is the site of protein synthesis?",
             "Basic cell biology.", ["one word"], "organelle"),
            ("DNA Replication", "Which enzyme synthesizes the new DNA strand?",
             "Semi-conservative replication.", ["DNA polymerase name"], "enzyme"),
            ("Genetics Cross", "Cross PP x pp peas. What proportion of offspring are PP?",
             "Mendelian monohybrid cross.", ["fraction"], "proportion = <fraction>"),
            ("Enzyme Kinetics", "Define Km and Vmax in Michaelis-Menten kinetics.",
             "Enzyme catalysis parameters.", ["two definitions"], "Km, Vmax"),
            ("Cell Signaling", "Outline the MAPK cascade and its role in cell proliferation.",
             "Signal transduction pathways.", ["key intermediates"], "cascade summary"),
            ("Systems Biology", "Formulate a coupled ODE model for predator-prey dynamics with a time delay.",
             "Nonlinear dynamical systems in ecology.", ["state variables"], "ODE system"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Biology", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Biology"],
        )

    def _generate_computer_science(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Sorting", "Sort [3, 1, 2] by hand using insertion sort.",
             "Elementary sorting algorithm.", ["show intermediate states"], "sorted list"),
            ("Complexity", "Give the Big-O of binary search.",
             "Asymptotic analysis.", ["base-2 logarithm"], "O(log n)"),
            ("Data Structure", "Implement a stack with push, pop, and min in O(1).",
             "Abstract data type design.", ["amortized analysis"], "pseudocode"),
            ("Algorithms", "Describe Dijkstra's algorithm and its runtime with a binary heap.",
             "Shortest-path graph algorithm.", ["non-negative weights"], "complexity + description"),
            ("Systems", "Explain how demand paging uses the page table and TLB.",
             "Virtual memory management.", ["OS-specific terms"], "explanation"),
            ("Theory", "Prove that NP ∩ co-NP is closed under complement.",
             "Computational complexity classes.", ["polynomial reductions"], "proof"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Computer Science", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Computer Science"],
        )

    def _generate_engineering(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Units", "Convert 5 meters to centimeters.",
             "SI unit conversion.", ["cm"], "500 cm"),
            ("Statics", "A 10 N weight hangs from two symmetric cables. Find the tension in each.",
             "Force equilibrium.", ["ignore cable mass"], "tension = <number> N"),
            ("Materials", "Calculate the stress in a 1 cm^2 rod under 500 N tension.",
             "Stress-strain basics.", ["Pa"], "stress = <number> Pa"),
            ("Dynamics", "Derive the transfer function of a series RLC circuit.",
             "Second-order system modeling.", ["Laplace domain"], "H(s) = <expression>"),
            ("Controls", "Design a PID controller for a DC motor with given plant G(s).",
             "Feedback control design.", ["stability margins"], "controller form"),
            ("Design", "Perform a fatigue-life analysis using an SN curve for a steel component under cyclic loading.",
             "Reliability engineering.", ["Basquin equation"], "cycles to failure"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Engineering", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Engineering"],
        )

    def _generate_history(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Dating", "Was the Roman Empire's fall before or after 476 AD?",
             "Basic historical chronology.", ["one word"], "before/after"),
            ("Cause and Effect", "Name one factor that contributed to the Black Death's spread.",
             "Medieval pandemics.", ["trade routes"], "factor"),
            ("Analysis", "Compare two causes of the French Revolution.",
             "18th-century European upheaval.", ["specific examples"], "comparison"),
            ("Primary Source", "Explain how the Magna Carta limited royal authority.",
             "English constitutional history.", ["at least two clauses"], "explanation"),
            ("Synthesis", "Assess the role of industrialization in driving 19th-century nationalism.",
             "Interconnected historical forces.", ["multiple regions"], "thesis + evidence"),
            ("Historiography", "Debate the 'colonial depletion' thesis as an explanation for pre-Columbian decline in the Andes.",
             "Revisionist scholarship.", ["cite secondary sources"], "historiographical argument"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "History", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["History"],
        )

    def _generate_literature(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Character", "Who is the main character in 'Romeo and Juliet'?",
             "Shakespearean tragedy.", ["one name"], "name"),
            ("Theme", "Name one theme in 'To Kill a Mockingbird'.",
             "American fiction.", ["single concept"], "theme"),
            ("Analysis", "Explain the symbolism of the green light in 'The Great Gatsby'.",
             "Modernist American novel.", ["Fitzgerald's intent"], "symbolism analysis"),
            ("Genre", "Compare the structure of a sonnet and a villanelle.",
             "Poetic forms.", ["rhyme scheme"], "comparison"),
            ("Theory", "Apply Bakhtin's concept of dialogism to a multi-narrator novel.",
             "Literary theory.", ["at least two voices"], "application"),
            ("Semiotics", "Decode the semiotic function of the 'unreliable narrator' across three modernist texts.",
             "Narratology.", ["structuralist terms"], "semiotic reading"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Literature", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Literature"],
        )

    def _generate_philosophy(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Logic", "Is 'All birds fly' a universal affirmative or particular?", 
             "Categorical propositions.", ["one term"], "type"),
            ("Ethics", "State the trolley problem in one sentence.",
             "Moral dilemmas.", ["consequentialist framing"], "summary"),
            ("Theory", "Explain Plato's allegory of the cave in two sentences.",
             "Platonic epistemology.", ["shadow / sun metaphor"], "summary"),
            ("Metaphysics", "Contrast Descartes' mind-body dualism with Spinoza's monism.",
             "Nature of reality.", ["substance vs attribute"], "contrast"),
            ("Logic", "Construct a formal proof of (P -> Q) -> (¬Q -> ¬P).",
             "Propositional calculus.", ["natural deduction"], "proof"),
            ("Metaethics", "Defend or refute moral realism using the argument from moral disagreement.",
             "Metaethical methodology.", ["semantic / metaphysical premises"], "argument"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Philosophy", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Philosophy"],
        )

    def _generate_languages(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Conjugation", "Conjugate 'hablar' (Spanish) in the present tense.",
             "Romance verb conjugation.", ["yo ... nosotros"], "conjugation"),
            ("Grammar", "Identify the part of speech for 'quickly' in English.",
             "Descriptive grammar.", ["single label"], "part of speech"),
            ("Syntax", "Draw a parse tree for 'The cat sat on the mat'.",
             "Sentence structure.", ["bracketed or diagram"], "tree"),
            ("Semantics", "Give two lexical senses of 'bank' and frame them in sentences.",
             "Word meaning.", ["distinct meanings"], "senses + examples"),
            ("Phonology", "Transcribe 'think' in IPA and note its distinctive feature.",
             "Phonetic transcription.", ["IPA symbols"], "transcription"),
            ("Historical", "Trace the Great Vowel Shift and its effect on English spelling.",
             "Historical linguistics.", ["chronological stages"], "narrative"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Languages", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Languages"],
        )

    def _generate_art_history(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Date", "Was Van Gogh's 'Starry Night' painted in the 19th century?",
             "Basic chronology.", ["yes/no"], "yes/no"),
            ("Technique", "Name the medium Van Gogh used for 'Starry Night'.",
             "Painting materials.", ["oil on canvas"], "medium"),
            ("Style", "Compare the composition of a Renaissance and a Baroque painting.",
             "Art historical styles.", ["perspective / movement"], "comparison"),
            ("Iconography", "Interpret the meaning of the laurel wreath in Caravaggio's 'David with the Head of Goliath'.",
             "Symbol interpretation.", ["Christian symbolism"], "interpretation"),
            ("Context", "Analyze how the Arte Povera manifesto shaped material choices in 1960s sculpture.",
             "Modernist movement.", ["primary text"], "analysis"),
            ("Theory", "Critique Titian's 'Bacchus and Ariadne' through the lens of phenomenology and color theory, citing visual evidence.",
             "Aesthetic theory.", ["sensory experience"], "critical essay"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Art History", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Art History"],
        )

    def _generate_geography(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Location", "Is Brazil in the southern or northern hemisphere?",
             "Global geography.", ["one word"], "hemisphere"),
            ("Physical", "Which river flows through Egypt?",
             "River systems.", ["one river"], "Nile"),
            ("Human", "Explain the relationship between GDP and energy consumption in industrialized nations.",
             "Resource geography.", ["correlation"], "explanation"),
            ("Mapping", "Describe two common projections used for world maps and their distortion trade-offs.",
             "Cartographic projections.", ["Mercator / Peters"], "comparison"),
            ("Regional", "Compare urbanization patterns in Sub-Saharan Africa and East Asia since 1990.",
             "Development geography.", ["demographics"], "comparison"),
            ("Spatial Analysis", "Model the diffusion of a disease vector across a heterogeneous landscape using GIS-based spatial statistics.",
             "Geospatial analysis.", ["spatial autocorrelation"], "methodology"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Geography", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Geography"],
        )

    def _generate_music(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Rhythm", "How many beats does a quarter note get in 4/4 time?",
             "Basic meter.", ["integer"], "1 beat"),
            ("Theory", "Name the notes in a C major triad.",
             "Harmonic triads.", ["root position"], "C-E-G"),
            ("Form", "Identify the structure of a 12-bar blues progression.",
             "Musical form.", ["three phrases"], "AAB form"),
            ("Analysis", "Explain how Debussy uses whole-tone scales to evoke 'floating' quality.",
             "Impressionist harmony.", ["non-tonal harmony"], "analysis"),
            ("Composition", "Compose a 16-measure phrase using sonata-form exposition conventions.",
             "Large-scale structure.", ["theme + development"], "composition"),
            ("Ethnomusicology", "Analyze the rhythmic cycles (tala) of North Indian classical music and their relationship to metric modulation.",
             "Cross-cultural music theory.", ["adda tala"], "analysis"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Music", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Music"],
        )

    def _generate_visual_arts(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Color", "What are the three subtractive primary colors?",
             "Color theory basics.", ["three terms"], "cyan, magenta, yellow"),
            ("Technique", "Describe the cross-hatching technique.",
             "Drawing methods.", ["one sentence"], "description"),
            ("Medium", "Compare oil paint and watercolor in terms of drying time and blending.",
             "Painting media.", ["two media"], "comparison"),
            ("Composition", "Explain how Mondrian used the rule of thirds and primary colors in 'Composition with Red Blue Yellow'.",
             "De Stijl principles.", ["geometric abstraction"], "analysis"),
            ("Theory", "Discuss how Gestalt principles apply to Picasso's cubist collages.",
             "Perception theory.", ["figure / ground"], "discussion"),
            ("Semiotics", "Interrogate the indexical and symbolic registers of a contemporary photograph addressing climate crisis.",
             "Visual semiotics.", ["Benjamin / Barthes"], "semiotic reading"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Visual Arts", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Visual Arts"],
        )

    def _generate_creative_writing(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Character", "Write a 50-word character sketch of someone waiting at a bus stop.",
             "Narrative basics.", ["exactly 50 words"], "50-word sketch"),
            ("Dialogue", "Write a 60-word dialogue where two people misunderstand each other.",
             "Conversational subtext.", ["dialogue only"], "dialogue"),
            ("Plot", "Outline the three-act structure of 'The Tortoise and the Hare'.",
             "Folk tale narrative.", ["setup / climax / resolution"], "outline"),
            ("Style", "Rewrite this prosaic line in Hemingway's icebergged style: 'She was sad.'",
             "Minimalist prose.", ["one sentence"], "rewritten line"),
            ("Narrative", "Craft a 300-word story where the last line reframes the entire meaning.",
             "Twist endings.", ["word count"], "story"),
            ("Genre", "Write an excerpt (300-500 words) of hard science fiction that integrates a verifiable physics concept as plot driver.",
             "Speculative fiction.", ["no magic"], "excerpt"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Creative Writing", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Creative Writing"],
        )

    def _generate_design(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Layout", "What does UI stand for in design?",
             "Design terminology.", ["acronym"], "User Interface"),
            ("Typography", "Name two sans-serif fonts commonly used on the web.",
             "Font classification.", ["two names"], "font names"),
            ("Color", "Pick an accessible color pair for body text on a white background.",
             "Web accessibility.", ["WCAG AA contrast"], "hex pair"),
            ("UX", "Design a checkout flow for an online store, reducing steps from cart to confirmation.",
             "E-commerce UX.", ["minimum 3 steps"], "flow description"),
            ("Systems", "Apply a service-design blueprint to diagnose friction in a university course-registration system.",
             "Design thinking.", ["frontstage/backstage"], "blueprint"),
            ("Theory", "Propose a design system that reconciles material semantics with biophilic design principles for a neurodiverse workspace.",
             "Inclusive design.", ["evidence-based"], "proposal"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Design", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Design"],
        )

    def _generate_film_studies(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Genre", "Is 'Jurassic Park' an action or horror film?",
             "Film genre basics.", ["one word"], "genre"),
            ("Cinematography", "What does a close-up shot convey about a character?",
             "Shot scales.", ["emotion / intimacy"], "effect"),
            ("Editing", "Explain match-on-action cutting using an example from any action film.",
             "Continuity editing.", ["temporal continuity"], "explanation"),
            ("Theory", "Analyse how the dolly zoom in 'Vertigo' realizes 'acousmatic' tension.",
             "Film language.", ["Hitchcock"], "analysis"),
            ("Auteur", "Situate the motifs of mirrors and doubles across three films by Ingmar Bergman.",
             "Auteur studies.", ["specific motifs"], "motifs overview"),
            ("Semiotics", "Deconstruct the ideological register of the 'final girl' trope across the slasher canon (1978-1995).",
             "Genre theory.", ["Carol J. Clover"], "deconstruction"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Film Studies", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Film Studies"],
        )

    def _generate_theater(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Form", "What is the name of a play's dramatic structure with five parts?",
             "Classical drama.", ["one word"], "Shakespearean / Aristotelian"),
            ("Terminology", "Define 'aside' in stage acting.",
             "Dramatic convention.", ["one sentence"], "definition"),
            ("Text", "Summarize the prologue of 'Romeo and Juliet' in one sentence.",
             "Shakespearean prologue.", ["one sentence"], "summary"),
            ("Space", "Compare proscenium and thrust staging layouts.",
             "Theatrical space.", ["audience orientation"], "comparison"),
            ("History", "Contrast Brecht's alienation effect with Stanislavski's emotional memory.",
             "Performance theory.", ["two techniques"], "contrast"),
            ("Practice", "Design a devised theatre piece that incorporates live-feed video and addresses climate grief, specifying rehearsal methodology.",
             "Contemporary practice.", ["devising process"], "design"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Theater", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Theater"],
        )

    def _generate_business(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Term", "What does ROI stand for?",
             "Business metric.", ["acronym"], "Return on Investment"),
            ("Finance", "If revenue is $1000 and costs are $600, what is profit?",
             "Basic accounting.", ["dollars"], "$400"),
            ("Marketing", "Explain the 4Ps of marketing with one example each.",
             "Marketing mix.", ["product / price / place / promotion"], "examples"),
            ("Strategy", "Perform a SWOT analysis for a subscription-box startup.",
             "Strategic planning.", ["internal/external"], "SWOT grid"),
            ("Operations", "Calculate the EOQ given demand, ordering cost, and holding cost.",
             "Inventory management.", ["EOQ formula"], "EOQ value"),
            ("Management", "Design a governance framework for an AI-driven platform balancing innovation velocity against regulatory compliance.",
             "Corporate governance.", ["risk controls"], "framework"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Business", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Business"],
        )

    def _generate_economics(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Concept", "When price rises and quantity demanded falls, what is this relationship called?",
             "Law of demand.", ["one term"], "law of demand / inverse relationship"),
            ("Micro", "If a $2 tax creates a $500 deadweight loss, what does this signal about elasticity?",
             "Tax incidence.", ["elastic / inelastic"], "elasticity signal"),
            ("Macro", "Explain how the spending multiplier works in a closed economy.",
             "Keynesian multiplier.", ["MPC"], "explanation"),
            ("Theory", "Graph the effect of a binding price ceiling on equilibrium surplus.",
             "Market interventions.", ["shortage"], "graph description"),
            ("Policy", "Compare the effectiveness of fiscal vs monetary policy in a liquidity trap.",
             "Macroeconomic policy.", ["zero lower bound"], "comparison"),
            ("Advanced", "Solve for the steady-state capital-labor ratio in a Ramsey-Cass-Koopmans growth model with a CES production function.",
             "Optimal growth theory.", ["transversality condition"], "steady state"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Economics", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Economics"],
        )

    def _generate_law(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Term", "What does 'pro bono' mean?",
             "Legal Latin.", ["English translation"], "for the public good"),
            ("Constitutional", "Name one right protected by the First Amendment.",
             "U.S. Bill of Rights.", ["one right"], "right"),
            ("Contract", "List the four elements required to form a valid contract.",
             "Contract law.", ["offer, acceptance, consideration, intent"], "elements"),
            ("Tort", "Differentiate negligence from strict liability.",
             "Tort law.", ["fault requirement"], "differentiation"),
            ("Corporate", "Outline the fiduciary duties of a corporate board under Delaware law.",
             "Corporate governance.", ["duty of care / loyalty"], "duties"),
            ("International", "Argue whether the principle of 'pacta sunt servanda' can justify enforcing a treaty that violates fundamental human rights.",
             "Treaty law.", ["Vienna Convention"], "argument"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Law", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Law"],
        )

    def _generate_medicine(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Anatomy", "How many chambers does a human heart have?",
             "Cardiovascular system.", ["integer"], "4"),
            ("Physiology", "What is the primary gas exchanged in the lungs?",
             "Respiratory system.", ["one gas"], "oxygen / carbon dioxide"),
            ("Pathology", "Name the metabolic pathway that produces ATP in the absence of oxygen.",
             "Cellular respiration.", ["anaerobic"], "pathway"),
            ("Pharmacology", "Explain the mechanism of action of beta-blockers.",
             "Cardiovascular drugs.", ["receptor"], "mechanism"),
            ("Diagnostics", "Interpret an ECG showing ST-elevation in leads II, III, aVF.",
             "Cardiac biomarkers.", ["acute MI"], "interpretation"),
            ("Clinical", "Design a management plan for a patient presenting with acute chest pain, atrial fibrillation, and a CHA2DS2-VASc score of 3.",
             "Evidence-based medicine.", ["risk stratification"], "plan"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Medicine", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Medicine"],
        )

    def _generate_cooking(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Technique", "What cooking method uses dry heat in an enclosed pot?",
             "Heat transfer methods.", ["one word"], "braising"),
            ("Temperature", "At what internal temperature is a beef steak medium-rare? (Fahrenheit)",
             "Meat doneness.", ["degrees F"], "130-135 F"),
            ("Sauce", "Name the mother sauce that is thickened with a roux and milk.",
             "French cuisine.", ["one sauce"], "béchamel"),
            ("Flavor", "Describe how umami is amplified in a miso ramble.",
             "Flavor science.", ["fermentation"], "description"),
            ("Fermentation", "Outline the biochemical steps of lacto-fermentation in sauerkraut production.",
             "Food microbiology.", ["salt / bacteria"], "steps"),
            ("Science", "Engineer a sous-vide protocol for a 2-inch thick ribeye that balances lipid oxidation against myosin denaturation over a 4-hour hold.",
             "Culinary science.", ["temperature / time"], "protocol"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Cooking", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Cooking"],
        )

    def _generate_personal_finance(self, difficulty: Difficulty) -> Problem:
        level = self._level(difficulty)
        templates = [
            ("Term", "What does APR represent?",
             "Borrowing cost.", ["acronym"], "Annual Percentage Rate"),
            ("Budgeting", "If you earn $4000/month and spend $3200, how much can you save?",
             "Monthly cash flow.", ["dollars"], "$800"),
            ("Investing", "Explain how a Roth IRA differs from a traditional IRA.",
             "Retirement accounts.", ["tax treatment"], "difference"),
            ("Compound Interest", "Calculate the future value of $1000 at 5% annual interest compounded monthly for 10 years.",
             "Time value of money.", ["compound formula"], "FV = <number>"),
            ("Portfolio", "Construct an efficient frontier for three assets given their expected returns and covariance matrix.",
             "Modern portfolio theory.", ["mean-variance"], "frontier"),
            ("Advanced", "Design a tax-efficient withdrawal strategy spanning 30 years of retirement that minimizes lifetime tax burden while hedging sequence-of-returns risk.",
             "Financial planning.", ["required minimum distributions"], "strategy"),
        ]
        idx = min(level, len(templates) - 1)
        title, question, context, constraints, out_fmt = templates[idx]
        return self._make_problem(
            "Personal Finance", difficulty, title, question,
            context, constraints, out_fmt, _DOMAIN_TAGS["Personal Finance"],
        )


__all__ = [
    "Difficulty",
    "DIFFICULTY_ORDER",
    "DomainInfo",
    "DOMAINS",
    "DOMAIN_CATEGORIES",
    "Problem",
    "ProblemMetadata",
    "ProblemGenerator",
]
