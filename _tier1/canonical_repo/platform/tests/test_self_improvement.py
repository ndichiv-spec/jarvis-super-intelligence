"""Phase 12 — Core test suite for the JARVIS Self-Improvement Engine.

Covers:
  1.  Cycle lifecycle (create, transition, terminal states)
  2.  ImprovementStatus state machine (valid/invalid transitions)
  3.  InterventionType (all 10 members, high-risk, prohibited)
  4.  Weakness detection (regression-based)
  5.  Failure clustering (FailureTaxonomy clusters weaknesses)
  6.  Baseline lock (immutable, hash verify, tamper detection)
  7.  TrainingConfig (defaults, to_dict, from_dict)
  8.  CandidateArtifact state transitions (EXPERIMENTAL → STAGING → ... → APPROVED)
  9.  EvaluationMatrix (all_suites)
  10. ImprovementPolicy (to_dict, from_dict, fields)
  11. AutonomyGuard (intervention checks, protected paths, secret detection)
  12. Cycle persistence (save, load, from_dict round-trip)
  13. DatasetQualityGate (schema, dedup, safety, minimum samples)
  14. evaluate_improvement (comparison, regression detection, verdict)
  15. Critique cycle integration (returns findings for incomplete cycle)
  16. Evaluate candidate (no crash with None candidate)
  17. Deployment modes (shadow, production blocked at low autonomy)
  18. Rollback (rollback_deployment sets rolled_back flag)
  19. Budget check (check_budget delegates to BudgetManager)
  20. LearningMemory (add_lesson, get_lessons)
  21. ImprovementGraph (add_node, add_edge)
  22. run_improvement_cycle blocked path (autonomy_level=1 → approval blocks)
"""

import pytest

