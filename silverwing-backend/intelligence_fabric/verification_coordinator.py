"""Verification Coordinator for the Silverwing Intelligence Fabric.

The ``VerificationCoordinator`` is responsible for cross-checking claims
produced by agents against evidence sources.  It works in conjunction
with the Model Router (for model-based verification) and the Evidence
System (for source-based verification).

Design:
    1. When an agent produces claims, it registers them with the
       coordinator via ``register_claims``.
    2. The coordinator determines which claims need verification
       based on the agent's verification policy.
    3. It selects an appropriate model via the ``ModelRouter`` and
       routes a verification prompt.
    4. Results are stored as verification records and can be queried.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from fabric_models import AgentSpec, RiskLevel


class VerificationStatus(str, Enum):
    """Outcome of a verification check."""
    PENDING = "pending"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"
    MIXED = "mixed"
    SKIPPED = "skipped"


class VerificationCoordinator:
    """Coordinates claim verification across agents and model calls."""

    def __init__(self, router=None) -> None:
        self._router = router  # ModelRouter from the Gateway
        # Stores: {claim_id: {record}}
        self._records: Dict[str, Dict[str, Any]] = {}
        # Stores: {mission_id: [claim_ids]}
        self._mission_claims: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_claims(self, mission_id: str, agent_id: str,
                        claims: List[Dict[str, Any]]) -> List[str]:
        """Register claims produced by an agent for later verification.

        Each claim dict should have at least ``statement`` (or ``text``)
        and may have ``evidence_ids``, ``sources``, ``confidence``.
        """

        claim_ids: List[str] = []
        for claim in claims:
            claim_id = f"claim-{uuid.uuid4().hex[:12]}"
            record = {
                "claim_id": claim_id,
                "mission_id": mission_id,
                "agent_id": agent_id,
                "statement": claim.get("statement") or claim.get("text", ""),
                "evidence_ids": claim.get("evidence_ids", []),
                "sources": claim.get("sources", []),
                "confidence": claim.get("confidence", 0.0),
                "verification_policy": claim.get("verification_policy", "standard"),
                "status": VerificationStatus.PENDING.value,
                "registered_at": time.time(),
                "verified_at": None,
                "verifying_model": None,
                "verifying_agent": None,
            }
            self._records[claim_id] = record
            self._mission_claims.setdefault(mission_id, []).append(claim_id)
            claim_ids.append(claim_id)

        return claim_ids

    # ------------------------------------------------------------------
    # Verification scheduling
    # ------------------------------------------------------------------

    def needs_verification(self, agent: AgentSpec, capability: str) -> bool:
        """Determine whether a task's claims need external verification."""

        if agent.verification_policy == "skip":
            return False
        if agent.verification_policy == "strict":
            return True
        if agent.verification_policy == "standard":
            # Only verify high-risk or evidence-heavy tasks
            return capability in ("research", "analysis", "verification")
        return True

    def schedule_verification(self, mission_id: str, agent: AgentSpec,
                              task_capability: str) -> List[str]:
        """Return claim IDs that need verification for this mission+agent+task."""

        claim_ids = self._mission_claims.get(mission_id, [])
        if not self.needs_verification(agent, task_capability):
            # Mark as skipped
            for cid in claim_ids:
                if self._records[cid]["status"] == VerificationStatus.PENDING.value:
                    self._records[cid]["status"] = VerificationStatus.SKIPPED.value
                    self._records[cid]["verified_at"] = time.time()
            return []
        return [cid for cid in claim_ids
                if self._records[cid]["status"] == VerificationStatus.PENDING.value]

    # ------------------------------------------------------------------
    # Model routing for verification
    # ------------------------------------------------------------------

    def select_verification_model(self, privacy: str = "public",
                                  cost: str = "best_quality") -> str:
        """Ask the ModelRouter to select a model for verification.

        If no router is available (e.g. in tests), returns a default
        lightweight model reference.
        """

        if self._router is not None:
            try:
                decision = self._router.select(
                    capability="verification",
                    privacy=privacy,
                    cost=cost,
                    task="verify_claim",
                )
                return decision.selected_model
            except Exception:
                pass

        return "silverwing:silverwing-decoder-v2"

    # ------------------------------------------------------------------
    # Recording results
    # ------------------------------------------------------------------

    def record_result(self, claim_id: str, status: VerificationStatus,
                      verifying_agent: Optional[str] = None,
                      verifying_model: Optional[str] = None,
                      notes: str = "") -> None:
        """Record the result of verifying a claim."""

        if claim_id not in self._records:
            return

        record = self._records[claim_id]
        record["status"] = status.value if isinstance(status, VerificationStatus) else status
        record["verified_at"] = time.time()
        record["verifying_agent"] = verifying_agent
        record["verifying_model"] = verifying_model
        record["notes"] = notes

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_record(self, claim_id: str) -> Optional[Dict[str, Any]]:
        return self._records.get(claim_id)

    def get_mission_records(self, mission_id: str) -> List[Dict[str, Any]]:
        claim_ids = self._mission_claims.get(mission_id, [])
        return [self._records[cid] for cid in claim_ids if cid in self._records]

    def summary(self, mission_id: Optional[str] = None) -> Dict[str, Any]:
        """Return a summary of verification status counts."""

        records = self.get_mission_records(mission_id) if mission_id \
            else list(self._records.values())

        counts: Dict[str, int] = {}
        for r in records:
            status = r["status"]
            counts[status] = counts.get(status, 0) + 1

        return {
            "total_claims": len(records),
            "status_counts": counts,
            "verified_rate": round(
                counts.get(VerificationStatus.VERIFIED.value, 0) /
                max(len(records), 1), 4
            ),
        }

    # ------------------------------------------------------------------
    # Async interface (delegates to the router if available)
    # ------------------------------------------------------------------

    async def async_verify_claim(self, claim_id: str,
                                 privacy: str = "public",
                                 cost: str = "best_quality") -> VerificationStatus:
        """Asynchronously verify a single claim using the ModelRouter."""

        record = self._records.get(claim_id)
        if record is None:
            return VerificationStatus.UNVERIFIABLE

        if not self._router:
            return VerificationStatus.UNVERIFIABLE

        model = self.select_verification_model(privacy, cost)

        # Build the verification message
        statement = record["statement"]
        evidence_ids = record.get("evidence_ids", [])
        evidence_texts: List[str] = []
        for eid in evidence_ids:
            evidence_texts.append(f"[evidence {eid}]")

        system = (
            f"You are a fact-checking assistant. "
            f"Verify the following claim. If the claim is supported by "
            f"the evidence, respond 'VERIFIED'. If contradicted, respond "
            f"'CONTRADICTED'. If you cannot determine, response "
            f"'UNVERIFIABLE'. "
            f"Claim: {statement}"
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": (
                f"Evidence:\n" + "\n".join(evidence_texts) + "\n\n"
                f"Claim: {statement}\n"
                f"Respond only with 'VERIFIED', 'CONTRADICTED', or 'UNVERIFIABLE'."
            )},
        ]

        try:
            from model_provider import ModelRequest  # imported lazily to avoid circular deps
            req = ModelRequest(messages=messages, model=model,
                               temperature=0.0, max_tokens=512)
            resp, _decision = await self._router.route_and_chat(
                req, task="verify_claim", privacy=privacy, cost=cost,
                capability="verification")

            answer = resp.content.strip().upper()
            if "VERIFIED" in answer:
                status = VerificationStatus.VERIFIED
            elif "CONTRICT" in answer:
                status = VerificationStatus.CONTRADICTED
            elif "UNVERIFIABLE" in answer:
                status = VerificationStatus.UNVERIFIABLE
            else:
                status = VerificationStatus.MIXED

            self.record_result(
                claim_id, status,
                verifying_agent="verifier", verifying_model=resp.model,
                notes=resp.content[:500])
            return status

        except Exception as e:
            self.record_result(
                claim_id, VerificationStatus.UNVERIFIABLE,
                notes=f"Error: {e}")
            return VerificationStatus.UNVERIFIABLE
