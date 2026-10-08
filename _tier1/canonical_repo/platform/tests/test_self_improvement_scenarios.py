"""Phase 12 — Validation scenarios A-J for the Self-Improvement Engine.

Each scenario tests a real end-to-end step of the improvement lifecycle:

  A. Weakness detection from baseline/candidate comparison
  B. Hypothesis formation from a detected weakness
  C. Dataset improvement loop (failure extraction → quality gate)
  D. Baseline establishment and lock verification
  E. Training job submission via JobRegistry (test mode)
  F. Candidate evaluation against evaluation matrix
  G. Promotion evaluation (no-candidate path)
  H. Rejection verification
  I. Deployment policy (shadow allowed, production blocked at low autonomy)
  J. Lesson generation from a completed cycle
"""

import pytest

from jarvis_backend.core import get_store, now_iso
from jarvis_backend.self_improvement import (
    AutonomyGuard,
    BaselineLock,
    CandidateArtifact,
    CandidateStatus,
    DeploymentMode,
    EvaluationMatrix,
    FailureCategory,
    FailureSeverity,
    ImprovementPolicy,
    ImprovementResult,
    ImprovementStatus,
    InterventionType,
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
# Scenario A — Weakness detection
# ===========================================================================

class TestScenarioA_WeaknessDetection:
    """Scenario A: Detect a weakness from baseline vs candidate regression."""

    def test_weakness_detected_from_regression(self):
        detector = WeaknessDetector()
        baseline = {
            "metrics": [
                {"name": "accuracy", "value": 0.88, "higher_is_better": True,
                 "evaluation_version": "math_v1",
                 "provenance": ["baseline_lock"]},
            ],
        }
        candidate = {
            "metrics": [
                {"name": "accuracy", "value": 0.72, "higher_is_better": True,
                 "evaluation_version": "math_v1",
                 "provenance": ["eval:math_v1"]},
            ],
            "sample_count": 200,
        }
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 1
        w = weaknesses[0]
        assert w.target_capability == "math_v1"
        assert w.failures[0].category == FailureCategory.METRIC_REGRESSION
        assert w.failures[0].baseline_value == 0.88
        assert w.failures[0].current_value == 0.72
        # Severity should be high or critical (>15% drop)
        assert w.severity in (FailureSeverity.HIGH, FailureSeverity.CRITICAL)


# ===========================================================================
# Scenario B — Hypothesis formation
# ===========================================================================

class TestScenarioB_HypothesisFormation:
    """Scenario B: Form a hypothesis from a detected weakness."""

    def test_hypothesis_formed_from_weakness(self):
        detector = WeaknessDetector()
        baseline = {"metrics": [
            {"name": "accuracy", "value": 0.88, "higher_is_better": True,
             "evaluation_version": "math_v1"},
        ]}
        candidate = {"metrics": [
            {"name": "accuracy", "value": 0.72, "higher_is_better": True,
             "evaluation_version": "math_v1"},
        ]}
        weaknesses = detector.detect_from_results(baseline, candidate, min_regression=0.05)
        assert len(weaknesses) == 1

        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="math_v1",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc123",
            problem_statement="Math accuracy regression detected",
            mission_id="m1",
            owner="test_user",
        )
        cycle.save()
        hypothesis = orch.form_hypothesis(cycle, weaknesses[0])
        assert hypothesis is not None
        assert hypothesis.hypothesis_id.startswith("hyp_")
        assert len(hypothesis.statement) > 0
        assert hypothesis.target_metric is not None
        cycle.save()
        assert len(cycle.hypotheses) > 0


# ===========================================================================
# Scenario C — Dataset improvement loop
# ===========================================================================

class TestScenarioC_DatasetImprovement:
    """Scenario C: Run dataset improvement on failure examples."""

    def test_dataset_loop_extract_and_validate(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="code_generation",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc123",
            problem_statement="Code generation failures",
        )
        cycle.save()
        evaluation_results = {
            "failures": [
                {"prompt": "Write a function to sort a list", "response": "Incomplete",
                 "expected": "def sort_list(l): return sorted(l)", "category": "code_gen"},
                {"prompt": "Implement binary search", "response": "Incorrect logic",
                 "expected": "def binary_search(arr, x): ...", "category": "code_gen"},
                {"prompt": "Create a hash map in Python", "response": "Syntax error",
                 "expected": "class HashMap: ...", "category": "code_gen"},
                {"prompt": "Write a recursive factorial", "response": "Wrong output",
                 "expected": "def fact(n): return 1 if n<=1 else n*fact(n-1)",
                 "category": "code_gen"},
                {"prompt": "Implement a queue", "response": "Missing methods",
                 "expected": "class Queue: ...", "category": "code_gen"},
            ],
        }
        result = orch.prepare_dataset(cycle, evaluation_results)
        assert result is not None
        assert hasattr(result, "step")
        assert result.step == "prepare_dataset"

    def test_dataset_quality_gate_validates(self):
        gate = DatasetQualityGate()
        examples = [
            {"prompt": f"q{i}", "response": f"a{i}", "category": "test",
             "source": "eval", "provenance": ["test"]}
            for i in range(6)
        ]
        result = gate.run_pipeline({"examples": examples})
        assert result["passed"]
        assert result["example_count"] == 6