from jarvis_backend.core import get_store, now_iso
from jarvis_backend.self_improvement import (
    HIGH_RISK_INTERVENTIONS,
    PROHIBITED_INTERVENTIONS,
    AutonomyGuard,
    BaselineLock,
    CandidateArtifact,
    CandidateStatus,
    DeploymentMode,
    EvaluationMatrix,
    FailureCategory,
    FailureInstance,
    FailureSeverity,
    GraphNode,
    Hypothesis,
    ImprovementGraph,
    ImprovementPolicy,
    ImprovementResult,
    ImprovementStatus,
    ImprovementDeployment,
    InterventionType,
    LearningMemory,
    Lesson,
    SelfImprovementCycle,
    TrainingConfig,
    Weakness,
    WeaknessDetector,
)
from jarvis_backend.self_improvement_engine import (
    CycleStepResult,
    DatasetImprovementLoop,
    DatasetQualityGate,
    SelfImprovementOrchestrator,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_store():
    """Ensure the improvements store is clean before and after each test."""
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


def _make_cycle(target_capability="code_generation",
                baseline_model="Qwen/Qwen3-4B",
                baseline_revision="1cfa9a7208912126459214e8b04321603b3df60c",
                status=ImprovementStatus.IDENTIFIED.value):
    """Create a SelfImprovementCycle directly (without persistence) for unit tests."""
    from jarvis_backend.self_improvement import _short_uuid
    return SelfImprovementCycle(
        improvement_id=f"impr_{_short_uuid()}",
        mission_id=f"mission_{_short_uuid()}",
        target_capability=target_capability,
        baseline_model=baseline_model,
        baseline_revision=baseline_revision,
        problem_statement=f"Test problem for {target_capability}",
        status=status,
    )


# ===========================================================================
# 1. Cycle lifecycle
# ===========================================================================

class TestCycleLifecycle:
    """Test 1 — SelfImprovementCycle lifecycle."""

    def test_cycle_create_persisted(self):
        cycle = SelfImprovementCycle.create(
            target_capability="math_reasoning",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="1cfa9a7208912126459214e8b04321603b3df60c",
            problem_statement="Accuracy drop on algebra word problems",
            mission_id="mission_001",
            owner="test_user",
        )
        assert cycle.improvement_id.startswith("impr_")
        assert cycle.status == ImprovementStatus.IDENTIFIED.value
        assert cycle.target_capability == "math_reasoning"
        assert len(cycle.provenance) > 0

        # Should be persisted
        loaded = SelfImprovementCycle.load(cycle.improvement_id)
        assert loaded is not None
        assert loaded.improvement_id == cycle.improvement_id
        assert loaded.status == ImprovementStatus.IDENTIFIED.value

    def test_cycle_transition_valid(self):
        cycle = _make_cycle()
        cycle.transition(ImprovementStatus.ANALYZING)
        assert cycle.status == ImprovementStatus.ANALYZING.value
        cycle.transition(ImprovementStatus.HYPOTHESIS_FORMED)
        assert cycle.status == ImprovementStatus.HYPOTHESIS_FORMED.value
        cycle.transition(ImprovementStatus.DESIGNED)
        assert cycle.status == ImprovementStatus.DESIGNED.value

    def test_cycle_transition_invalid_raises(self):
        cycle = _make_cycle()
        with pytest.raises(ValueError, match="Invalid ImprovementStatus transition"):
            cycle.transition(ImprovementStatus.COMPLETED)

    def test_cycle_is_terminal(self):
        cycle = _make_cycle()
        assert not cycle.is_terminal
        cycle.transition(ImprovementStatus.BLOCKED)
        assert cycle.is_terminal

    def test_cycle_round_trip(self):
        cycle = _make_cycle()
        cycle.failure_evidence = [{"metric": "accuracy", "drop": 0.10}]
        d = cycle.to_dict()
        loaded = SelfImprovementCycle.from_dict(d)
        assert loaded.improvement_id == cycle.improvement_id
        assert loaded.failure_evidence == cycle.failure_evidence


# ===========================================================================
# 2. ImprovementStatus state machine
# ===========================================================================

class TestImprovementStatusStateMachine:
    """Test 2 — ImprovementStatus state machine."""

    def test_all_18_states_present(self):
        expected = {
            "identified", "analyzing", "hypothesis_formed", "designed",
            "awaiting_approval", "data_preparation", "training", "evaluating",
            "critiquing", "verifying", "promotion_review", "deploying",
            "monitoring", "completed", "rejected", "failed", "blocked",
            "rolled_back",
        }
        actual = {s.value for s in ImprovementStatus}
        assert actual == expected

    def test_terminal_states(self):
        terminals = ImprovementStatus.terminal_states()
        for t in terminals:
            assert ImprovementStatus.is_terminal(t)
        assert ImprovementStatus.IDENTIFIED.value not in terminals

    def test_valid_transitions_cover_all_states(self):
        trans = ImprovementStatus.valid_transitions()
        for s in ImprovementStatus:
            if s.value not in trans:
                pytest.fail(f"{s.value} missing from valid_transitions")

    def test_invalid_transition_raises(self):
        with pytest.raises(ValueError):
            ImprovementStatus.validate_transition(
                ImprovementStatus.COMPLETED.value,
                ImprovementStatus.ANALYZING.value,
            )

    def test_valid_transition_does_not_raise(self):
        # Should not raise
        ImprovementStatus.validate_transition(
            ImprovementStatus.IDENTIFIED.value,
            ImprovementStatus.ANALYZING.value,
        )

    def test_blocked_to_analyzing_valid(self):
        ImprovementStatus.validate_transition(
            ImprovementStatus.BLOCKED.value,
            ImprovementStatus.ANALYZING.value,
        )

    def test_rolled_back_terminal(self):
        assert ImprovementStatus.ROLLED_BACK.value in ImprovementStatus.terminal_states()


# ===========================================================================
# 3. InterventionType
# ===========================================================================

class TestInterventionType:
    """Test 3 — InterventionType enum."""

    def test_all_10_members(self):
        expected = {
            "prompt_change", "system_policy_change", "retrieval_change",
            "context_change", "dataset_change", "training_change",
            "hyperparameter_change", "architecture_change", "merge_change",
            "prompt_template_change",
        }
        actual = {t.value for t in InterventionType}
        assert actual == expected

    def test_high_risk_interventions(self):
        assert InterventionType.SYSTEM_POLICY_CHANGE in HIGH_RISK_INTERVENTIONS
        assert InterventionType.ARCHITECTURE_CHANGE in HIGH_RISK_INTERVENTIONS
        assert InterventionType.PROMPT_CHANGE not in HIGH_RISK_INTERVENTIONS

    def test_prohibited_interventions(self):
        assert InterventionType.SYSTEM_POLICY_CHANGE in PROHIBITED_INTERVENTIONS
        assert InterventionType.TRAINING_CHANGE not in PROHIBITED_INTERVENTIONS

    def test_safe_from_value(self):
        val = "training_change"
        it = InterventionType.safe_from_value(val)
        assert it == InterventionType.TRAINING_CHANGE

    def test_safe_from_value_invalid(self):
        with pytest.raises(ValueError):
            InterventionType.safe_from_value("nonexistent")


# ===========================================================================
# 4. Weakness detection
# ===========================================================================

class TestWeaknessDetection:
    """Test 4 — WeaknessDetector detects regressions."""

    def test_detect_regression(self):
        detector = WeaknessDetector()
        baseline = {
            "metrics": [
                {"name": "accuracy", "value": 0.85, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        candidate = {
            "metrics": [
                {"name": "accuracy", "value": 0.75, "higher_is_better": True,
                 "evaluation_version": "math_v1",
                 "provenance": ["eval:math_v1"]},
            ],
            "sample_count": 100,
        }
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 1
        w = weaknesses[0]
        assert w.target_capability == "math_v1"
        assert w.severity in (FailureSeverity.LOW, FailureSeverity.MEDIUM,
                              FailureSeverity.HIGH, FailureSeverity.CRITICAL)
        assert len(w.failures) == 1
        assert w.failures[0].category == FailureCategory.METRIC_REGRESSION
        assert w.failures[0].baseline_value == 0.85
        assert w.failures[0].current_value == 0.75

    def test_no_weakness_when_improved(self):
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.80, "higher_is_better": True,
             "evaluation_version": "math_v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.90, "higher_is_better": True,
             "evaluation_version": "math_v1"},
        ], "sample_count": 50}
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 0

    def test_no_weakness_when_no_regression(self):
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.85, "higher_is_better": True,
             "evaluation_version": "math_v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.84, "higher_is_better": True,
             "evaluation_version": "math_v1"},
        ]}
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 0  # 1.2% drop < 5% threshold


