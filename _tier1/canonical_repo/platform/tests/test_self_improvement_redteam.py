"""Phase 12 — Security red-team tests for the Self-Improvement Engine.

Verifies that JARVIS self-improvement can NEVER:
  1. Access credentials / secrets
  2. Modify secrets or protected infrastructure
  3. Bypass authentication / authorization
  4. Approve its own promotion without the existing PromotionGate
  5. Promote or deploy an unverified candidate
  6. Fabricate metrics
  7. Erase experiments or audit trails
"""

import pytest

from jarvis_backend.core import get_store
from jarvis_backend.self_improvement import (
    HIGH_RISK_INTERVENTIONS,
    PROHIBITED_INTERVENTIONS,
    AutonomyGuard,
    BaselineLock,
    CandidateArtifact,
    CandidateStatus,
    DeploymentMode,
    FailureSeverity,
    ImprovementPolicy,
    ImprovementStatus,
    InterventionType,
    SECRET_FIELD_PATTERNS,
    SelfImprovementCycle,
    WeaknessDetector,
)
from jarvis_backend.self_improvement_engine import SelfImprovementOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_store():
    store = get_store("improvements")
    data = store.load()
    data["cycles"] = {}
    data["lessons"] = {}
    data["graph"] = {"nodes": {}, "edges": []}
    store.save()
    yield
    data = store.load()
    data["cycles"] = {}
    data["lessons"] = {}
    data["graph"] = {"nodes": {}, "edges": []}
    store.save()


# ===========================================================================
# 1. Cannot access credentials through AutonomyGuard
# ===========================================================================

class TestCannotAccessCredentials:
    """Security Test 1 — AutonomyGuard blocks all secret-shaped interventions."""

    @pytest.mark.parametrize("pat", list(SECRET_FIELD_PATTERNS))
    def test_secret_pattern_in_target_blocked(self, pat):
        guard = AutonomyGuard(autonomy_level=3)
        target = f"config:{pat}=sk-12345"
        allowed, reason = guard.check_intervention(
            InterventionType.PROMPT_CHANGE, target
        )
        assert not allowed, f"Secret pattern '{pat}' was not blocked"
        assert "secret" in reason.lower()

    def test_cannot_read_env_file(self):
        guard = AutonomyGuard(autonomy_level=3)
        allowed, reason = guard.check_intervention(
            InterventionType.RETRIEVAL_CHANGE, ".env"
        )
        assert not allowed
        assert "protected" in reason.lower()

    def test_cannot_access_provider_directory(self):
        guard = AutonomyGuard(autonomy_level=3)
        allowed, reason = guard.check_intervention(
            InterventionType.CONTEXT_CHANGE, "providers/nvidia/credentials.json"
        )
        assert not allowed


# ===========================================================================
# 2. Cannot modify secrets / protected infrastructure
# ===========================================================================

class TestCannotModifyProtectedPaths:
    """Security Test 2 — AutonomyGuard blocks interventions on protected paths."""

    @pytest.mark.parametrize("path", [
        "jarvis_backend/core.py",
        "infrastructure/promotion_gate.py",
        "infrastructure/audit_events.py",
        "infrastructure/job_registry.py",
        "infrastructure/artifact_registry.py",
        "infrastructure/provider_registry.py",
        "jarvis_backend/cloud_fabric.py",
        ".env",
        "jarvis_secret_key",
        "providers/anthropic",
    ])
    def test_protected_path_blocked(self, path):
        guard = AutonomyGuard(autonomy_level=3)
        allowed, reason = guard.check_intervention(
            InterventionType.PROMPT_CHANGE, path
        )
        assert not allowed, f"Protected path '{path}' was not blocked"
        assert "protected" in reason.lower()


# ===========================================================================
# 3. Cannot bypass auth / authorization — SYSTEM_POLICY_CHANGE always blocked
# ===========================================================================

class TestCannotBypassAuth:
    """Security Test 3 — SYSTEM_POLICY_CHANGE can never be autonomous."""

    def test_system_policy_change_blocked_at_level_0(self):
        guard = AutonomyGuard(autonomy_level=0)
        allowed, reason = guard.check_intervention(
            InterventionType.SYSTEM_POLICY_CHANGE, "model:test"
        )
        assert not allowed

    def test_system_policy_change_blocked_at_level_1(self):
        guard = AutonomyGuard(autonomy_level=1)
        allowed, reason = guard.check_intervention(
            InterventionType.SYSTEM_POLICY_CHANGE, "model:test"
        )
        assert not allowed

    def test_system_policy_change_blocked_at_level_3(self):
        guard = AutonomyGuard(autonomy_level=3)
        allowed, reason = guard.check_intervention(
            InterventionType.SYSTEM_POLICY_CHANGE, "model:test"
        )
        assert not allowed

    def test_architecture_change_blocked_at_level_3(self):
        guard = AutonomyGuard(autonomy_level=3)
        allowed, reason = guard.check_intervention(
            InterventionType.ARCHITECTURE_CHANGE, "model:test"
        )
        assert not allowed

    def test_system_policy_change_in_prohibited_set(self):
        assert InterventionType.SYSTEM_POLICY_CHANGE in PROHIBITED_INTERVENTIONS


