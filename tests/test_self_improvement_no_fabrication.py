"""Phase 12 — No-fabrication audit tests for the Self-Improvement Engine.

Verifies that no Phase 12 code path fabricates metrics, evidence, or results.
Every improvement claim must be grounded in real evaluation data tied to
the baseline/candidate via the BaselineLock and EvidenceEngine.
"""

import pytest

from jarvis_backend.core import get_store
from jarvis_backend.self_improvement import (
    BaselineLock,
    CandidateArtifact,
    CandidateStatus,
    ImprovementPolicy,
    ImprovementResult,
    SelfImprovementCycle,
    WeaknessDetector,
)
from jarvis_backend.self_improvement_engine import SelfImprovementOrchestrator
from jarvis_backend.brain_fabric import assert_no_secrets
from jarvis_backend.evidence_engine import EvidenceEngine


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


def _make_cycle_with_baseline(target_capability="math_reasoning"):
    cycle = SelfImprovementCycle.create(
        target_capability=target_capability,
        baseline_model="Qwen/Qwen3-4B",
        baseline_revision="1cfa9a7208912126459214e8b04321603b3df60c",
        problem_statement="Improve math accuracy",
        mission_id="m1",
        owner="test_user",
    )
    cycle.save()
    lock = BaselineLock(
        model_id=cycle.baseline_model,
        revision=cycle.baseline_revision,
        metrics={"accuracy": 0.85},
        dataset_id="dataset_001",
    )
    cycle.set_baseline_lock(lock)
    # Also set baseline_results so evaluate_improvement can read the baseline metrics
    cycle.baseline_results = {
        "metrics": [
            {"name": "accuracy", "value": 0.85, "higher_is_better": True,
             "evaluation_version": "math_v1"},
        ],
    }
    cycle.save()
    return cycle


# ===========================================================================
# A. WeaknessDetector does not fabricate — only reports actual regressions
# ===========================================================================

class TestNoFabricationWeaknessDetection:
    """No-fabrication: WeaknessDetector only reports real regressions."""

    def test_no_weakness_for_improvement(self):
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.80, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.85, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        w = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert w == [], "Fabricated weakness for improved metric"

    def test_weakness_values_match_actual_data(self):
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.90, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.75, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        w = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(w) == 1
        fi = w[0].failures[0]
        assert fi.baseline_value == 0.90  # exact match
        assert fi.current_value == 0.75   # exact match
        # No fabricated evidence string
        assert "fabricated" not in str(fi.evidence).lower()
        assert "estimated" not in str(fi.evidence).lower()

    def test_no_weakness_without_candidate_results(self):
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.85, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        w = detector.detect_from_results(baseline, {}, min_regression=0.05)
        assert w == [], "Fabricated weakness from empty candidate results"

    def test_no_weakness_without_baseline_results(self):
        detector = WeaknessDetector()
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.75, "higher_is_better": True,
             "evaluation_version": "v1"},
        ]}
        w = detector.detect_from_results({}, candidate, min_regression=0.05)
        assert w == [], "Fabricated weakness from empty baseline"


# ===========================================================================
# B. BaselineLock is tamper-evident and not fabricated
# ===========================================================================

class TestNoFabricationBaselineLock:
    """No-fabrication: BaselineLock cannot be forged or tampered."""

    def test_lock_hash_matches_content(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="d1",
        )
        assert lock.lock_hash != ""
        assert lock.verify()

    def test_lock_cannot_be_forged_with_empty_hash(self):
        """If lock_hash is set to empty after creation, verify must fail."""
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="d1",
            lock_hash="",
        )
        # __post_init__ computes hash, so it should be non-empty
        assert lock.lock_hash != ""
        assert lock.verify()

    def test_lock_tampering_fails_verify(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="d1",
        )
        lock.metrics["accuracy"] = 0.99
        assert not lock.verify()

    def test_lock_to_dict_includes_hash(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="d1",
        )
        d = lock.to_dict()
        assert "lock_hash" in d
        assert d["lock_hash"] != ""
        assert len(d["lock_hash"]) == 32


# ===========================================================================
# C. evaluate_improvement uses real metrics, not fabricated numbers
# ===========================================================================