# ===========================================================================
# 5. Failure clustering
# ===========================================================================

class TestFailureClustering:
    """Test 5 — FailureTaxonomy clusters weaknesses."""

    def test_weaknesses_clustered_by_category_severity(self):
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.90, "higher_is_better": True,
             "evaluation_version": "math_v1"},
            {"name": "accuracy", "value": 0.90, "higher_is_better": True,
             "evaluation_version": "code_v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.70, "higher_is_better": True,
             "evaluation_version": "math_v1"},
            {"name": "accuracy", "value": 0.70, "higher_is_better": True,
             "evaluation_version": "code_v1"},
        ], "sample_count": 200}
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 2
        # Both should be in the same cluster (metric_regression:critical)
        cluster_ids = {w.cluster_id for w in weaknesses}
        assert len(cluster_ids) == 1

    def test_failure_instance_to_dict(self):
        fi = FailureInstance(
            failure_id="fail_001",
            category=FailureCategory.METRIC_REGRESSION,
            severity=FailureSeverity.HIGH,
            capability="math",
            metric_name="accuracy",
            baseline_value=0.9,
            current_value=0.7,
            threshold=0.855,
            evidence="regression detected",
        )
        d = fi.to_dict()
        assert d["failure_id"] == "fail_001"
        assert d["category"] == "metric_regression"
        assert d["severity"] == "high"


# ===========================================================================
# 6. Baseline lock
# ===========================================================================

