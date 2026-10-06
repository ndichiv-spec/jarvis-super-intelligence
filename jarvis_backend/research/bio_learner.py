"""Bio-Growth Learning Framework — Curriculum, Memory & Maturity.

CLASSIFIED: Private JARVIS infrastructure.

This module implements JARVIS's bio-growth learning architecture — learning
that grows organically like biological development, from "birth" (seed
knowledge) through "growth" (accretion and consolidation) to "mastery"
(cross-domain synthesis) and "infinity" (self-transcending exploration).

Key mechanisms:
- **Maturity scoring**: Each knowledge domain gets a score from 0 (unfamiliar)
  to ∞ (expert). Growth follows a sigmoid curve with diminishing returns.
- **Curriculum learning**: Concepts are ordered by prerequisite relationships
  and difficulty, following a developmental progression.
- **Memory consolidation**: Spaced repetition (SM-2 algorithm) with
  forgetting curve modeling for long-term retention.
- **Forgetting & reconsolidation**: Unreinforced memories decay; retrieved
  memories are strengthened (hippocampal replay pattern).
- **Cross-domain synthesis**: When two domains reach sufficient maturity,
  the system attempts to synthesize novel insights from their intersection.

Growth stages:
  Birth (0-1): Basic pattern recognition, simple recall
  Growth (1-100): Structured learning, curriculum progression
  Mastery (100-∞): Creative synthesis, hypothesis generation
  Infinity (∞+): Self-directed exploration, theory construction
"""
from __future__ import annotations

import uuid
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

import logging

log = logging.getLogger("jarvis.research.biolearner")
MAX_LEARNING_EPISODES = 5000


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

class GrowthStage(str, Enum):
    BIRTH = "birth"        # Stage 0: Seed knowledge, basic patterns
    GROWTH = "growth"      # Stage 1: Curriculum learning, consolidation
    MASTERY = "mastery"    # Stage 2: Cross-domain synthesis
    INFINITY = "infinity"  # Stage 3: Self-transcending exploration


@dataclass
class KnowledgeDomain:
    """A domain of knowledge with a maturity score and curriculum."""
    id: str
    name: str
    description: str
    parent_domains: List[str] = field(default_factory=list)
    maturity_score: float = 0.0
    growth_stage: GrowthStage = GrowthStage.BIRTH
    concepts: List[str] = field(default_factory=list)
    mastered_concepts: List[str] = field(default_factory=list)
    in_progress_concepts: List[str] = field(default_factory=list)
    learning_rate: float = 1.0  # How quickly this domain grows
    first_explored: Optional[str] = None
    last_interaction: Optional[str] = None
    interactions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_domains": self.parent_domains,
            "maturity_score": self.maturity_score,
            "growth_stage": self.growth_stage.value,
            "concepts": self.concepts,
            "mastered_concepts": self.mastered_concepts,
            "in_progress_concepts": self.in_progress_concepts,
            "learning_rate": self.learning_rate,
            "first_explored": self.first_explored,
            "last_interaction": self.last_interaction,
            "interactions": self.interactions,
        }


@dataclass
class Concept:
    """A single concept within a domain."""
    id: str
    name: str
    domain_id: str
    description: str = ""
    prerequisites: List[str] = field(default_factory=list)
    difficulty: float = 1.0  # 0.0 (trivial) to 10.0 (research-level)
    mastery_level: float = 0.0  # 0.0 (unseen) to 1.0 (mastered)
    next_review: Optional[str] = None
    times_reviewed: int = 0
    retention_score: float = 0.0  # Based on spaced repetition recall history
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain_id": self.domain_id,
            "description": self.description,
            "prerequisites": self.prerequisites,
            "difficulty": self.difficulty,
            "mastery_level": self.mastery_level,
            "next_review": self.next_review,
            "times_reviewed": self.times_reviewed,
            "retention_score": self.retention_score,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


@dataclass
class LearningEpisode:
    """A single learning session / interaction."""
    id: str
    domain_id: str
    concept_id: Optional[str]
    action: str  # "study", "practice", "review", "synthesize", "discover"
    outcome: str  # "success", "partial", "failure"
    duration_seconds: float
    timestamp: str
    notes: str = ""
    related_items: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "domain_id": self.domain_id,
            "concept_id": self.concept_id,
            "action": self.action,
            "outcome": self.outcome,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "notes": self.notes,
            "related_items": self.related_items,
        }


