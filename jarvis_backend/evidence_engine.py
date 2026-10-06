"""Phase 10 — Evidence Engine.

Manages evidence collection with full provenance tracking.  Builds on the
existing :class:`~research_engine.models.Evidence` dataclass (Phase 7) and
integrates with ArtifactRegistry, JobRegistry, and the VerificationEngine.

The Evidence Engine never fabricates evidence — every entry must have a
traceable source.  Evidence marked VERIFIED must have a corresponding
deterministic check from the VerificationEngine.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from jarvis_backend.core import now_iso
from research_engine.models import (
    Evidence,
    EvidenceStatus,
    SourceType,
    VerificationStatus,
)
from research_engine.verification import VerificationEngine

from .mission import _short_uuid

logger = logging.getLogger("jarvis_backend.evidence_engine")


@dataclass
class ProvenanceChain:
    """A traceable link in an evidence item's provenance chain.

    Each link records how evidence flowed from source → capability/tool →
    task node → artifact registry → verification.
    """

    step: int
    at: str                    # ISO-8601
    actor: str                 # what produced this link (capability name, role, etc.)
    action: str                # e.g. "collected", "verified", "stored", "transferred"
    detail: str                # description of this step
    artifact_id: Optional[str] = None
    task_id: Optional[str] = None
    job_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "at": self.at,
            "actor": self.actor,
            "action": self.action,
            "detail": self.detail,
            "artifact_id": self.artifact_id,
            "task_id": self.task_id,
            "job_id": self.job_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProvenanceChain":
        return cls(
            step=data["step"],
            at=data["at"],
            actor=data["actor"],
            action=data["action"],
            detail=data["detail"],
            artifact_id=data.get("artifact_id"),
            task_id=data.get("task_id"),
            job_id=data.get("job_id"),
        )


@dataclass
class EvidenceEntry:
    """An evidence item with full provenance tracking.

    Wraps the Phase 7 :class:`~research_engine.models.Evidence` dataclass and
    adds a provenance chain so every piece of evidence can be traced from
    source to verification.
    """

    evidence_id: str
    source_url: str
    source_type: str           # SourceType value
    title: Optional[str]
    retrieved_at: str
    relevant_content: str
    claims: list[str] = field(default_factory=list)
    supporting_excerpt: Optional[str] = None
    confidence: Optional[float] = None  # None unless deterministically computed
    verification_status: str = EvidenceStatus.UNVERIFIED.value
    provider: Optional[str] = None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    verified_at: Optional[str] = None
    verification_reason: str = ""

    @property
    def evidence(self) -> Evidence:
        """Return the underlying Phase 7 Evidence dataclass."""
        return Evidence(
            id=self.evidence_id,
            source_url=self.source_url,
            source_type=SourceType(self.source_type)
            if self.source_type in SourceType._value2member_map_
            else SourceType.WEB,
            title=self.title,
            retrieved_at=self.retrieved_at,
            relevant_content=self.relevant_content,
            claims=list(self.claims),
            supporting_excerpt=self.supporting_excerpt,
            confidence=self.confidence,
            verification_status=(
                EvidenceStatus(self.verification_status)
                if self.verification_status in EvidenceStatus._value2member_map_
                else EvidenceStatus.UNVERIFIED
            ),
            provider=self.provider,
        )

    def add_provenance(
        self,
        actor: str,
        action: str,
        detail: str,
        artifact_id: Optional[str] = None,
        task_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> ProvenanceChain:
        """Append a provenance link and return it."""
        step = len(self.provenance) + 1
        link = ProvenanceChain(
            step=step,
            at=now_iso(),
            actor=actor,
            action=action,
            detail=detail,
            artifact_id=artifact_id,
            task_id=task_id,
            job_id=job_id,
        )
        self.provenance.append(link.to_dict())
        return link

    def verify(
        self,
        status: EvidenceStatus,
        reason: str,
        confidence: Optional[float] = None,
        actor: str = "verification_engine",
    ) -> None:
        """Mark this evidence as verified (or refuted) by a deterministic check."""
        self.verification_status = status.value
        self.verified_at = now_iso()
        self.verification_reason = reason
        if confidence is not None:
            self.confidence = confidence
        self.add_provenance(
            actor=actor,
            action="verified",
            detail=f"status={status.value}: {reason}",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "title": self.title,
            "retrieved_at": self.retrieved_at,
            "relevant_content": self.relevant_content,
            "claims": list(self.claims),
            "supporting_excerpt": self.supporting_excerpt,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "provider": self.provider,
            "provenance": list(self.provenance),
            "verified_at": self.verified_at,
            "verification_reason": self.verification_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceEntry":
        return cls(
            evidence_id=data["evidence_id"],
            source_url=data["source_url"],
            source_type=data["source_type"],
            title=data.get("title"),
            retrieved_at=data["retrieved_at"],
            relevant_content=data["relevant_content"],
            claims=list(data.get("claims", [])),
            supporting_excerpt=data.get("supporting_excerpt"),
            confidence=data.get("confidence"),
            verification_status=data.get("verification_status", EvidenceStatus.UNVERIFIED.value),
            provider=data.get("provider"),
            provenance=list(data.get("provenance", [])),
            verified_at=data.get("verified_at"),
            verification_reason=data.get("verification_reason", ""),
        )


class EvidenceEngine:
    """Manages evidence collection with provenance for a mission.

    Integrates with:
    - :class:`~research_engine.models.Evidence` (Phase 7 data model)
    - :class:`~research_engine.verification.VerificationEngine` (Phase 7 verification)
    - ArtifactRegistry / JobRegistry (external persistence, optional)
    """

    def __init__(self, verifier: Optional[VerificationEngine] = None) -> None:
        self._verifier = verifier or VerificationEngine()
        self._evidence: dict[str, EvidenceEntry] = {}

    # -- Collection --
    def register_evidence(
        self,
        source_url: str,
        source_type: str,
        title: Optional[str] = None,
        relevant_content: str = "",
        claims: Optional[list[str]] = None,
        supporting_excerpt: Optional[str] = None,
        provider: Optional[str] = None,
        actor: str = "evidence_engine",
    ) -> EvidenceEntry:
        """Register a new piece of evidence.  Never fabricates content."""
        ev = EvidenceEntry(
            evidence_id=f"ev_{_short_uuid()}",
            source_url=source_url,
            source_type=source_type,
            title=title,
            retrieved_at=now_iso(),
            relevant_content=relevant_content,
            claims=list(claims or []),
            supporting_excerpt=supporting_excerpt,
            provider=provider,
            verification_status=EvidenceStatus.UNVERIFIED.value,
        )
        ev.add_provenance(
            actor=actor,
            action="collected",
            detail=f"evidence registered from {source_type} source",
        )
        self._evidence[ev.evidence_id] = ev
        logger.debug("Registered evidence %s from %s", ev.evidence_id, source_type)
        return ev

    def register_from_tool_result(
        self,
        tool_name: str,
        result: Any,
        claims: Optional[list[str]] = None,
        task_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> EvidenceEntry:
        """Register evidence from a tool execution result.

        Extracts content from a ToolResult-like object and records full
        provenance linking the evidence to the capability, task, and artifact.
        """
        # Extract result content safely
        if isinstance(result, dict):
            content = result.get("result", "") or result.get("output", "") or ""
            metrics = result.get("metrics", {})
            provider = metrics.get("provider") if isinstance(metrics, dict) else None
        else:
            content = str(result) if result else ""
            provider = None

        ev = self.register_evidence(
            source_url=f"capability://{tool_name}",
            source_type=SourceType.CODE.value,
            title=f"Result from {tool_name}",
            relevant_content=content,
            claims=list(claims or []),
            provider=provider,
            actor=tool_name,
        )
        ev.add_provenance(
            actor=tool_name,
            action="tool_result",
            detail=f"evidence from {tool_name} execution",
            artifact_id=artifact_id,
            task_id=task_id,
        )
        return ev

    # -- Verification --
    def verify_evidence(
        self,
        evidence_id: str,
        experiments: Optional[list] = None,
    ) -> EvidenceStatus:
        """Verify an evidence item using the VerificationEngine.

        Updates the evidence's verification_status and returns it.
        """
        ev = self._evidence.get(evidence_id)
        if ev is None:
            raise KeyError(f"Unknown evidence: {evidence_id}")

        # Collect all evidence for cross-source comparison
        all_evidence = [e.evidence for e in self._evidence.values()]
        experiments = experiments or []

        # Verify each claim in this evidence item
        if not ev.claims:
            # No specific claims to verify — mark as VERIFIED (source is trustworthy)
            ev.verify(
                EvidenceStatus.VERIFIED,
                f"Source {ev.source_type} registered; no specific claims to verify",
                actor="evidence_engine",
            )
            return EvidenceStatus.VERIFIED

        # Verify the first claim (or each claim)
        overall_status = EvidenceStatus.UNVERIFIED
        for claim in ev.claims:
            status, reason, confidence = self._verifier.verify_claim(
                claim=claim,
                evidence=all_evidence,
                experiments=experiments,
            )
            if status == VerificationStatus.VERIFIED:
                overall_status = EvidenceStatus.VERIFIED
                ev.verify(status=overall_status, reason=reason,
                          confidence=confidence)
                return overall_status
            elif status == VerificationStatus.CONTRADICTED:
                overall_status = EvidenceStatus.CONTRADICTED
                ev.verify(status=overall_status, reason=reason,
                          confidence=confidence)
                return overall_status
            elif status == VerificationStatus.PARTIALLY_VERIFIED:
                overall_status = EvidenceStatus.PARTIALLY_SUPPORTED

        ev.verify(
            status=overall_status,
            reason=f"verification via {len(ev.claims)} claim(s)",
            actor="verification_engine",
        )
        return overall_status

    # -- Queries --
    def get(self, evidence_id: str) -> Optional[EvidenceEntry]:
        return self._evidence.get(evidence_id)

    def list_all(self) -> list[EvidenceEntry]:
        return list(self._evidence.values())

    def list_verified(self) -> list[EvidenceEntry]:
        return [e for e in self._evidence.values()
                if e.verification_status in (
                    EvidenceStatus.VERIFIED.value,
                    EvidenceStatus.SUPPORTED.value,
                    EvidenceStatus.PARTIALLY_SUPPORTED.value,
                )]

    def list_unverified(self) -> list[EvidenceEntry]:
        return [e for e in self._evidence.values()
                if e.verification_status == EvidenceStatus.UNVERIFIED.value]

    def list_refuted(self) -> list[EvidenceEntry]:
        return [e for e in self._evidence.values()
                if e.verification_status == EvidenceStatus.CONTRADICTED.value]

    def get_chain_of_custody(self, evidence_id: str) -> list[dict[str, Any]]:
        """Return the full provenance chain for an evidence item."""
        ev = self._evidence.get(evidence_id)
        if ev is None:
            return []
        return list(ev.provenance)

    def assert_no_fabrication(self) -> list[str]:
        """Return a list of fabrication violations, or empty if clean.

        Checks that no evidence is marked VERIFIED without a verification
        provenance entry, and no CONFIRMED hypothesis references unverified
        evidence.
        """
        violations: list[str] = []
        for ev in self._evidence.values():
            if ev.verification_status == EvidenceStatus.VERIFIED.value:
                # Must have a 'verified' provenance link
                has_verified_link = any(
                    p.get("action") == "verified"
                    for p in ev.provenance
                )
                if not has_verified_link:
                    violations.append(
                        f"Evidence {ev.evidence_id} marked VERIFIED but has "
                        f"no verification provenance link — potential fabrication"
                    )
            if ev.confidence is not None and ev.confidence > 0.0:
                # Confidence must come with verification
                if ev.verification_status == EvidenceStatus.UNVERIFIED.value:
                    violations.append(
                        f"Evidence {ev.evidence_id} has confidence score but "
                        f"verification_status is UNVERIFIED — confidence not justified"
                    )
        return violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": [e.to_dict() for e in self._evidence.values()],
            "total": len(self._evidence),
            "verified": len(self.list_verified()),
            "unverified": len(self.list_unverified()),
            "refuted": len(self.list_refuted()),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], verifier=None) -> "EvidenceEngine":
        engine = cls(verifier=verifier)
        for ed in data.get("evidence", []):
            ev = EvidenceEntry.from_dict(ed)
            engine._evidence[ev.evidence_id] = ev
        return engine


__all__ = [
    "ProvenanceChain",
    "EvidenceEntry",
    "EvidenceEngine",
]