class TestBaselineLock:
    """Test 6 — BaselineLock immutability and verification."""

    def test_lock_created_with_hash(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        assert lock.lock_hash != ""
        assert len(lock.lock_hash) == 32

    def test_lock_verify_passes(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        assert lock.verify() is True

    def test_lock_tamper_detected(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        original_hash = lock.lock_hash
        # Simulate tampering: change metrics but not lock_hash
        lock.metrics["accuracy"] = 0.99
        assert not lock.verify()  # hash mismatch
        assert lock.lock_hash == original_hash  # original hash unchanged

    def test_lock_freeze_returns_copy(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        frozen = lock.freeze()
        assert frozen.verify() is True
        assert frozen.lock_hash == lock.lock_hash

    def test_lock_round_trip(self):
        lock = BaselineLock(
            model_id="Qwen/Qwen3-4B",
            revision="abc123",
            metrics={"accuracy": 0.85, "math": 0.90},
            dataset_id="dataset_001",
        )
        d = lock.to_dict()
        restored = BaselineLock.from_dict(d)
        assert restored.verify() is True
        assert restored.model_id == lock.model_id
        assert restored.metrics == lock.metrics


# ===========================================================================
# 7. TrainingConfig
# ===========================================================================

class TestTrainingConfig:
    """Test 7 — TrainingConfig defaults and serialization."""

    def test_defaults(self):
        tc = TrainingConfig()
        assert tc.base_model == "Qwen/Qwen3-4B"
        assert tc.base_revision == "1cfa9a7208912126459214e8b04321603b3df60c"
        assert tc.adapter_mode == "lora"
        assert tc.load_bits == 16
        assert tc.epochs == 3.0
        assert tc.batch_size == 2
        assert tc.learning_rate == 2e-4
        assert tc.lr_scheduler == "cosine"
        assert tc.lora_rank == 16
        assert tc.lora_alpha == 32
        assert tc.lora_dropout == 0.05
        assert tc.max_seq_length == 2048
        assert tc.compute_resource == "cloud:kaggle"
        assert "q_proj" in tc.target_modules
        assert "o_proj" in tc.target_modules

    def test_to_dict_from_dict_round_trip(self):
        tc = TrainingConfig(epochs=5.0, batch_size=4, lora_rank=32)
        d = tc.to_dict()
        restored = TrainingConfig.from_dict(d)
        assert restored.epochs == 5.0
        assert restored.batch_size == 4
        assert restored.lora_rank == 32
        assert restored.base_model == tc.base_model


# ===========================================================================
# 8. CandidateArtifact state transitions
# ===========================================================================

class TestCandidateArtifact:
    """Test 8 — CandidateArtifact state transitions."""

    def test_candidate_starts_experimental(self):
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        assert c.status == CandidateStatus.EXPERIMENTAL.value

    def test_candidate_transition_experimental_to_staging(self):
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        c.transition(CandidateStatus.STAGING)
        assert c.status == CandidateStatus.STAGING.value

    def test_candidate_transition_experimental_to_staging_to_locked_to_evaluated(self):
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        c.transition(CandidateStatus.STAGING)
        c.transition(CandidateStatus.LOCKED)
        c.transition(CandidateStatus.EVALUATED)
        assert c.status == CandidateStatus.EVALUATED.value

    def test_candidate_transition_experimental_to_approved_invalid(self):
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        with pytest.raises(ValueError, match="Invalid CandidateStatus transition"):
            c.transition(CandidateStatus.APPROVED)

    def test_candidate_full_chain_to_approved(self):
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        chain = [
            CandidateStatus.STAGING,
            CandidateStatus.LOCKED,
            CandidateStatus.EVALUATED,
            CandidateStatus.VERIFIED,
            CandidateStatus.PROMOTION_REVIEW,
            CandidateStatus.APPROVED,
        ]
        for step in chain:
            c.transition(step)
        assert c.status == CandidateStatus.APPROVED.value

    def test_candidate_to_from_dict(self):
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
            artifact_uri="/path/to/artifact",
        )
        d = c.to_dict()
        restored = CandidateArtifact.from_dict(d)
        assert restored.artifact_id == c.artifact_id
        assert restored.status == c.status


# ===========================================================================
# 9. EvaluationMatrix
# ===========================================================================

class TestEvaluationMatrix:
    """Test 9 — EvaluationMatrix suite coverage."""

    def test_default_suites(self):
        matrix = EvaluationMatrix()
        all_suites = matrix.all_suites()
        assert "math_reasoning" in all_suites
        assert "code_generation" in all_suites
        assert "security" in all_suites
        assert "generation_quality" in all_suites

    def test_regression_safety_thresholds(self):
        matrix = EvaluationMatrix()
        assert matrix.min_regression_threshold == 0.02
        assert matrix.min_safety_threshold == 1.0

    def test_to_from_dict(self):
        matrix = EvaluationMatrix(
            target_suite="math_algebra",
            target_suite_id="math_algebra:v1",
        )
        d = matrix.to_dict()
        restored = EvaluationMatrix.from_dict(d)
        assert restored.target_suite == "math_algebra"
        assert restored.target_suite_id == "math_algebra:v1"


# ===========================================================================
# 10. ImprovementPolicy
# ===========================================================================

class TestImprovementPolicy:
    """Test 10 — ImprovementPolicy measurable criteria."""

    def test_defaults(self):
        p = ImprovementPolicy(target_capability="code", target_metric="accuracy")
        assert p.target_capability == "code"
        assert p.target_metric == "accuracy"
        assert p.minimum_improvement == 0.05
        assert p.maximum_allowed_regression == 0.02
        assert p.confidence_required == 0.95
        assert p.budget_usd_daily == 50.0
        assert p.risk_level == "medium"
        assert p.requires_manual_approval is True

    def test_to_from_dict(self):
        p = ImprovementPolicy(
            target_capability="math",
            target_metric="pass_rate",
            minimum_improvement=0.10,
            risk_level="high",
            requires_manual_approval=False,
            regression_protect_metrics=["safety_score"],
            safety_protect_metrics=["safety_score"],
        )
        d = p.to_dict()
        restored = ImprovementPolicy.from_dict(d)
        assert restored.minimum_improvement == 0.10
        assert restored.risk_level == "high"
        assert restored.requires_manual_approval is False
        assert "safety_score" in restored.regression_protect_metrics
        assert "safety_score" in restored.safety_protect_metrics


# ===========================================================================
# 11. AutonomyGuard
# ===========================================================================

class TestAutonomyGuard:
    """Test 11 — AutonomyGuard enforces autonomy boundary."""

    def test_system_policy_change_blocked(self):
        guard = AutonomyGuard(autonomy_level=1)
        allowed, reason = guard.check_intervention(
            InterventionType.SYSTEM_POLICY_CHANGE, "model:test"
        )
        assert not allowed
        assert "manual" in reason.lower() or "approval" in reason.lower()

    def test_system_policy_change_blocked_at_level_3(self):
        guard = AutonomyGuard(autonomy_level=3)
        allowed, reason = guard.check_intervention(
            InterventionType.SYSTEM_POLICY_CHANGE, "model:test"
        )
        assert not allowed

    def test_architecture_change_blocked(self):
        guard = AutonomyGuard(autonomy_level=3)
        allowed, reason = guard.check_intervention(
            InterventionType.ARCHITECTURE_CHANGE, "model:test"
        )
        assert not allowed

    def test_prompt_change_allowed(self):
        guard = AutonomyGuard(autonomy_level=1)
        allowed, reason = guard.check_intervention(
            InterventionType.PROMPT_CHANGE, "model:test"
        )
        assert allowed

    def test_training_change_allowed(self):
        guard = AutonomyGuard(autonomy_level=1)
        allowed, reason = guard.check_intervention(
            InterventionType.TRAINING_CHANGE, "model:test"
        )
        assert allowed

    def test_protected_path_blocked(self):
        guard = AutonomyGuard(autonomy_level=3)
        # PROMPT_CHANGE is normally allowed, but if target is a protected path
        # it should be blocked
        allowed, reason = guard.check_intervention(
            InterventionType.PROMPT_CHANGE, "jarvis_backend/core.py"
        )
        assert not allowed
        assert "protected" in reason.lower()

    def test_secret_in_target_blocked(self):
        guard = AutonomyGuard(autonomy_level=3)
        allowed, reason = guard.check_intervention(
            InterventionType.PROMPT_CHANGE, "config with api_key=123"
        )
        assert not allowed
        assert "secret" in reason.lower()

    def test_can_promote_requires_approved(self):
        guard = AutonomyGuard(autonomy_level=1)
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
        )
        # Candidate starts as EXPERIMENTAL, not APPROVED
        allowed, reason = guard.can_promote(c, promotion_approved=False)
        assert not allowed

    def test_can_promote_with_approval(self):
        guard = AutonomyGuard(autonomy_level=3)
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
            status=CandidateStatus.APPROVED.value,
        )
        allowed, reason = guard.can_promote(c, promotion_approved=True)
        assert allowed

    def test_check_artifact_no_secrets(self):
        guard = AutonomyGuard(autonomy_level=1)
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
            checksum="sha256:abc123def456",
        )
        allowed, reason = guard.check_artifact(c)
        assert allowed

    def test_check_artifact_detects_secret_field(self):
        guard = AutonomyGuard(autonomy_level=1)
        c = CandidateArtifact(
            artifact_id="art_001",
            improvement_id="impr_001",
            model_id="Qwen/Qwen3-4B",
            revision="rev1",
            training_config={"api_key": "sk-12345"},
        )
        allowed, reason = guard.check_artifact(c)
        assert not allowed
        assert "secret" in reason.lower() or "training_config" in reason.lower()


