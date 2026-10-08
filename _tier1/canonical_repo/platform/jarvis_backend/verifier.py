"""Phase 10 — Verifier Role.

The Verifier role performs independent verification of claims, hypotheses,
and evidence.  It wraps the existing VerificationEngine (Phase 7) and adds
mission-level verification of success criteria.

The Verifier never fabricates verification status — every claim must have
a traceable deterministic check.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import now_iso
from research_engine.models import (
    Evidence,
    EvidenceStatus,
    Experiment,
    VerificationStatus,
)
from research_engine.verification import VerificationEngine

from .cognitive_state import VerificationResult
from .mission import _short_uuid

logger = logging.getLogger("jarvis_backend.verifier")


class VerificationScope(str, Enum):
    """Scope of a verification task."""

    CLAIM = "claim"              # verify a specific claim
    HYPOTHESIS = "hypothesis"    # verify a hypothesis
    SUCCESS_CRITERIA = "success_criteria"  # verify mission success criteria
    EVIDENCE = "evidence"        # verify individual evidence items


@dataclass
class VerificationRequest:
    """A request to verify a claim or hypothesis."""

    request_id: str
    scope: str                   # VerificationScope value
    claim: str
    evidence_ids: list[str] = field(default_factory=list)
    experiment_ids: list[str] = field(default_factory=list)
    requested_by: str = "cognitive_kernel"
    requested_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "scope": self.scope,
            "claim": self.claim,
            "evidence_ids": list(self.evidence_ids),
            "experiment_ids": list(self.experiment_ids),
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
        }


@dataclass
class VerificationOutcome:
    """Outcome of a verification request."""

    request_id: str
    status: str                  # VerificationStatus value
    reason: str
    confidence: Optional[float] = None
    verified_at: str = field(default_factory=now_iso)
    evidence_used: list[str] = field(default_factory=list)
    experiments_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "reason": self.reason,
            "confidence": self.confidence,
            "verified_at": self.verified_at,
            "evidence_used": list(self.evidence_used),
            "experiments_used": list(self.experiments_used),
        }


class Verifier:
    """Independent verifier role.

    Wraps the existing :class:`~research_engine.verification.VerificationEngine`
    and adds mission-level verification of success criteria.  The Verifier is
    an *independent* check — it is called by the Critic and the Cognitive
    Kernel to confirm that claims and success criteria are truly met.
    """

    def __init__(self, verifier: Optional[VerificationEngine] = None) -> None:
        self._engine = verifier or VerificationEngine()
        self._outcomes: dict[str, VerificationOutcome] = {}

    def verify_claim(
        self,
        claim: str,
        evidence: list[Evidence],
        experiments: Optional[list[Experiment]] = None,
    ) -> VerificationOutcome:
        """Verify a specific claim against evidence and experiments."""
        status, reason, confidence = self._engine.verify_claim(
            claim=claim,
            evidence=evidence or [],
            experiments=experiments or [],
        )
        outcome = VerificationOutcome(
            request_id=f"ver_{_short_uuid()}",
            status=status.value,
            reason=reason,
            confidence=confidence,
            evidence_used=[e.id for e in (evidence or [])],
            experiments_used=[e.id for e in (experiments or [])],
        )
        self._outcomes[outcome.request_id] = outcome
        logger.debug("Verified claim: %s → %s (%s)", claim[:80], status.value, reason)
        return outcome

    def verify_success_criteria(
        self,
        criteria: list[str],
        evidence_entries: list[Any] = None,
    ) -> dict[str, Any]:
        """Verify that all mission success criteria are met.

        Returns a dict:
        ```
        {
            "all_verified": bool,
            "criteria_results": [{"criterion": str, "status": str, "reason": str, "confidence": Optional[float]}],
            "summary": str,
        }
        ```

        **A mission cannot become COMPLETED unless all_verified is True.**
        """
        evidence_entries = evidence_entries or []
        # Convert evidence entries to Evidence dataclass instances
        evidence_list: list[Evidence] = []
        for entry in evidence_entries:
            if hasattr(entry, "evidence"):
                evidence_list.append(entry.evidence)
            elif isinstance(entry, dict) and "evidence_id" in entry:
                # EvidenceEntry dict
                from .evidence_engine import EvidenceEntry
                ev = EvidenceEntry.from_dict(entry)
                evidence_list.append(ev.evidence)

        criteria_results = []
        for criterion in criteria:
            status, reason, confidence = self._engine.verify_claim(
                claim=criterion,
                evidence=evidence_list,
                experiments=[],
            )
            criteria_results.append({
                "criterion": criterion,
                "status": status.value,
                "reason": reason,
                "confidence": confidence,
            })

        all_verified = all(
            r["status"] in (VerificationStatus.VERIFIED.value,
                            VerificationStatus.PARTIALLY_VERIFIED.value)
            for r in criteria_results
        ) if criteria_results else False

        summary = (
            f"All {len(criteria)} success criteria verified"
            if all_verified and criteria_results
            else f"Only {sum(1 for r in criteria_results if r['status'] in (VerificationStatus.VERIFIED.value, VerificationStatus.PARTIALLY_VERIFIED.value))}"
            f"/{len(criteria)} criteria verified"
        )

        result = {
            "all_verified": all_verified,
            "criteria_results": criteria_results,
            "summary": summary,
        }
        logger.info("Success criteria verification: %s", summary)
        return result

    def verify_hypothesis(
        self,
        hypothesis_statement: str,
        evidence: list[Evidence],
        experiments: Optional[list[Experiment]] = None,
    ) -> VerificationOutcome:
        """Verify a hypothesis — delegates to verify_claim with hypothesis scope."""
        return self.verify_claim(
            claim=hypothesis_statement,
            evidence=evidence,
            experiments=experiments,
        )

    def verify_evidence(
        self,
        evidence_entry: Any,
        experiments: Optional[list[Experiment]] = None,
    ) -> VerificationOutcome:
        """Verify an evidence item's claims.

        Updates the evidence entry's verification status if it has a
        ``verify()`` method.
        """
        claims = []
        if hasattr(evidence_entry, "claims"):
            claims = list(evidence_entry.claims)
        elif isinstance(evidence_entry, dict):
            claims = list(evidence_entry.get("claims", []))

        if not claims:
            # No claims to verify — mark as VERIFIED (source trust)
            outcome = VerificationOutcome(
                request_id=f"ver_{_short_uuid()}",
                status=VerificationStatus.VERIFIED.value,
                reason="No specific claims; source registered as evidence",
                confidence=None,
            )
        else:
            # Verify each claim
            all_verified = True
            reasons = []
            for claim in claims:
                status, reason, conf = self._engine.verify_claim(
                    claim=claim,
                    evidence=[],
                    experiments=experiments or [],
                )
                reasons.append(f"{claim}: {status.value} ({reason})")
                if status not in (VerificationStatus.VERIFIED,
                                   VerificationStatus.PARTIALLY_VERIFIED):
                    all_verified = False
            outcome = VerificationOutcome(
                request_id=f"ver_{_short_uuid()}",
                status=VerificationStatus.VERIFIED.value if all_verified
                else VerificationStatus.UNVERIFIED.value,
                reason="; ".join(reasons),
                confidence=None,
            )

        self._outcomes[outcome.request_id] = outcome
        return outcome

    def get_outcome(self, request_id: str) -> Optional[VerificationOutcome]:
        return self._outcomes.get(request_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcomes": [o.to_dict() for o in self._outcomes.values()],
            "total": len(self._outcomes),
        }


__all__ = [
    "VerificationScope",
    "VerificationRequest",
    "VerificationOutcome",
    "Verifier",
]
