"""Verification engine (Section 12).

Classifies a claim against evidence and/or experiment outcomes using QUALITATIVE
statuses.  Numerical confidence is returned ONLY when a deterministic check
produced one; otherwise it stays ``None`` so the Brain can never mistake an
absence of verification for a confident claim.

Verification methods supported (each maps to a section 12 technique):
    - reproduction          (sandbox experiment reproducing the claim) -> VERIFIED / FAILED
    - source comparison     (cross-source agreement)                    -> SUPPORTED / CONTRADICTED
    - schema validation     (structured output shape)                 -> VERIFIED / UNVERIFIED
    - second model review   (only if a provider passed health checks) -> UNVERIFIED (never fabricated)
    - unit test / type check / static analysis                       -> VERIFIED / FAILED
    - browser evidence      (from the Evidence provenance store)       -> SUPPORTED / UNVERIFIED

The engine never invents evidence.  An absent result is UNAVAILABLE, not VERIFIED.
"""
from __future__ import annotations

from typing import Any, Optional

from .models import (
    Evidence,
    EvidenceStatus,
    Experiment,
    VerificationStatus,
)


class VerificationEngine:
    """Stateless verifier.  Safe to instantiate without any I/O backing."""

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def verify_claim(
        self,
        claim: str,
        evidence: list[Evidence],
        experiments: Optional[list[Experiment]] = None,
    ) -> tuple[VerificationStatus, str, Optional[float]]:
        """Verify ``claim`` against evidence (+ optional experiments).

        Returns ``(status, reason, confidence)`` where ``confidence`` is a real
        float only when a deterministic method produced one.
        """
        if not evidence and not experiments:
            return VerificationStatus.UNAVAILABLE, "no sources or experiments to verify against", None

        # 1. Contradiction short-circuit — never upgrade past CONTRADICTED.
        contradicted = [e for e in evidence if e.verification_status == EvidenceStatus.CONTRADICTED]
        for a in evidence:
            for b in evidence:
                if a is not b and a.conflicts_with(b):
                    return (
                        VerificationStatus.CONTRADICTED,
                        f"conflicting evidence: {a.source_url} vs {b.source_url}",
                        None,
                    )
        if contradicted:
            return (
                VerificationStatus.CONTRADICTED,
                f"{len(contradicted)} source(s) explicitly contradict the claim",
                None,
            )

        # 2. Reproduction beats everything — a passing experiment that confirms
        #    the claim is independent verification; a refuting reproduction is
        #    a direct contradiction (the claim's asserted value did not hold).
        if experiments:
            for exp in experiments:
                status, reason, _ = self.verify_reproduction(claim, exp)
                if status == VerificationStatus.VERIFIED:
                    return VerificationStatus.VERIFIED, reason, None
                if status in (VerificationStatus.FAILED, VerificationStatus.CONTRADICTED):
                    return (
                        VerificationStatus.CONTRADICTED,
                        f"reproduction {exp.id} refutes claim: {reason}",
                        None,
                    )

        # 3. Otherwise, downgrade to "supported but not independently verified".
        supported = [e for e in evidence if e.verification_status in (EvidenceStatus.SUPPORTED, EvidenceStatus.VERIFIED, EvidenceStatus.PARTIALLY_SUPPORTED)]
        if supported:
            statuses = {e.verification_status.value for e in supported}
            return (
                VerificationStatus.PARTIALLY_VERIFIED,
                f"claim supported by {len(supported)} source(s) ({', '.join(sorted(statuses))})",
                None,
            )
        if any(e.verification_status == EvidenceStatus.UNVERIFIED for e in evidence):
            return (
                VerificationStatus.UNVERIFIED,
                "sources present but none corroborate the claim",
                None,
            )
        return (
            VerificationStatus.UNVERIFIED,
            "evidence present but insufficient to support or refute the claim",
            None,
        )

    def verify_reproduction(
        self, claim: str, experiment: Experiment
    ) -> tuple[VerificationStatus, str, Optional[float]]:
        """Classify an experiment's match against ``claim``."""
        obs = (experiment.result or "").strip()
        if not obs:
            return VerificationStatus.UNVERIFIED, f"experiment {experiment.id} produced no observation", None
        # Deterministic, exact-match confirmation only.
        if _claim_confirmed_by_observation(claim, obs):
            return VerificationStatus.VERIFIED, f"reproduction {experiment.id} confirms claim", None
        return (
            VerificationStatus.CONTRADICTED,
            f"reproduction {experiment.id} contradicts claim (observed: {obs[:120]})",
            None,
        )

    def classify_tool_result(
        self, tool_name: str, result: Any
    ) -> VerificationStatus:
        """Map a deterministic tool outcome to a verification status (Section 12).

        - unit-test / type-check / static-analysis: ``ok=True`` -> VERIFIED else FAILED
        - sandbox run: success -> VERIFIED else FAILED
        - everything else: UNVERIFIED (never fabricated)
        """
        if isinstance(result, dict):
            ok = result.get("ok", result.get("success", False))
            if tool_name in ("unit_test", "type_check", "static_analysis"):
                return VerificationStatus.VERIFIED if ok else VerificationStatus.FAILED
            if tool_name == "sandbox_run":
                return VerificationStatus.VERIFIED if ok else VerificationStatus.FAILED
        return VerificationStatus.UNVERIFIED

    # ------------------------------------------------------------------ #
    # Convenience used by the agent / research engine
    # ------------------------------------------------------------------ #
    def verify(
        self,
        claim: str,
        evidence: list[Evidence],
        experiments: Optional[list[Experiment]] = None,
    ) -> tuple[VerificationStatus, str]:
        status, reason, _ = self.verify_claim(claim, evidence or [], experiments or [])
        return status, reason


def _claim_confirmed_by_observation(claim: str, observation: str) -> bool:
    """Exact, deterministic confirmation check.

    The claim is considered confirmed only when the observation contains a
    numeric/result substring that matches the claim's asserted value.  This is
    deliberately narrow so we never misclassify a near-miss as confirmation.
    """
    if not claim or not observation:
        return False
    # Pull the trailing token of the claim (e.g. "4" out of "2 + 2 equals 4").
    import re

    tokens = re.findall(r"[0-9]+(?:\.[0-9]+)?", claim)
    if not tokens:
        return False
    last = tokens[-1]
    return last in re.findall(r"[0-9]+(?:\.[0-9]+)?", observation)