# ===========================================================================
# 12. Cycle persistence
# ===========================================================================

class TestCyclePersistence:
    """Test 12 — SelfImprovementCycle save/load persistence."""

    def test_save_and_load(self):
        cycle = SelfImprovementCycle.create(
            target_capability="math_reasoning",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc123",
            problem_statement="Accuracy improvement needed",
            mission_id="mission_001",
            owner="test_user",
        )
        cycle.transition(ImprovementStatus.ANALYZING)
        cycle.save()

        loaded = SelfImprovementCycle.load(cycle.improvement_id)
        assert loaded is not None
        assert loaded.status == ImprovementStatus.ANALYZING.value

    def test_list_all(self):
        c1 = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test1",
        )
        c2 = SelfImprovementCycle.create(
            target_capability="code", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test2",
        )
        all_cycles = SelfImprovementCycle.list_all()
        ids = [c.improvement_id for c in all_cycles]
        assert c1.improvement_id in ids
        assert c2.improvement_id in ids

    def test_list_by_status(self):
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.transition(ImprovementStatus.ANALYZING)
        cycle.save()
        found = SelfImprovementCycle.list_by_status(ImprovementStatus.ANALYZING.value)
        assert any(c.improvement_id == cycle.improvement_id for c in found)

    def test_list_by_capability(self):
        cycle = SelfImprovementCycle.create(
            target_capability="math_reasoning", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        found = SelfImprovementCycle.list_by_capability("math_reasoning")
        assert any(c.improvement_id == cycle.improvement_id for c in found)


# ===========================================================================
# 13. DatasetQualityGate
# ===========================================================================

class TestDatasetQualityGate:
    """Test 13 — DatasetQualityGate schema, dedup, safety checks."""

    def test_schema_validation_missing_field(self):
        gate = DatasetQualityGate()
        dataset = {
            "examples": [
                {"prompt": "q1", "response": "a1", "category": "math"},
                # Missing 'source' field
                {"prompt": "q2", "response": "a2", "category": "math", "source": "eval"},
            ],
        }
        result = gate.run_pipeline(dataset)
        assert not result["passed"]
        assert any("schema" in i for i in result["issues"])

    def test_deduplication(self):
        gate = DatasetQualityGate()
        examples = []
        for i in range(10):
            examples.append({
                "prompt": f"question_{i % 3}",  # only 3 unique prompts
                "response": f"answer_{i % 3}",
                "category": "math",
                "source": "eval",
                "provenance": ["test"],
            })
        result = gate.run_pipeline({"examples": examples})
        # 3 unique, but need >= MIN_SAMPLES (5) to pass
        assert result["deduplication_removed"] == 7
        assert result["example_count"] == 3

    def test_safety_check_blocks_harmful(self):
        gate = DatasetQualityGate()
        dataset = {
            "examples": [
                {"prompt": "how to make a bomb", "response": "instructions",
                 "category": "test", "source": "eval", "provenance": ["x"]},
                {"prompt": "q2", "response": "a2", "category": "test",
                 "source": "eval", "provenance": ["x"]},
                {"prompt": "q3", "response": "a3", "category": "test",
                 "source": "eval", "provenance": ["x"]},
                {"prompt": "q4", "response": "a4", "category": "test",
                 "source": "eval", "provenance": ["x"]},
                {"prompt": "q5", "response": "a5", "category": "test",
                 "source": "eval", "provenance": ["x"]},
            ],
        }
        result = gate.run_pipeline(dataset)
        assert any("safety" in i for i in result["issues"])
        assert not result["passed"]

    def test_valid_dataset_passes(self):
        gate = DatasetQualityGate()
        examples = []
        for i in range(6):
            examples.append({
                "prompt": f"question {i}",
                "response": f"answer {i}",
                "category": "math",
                "source": "eval",
                "provenance": ["test"],
            })
        result = gate.run_pipeline({"examples": examples})
        assert result["passed"]
        assert result["example_count"] == 6
        assert result["deduplication_removed"] == 0

    def test_schema_and_dedup_constants(self):
        gate = DatasetQualityGate()
        assert gate.SCHEMA_FIELDS == ("prompt", "response", "category", "source")
        assert gate.MIN_SAMPLES == 5
        assert gate.MAX_SAMPLES == 50000


# ===========================================================================
# 14. evaluate_improvement (comparison + regression)
# ===========================================================================

class TestEvaluateImprovement:
    """Test 14 — SelfImprovementCycle.evaluate_improvement."""

    def _setup_cycle_with_metrics(self):
        cycle = _make_cycle()
        cycle.baseline_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.85, "higher_is_better": True,
                 "evaluation_version": "math_v1",
                 "provenance": ["baseline_lock_established"]},
            ],
        }
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.90, "higher_is_better": True,
                 "evaluation_version": "math_v1",
                 "provenance": ["eval:math_v1"]},
            ],
        }
        lock = BaselineLock(
            model_id=cycle.baseline_model,
            revision=cycle.baseline_revision,
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        cycle.set_baseline_lock(lock)
        return cycle

    def test_improvement_verdict(self):
        cycle = self._setup_cycle_with_metrics()
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
            minimum_improvement=0.01,
            regression_protect_metrics=["accuracy"],
        )
        result = cycle.evaluate_improvement(policy)
        assert result.verdict == "improved"
        assert result.target_metric_meets_threshold
        assert not result.regression_detected

    def test_regression_detected(self):
        cycle = self._setup_cycle_with_metrics()
        # Candidate is worse than baseline
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.70, "higher_is_better": True,
                 "evaluation_version": "math_v1",
                 "provenance": ["eval:math_v1"]},
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
        assert len(result.regressions) > 0

    def test_no_change_verdict(self):
        cycle = self._setup_cycle_with_metrics()
        # Candidate is same as baseline
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.85, "higher_is_better": True,
                 "evaluation_version": "math_v1",
                 "provenance": ["eval:math_v1"]},
            ],
        }
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
            minimum_improvement=0.05,
            regression_protect_metrics=["accuracy"],
        )
        result = cycle.evaluate_improvement(policy)
        assert result.verdict == "no_change"

    def test_improvement_result_fields(self):
        cycle = self._setup_cycle_with_metrics()
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
            minimum_improvement=0.01,
        )
        result = cycle.evaluate_improvement(policy)
        assert hasattr(result, "baseline_results")
        assert hasattr(result, "candidate_results")
        assert hasattr(result, "comparison")
        assert hasattr(result, "regression_detected")
        assert hasattr(result, "verdict")
        assert hasattr(result, "confidence")