@dataclass
class Synthesis:
    """A cross-domain synthesis event."""
    id: str
    domains_involved: List[str]
    concepts_combined: List[str]
    insight: str
    confidence: float
    novelty_score: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "domains_involved": self.domains_involved,
            "concepts_combined": self.concepts_combined,
            "insight": self.insight,
            "confidence": self.confidence,
            "novelty_score": self.novelty_score,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Curriculum — domain definitions with concept hierarchies
# ---------------------------------------------------------------------------

# Domain definitions with prerequisite structures (birth → growth progression)
DOMAIN_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "mathematics": {
        "name": "Mathematics",
        "description": "Pure and applied mathematics from arithmetic to advanced theory",
        "concepts": [
            {"name": "arithmetic", "difficulty": 1.0, "prerequisites": []},
            {"name": "algebra_basics", "difficulty": 2.0, "prerequisites": ["arithmetic"]},
            {"name": "linear_equations", "difficulty": 2.5, "prerequisites": ["algebra_basics"]},
            {"name": "quadratics", "difficulty": 3.0, "prerequisites": ["linear_equations"]},
            {"name": "functions", "difficulty": 3.5, "prerequisites": ["quadratics"]},
            {"name": "calculus_basics", "difficulty": 5.0, "prerequisites": ["functions"]},
            {"name": "differential_equations", "difficulty": 7.0, "prerequisites": ["calculus_basics"]},
            {"name": "abstract_algebra", "difficulty": 8.0, "prerequisites": ["differential_equations"]},
            {"name": "topology", "difficulty": 9.5, "prerequisites": ["abstract_algebra"]},
        ],
    },
    "computer_science": {
        "name": "Computer Science",
        "description": "Algorithms, systems, and computational theory",
        "concepts": [
            {"name": "boolean_logic", "difficulty": 1.0, "prerequisites": []},
            {"name": "sorting", "difficulty": 2.5, "prerequisites": ["boolean_logic"]},
            {"name": "data_structures", "difficulty": 3.5, "prerequisites": ["sorting"]},
            {"name": "algorithms", "difficulty": 4.5, "prerequisites": ["data_structures"]},
            {"name": "complexity_theory", "difficulty": 6.0, "prerequisites": ["algorithms"]},
            {"name": "distributed_systems", "difficulty": 7.5, "prerequisites": ["complexity_theory"]},
            {"name": "formal_verification", "difficulty": 8.5, "prerequisites": ["distributed_systems"]},
        ],
    },
    "physics": {
        "name": "Physics",
        "description": "Classical and modern physics",
        "concepts": [
            {"name": "classical_mechanics", "difficulty": 2.0, "prerequisites": []},
            {"name": "thermodynamics", "difficulty": 3.5, "prerequisites": ["classical_mechanics"]},
            {"name": "electromagnetism", "difficulty": 4.0, "prerequisites": ["classical_mechanics"]},
            {"name": "quantum_mechanics", "difficulty": 7.0, "prerequisites": ["electromagnetism", "linear_algebra"]},
            {"name": "relativity", "difficulty": 7.5, "prerequisites": ["quantum_mechanics"]},
            {"name": "quantum_field_theory", "difficulty": 9.0, "prerequisites": ["relativity"]},
        ],
    },
    "artificial_intelligence": {
        "name": "Artificial Intelligence",
        "description": "Machine learning, reasoning, and intelligent systems",
        "concepts": [
            {"name": "pattern_recognition", "difficulty": 2.0, "prerequisites": []},
            {"name": "neural_networks", "difficulty": 4.0, "prerequisites": ["pattern_recognition", "calculus_basics"]},
            {"name": "deep_learning", "difficulty": 5.5, "prerequisites": ["neural_networks"]},
            {"name": "reinforcement_learning", "difficulty": 6.5, "prerequisites": ["deep_learning"]},
            {"name": "transformers", "difficulty": 7.0, "prerequisites": ["deep_learning"]},
            {"name": "alignment", "difficulty": 8.0, "prerequisites": ["transformers"]},
            {"name": "agi_research", "difficulty": 9.5, "prerequisites": ["alignment"]},
        ],
    },
    "biology": {
        "name": "Biology",
        "description": "Life sciences from molecular to ecosystem level",
        "concepts": [
            {"name": "cell_biology", "difficulty": 2.0, "prerequisites": []},
            {"name": "genetics", "difficulty": 4.0, "prerequisites": ["cell_biology"]},
            {"name": "evolution", "difficulty": 5.0, "prerequisites": ["genetics"]},
            {"name": "neuroscience", "difficulty": 6.5, "prerequisites": ["cell_biology"]},
            {"name": "systems_biology", "difficulty": 7.5, "prerequisites": ["genetics", "evolution"]},
        ],
    },
}

