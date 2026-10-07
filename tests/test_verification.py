"""Tests for the Verification Engine (Section 12).

Pure, no I/O, no secrets.  Covers UNAVAILABLE (no evidence), VERIFIED
(reproduction), and CONTRADICTED (conflicting evidence).
"""
from __future__ import annotations

import pytest

from research_engine.models import (
    Evidence,
    EvidenceStatus,
    Experiment,
    ResearchMode,
    SourceType,
    VerificationStatus,
)
from research_engine.verification import VerificationEngine, _claim_confirmed_by_observation

pytestmark = pytest.mark.brain


def _ev(claim: str, status: EvidenceStatus = EvidenceStatus.SUPPORTED,
        url: str = "https://example.org") -> Evidence:
    return Evidence(
        id="ev-x",
        source_url=url,
        source_type=SourceType.WEB,
        title="t",
        retrieved_at="2024-01-01T00:00:00+00:00",
        relevant_content=claim,
        claims=[claim],
        supporting_excerpt=claim,
        confidence=None,
        verification_status=status,
    )


def test_no_evidence_is_unavailable():
    v = VerificationEngine()
    status, reason = v.verify("anything", [], None)
    assert status == VerificationStatus.UNAVAILABLE
    assert "no sources" in reason.lower()


def test_reproduction_verifies_claim():
    v = VerificationEngine()
    exp = Experiment(
        id="exp-1", objective="2+2", hypothesis="print(2+2) -> 4",
        observations=["4"], result="4",
    )
    status, reason = v.verify("does 2+2 equal 4", [_ev("2+2=4")], [exp])
    assert status == VerificationStatus.VERIFIED
    assert "reproduction" in reason.lower()


def test_reproduction_failure_contradicts():
    v = VerificationEngine()
    # The real computation 2+2 yields 4, but the claim asserts 5 -> contradiction.
    exp = Experiment(id="exp-1", objective="2+2", hypothesis="print(2+2) -> 4",
                     observations=["4"], result="4")
    status, _ = v.verify("2+2 equals 5", [_ev("math fact")], [exp])
    assert status == VerificationStatus.CONTRADICTED


def test_conflicting_evidence_is_contradicted():
    v = VerificationEngine()
    a = _ev("the value is 4")
    b = _ev("not the value is 4")  # 'not ' + residual => _contradicts -> True
    status, _ = v.verify("claim", [a, b], None)
    assert status == VerificationStatus.CONTRADICTED


def test_supported_evidence_partially_verified():
    v = VerificationEngine()
    status, _ = v.verify("claim", [_ev("claim")], None)
    assert status == VerificationStatus.PARTIALLY_VERIFIED


def test_unverified_evidence_only():
    v = VerificationEngine()
    e = _ev("claim", status=EvidenceStatus.UNVERIFIED)
    status, reason = v.verify("claim", [e], None)
    assert status == VerificationStatus.UNVERIFIED


def test_claim_confirmed_by_observation():
    assert _claim_confirmed_by_observation("2+2 equals 4", "4") is True
    assert _claim_confirmed_by_observation("2+2 equals 5", "4") is False
    assert _claim_confirmed_by_observation("", "") is False


def test_experiment_classification():
    v = VerificationEngine()
    # A successful sandbox run -> VERIFIED by classify_tool_result.
    res = {"success": True, "result": "4"}
    assert v.classify_tool_result("sandbox_run", res) == VerificationStatus.VERIFIED
    # A failed sandbox run -> FAILED.
    res_fail = {"success": False, "error": "violation"}
    assert v.classify_tool_result("sandbox_run", res_fail) == VerificationStatus.FAILED
    # Unknown tool -> UNVERIFIED (never fabricated).
    assert v.classify_tool_result("magic", {"success": True}) == VerificationStatus.UNVERIFIED