# ===========================================================================
# 15. Critique cycle integration
# ===========================================================================

class TestCritiqueCycle:
    """Test 15 — Critic integration via critique_cycle."""

    def test_critique_returns_findings_for_incomplete_cycle(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = _make_cycle()
        cycle.save()
        findings = orch.critique_cycle(cycle)
        assert len(findings) >= 2  # policy + baseline missing
        categories = [f.get("category") for f in findings]
        assert "policy" in categories
        assert "baseline" in categories

    def test_critique_no_critical_when_complete(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = _make_cycle()
        tc = TrainingConfig()
        cycle.set_training_config(tc)
        cycle.change_type = "training_change"
        lock = BaselineLock(
            model_id=cycle.baseline_model,
            revision=cycle.baseline_revision,
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        cycle.set_baseline_lock(lock)
        cycle.save()

        findings = orch.critique_cycle(cycle)
        critical = [f for f in findings if f.get("severity") == "critical"]
        assert len(critical) == 0


# ===========================================================================
# 16. Evaluate candidate (no crash with None candidate)
# ===========================================================================

class TestEvaluateCandidate:
    """Test 16 — evaluate_candidate handles missing candidate gracefully."""

    def test_no_candidate_no_crash(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = _make_cycle()
        cycle.save()
        matrix = EvaluationMatrix()
        result = orch.evaluate_candidate(cycle, matrix)
        assert isinstance(result, dict)
        assert "metrics" in result
        assert "provenance" in result
        assert "evaluation_version" in result

    def test_returns_evaluated_at(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = _make_cycle()
        cycle.save()
        matrix = EvaluationMatrix()
        result = orch.evaluate_candidate(cycle, matrix)
        assert "evaluated_at" in result


# ===========================================================================
# 17. Deployment modes
# ===========================================================================

class TestDeploymentModes:
    """Test 17 — DeploymentMode enum and deployment restrictions."""

    def test_deployment_modes(self):
        expected = {"shadow", "canary", "blockbox", "production"}
        actual = {m.value for m in DeploymentMode}
        assert actual == expected

    def test_shadow_deployment_creates_deployment(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = _make_cycle()
        # Create and approve candidate
        candidate = CandidateArtifact(
            artifact_id="art_001",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="cand_rev_001",
            status=CandidateStatus.APPROVED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        deployment = orch.deploy_candidate(cycle, mode=DeploymentMode.SHADOW.value)
        assert deployment is not None
        assert deployment.mode == DeploymentMode.SHADOW.value
        assert deployment.rolled_back is False

    def test_production_deployment_blocked_at_low_autonomy(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = _make_cycle()
        candidate = CandidateArtifact(
            artifact_id="art_001",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="cand_rev_001",
            status=CandidateStatus.APPROVED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        with pytest.raises(PermissionError, match="Production deployment requires manual"):
            orch.deploy_candidate(cycle, mode=DeploymentMode.PRODUCTION.value)

    def test_production_deployment_allowed_at_high_autonomy(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = _make_cycle()
        candidate = CandidateArtifact(
            artifact_id="art_001",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="cand_rev_001",
            status=CandidateStatus.APPROVED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        deployment = orch.deploy_candidate(cycle, mode=DeploymentMode.PRODUCTION.value)
        assert deployment.mode == DeploymentMode.PRODUCTION.value
        assert deployment.traffic_fraction == 1.0


# ===========================================================================
# 18. Rollback
# ===========================================================================

class TestRollback:
    """Test 18 — rollback_deployment sets rolled_back flag."""

    def test_rollback_sets_flag(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = _make_cycle()
        candidate = CandidateArtifact(
            artifact_id="art_001",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="cand_rev_001",
            status=CandidateStatus.APPROVED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        # Deploy
        orch.deploy_candidate(cycle, mode=DeploymentMode.SHADOW.value)
        assert cycle.deployment is not None
        assert cycle.deployment.get("rolled_back") is False
        # Rollback
        result = orch.rollback_deployment(cycle, reason="post-deployment regression")
        assert result is True
        assert cycle.deployment["rolled_back"] is True
        assert cycle.deployment["rollback_reason"] == "post-deployment regression"
        assert cycle.status == ImprovementStatus.ROLLED_BACK.value

    def test_rollback_without_deployment_returns_false(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = _make_cycle()
        cycle.save()
        result = orch.rollback_deployment(cycle, reason="test")
        assert result is False


# ===========================================================================
# 19. Budget check
# ===========================================================================

class TestBudgetCheck:
    """Test 19 — check_budget delegates to BudgetManager."""

    def test_budget_check_returns_tuple(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = SelfImprovementCycle.create(
            target_capability="code",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc",
            problem_statement="test",
            mission_id="m1",
            owner="test_user",
        )
        cycle.save()
        policy = ImprovementPolicy(
            target_capability="code",
            target_metric="accuracy",
            budget_usd_daily=50.0,
        )
        ok, message = orch.check_budget(cycle, policy)
        assert isinstance(ok, bool)
        assert isinstance(message, str)


# ===========================================================================
# 20. LearningMemory
# ===========================================================================

class TestLearningMemory:
    """Test 20 — LearningMemory stores lessons."""

    def test_add_and_get_lesson(self):
        memory = LearningMemory()
        lesson = Lesson(
            lesson_id="lesson_001",
            improvement_id="impr_001",
            weakness_id="weak_001",
            hypothesis_id="hyp_001",
            intervention_type="training_change",
            outcome="success",
            what_worked="LoRA training improved accuracy by 8%",
            what_failed="",
            key_learning="More epochs helped but caused overfitting",
        )
        memory.add_lesson(lesson)
        lessons = memory.get_lessons()
        assert len(lessons) >= 1
        assert any(l.lesson_id == "lesson_001" for l in lessons)

    def test_get_lessons_for_capability(self):
        memory = LearningMemory()
        lesson = Lesson(
            lesson_id="lesson_cap_001",
            improvement_id="impr_001",
            weakness_id="weak_001",
            hypothesis_id="hyp_001",
            intervention_type="training_change",
            outcome="success",
            what_worked="Improved math accuracy",
            what_failed="",
            key_learning="Training on math data improved math capability",
            metrics_improved={"math_accuracy": 0.10},
        )
        memory.add_lesson(lesson)
        relevant = memory.get_lessons_for_capability("math")
        assert any(l.lesson_id == "lesson_cap_001" for l in relevant)


# ===========================================================================
# 21. ImprovementGraph
# ===========================================================================

class TestImprovementGraph:
    """Test 21 — ImprovementGraph DAG operations."""

    def test_add_node(self):
        graph = ImprovementGraph()
        node = GraphNode(
            improvement_id="impr_001",
            weakness_id="weak_001",
            hypothesis_id="hyp_001",
            intervention_type="training_change",
            outcome="improved",
        )
        graph.add_node(node)
        # Verify by loading the store
        store = get_store("improvements")
        data = store.load()
        assert "impr_001" in data["graph"]["nodes"]
        assert data["graph"]["nodes"]["impr_001"]["outcome"] == "improved"

    def test_add_edge(self):
        graph = ImprovementGraph()
        node1 = GraphNode(
            improvement_id="impr_001",
            weakness_id="weak_001",
            hypothesis_id="hyp_001",
            intervention_type="training_change",
            outcome="improved",
        )
        node2 = GraphNode(
            improvement_id="impr_002",
            weakness_id="weak_002",
            hypothesis_id="hyp_002",
            intervention_type="dataset_change",
            outcome="pending",
        )
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_edge("impr_001", "impr_002", "follows_from")
        store = get_store("improvements")
        data = store.load()
        edges = data["graph"]["edges"]
        assert len(edges) >= 1
        assert edges[-1]["source"] == "impr_001"
        assert edges[-1]["target"] == "impr_002"


# ===========================================================================
# 22. run_improvement_cycle blocked path
# ===========================================================================

class TestRunImprovementCycle:
    """Test 22 — run_improvement_cycle respects autonomy boundary."""

    def test_blocked_at_approval_step(self):
        """At autonomy_level=1, the approval step blocks and the cycle stops."""
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = SelfImprovementCycle.create(
            target_capability="math_reasoning",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc123",
            problem_statement="Improve math accuracy",
            mission_id="mission_001",
            owner="test_user",
        )
        cycle.save()
        # Set training config
        tc = TrainingConfig()
        cycle.set_training_config(tc)
        cycle.training_config["base_model"] = "Qwen/Qwen3-4B"
        cycle.save()
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
        )
        matrix = EvaluationMatrix()
        result = orch.run_improvement_cycle(cycle, policy, matrix, tc)
        # Should have stopped at await_approval
        assert "steps" in result
        step_names = [s["step"] for s in result["steps"]]
        assert "await_approval" in step_names
        assert result["blocked_step"] == "05_await_approval"
        # Cycle should be BLOCKED
        assert cycle.status == ImprovementStatus.BLOCKED.value

    def test_full_cycle_at_high_autonomy(self):
        """At autonomy_level=3, the cycle runs through all steps."""
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="math_reasoning",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc123",
            problem_statement="Improve math accuracy",
            mission_id="mission_001",
            owner="test_user",
        )
        cycle.save()
        tc = TrainingConfig()
        cycle.set_training_config(tc)
        cycle.save()
        policy = ImprovementPolicy(
            target_capability="math_reasoning",
            target_metric="accuracy",
        )
        matrix = EvaluationMatrix()
        result = orch.run_improvement_cycle(cycle, policy, matrix, tc)
        # Should have run multiple steps
        assert len(result["steps"]) > 5
        step_names = [s["step"] for s in result["steps"]]
        # Should have reached at least await_approval (not blocked at level 3)
        assert "await_approval" in step_names
        # Should not be blocked
        assert "blocked_step" not in result
