"""Phase 10 — Canonical Cognitive State.

The CognitiveState is the single, explicit representation of what the
Cognitive Kernel knows, believes, and plans at any given moment.  It is
checkpointed after every cycle so a mission can resume after a crash.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import now_iso

from .mission import _short_uuid


class CognitivePhase(str, Enum):
    """Phases of the cognitive loop (Section 4)."""

    PERCEIVE = "perceive"
    UNDERSTAND = "understand"
    HYPOTHESIZE = "hypothesize"
    PLAN = "plan"
    AUTHORIZE = "authorize"
    EXECUTE = "execute"
    OBSERVE = "observe"
    CRITIQUE = "critique"
    VERIFY = "verify"
    LEARN = "learn"
    REPLAN = "replan"
    COMPLETE = "complete"
    PAUSED = "paused"
    FAILED = "failed"


@dataclass
class Observation:
    """A single observation captured during the OBSERVE phase."""

    obs_id: str
    at: str
    source: str          # capability that produced the observation
    content: str         # raw observation text (secrets already scrubbed)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "obs_id": self.obs_id,
            "at": self.at,
            "source": self.source,
            "content": self.content,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        return cls(
            obs_id=data["obs_id"],
            at=data["at"],
            source=data["source"],
            content=data["content"],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class KnownFact:
    """A fact the kernel has established (with provenance)."""

    fact_id: str
    statement: str
    source: str           # where this fact came from
    confidence: Optional[float] = None  # None unless deterministically computed
    verified: bool = False
    established_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "statement": self.statement,
            "source": self.source,
            "confidence": self.confidence,
            "verified": self.verified,
            "established_at": self.established_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnownFact":
        return cls(
            fact_id=data["fact_id"],
            statement=data["statement"],
            source=data["source"],
            confidence=data.get("confidence"),
            verified=data.get("verified", False),
            established_at=data.get("established_at", now_iso()),
        )


@dataclass
class CriticFinding:
    """A finding from the Critic role — analysis only, no execution authority."""

    finding_id: str
    at: str
    severity: str          # "info" | "warning" | "error"
    category: str          # e.g. "evidence_quality", "fabricaton", "budget", "logic"
    description: str
    recommendation: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "at": self.at,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CriticFinding":
        return cls(
            finding_id=data["finding_id"],
            at=data["at"],
            severity=data["severity"],
            category=data["category"],
            description=data["description"],
            recommendation=data.get("recommendation"),
        )


@dataclass
class VerificationResult:
    """Result of verifying a claim or hypothesis."""

    claim: str
    status: str           # VerificationStatus value
    reason: str
    confidence: Optional[float] = None
    evidence_refs: list[str] = field(default_factory=list)
    at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "status": self.status,
            "reason": self.reason,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationResult":
        return cls(
            claim=data["claim"],
            status=data["status"],
            reason=data["reason"],
            confidence=data.get("confidence"),
            evidence_refs=list(data.get("evidence_refs", [])),
            at=data.get("at", now_iso()),
        )


@dataclass
class BudgetState:
    """Snapshot of budget consumption within the cognitive loop."""

    steps_consumed: int = 0
    steps_remaining: int = 0
    tokens_consumed: int = 0
    cost_spent_usd: float = 0.0
    seconds_elapsed: float = 0.0
    iterations_consumed: int = 0
    exhausted: bool = False
    exhaustion_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps_consumed": self.steps_consumed,
            "steps_remaining": self.steps_remaining,
            "tokens_consumed": self.tokens_consumed,
            "cost_spent_usd": self.cost_spent_usd,
            "seconds_elapsed": self.seconds_elapsed,
            "iterations_consumed": self.iterations_consumed,
            "exhausted": self.exhausted,
            "exhaustion_reason": self.exhaustion_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetState":
        return cls(
            steps_consumed=data.get("steps_consumed", 0),
            steps_remaining=data.get("steps_remaining", 0),
            tokens_consumed=data.get("tokens_consumed", 0),
            cost_spent_usd=data.get("cost_spent_usd", 0.0),
            seconds_elapsed=data.get("seconds_elapsed", 0.0),
            iterations_consumed=data.get("iterations_consumed", 0),
            exhausted=data.get("exhausted", False),
            exhaustion_reason=data.get("exhaustion_reason"),
        )


@dataclass
class CognitiveState:
    """Canonical representation of everything the Cognitive Kernel knows.

    This state is the single source of truth during a cognitive cycle.  It is
    checkpointed after every cycle so the mission can resume after a crash.

    The Brain never sees raw credentials — all evidence and observations are
    scrubbed via ``scrub_secrets`` before entering this state.
    """

    mission_id: str
    cycle: int = 0
    phase: str = CognitivePhase.UNDERSTAND.value
    objective: str = ""
    known_facts: list[dict[str, Any]] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    active_hypothesis: Optional[str] = None
    plan: Optional[dict[str, Any]] = None  # serialized ExecutionGraph
    observations: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    critic_findings: list[dict[str, Any]] = field(default_factory=list)
    verification_results: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    confidence_state: dict[str, Any] = field(default_factory=dict)
    next_action: Optional[str] = None
    budget_state: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=now_iso)
    last_updated: str = field(default_factory=now_iso)

    # -- Serialization --
    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "cycle": self.cycle,
            "phase": self.phase,
            "objective": self.objective,
            "known_facts": list(self.known_facts),
            "unknowns": list(self.unknowns),
            "hypotheses": list(self.hypotheses),
            "active_hypothesis": self.active_hypothesis,
            "plan": dict(self.plan) if self.plan else None,
            "observations": list(self.observations),
            "evidence": list(self.evidence),
            "critic_findings": list(self.critic_findings),
            "verification_results": list(self.verification_results),
            "decisions": list(self.decisions),
            "open_questions": list(self.open_questions),
            "confidence_state": dict(self.confidence_state),
            "next_action": self.next_action,
            "budget_state": dict(self.budget_state),
            "started_at": self.started_at,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CognitiveState":
        return cls(
            mission_id=data["mission_id"],
            cycle=data.get("cycle", 0),
            phase=data.get("phase", CognitivePhase.UNDERSTAND.value),
            objective=data.get("objective", ""),
            known_facts=list(data.get("known_facts", [])),
            unknowns=list(data.get("unknowns", [])),
            hypotheses=list(data.get("hypotheses", [])),
            active_hypothesis=data.get("active_hypothesis"),
            plan=dict(data["plan"]) if data.get("plan") else None,
            observations=list(data.get("observations", [])),
            evidence=list(data.get("evidence", [])),
            critic_findings=list(data.get("critic_findings", [])),
            verification_results=list(data.get("verification_results", [])),
            decisions=list(data.get("decisions", [])),
            open_questions=list(data.get("open_questions", [])),
            confidence_state=dict(data.get("confidence_state", {})),
            next_action=data.get("next_action"),
            budget_state=dict(data.get("budget_state", {})),
            started_at=data.get("started_at", now_iso()),
            last_updated=data.get("last_updated", now_iso()),
        )

    # -- Helpers --
    def add_fact(
        self,
        statement: str,
        source: str,
        confidence: Optional[float] = None,
        verified: bool = False,
    ) -> KnownFact:
        """Record a known fact and return it."""
        fact = KnownFact(
            fact_id=f"fact_{_short_uuid()}",
            statement=statement,
            source=source,
            confidence=confidence,
            verified=verified,
        )
        self.known_facts.append(fact.to_dict())
        self.last_updated = now_iso()
        return fact

    def add_observation(
        self,
        source: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Observation:
        """Record an observation (already scrubbed of secrets)."""
        obs = Observation(
            obs_id=f"obs_{_short_uuid()}",
            at=now_iso(),
            source=source,
            content=content,
            metadata=metadata or {},
        )
        self.observations.append(obs.to_dict())
        self.last_updated = now_iso()
        return obs

    def add_question(self, question: str) -> None:
        """Record an open question for future hypothesis generation."""
        if question not in self.open_questions:
            self.open_questions.append(question)
            self.last_updated = now_iso()

    def advance_phase(self) -> None:
        """Advance to the next phase in the cognitive loop."""
        order = list(CognitivePhase)
        try:
            current = CognitivePhase(self.phase)
        except ValueError:
            current = CognitivePhase.UNDERSTAND
        idx = order.index(current)
        if idx + 1 < len(order):
            self.phase = order[idx + 1].value
        self.last_updated = now_iso()

    @property
    def step_budget_exhausted(self) -> bool:
        return self.budget_state.get("exhausted", False)

    def is_complete(self) -> bool:
        """True when the cognitive loop has reached a terminal phase."""
        return self.phase in (
            CognitivePhase.COMPLETE.value,
            CognitivePhase.FAILED.value,
            CognitivePhase.PAUSED.value,
        )


__all__ = [
    "CognitivePhase",
    "Observation",
    "KnownFact",
    "CriticFinding",
    "VerificationResult",
    "BudgetState",
    "CognitiveState",
]