# ===========================================================================
# Scenario D — Baseline establishment
# ===========================================================================

class TestScenarioD_BaselineEstablishment:
    """Scenario D: Establish and lock baseline for comparison."""

    def test_baseline_lock_established(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="math_reasoning",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="1cfa9a7208912126459214e8b04321603b3df60c",
            problem_statement="Baseline needed",
        )
        cycle.save()
        lock = orch.establish_baseline(
            cycle,
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc123",
            baseline_metrics={"accuracy": 0.88, "math": 0.85},
        )
        assert lock is not None
        assert lock.model_id == "Qwen/Qwen3-4B"
        assert lock.metrics["accuracy"] == 0.88
        assert lock.lock_hash != ""
        assert lock.verify()
        assert cycle.get_baseline_lock() is not None
        assert cycle.get_baseline_lock().lock_hash != ""

    def test_baseline_lock_immutable_after_establishment(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        lock = orch.establish_baseline(
            cycle, "Qwen/Qwen3-4B", "abc123", {"accuracy": 0.90}
        )
        original_hash = lock.lock_hash
        # Verify immutability
        assert lock.verify()
        # Try to tamper
        cycle.dataset["baseline_lock"]["metrics"]["accuracy"] = 0.99
        cycle.save()
        loaded = SelfImprovementCycle.load(cycle.improvement_id)
        lock_loaded = loaded.get_baseline_lock()
        assert not lock_loaded.verify()
        assert lock_loaded.lock_hash == original_hash


# ===========================================================================
# Scenario E — Kaggle training (test mode)
# ===========================================================================

class TestScenarioE_TrainingJobSubmission:
    """Scenario E: Submit training job via JobRegistry in test mode."""

    def test_training_job_submitted(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = SelfImprovementCycle.create(
            target_capability="code_repair",
            baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc123",
            problem_statement="Improve code repair",
        )
        cycle.save()
        tc = TrainingConfig()
        cycle.set_training_config(tc)
        # Transition through the required states before training
        cycle.transition(ImprovementStatus.ANALYZING)
        cycle.transition(ImprovementStatus.HYPOTHESIS_FORMED)
        cycle.transition(ImprovementStatus.DESIGNED)
        cycle.transition(ImprovementStatus.AWAITING_APPROVAL)
        cycle.transition(ImprovementStatus.DATA_PREPARATION)
        cycle.change_type = "training_change"
        cycle.save()
        result = orch.train_candidate(cycle, training_config=tc)
        assert result is not None
        assert hasattr(result, "step")
        assert result.step == "train_candidate"
        assert result.success
        # Job should have been created
        assert result.details.get("job_id") is not None or result.details.get("candidate_artifact_id") is not None

    def test_training_config_defaults_to_kaggle(self):
        tc = TrainingConfig()
        assert tc.compute_resource == "cloud:kaggle"
        assert tc.adapter_mode == "lora"
        assert tc.base_model == "Qwen/Qwen3-4B"


# ===========================================================================
# Scenario F — Candidate evaluation
# ===========================================================================

class TestScenarioF_CandidateEvaluation:
    """Scenario F: Evaluate candidate against evaluation matrix."""

    def test_candidate_evaluated_no_crash(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        matrix = EvaluationMatrix()
        result = orch.evaluate_candidate(cycle, matrix)
        assert isinstance(result, dict)
        assert "metrics" in result
        assert "provenance" in result
        assert result["evaluation_version"] is not None

    def test_candidate_evaluation_includes_provenance(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="code", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        matrix = EvaluationMatrix()
        result = orch.evaluate_candidate(cycle, matrix)
        assert len(result["provenance"]) > 0


# ===========================================================================
# Scenario G — Promotion evaluation (no-candidate path)
# ===========================================================================

class TestScenarioG_PromotionEvaluation:
    """Scenario G: PromotionGate evaluation rejects unverified candidates."""

    def test_promotion_rejected_without_candidate(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        policy = ImprovementPolicy(
            target_capability="math", target_metric="accuracy"
        )
        result = orch.evaluate_for_promotion(cycle, policy)
        assert isinstance(result, dict)
        assert result["outcome"] == "rejected"
        assert "no_candidate_artifact" in result["reason"]


# ===========================================================================
# Scenario H — Rejection verification
# ===========================================================================

class TestScenarioH_RejectionVerification:
    """Scenario H: A rejected candidate stays rejected and cannot be deployed."""

    def test_rejected_candidate_cannot_deploy(self):
        orch = SelfImprovementOrchestrator(autonomy_level=3)
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        candidate = CandidateArtifact(
            artifact_id="art_rejected",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="cand1",
            status=CandidateStatus.REJECTED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        with pytest.raises(ValueError, match="must be APPROVED"):
            orch.deploy_candidate(cycle, mode=DeploymentMode.SHADOW.value)


# ===========================================================================
# Scenario I — Deployment policy
# ===========================================================================

class TestScenarioI_DeploymentPolicy:
    """Scenario I: Shadow deployment allowed; production blocked at low autonomy."""

    def test_shadow_deployment_at_level_1(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        candidate = CandidateArtifact(
            artifact_id="art_approved",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="cand1",
            status=CandidateStatus.APPROVED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        deployment = orch.deploy_candidate(cycle, mode=DeploymentMode.SHADOW.value)
        assert deployment is not None
        assert deployment.mode == DeploymentMode.SHADOW.value
        assert not deployment.rolled_back

    def test_production_blocked_at_level_1(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        candidate = CandidateArtifact(
            artifact_id="art_approved",
            improvement_id=cycle.improvement_id,
            model_id="Qwen/Qwen3-4B",
            revision="cand1",
            status=CandidateStatus.APPROVED.value,
        )
        cycle.set_candidate(candidate)
        cycle.save()
        with pytest.raises(PermissionError, match="Production deployment requires manual"):
            orch.deploy_candidate(cycle, mode=DeploymentMode.PRODUCTION.value)


# ===========================================================================
# Scenario J — Lesson generation
# ===========================================================================

class TestScenarioJ_LessonGeneration:
    """Scenario J: Generate a lesson from a completed improvement cycle."""

    def test_lesson_generated(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        # Set up enough state for lesson generation
        cycle.target_capability = "math_reasoning"
        cycle.change_type = "training_change"
        lock = BaselineLock(
            model_id=cycle.baseline_model,
            revision=cycle.baseline_revision,
            metrics={"accuracy": 0.85},
            dataset_id="dataset_001",
        )
        cycle.set_baseline_lock(lock)
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.90, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        cycle.baseline_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.85, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        cycle.save()

        policy = ImprovementPolicy(
            target_capability="math", target_metric="accuracy"
        )
        result = cycle.evaluate_improvement(policy)
        lesson = orch.generate_lesson(cycle, result)
        assert lesson is not None
        assert lesson.lesson_id.startswith("lesson_")
        assert lesson.intervention_type == "training_change"
        assert lesson.outcome in ("success", "failure")
        assert len(lesson.key_learning) > 0

    def test_lesson_persisted_to_learning_memory(self):
        orch = SelfImprovementOrchestrator(autonomy_level=1)
        cycle = SelfImprovementCycle.create(
            target_capability="math", baseline_model="Qwen/Qwen3-4B",
            baseline_revision="abc", problem_statement="test",
        )
        cycle.save()
        lock = BaselineLock(
            model_id=cycle.baseline_model,
            revision=cycle.baseline_revision,
            metrics={"accuracy": 0.90},
            dataset_id="dataset_001",
        )
        cycle.set_baseline_lock(lock)
        cycle.candidate_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.85, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        cycle.baseline_results = {
            "metrics": [
                {"name": "accuracy", "value": 0.90, "higher_is_better": True,
                 "evaluation_version": "math_v1"},
            ],
        }
        cycle.save()
        policy = ImprovementPolicy(target_capability="math", target_metric="accuracy")
        result = cycle.evaluate_improvement(policy)
        lesson = orch.generate_lesson(cycle, result)
        orch.learning_memory.add_lesson(lesson)
        lessons = orch.learning_memory.get_lessons()
        assert any(l.lesson_id == lesson.lesson_id for l in lessons)
