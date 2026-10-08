"""Phase 10 — Hypothesis Engine.

Manages the lifecycle of hypotheses within a mission.  Hypotheses are testable
claims that drive the cognitive loop.  Their status transitions are deterministic
— a hypothesis is never marked CONFIRMED or REJECTED without supporting evidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import now_iso
from research_engine.models import VerificationStatus

from .cognitive_state import CognitivePhase
from .mission import _short_uuid

logger = logging.getLogger("jarvis_backend.hypothesis_engine")


class HypothesisStatus(str, Enum):
    """Status of a hypothesis in the evaluation pipeline.

    A hypothesis is never CONFIRMED or REJECTED without evidence.
    """

    PROPOSED = "PROPOSED"
    TESTING = "TESTING"
    SUPPORTED = "SUPPORTED"
    WEAKENED = "WEAKENED"
    REJECTED = "REJECTED"
    CONFIRMED = "CONFIRMED"
    INCONCLUSIVE = "INCONCLUSIVE"


# Statuses that indicate the hypothesis has been resolved.
RESOLVED_STATUSES: frozenset[HypothesisStatus] = frozenset({
    HypothesisStatus.CONFIRMED,
    HypothesisStatus.REJECTED,
    HypothesisStatus.INCONCLUSIVE,
})


class HypothesisError(ValueError):
    """Raised on illegal hypothesis status transitions."""


# Transition table: current → allowed targets
_HYPOTHESIS_TRANSITIONS: dict[HypothesisStatus, frozenset[HypothesisStatus]] = {
    HypothesisStatus.PROPOSED: frozenset({
        HypothesisStatus.TESTING,
        HypothesisStatus.REJECTED,  # trivial contradiction at proposal time
        HypothesisStatus.INCONCLUSIVE,
    }),
    HypothesisStatus.TESTING: frozenset({
        HypothesisStatus.SUPPORTED,
        HypothesisStatus.WEAKENED,
        HypothesisStatus.REJECTED,
        HypothesisStatus.CONFIRMED,
        HypothesisStatus.INCONCLUSIVE,
    }),
    HypothesisStatus.SUPPORTED: frozenset({
        HypothesisStatus.CONFIRMED,
        HypothesisStatus.WEAKENED,
        HypothesisStatus.REJECTED,
        HypothesisStatus.INCONCLUSIVE,
    }),
    HypothesisStatus.WEAKENED: frozenset({
        HypothesisStatus.SUPPORTED,
        HypothesisStatus.REJECTED,
        HypothesisStatus.INCONCLUSIVE,
    }),
    # Resolved states are terminal.
    HypothesisStatus.CONFIRMED: frozenset(),
    HypothesisStatus.REJECTED: frozenset(),
    HypothesisStatus.INCONCLUSIVE: frozenset(),
}


@dataclass
class Hypothesis:
    """A testable claim being investigated during a mission."""

    id: str
    statement: str
    context: str           # what scenario/domain this hypothesis pertains to
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    rationale: str = ""
    proposed_by: str = "cognitive_kernel"
    proposed_at: str = field(default_factory=now_iso)
    tested_at: Optional[str] = None
    confidence: Optional[float] = None  # None unless deterministically computed
    evidence_ids: list[str] = field(default_factory=list)
    refuted_by: list[str] = field(default_factory=list)
    conclusion: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "context": self.context,
            "status": self.status.value,
            "rationale": self.rationale,
            "proposed_by": self.proposed_by,
            "proposed_at": self.proposed_at,
            "tested_at": self.tested_at,
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
            "refuted_by": list(self.refuted_by),
            "conclusion": self.conclusion,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hypothesis":
        try:
            status = HypothesisStatus(data.get("status", "PROPOSED"))
        except ValueError:
            status = HypothesisStatus.PROPOSED
        return cls(
            id=data["id"],
            statement=data["statement"],
            context=data.get("context", ""),
            status=status,
            rationale=data.get("rationale", ""),
            proposed_by=data.get("proposed_by", "cognitive_kernel"),
            proposed_at=data.get("proposed_at", now_iso()),
            tested_at=data.get("tested_at"),
            confidence=data.get("confidence"),
            evidence_ids=list(data.get("evidence_ids", [])),
            refuted_by=list(data.get("refuted_by", [])),
            conclusion=data.get("conclusion"),
        )


class HypothesisEngine:
    """Manages hypothesis lifecycle within a mission.

    The engine is deterministic — status changes require supporting evidence.
    It delegates verification to :class:`~research_engine.verification.VerificationEngine`.
    """

    def __init__(self, verifier=None) -> None:
        from research_engine.verification import VerificationEngine

        self._verifier = verifier or VerificationEngine()
        self._hypotheses: dict[str, Hypothesis] = {}

    # -- Creation --
    def propose(
        self,
        statement: str,
        context: str = "",
        rationale: str = "",
        proposed_by: str = "cognitive_kernel",
    ) -> Hypothesis:
        """Propose a new hypothesis (status = PROPOSED).

        Returns the created Hypothesis.
        """
        h = Hypothesis(
            id=f"hyp_{_short_uuid()}",
            statement=statement,
            context=context,
            status=HypothesisStatus.PROPOSED,
            rationale=rationale,
            proposed_by=proposed_by,
        )
        self._hypotheses[h.id] = h
        logger.debug("Proposed hypothesis %s: %s", h.id, statement[:80])
        return h

    # -- Selection --
    def select_next(self) -> Optional[Hypothesis]:
        """Select the highest-priority hypothesis to test next.

        Priority order: TESTING (incomplete) > PROPOSED > WEAKENED > SUPPORTED.
        Resolved hypotheses (CONFIRMED/REJECTED/INCONCLUSIVE) are skipped.
        """
        if not self._hypotheses:
            return None

        priority_order = [
            HypothesisStatus.TESTING,
            HypothesisStatus.PROPOSED,
            HypothesisStatus.WEAKENED,
            HypothesisStatus.SUPPORTED,
        ]

        for status in priority_order:
            candidates = [
                h for h in self._hypotheses.values()
                if h.status == status and h.id not in RESOLVED_STATUSES
            ]
            if candidates:
                # Pick the one with the fewest evidence_ids (try simplest first
                # to minimize work) — or oldest if tied.
                candidates.sort(key=lambda h: (len(h.evidence_ids), h.proposed_at))
                return candidates[0]
        return None

    # -- Evaluation --
    def evaluate(
        self,
        hypothesis_id: str,
        evidence: list[Any],
        experiments: Optional[list[Any]] = None,
    ) -> HypothesisStatus:
        """Evaluate a hypothesis against evidence.

        Uses the VerificationEngine to classify the hypothesis's claim.
        Returns the new status.  Never upgrades without deterministic support
        — CONFIRMED requires VerificationStatus.VERIFIED, REJECTED requires
        CONTRADICTED or a refuting experiment.
        """
        h = self._hypotheses.get(hypothesis_id)
        if h is None:
            raise KeyError(f"Unknown hypothesis: {hypothesis_id}")

        experiments = experiments or []

        # Use the VerificationEngine for a deterministic classification.
        ver_status, reason, confidence = self._verifier.verify_claim(
            claim=h.statement,
            evidence=evidence or [],
            experiments=experiments,
        )

        # Record evidence references for provenance.
        for e in (evidence or []):
            eid = getattr(e, "id", None) or (e.get("id") if isinstance(e, dict) else None)
            if eid and eid not in h.evidence_ids:
                h.evidence_ids.append(eid)

        if experiments:
            for exp in experiments:
                if hasattr(exp, "verification") and exp.verification == VerificationStatus.CONTRADICTED:
                    # Experiment refuted the hypothesis.
                    h.refuted_by.append(getattr(exp, "id", str(exp)))

        # Map verification status to hypothesis status (deterministic, no fabrication)
        new_status: HypothesisStatus
        if ver_status == VerificationStatus.VERIFIED:
            new_status = HypothesisStatus.CONFIRMED
        elif ver_status == VerificationStatus.CONTRADICTED:
            new_status = HypothesisStatus.REJECTED
        elif ver_status == VerificationStatus.PARTIALLY_VERIFIED:
            new_status = HypothesisStatus.SUPPORTED
        elif ver_status == VerificationStatus.FAILED:
            new_status = HypothesisStatus.WEAKENED
        elif ver_status == VerificationStatus.UNAVAILABLE:
            new_status = HypothesisStatus.INCONCLUSIVE
        else:  # UNVERIFIED
            new_status = HypothesisStatus.INCONCLUSIVE if not evidence else HypothesisStatus.WEAKENED

        # Validate transition
        if new_status != h.status:
            self._validate_transition(h.status, new_status)

        h.status = new_status
        h.tested_at = now_iso()
        h.confidence = confidence
        if new_status in RESOLVED_STATUSES:
            h.conclusion = reason

        logger.debug("Hypothesis %s → %s (%s)", h.id, new_status.value, reason)
        return new_status

    # -- Status updates --
    def mark_testing(self, hypothesis_id: str) -> None:
        """Mark a hypothesis as actively being tested."""
        h = self._hypotheses.get(hypothesis_id)
        if h is None:
            raise KeyError(f"Unknown hypothesis: {hypothesis_id}")
        self._validate_transition(h.status, HypothesisStatus.TESTING, allow_direct=True)
        h.status = HypothesisStatus.TESTING
        h.tested_at = now_iso()

    def close_as_inconclusive(self, hypothesis_id: str, reason: str = "") -> None:
        """Mark a hypothesis as inconclusive (insufficient evidence to decide)."""
        h = self._hypotheses.get(hypothesis_id)
        if h is None:
            raise KeyError(f"Unknown hypothesis: {hypothesis_id}")
        if h.status in RESOLVED_STATUSES:
            return
        self._validate_transition(h.status, HypothesisStatus.INCONCLUSIVE, allow_any=True)
        h.status = HypothesisStatus.INCONCLUSIVE
        h.tested_at = now_iso()
        h.conclusion = reason or "Insufficient evidence to confirm or reject"

    # -- Experiment outcome recording (Phase 11) --
    def record_experiment_outcome(
        self,
        hypothesis_id: str,
        experiment: Any,
    ) -> Optional[HypothesisStatus]:
        """Record an experiment's outcome against a hypothesis.

        Examines the experiment's comparison results and metrics to determine
        whether the hypothesis is SUPPORTED, WEAKENED, REJECTED, or remains
        INCONCLUSIVE.  Never fabricates — only reports what the experiment data
        shows.

        Args:
            hypothesis_id: The hypothesis being tested.
            experiment: An Experiment object or dict with comparison data.
        """
        h = self._hypotheses.get(hypothesis_id)
        if h is None:
            raise KeyError(f"Unknown hypothesis: {hypothesis_id}")

        exp = experiment.to_dict() if hasattr(experiment, "to_dict") else experiment
        comparisons = exp.get("comparisons", [])
        baseline = exp.get("baseline")
        candidates = exp.get("candidates", [])
        blocked_reason = exp.get("blocked_reason")

        # If experiment was blocked, it didn't test the hypothesis
        if blocked_reason:
            h.conclusion = f"Experiment BLOCKED: {blocked_reason}"
            if h.status not in RESOLVED_STATUSES:
                self._validate_transition(h.status, HypothesisStatus.INCONCLUSIVE)
                h.status = HypothesisStatus.INCONCLUSIVE
                h.tested_at = now_iso()
            return h.status

        # If no baseline, we can't determine improvement
        if not baseline and not comparisons:
            h.conclusion = "Experiment completed but no baseline or comparisons for evaluation"
            if h.status not in RESOLVED_STATUSES:
                self._validate_transition(h.status, HypothesisStatus.INCONCLUSIVE)
                h.status = HypothesisStatus.INCONCLUSIVE
                h.tested_at = now_iso()
            return h.status

        # Analyze comparisons to determine hypothesis outcome
        # Collect metric names and relative differences
        metric_results: list[tuple[str, float]] = []
        for comp in comparisons:
            if isinstance(comp, dict):
                name = comp.get("metric_name", "unknown")
                rel = comp.get("relative_difference", 0.0)
                metric_results.append((name, float(rel) if rel is not None else 0.0))

        if not metric_results:
            h.conclusion = "No measurable comparisons available"
            if h.status not in RESOLVED_STATUSES:
                self._validate_transition(h.status, HypothesisStatus.INCONCLUSIVE)
                h.status = HypothesisStatus.INCONCLUSIVE
                h.tested_at = now_iso()
            return h.status

        # Determine overall direction: are most metrics improving?
        positive = sum(1 for _, d in metric_results if d > 0)
        negative = sum(1 for _, d in metric_results if d < 0)
        total = len(metric_results)

        summary = f"Examined {total} metric(s): {positive} improved, {negative} regressed"

        # Check if experiment was designed to improve (positive direction)
        hypothesis_text = h.statement.lower()
        is_improvement = "improve" in hypothesis_text or "better" in hypothesis_text

        if is_improvement:
            # For improvement hypotheses:
            # - All positive → SUPPORTED
            # - Some positive, some negative → WEAKENED
            # - All negative → REJECTED
            if negative == 0 and positive > 0:
                new_status = HypothesisStatus.SUPPORTED
            elif positive > 0 and negative > 0:
                new_status = HypothesisStatus.WEAKENED
            elif negative > 0 and positive == 0:
                new_status = HypothesisStatus.REJECTED
            else:
                new_status = HypothesisStatus.INCONCLUSIVE
        else:
            # For non-improvement hypotheses, rely on verification engine
            return self.evaluate(hypothesis_id, evidence=[], experiments=[experiment])

        if new_status != h.status:
            self._validate_transition(h.status, new_status)
        h.status = new_status
        h.tested_at = now_iso()
        h.conclusion = summary
        h.confidence = positive / total if total > 0 else 0.0

        logger.debug("Hypothesis %s → %s via experiment (comparisons=%d)",
                     h.id, new_status.value, len(metric_results))
        return h.status

    # -- Queries --
    def get(self, hypothesis_id: str) -> Optional[Hypothesis]:
        return self._hypotheses.get(hypothesis_id)

    def list_all(self) -> list[Hypothesis]:
        return list(self._hypotheses.values())

    def active(self) -> list[Hypothesis]:
        """Return all non-resolved hypotheses."""
        return [h for h in self._hypotheses.values()
                if h.status not in RESOLVED_STATUSES]

    def resolved(self) -> list[Hypothesis]:
        """Return all resolved hypotheses."""
        return [h for h in self._hypotheses.values()
                if h.status in RESOLVED_STATUSES]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypotheses": [h.to_dict() for h in self._hypotheses.values()],
            "active_count": len(self.active()),
            "resolved_count": len(self.resolved()),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], verifier=None) -> "HypothesisEngine":
        engine = cls(verifier=verifier)
        for hd in data.get("hypotheses", []):
            h = Hypothesis.from_dict(hd)
            engine._hypotheses[h.id] = h
        return engine

    # -- Internal --
    @staticmethod
    def _validate_transition(
        current: HypothesisStatus,
        target: HypothesisStatus,
        allow_direct: bool = False,
        allow_any: bool = False,
    ) -> None:
        """Validate a hypothesis status transition."""
        if current == target:
            return
        if current in RESOLVED_STATUSES:
            raise HypothesisError(
                f"Cannot transition hypothesis from resolved state {current.value}"
            )
        if allow_any:
            return
        if allow_direct and target == HypothesisStatus.TESTING and current == HypothesisStatus.PROPOSED:
            return
        allowed = _HYPOTHESIS_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise HypothesisError(
                f"Illegal hypothesis transition: {current.value} → "
                f"{target.value}. Allowed: {sorted(s.value for s in allowed) or '[]'}"
            )


__all__ = [
    "HypothesisStatus",
    "RESOLVED_STATUSES",
    "HypothesisError",
    "Hypothesis",
    "HypothesisEngine",
]