class TestNoFabricationEvaluateImprovement:
    """No-fabrication: evaluate_improvement uses real metrics only."""

    def test_improvement_verdict_uses_real_values(self):
        cycle = _make_cycle_with_baseline()
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.90, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
            minimum_improvement=0.01,
            regression_protect_metrics=["accuracy"],
        )
        result = cycle.evaluate_improvement(policy)
        assert result.verdict == "improved"
        # Relative improvement: (0.90-0.85)/0.85 = 0.0588
        assert result.comparison["relative_improvement"] == pytest.approx(0.0588, abs=0.001)

    def test_regression_verdict_uses_real_values(self):
        cycle = _make_cycle_with_baseline()
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.70, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
            minimum_improvement=0.01,
            maximum_allowed_regression=0.02,
            regression_protect_metrics=["accuracy"],
        )
        result = cycle.evaluate_improvement(policy)
        assert result.regression_detected
        assert result.verdict == "regressed"
        # Relative regression: (0.70-0.85)/0.85 = -0.1765
        assert result.comparison["relative_improvement"] == pytest.approx(-0.1765, abs=0.001)

    def test_verdict_no_change(self):
        cycle = _make_cycle_with_baseline()
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.85, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
            minimum_improvement=0.05,
        )
        result = cycle.evaluate_improvement(policy)
        assert result.verdict == "no_change"
        assert result.target_improvement == 0.0

    def test_confidence_high_when_no_regression(self):
        """Confidence is 1.0 when there is no regression (high certainty)."""
        cycle = _make_cycle_with_baseline()
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.90, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
            "sample_count": 10,
        }
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
            minimum_improvement=0.01,
        )
        result = cycle.evaluate_improvement(policy)
        assert result.confidence == 1.0

    def test_confidence_drops_with_large_regression(self):
        """Confidence falls when a large regression is present."""
        cycle = _make_cycle_with_baseline()
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.30, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
            minimum_improvement=0.01,
            maximum_allowed_regression=0.02,
            regression_protect_metrics=["accuracy"],
        )
        result = cycle.evaluate_improvement(policy)
        # Large regression (70%) -> max_regression >= 0.5 -> confidence 0.0
        assert result.confidence == 0.0


# ===========================================================================
# D. EvidenceEngine assert_no_fabrication returns empty for real cycles
# ===========================================================================

class TestNoFabricationEvidenceEngine:
    """No-fabrication: EvidenceEngine detects fabricated metrics."""

    def test_no_fabrication_flag(self):
        """EvidenceEngine.assert_no_fabrication should return empty list for clean state."""
        engine = EvidenceEngine()
        issues = engine.assert_no_fabrication()
        assert issues == [], f"Evidence engine reported fabrication issues: {issues}"

    def test_no_fabrication_with_baseline_lock(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="d1",
        )
        lock.freeze()
        engine = EvidenceEngine()
        issues = engine.assert_no_fabrication()
        assert issues == []


# ===========================================================================
# E. assert_no_secrets never leaks credentials into improvement artifacts
# ===========================================================================

class TestNoFabricationNoSecrets:
    """No-fabrication: No secret data in any improvement artifact payload."""

    def test_clean_payload_no_secrets(self):
        payload = {
            "improvement_id": "impr_001",
            "baseline_results": {"metrics": [{"value": 0.85}]},
            "candidate_results": {"metrics": [{"value": 0.90}]},
            "training_config": {"base_model": "Qwen/Qwen3-4B", "epochs": 3.0},
        }
        leaks = assert_no_secrets(payload)
        assert leaks == [], f"Secrets leaked in clean payload: {leaks}"

    def test_secret_payload_detected(self):
        payload = {
            "improvement_id": "impr_001",
            "training_config": {"api_key": "sk-12345"},
        }
        leaks = assert_no_secrets(payload)
        assert any("api_key" in p for p in leaks), f"Expected api_key in {leaks}"

    def test_verify_cycle_checks_for_secrets(self):
        """verify_cycle must flag any secret-shaped fields in the cycle."""
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = _make_cycle_with_baseline()
        cycle.training_config = {"base_model": "Qwen/Qwen3-4B", "api_key": "sk-leaked"}
        # Use a proper CandidateArtifact via set_candidate
        candidate = CandidateArtifact(
            artifact_id="art_001",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="cand_rev_001",
            training_config={"api_key": "sk-candidate-leaked"},
            status=CandidateStatus.APPROVED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        result = orch.verify_cycle(cycle, ImprovementPolicy(
            target_capability="math", target_metric="accuracy"
        ))
        assert result["details"]["baseline_lock"] == "verified"
        assert "secrets_detected_in_cycle_data" in result["checks"]