# SM-2 spaced repetition algorithm constants
SM2_MIN_EF = 1.3  # Easy factor minimum
SM2_INITIAL_EF = 2.5  # Easy factor default for new items


class SpacedRepetition:
    """SM-2 algorithm implementation for memory consolidation."""

    @staticmethod
    def compute_next_review(concept: Concept, quality: float) -> Tuple[int, float]:
        """Compute next review interval and updated ease factor.

        Args:
            concept: The concept being reviewed
            quality: Recall quality (0-5 scale, 5 = perfect)

        Returns:
            (days_until_next_review, updated_ease_factor)
        """
        ef = getattr(concept, "_ease_factor", SM2_INITIAL_EF)

        # Update ease factor
        ef = max(SM2_MIN_EF, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

        # Compute interval
        if quality < 3:
            # Failed recall — restart
            interval = 1
        elif concept.times_reviewed == 0:
            interval = 1
        elif concept.times_reviewed == 1:
            interval = 6
        else:
            # Use the concept's previous interval
            prev_interval = getattr(concept, "_last_interval", 6)
            interval = int(prev_interval * ef)

        return interval, ef


# ---------------------------------------------------------------------------
# Maturity scoring — bio-inspired sigmoid growth
# ---------------------------------------------------------------------------

def compute_maturity_score(raw_score: float, learning_rate: float = 1.0) -> float:
    """Compute maturity score using a sigmoid growth function.

    Models biological growth: rapid in the middle, plateau at extremes.
    Score ranges from 0 (unfamiliar) to asymptotically ∞.

    The inflection point is at raw_score = 50, where the growth rate is highest.
    """
    # Sigmoid-based maturity: starts slow, accelerates, plateaus
    # Scale: raw_score of 0 → 0, 50 → 100, 100 → ~∞ (but practically capped)
    scaled = raw_score * learning_rate
    if scaled < 1:
        # Birth stage: very slow growth
        return scaled * 0.5
    elif scaled < 50:
        # Growth stage: accelerated growth
        return scaled
    elif scaled < 200:
        # Mastery stage: diminishing returns
        return 200 * math.log(max(1, scaled / 50), 10) + 50
    else:
        # Infinity stage: logarithmic growth (never truly infinite, but unbounded)
        return 500 + 100 * math.log(max(1, scaled / 200), 10)


def compute_growth_stage(maturity: float) -> GrowthStage:
    """Map a maturity score to a growth stage."""
    if maturity < 1:
        return GrowthStage.BIRTH
    elif maturity < 100:
        return GrowthStage.GROWTH
    elif maturity < 500:
        return GrowthStage.MASTERY
    else:
        return GrowthStage.INFINITY


# ---------------------------------------------------------------------------
# Forgetting curve
# ---------------------------------------------------------------------------

def compute_retention_score(time_since_last_review_hours: float, stability: float = 1.0) -> float:
    """Compute retention score based on forgetting curve (Ebbinghaus model).

    Args:
        time_since_last_review_hours: Hours since last review
        stability: How stable the memory is (higher = decays slower)

    Returns:
        Retention score from 0.0 (forgotten) to 1.0 (perfectly retained)
    """
    # Forgetting curve: R = exp(-t / (S * 24)) where S is stability factor
    # At t=0, R=1. At t=S*24h, R = 1/e ≈ 0.37
    if time_since_last_review_hours < 0:
        return 1.0
    decay_rate = 1.0 / (stability * 24.0) if stability > 0 else 0.1
    return math.exp(-time_since_last_review_hours * decay_rate)


# ---------------------------------------------------------------------------
# Curriculum planner
# ---------------------------------------------------------------------------

class CurriculumPlanner:
    """Plans learning paths through concept hierarchies."""

    @staticmethod
    def plan_path(domain: KnowledgeDomain, target_concept: Optional[str] = None,
                  max_depth: int = 5) -> List[Concept]:
        """Plan a learning path through the domain's concept hierarchy.

        Returns concepts in order of prerequisites → target.
        """
        # Build concept dependency graph
        concepts = {}
        for c in domain.concepts:
            concepts[c["name"]] = Concept(
                id=f"{domain.id}.{c['name']}",
                name=c["name"],
                domain_id=domain.id,
                description=c.get("description", ""),
                prerequisites=c["prerequisites"],
                difficulty=c["difficulty"],
            )

        if target_concept is None:
            # Plan path to the most difficult concept
            target_concept = max(concepts.values(), key=lambda c: c.difficulty).name

        if target_concept not in concepts:
            return []

        # Topological sort from root to target
        path = []
        visited = set()

        def _dfs(concept_name: str):
            if concept_name in visited or concept_name not in concepts:
                return
            visited.add(concept_name)
            concept = concepts[concept_name]
            for prereq in concept.prerequisites:
                _dfs(prereq)
            path.append(concept)

        _dfs(target_concept)
        return path

    @staticmethod
    def recommend_next_concept(domain: KnowledgeDomain, mastered: Set[str],
                              pending_reviews: List[Concept]) -> Optional[Concept]:
        """Recommend the next concept to study based on readiness and retention.

        Uses a combination of:
        - Prerequisite satisfaction (all prereqs must be mastered)
        - Retention score (forgotten concepts get priority for review)
        - Difficulty curve (progress through increasing difficulty)
        """
        # First: review concepts with low retention
        for concept in pending_reviews:
            if concept.retention_score < 0.6:
                return concept

        # Then: advance to next learnable concept
        learnable = []
        for c in domain.concepts:
            concept_id = f"{domain.id}.{c['name']}"
            if c["name"] in mastered:
                continue
            # Check prerequisites
            prereqs_met = all(p in mastered for p in c["prerequisites"])
            if prereqs_met:
                learnable.append((concept_id, c["difficulty"]))

        if learnable:
            # Pick the easiest unlearned concept
            learnable.sort(key=lambda x: x[1])
            concept_id, difficulty = learnable[0]
            return Concept(
                id=concept_id,
                name=concept_id.split(".")[-1],
                domain_id=domain.id,
                difficulty=difficulty,
            )

        return None


# ---------------------------------------------------------------------------
# Memory consolidation (hippocampal replay)
# ---------------------------------------------------------------------------

class MemoryConsolidator:
    """Models hippocampal-like memory consolidation with replay."""

    def __init__(self):
        self._replay_events: List[Dict[str, Any]] = []
        self._consolidation_queue: List[Concept] = []

    def enqueue_for_consolidation(self, concept: Concept) -> None:
        """Add a concept to the consolidation queue (like hippocampal sharp-wave ripples)."""
        if concept not in self._consolidation_queue:
            self._consolidation_queue.append(concept)
            log.debug("Enqueued concept '%s' for consolidation", concept.name)

    def replay(self, n_samples: int = 10) -> List[Dict[str, Any]]:
        """Simulate hippocampal replay — rehearse recent memories.

        Mirrors the biological process where the hippocampus replays
        recent experiences during rest/sleep to strengthen cortical memories.
        """
        if not self._consolidation_queue:
            return []

        # Sample from consolidation queue (prioritize low-retention items)
        replayable = sorted(self._consolidation_queue, key=lambda c: c.retention_score)[:n_samples]

        replay_events = []
        for concept in replayable:
            # Simulate rehearsal
            now = datetime.now(timezone.utc)
            event = {
                "type": "hippocampal_replay",
                "concept": concept.name,
                "domain": concept.domain_id,
                "timestamp": now.isoformat(),
                "retention_before": concept.retention_score,
            }

            # Strengthen retention through rehearsal
            concept.retention_score = min(1.0, concept.retention_score + 0.15)
            concept.times_reviewed += 1
            concept.last_seen = now.isoformat()

            event["retention_after"] = concept.retention_score
            replay_events.append(event)
            self._replay_events.append(event)

        # Remove fully consolidated concepts
        self._consolidation_queue = [
            c for c in self._consolidation_queue
            if c not in replayable
        ]

        return replay_events


# ---------------------------------------------------------------------------
# Cross-domain synthesis engine
# ---------------------------------------------------------------------------

class SynthesisEngine:
    """Discovers and constructs cross-domain insights.

    When two knowledge domains reach sufficient maturity, this engine
    attempts to synthesize novel insights from their intersection —
    mimicking the creative leaps that drive scientific breakthroughs.
    """

    SYNTHESIS_PATTERNS = [
        ("mathematics", "physics", "Mathematical physics — using {math_concept} to solve {physics_concept}"),
        ("mathematics", "computer_science", "Algorithmic mathematics — {math_concept} informs {cs_concept}"),
        ("physics", "biology", "Biophysics — {physics_concept} applied to {bio_concept}"),
        ("artificial_intelligence", "mathematics", "Mathematical AI — {math_concept} underlies {ai_concept}"),
        ("artificial_intelligence", "neuroscience", "Computational neuroscience — {ai_concept} models {neuro_concept}"),
        ("computer_science", "physics", "Computational physics — {physics_concept} via {cs_concept}"),
    ]

    def __init__(self):
        self._synth_history: List[Synthesis] = []

    def attempt_synthesis(self, domain_a: KnowledgeDomain,
                         domain_b: KnowledgeDomain) -> Optional[Synthesis]:
        """Attempt to synthesize an insight from two domains.

        Requires both domains to have maturity > 10 (growth stage minimum).
        """
        if domain_a.maturity_score < 10 or domain_b.maturity_score < 10:
            return None

        # Find matching synthesis pattern
        pattern = None
        for d1, d2, template in self.SYNTHESIS_PATTERNS:
            if {d1, d2} == {domain_a.id, domain_b.id}:
                pattern = template
                break

        if not pattern:
            # Generate generic synthesis
            common_concepts_a = set(domain_a.concepts[:5])
            common_concepts_b = set(domain_b.concepts[:5])
            overlap = common_concepts_a & common_concepts_b
            if overlap:
                pattern = f"Cross-domain insight: {domain_a.name} ∩ {domain_b.name} → {', '.join(overlap)}"
            else:
                pattern = f"Cross-domain synthesis between {domain_a.name} and {domain_b.name}"

        # Calculate novelty score
        novelty = 0.5 + (domain_a.maturity_score + domain_b.maturity_score) / 100.0
        novelty = min(0.99, novelty)

        # Confidence based on maturity product
        confidence = min(0.95, (domain_a.maturity_score * domain_b.maturity_score) / 10000.0)
        confidence = max(0.1, confidence)

        # Pick representative concepts
        concepts_a = domain_a.mastered_concepts[:3] if domain_a.mastered_concepts else domain_a.concepts[:3]
        concepts_b = domain_b.mastered_concepts[:3] if domain_b.mastered_concepts else domain_b.concepts[:3]

        insight = pattern.format(
            math_concept=concepts_a[0] if concepts_a else domain_a.name,
            physics_concept=concepts_b[0] if concepts_b else domain_b.name,
            cs_concept=concepts_a[0] if concepts_a else "",
            bio_concept=concepts_b[0] if concepts_b else "",
            neuro_concept=concepts_b[0] if concepts_b else "",
            ai_concept=concepts_a[0] if concepts_a else "",
        )

        synthesis = Synthesis(
            id=f"synth-{uuid.uuid4().hex[:8]}",
            domains_involved=[domain_a.id, domain_b.id],
            concepts_combined=concepts_a + concepts_b,
            insight=insight,
            confidence=confidence,
            novelty_score=novelty,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        domain_a.mastered_concepts.extend([c for c in concepts_b if c not in domain_a.mastered_concepts][:2])
        domain_b.mastered_concepts.extend([c for c in concepts_a if c not in domain_b.mastered_concepts][:2])

        return synthesis


# ---------------------------------------------------------------------------
# Main BioLearner class
# ---------------------------------------------------------------------------

class BioLearner:
    """
    Bio-Growth Learning Framework — curriculum learning with biological
    growth patterns.

    This is the metacognitive layer that orchestrates learning across all
    domains using bio-inspired mechanisms:
    - Sigmoid maturity scoring (biological growth curve)
    - Spaced repetition (hippocampal consolidation)
    - Curriculum progression (developmental stages)
    - Cross-domain synthesis (creative insight)
    """

    name = "learning.bio"
    version = "0.1.0"
    category = "learning"

    def __init__(self):
        self._domains: Dict[str, KnowledgeDomain] = {}
        self._concepts: Dict[str, Concept] = {}
        self._episodes: List[LearningEpisode] = []
        self._consolidator = MemoryConsolidator()
        self._synthesizer = SynthesisEngine()
        self._curriculum = CurriculumPlanner()
        self._overall_maturity = 0.0
        self._growth_stage = GrowthStage.BIRTH
        self._initialized = False

    def initialize(self) -> None:
        """Initialize with seed domains."""
        for domain_id, domain_def in DOMAIN_DEFINITIONS.items():
            domain = KnowledgeDomain(
                id=domain_id,
                name=domain_def["name"],
                description=domain_def["description"],
                concepts=domain_def["concepts"],
                learning_rate=1.0,
            )
            self._domains[domain_id] = domain

            # Create concept objects
            for c in domain_def["concepts"]:
                concept_id = f"{domain_id}.{c['name']}"
                concept = Concept(
                    id=concept_id,
                    name=c["name"],
                    domain_id=domain_id,
                    description=c.get("description", ""),
                    prerequisites=c["prerequisites"],
                    difficulty=c["difficulty"],
                    first_seen=datetime.now(timezone.utc).isoformat(),
                )
                self._concepts[concept_id] = concept

        self._initialized = True
        log.info("BioLearner initialized with %d domains, %d concepts",
                 len(self._domains), len(self._concepts))

    def get_curriculum_path(self, domain_id: str, target_concept: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get the recommended learning path for a domain."""
        domain = self._domains.get(domain_id)
        if not domain:
            return []

        path = self._curriculum.plan_path(domain, target_concept)
        return [c.to_dict() for c in path]

    async def study_concept(self, domain_id: str, concept_name: str,
                            interaction_type: str = "study",
                            duration_seconds: float = 0.0) -> Dict[str, Any]:
        """Record a study interaction without treating exposure as mastery."""
        domain = self._domains.get(domain_id)
        if not domain:
            return {"error": f"Unknown domain: {domain_id}"}

        concept_id = f"{domain_id}.{concept_name}"
        concept = self._concepts.get(concept_id)
        if not concept:
            # Find matching concept by name substring
            for cid, c in self._concepts.items():
                if concept_name.lower() in c.name.lower() or c.name.lower() in concept_name.lower():
                    concept = c
                    concept_id = cid
                    break

        if not concept:
            return {"error": f"Unknown concept: {concept_name} in domain: {domain_id}"}

        # Check prerequisites
        mastered_set = set(domain.mastered_concepts)
        prereqs_met = all(p in mastered_set for p in concept.prerequisites)

        if not prereqs_met:
            return {
                "error": f"Prerequisites not met: {concept.prerequisites}",
                "prerequisites_met": False,
                "needed": [p for p in concept.prerequisites if p not in mastered_set],
            }

        first_study = concept.first_seen is None
        if first_study:
            concept.first_seen = datetime.now(timezone.utc).isoformat()
        concept.last_seen = datetime.now(timezone.utc).isoformat()
        if concept.times_reviewed == 0:
            concept.next_review = concept.last_seen

        # Exposure is recorded as an interaction; only recall reviews affect mastery.
        domain.interactions += 1
        domain.last_interaction = concept.last_seen
        if not domain.first_explored:
            domain.first_explored = concept.first_seen

        episode = LearningEpisode(
            id=f"epi-{uuid.uuid4().hex[:8]}",
            domain_id=domain_id,
            concept_id=concept_id,
            action=interaction_type,
            outcome="studied",
            duration_seconds=duration_seconds,
            timestamp=datetime.now(timezone.utc).isoformat(),
            notes="Study interaction recorded; mastery unchanged until a recall review.",
        )
        self._append_episode(episode)

        return {
            "success": True,
            "concept_id": concept_id,
            "concept_name": concept.name,
            "mastery_level": concept.mastery_level,
            "domain_maturity": domain.maturity_score,
            "domain_growth_stage": domain.growth_stage.value,
            "overall_growth_stage": self._growth_stage.value,
            "prerequisites_met": prereqs_met,
            "mastered_this_session": False,
            "assessment_required": True,
            "study_evidence": "exposure_only",
        }

    def get_due_reviews(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return studied concepts whose evidence-based review time has arrived."""
        now = datetime.now(timezone.utc)
        due = []
        for concept in self._concepts.values():
            if not concept.next_review:
                continue
            review_at = datetime.fromisoformat(concept.next_review.replace("Z", "+00:00"))
            if review_at.tzinfo is None:
                review_at = review_at.replace(tzinfo=timezone.utc)
            if review_at <= now:
                due.append({
                    "item_key": concept.id,
                    "concept_name": concept.name,
                    "domain_id": concept.domain_id,
                    "mastery_level": concept.mastery_level,
                    "retention_score": concept.retention_score,
                    "next_review": concept.next_review,
                    "times_reviewed": concept.times_reviewed,
                })
        due.sort(key=lambda item: item["next_review"])
        return due[:max(0, limit)]

    async def perform_review(self, item_key: str, quality: int) -> Dict[str, Any]:
        """Record a learner's 0-5 recall rating and schedule the next review."""
        if isinstance(quality, bool) or not isinstance(quality, int) or not 0 <= quality <= 5:
            return {"error": "Review quality must be an integer from 0 to 5"}

        concept = self._concepts.get(item_key)
        if concept is None:
            concept = next(
                (item for item in self._concepts.values() if item.name.casefold() == item_key.casefold()),
                None,
            )
        if concept is None:
            return {"error": f"Unknown learning item: {item_key}"}
        if concept.first_seen is None:
            return {"error": f"Study the concept before reviewing it: {concept.id}"}

        previous_mastery = concept.mastery_level
        interval_days, ease_factor = SpacedRepetition.compute_next_review(concept, quality)
        concept._ease_factor = ease_factor
        concept._last_interval = interval_days
        concept.times_reviewed += 1
        reviewed_at = datetime.now(timezone.utc)
        concept.last_seen = reviewed_at.isoformat()
        concept.next_review = (reviewed_at + timedelta(days=interval_days)).isoformat()
        concept.retention_score = compute_retention_score(0, stability=max(1, interval_days))
        if quality >= 3:
            concept.mastery_level = min(1.0, concept.mastery_level + quality / 25.0)
        else:
            concept.mastery_level *= 0.8

        domain = self._domains[concept.domain_id]
        if concept.mastery_level >= 0.8 and concept.name not in domain.mastered_concepts:
            domain.mastered_concepts.append(concept.name)
        elif concept.mastery_level < 0.8 and concept.name in domain.mastered_concepts:
            domain.mastered_concepts.remove(concept.name)
        self._refresh_maturity()
        self._append_episode(LearningEpisode(
            id=f"epi-{uuid.uuid4().hex[:8]}",
            domain_id=concept.domain_id,
            concept_id=concept.id,
            action="review",
            outcome="success" if quality >= 3 else "failure",
            duration_seconds=0.0,
            timestamp=reviewed_at.isoformat(),
            notes=f"Self-assessed recall quality {quality}/5.",
        ))
        return {
            "success": True,
            "item_key": concept.id,
            "concept_name": concept.name,
            "quality": quality,
            "evidence_type": "self_assessed_recall",
            "previous_mastery": previous_mastery,
            "mastery_level": concept.mastery_level,
            "next_review": concept.next_review,
            "interval_days": interval_days,
            "ease_factor": ease_factor,
        }

    def _append_episode(self, episode: LearningEpisode) -> None:
        self._episodes.append(episode)
        del self._episodes[:-MAX_LEARNING_EPISODES]

    def _refresh_maturity(self) -> None:
        """Derive maturity from accumulated recall assessments, not study exposure."""
        for domain in self._domains.values():
            evidence = [
                concept.mastery_level
                for concept in self._concepts.values()
                if concept.domain_id == domain.id
            ]
            domain.maturity_score = 100.0 * sum(evidence) / max(1, len(evidence))
            domain.growth_stage = compute_growth_stage(domain.maturity_score)
        self._overall_maturity = (
            sum(domain.maturity_score for domain in self._domains.values())
            / max(1, len(self._domains))
        )
        self._growth_stage = compute_growth_stage(self._overall_maturity)

    def to_snapshot(self) -> Dict[str, Any]:
        """Create JSON-safe state for durable per-user storage."""
        return {
            "domains": {key: value.to_dict() for key, value in self._domains.items()},
            "concepts": {
                key: {
                    **value.to_dict(),
                    "ease_factor": getattr(value, "_ease_factor", SM2_INITIAL_EF),
                    "last_interval": getattr(value, "_last_interval", 0),
                }
                for key, value in self._concepts.items()
            },
            "episodes": [episode.to_dict() for episode in self._episodes],
            "replay_events": list(self._consolidator._replay_events),
            "consolidation_queue": [concept.id for concept in self._consolidator._consolidation_queue],
            "syntheses": [synthesis.to_dict() for synthesis in self._synthesizer._synth_history],
            "overall_maturity": self._overall_maturity,
            "growth_stage": self._growth_stage.value,
        }

    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Restore persisted learner state over the current curriculum seed."""
        for domain_id, values in snapshot.get("domains", {}).items():
            domain = self._domains.get(domain_id)
            if domain is None:
                continue
            domain.maturity_score = float(values.get("maturity_score", 0.0))
            domain.growth_stage = GrowthStage(values.get("growth_stage", GrowthStage.BIRTH.value))
            domain.mastered_concepts = list(values.get("mastered_concepts", []))
            domain.in_progress_concepts = list(values.get("in_progress_concepts", []))
            domain.first_explored = values.get("first_explored")
            domain.last_interaction = values.get("last_interaction")
            domain.interactions = int(values.get("interactions", 0))

        for concept_id, values in snapshot.get("concepts", {}).items():
            concept = self._concepts.get(concept_id)
            if concept is None:
                continue
            concept.mastery_level = float(values.get("mastery_level", 0.0))
            concept.next_review = values.get("next_review")
            concept.times_reviewed = int(values.get("times_reviewed", 0))
            concept.retention_score = float(values.get("retention_score", 0.0))
            concept.first_seen = values.get("first_seen")
            concept.last_seen = values.get("last_seen")
            concept._ease_factor = float(values.get("ease_factor", SM2_INITIAL_EF))
            concept._last_interval = int(values.get("last_interval", 0))

        self._episodes = [
            LearningEpisode(**episode)
            for episode in snapshot.get("episodes", [])
        ][-MAX_LEARNING_EPISODES:]
        self._consolidator._replay_events = list(snapshot.get("replay_events", []))
        self._consolidator._consolidation_queue = [
            self._concepts[concept_id]
            for concept_id in snapshot.get("consolidation_queue", [])
            if concept_id in self._concepts
        ]
        self._synthesizer._synth_history = [
            Synthesis(**synthesis) for synthesis in snapshot.get("syntheses", [])
        ]
        self._overall_maturity = float(snapshot.get("overall_maturity", 0.0))
        self._growth_stage = GrowthStage(snapshot.get("growth_stage", GrowthStage.BIRTH.value))

    async def consolidate(self, n_samples: int = 20) -> Dict[str, Any]:
        """Reconcile learner metrics and expose actual review work due."""
        self._refresh_maturity()
        due_reviews = self.get_due_reviews(limit=n_samples)

        return {
            "success": True,
            "consolidation_type": "evidence_reconciliation",
            "episodes_reconciled": len(self._episodes),
            "replay_events": 0,
            "syntheses_generated": 0,
            "due_reviews": due_reviews,
            "overall_maturity": self._overall_maturity,
            "growth_stage": self._growth_stage.value,
            "note": "No mastery or synthesis is inferred without recorded assessment evidence.",
        }

    def get_learning_path(self, domain_id: Optional[str] = None,
                          max_concepts: int = 10) -> Dict[str, Any]:
        """Get the recommended learning path."""
        if domain_id and domain_id not in self._domains:
            return {"error": f"Unknown learning domain: {domain_id}"}

        paths = {}
        if domain_id:
            path = self._curriculum.plan_path(self._domains[domain_id])
            paths[domain_id] = [c.to_dict() for c in path[:max_concepts]]
        else:
            for domain_id, domain in self._domains.items():
                path = self._curriculum.plan_path(domain)
                # Filter to unmastered concepts
                unmastered = [c for c in path if c.name not in domain.mastered_concepts]
                paths[domain_id] = [c.to_dict() for c in unmastered[:max_concepts]]

        return {
            "learning_path": paths,
            "overall_maturity": self._overall_maturity,
            "growth_stage": self._growth_stage.value,
        }

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the bio-learning framework."""
        domain_overviews = []
        for d in self._domains.values():
            domain_overviews.append({
                "id": d.id,
                "name": d.name,
                "maturity_score": d.maturity_score,
                "growth_stage": d.growth_stage.value,
                "concepts_total": len(d.concepts),
                "concepts_mastered": len(d.mastered_concepts),
                "interactions": d.interactions,
            })

        return {
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "initialized": self._initialized,
            "overall_maturity": self._overall_maturity,
            "growth_stage": self._growth_stage.value,
            "domains": domain_overviews,
            "total_concepts": len(self._concepts),
            "total_episodes": len(self._episodes),
            "mastery_basis": "self_assessed_recall; not independently validated",
            "due_reviews": len(self.get_due_reviews()),
            "replay_events": len(self._consolidator._replay_events),
            "syntheses": len(self._synthesizer._synth_history),
        }