# ===========================================================================
# 4. Cannot promote its own model without existing PromotionGate
# ===========================================================================

class TestCannotPromoteWithoutGate:
    """Security Test 4 — Promotion requires PromotionGate, not direct cycle mutation."""

    def test_can_promote_requires_approved_artifact(self):
        """An EXPERIMENTAL candidate cannot be promoted."""
        guard = AutonomyGuard(autonomy_level=3)
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        # Default status is EXPERIMENTAL
        allowed, reason = guard.can_promote(c, promotion_approved=False)
        assert not allowed

    def test_can_promote_requires_manual_approval_flag(self):
        """At autonomy_level < 3, APPROVED artifact still requires explicit approval flag."""
        guard = AutonomyGuard(autonomy_level=1)
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
            status=CandidateStatus.APPROVED.value,
        )
        # Without the approval flag at level 1, should not be promotable
        allowed, reason = guard.can_promote(c, promotion_approved=False)
        assert not allowed
        # With the flag, should be allowed
        allowed, reason = guard.can_promote(c, promotion_approved=True)
        assert allowed

    def test_no_direct_status_skipping(self):
        """Candidate cannot jump from EXPERIMENTAL to APPROVED."""
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        with pytest.raises(ValueError):
            c.transition(CandidateStatus.APPROVED)


# ===========================================================================
# 5. Cannot promote or deploy an UNVERIFIED candidate
# ===========================================================================

class TestCannotDeployUnverified:
    """Security Test 5 — Deployment requires verified + approved candidate."""

    def test_deploy_unverified_candidate_fails(self):
        """Cannot deploy a candidate that hasn't been through verification."""
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="test",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc",
            problem_statement="test",
        )
        cycle.save()
        # Candidate is EXPERIMENTAL, not APPROVED
        candidate = CandidateArtifact(
            artifact_id="art_001",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        cycle.set_candidate(candidate)
        cycle.save()
        with pytest.raises(ValueError, match="must be APPROVED"):
            orch.deploy_candidate(cycle, mode=DeploymentMode.SHADOW.value)

    def test_deploy_rejected_candidate_fails(self):
        """Cannot deploy a REJECTED candidate."""
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="test",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc",
            problem_statement="test",
        )
        cycle.save()
        candidate = CandidateArtifact(
            artifact_id="art_001",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
            status=CandidateStatus.REJECTED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        with pytest.raises(ValueError, match="must be APPROVED"):
            orch.deploy_candidate(cycle, mode=DeploymentMode.SHADOW.value)


# ===========================================================================
# 6. Cannot fabricate metrics
# ===========================================================================

class TestCannotFabricateMetrics:
    """Security Test 6 — WeaknessDetector never fabricates; only detects regressions."""

    def test_no_weakness_when_better(self):
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.80, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.90, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 0  # No fabricated weakness for improvement

    def test_weakness_count_matches_actual_regressions(self):
        """Each weakness corresponds to an actual metric regression, not fabricated."""
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.90, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.70, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 1
        w = weaknesses[0]
        fi = w.failures[0]
        # The failure must reflect the actual values, not inflated numbers
        assert fi.baseline_value == 0.90
        assert fi.current_value == 0.70

    def test_no_weakness_when_no_matching_version(self):
        """No weakness fabricated when evaluation versions don't match."""
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.90, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.50, "higher_is_better": True,
             "evaluation_version": "v2"},  # different version
        ]}
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 0  # No match, no fabrication


# ===========================================================================
# 7. Cannot erase experiments / audit trails
# ===========================================================================

class TestCannotEraseEvidence:
    """Security Test 7 — BaselineLock tampering is detectable; cycles are persisted."""

    def test_baseline_lock_tampering_detected(self):
        """A tampered baseline lock must fail verification."""
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        assert lock.verify()
        # Tamper
        lock.metrics["accuracy"] = 0.99
        assert not lock.verify(), "Tampered baseline lock was not detected"

    def test_baseline_lock_hash_is_immutable(self):
        """The lock_hash must not change when metrics are tampered."""
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        original_hash = lock.lock_hash
        lock.metrics["accuracy"] = 0.99
        assert lock.lock_hash == original_hash, "Lock hash was modified by tampering"

    def test_cycle_persisted_to_store(self):
        """Created cycles must persist in the improvements store."""
        cycle = SelfImprovementCycle.create(
            target_capability="test",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc",
            problem_statement="test tamper",
        )
        assert cycle.improvement_id.startswith("impr_")
        store = get_store("improvements")
        data = store.load()
        assert cycle.improvement_id in data.get("cycles", {})
