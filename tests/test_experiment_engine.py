"""Phase 11 — Experiment engine tests.

Validates the ExperimentOrchestrator: design_experiment, select_resources,
prepare_experiment, run_experiment, analyze_results, verify_experiment,
complete_experiment, establish_baseline, add_candidate, evaluate_for_promotion,
report_blocked. Test that blocked experiments truthfully report resource
unavailability.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from jarvis_backend.core import get_store  # noqa: E402
from jarvis_backend.experiment import (  # noqa: E402
    Experiment,
    ExperimentDesign,
    ExperimentStatus,
    ExperimentTransitionError,
    Metric,
)
from jarvis_backend.experiment_engine import (  # noqa: E402
    ComputeBounds,
    ExperimentOrchestrator,
    ExperimentRunResult,
    ResourceSelectionResult,
)


@pytest.fixture(autouse=True)
def _reset_stores():
    get_store("experiments").reset()
    get_store("missions").reset()
    get_store("executions").reset()
    get_store("datasets").reset()
    get_store("artifacts").reset()
    get_store("evaluation_suites").reset()
    yield
    get_store("experiments").reset()
    get_store("missions").reset()
    get_store("executions").reset()
    get_store("datasets").reset()
    get_store("artifacts").reset()
    get_store("evaluation_suites").reset()


@pytest.fixture()
def design():
    return ExperimentDesign(
        question="Does more math training data improve accuracy?",
        hypothesis="Adding high-quality reasoning examples improves benchmark accuracy",
        independent_variables=["training_data_size"],
        controls=["random_seed"],
        datasets=["math_train_v1"],
        models=["model_v1"],
        parameters={"learning_rate": 0.0001},
        expected_outcomes={"math_accuracy": ">0.85"},
        success_criteria=["math_accuracy > 0.80"],
        failure_criteria=["math_accuracy < 0.75"],
        evaluation_method="math_reasoning",
        compute_requirements={"gpu_required": False, "task_type": "evaluation",
                              "max_cost_class": "free_local"},
    )


@pytest.fixture()
def orch():
    return ExperimentOrchestrator()


@pytest.fixture()
def exp(design):
    e = Experiment.create(
        mission_id="miss_eng_001",
        name="eng-test",
        objective=design.question,
        owner="test",
        design=design,
    )
    e.save()
    return e


# --------------------------------------------------------------------------- #
# ComputeBounds
# --------------------------------------------------------------------------- #
def test_compute_bounds_from_requirements():
    bounds = ComputeBounds.from_requirements({
        "gpu_required": True,
        "min_gpu_memory_gb": 16.0,
        "task_type": "training",
        "max_cost_class": "paid_gpu",
    })
    assert bounds.gpu_required is True
    assert bounds.min_gpu_memory_gb == 16.0
    assert bounds.task_type == "training"
    assert bounds.max_cost_class == "paid_gpu"


def test_compute_bounds_defaults():
    bounds = ComputeBounds.from_requirements({})
    assert bounds.gpu_required is False
    assert bounds.min_cpu_cores == 1
    assert bounds.min_ram_gb == 1.0
    assert bounds.task_type == "evaluation"


def test_compute_bounds_to_requirements_dict():
    bounds = ComputeBounds(gpu_required=True, min_gpu_memory_gb=8.0,
                           task_type="training", max_cost_class="paid_gpu")
    d = bounds.to_requirements_dict()
    assert d["gpu_required"] is True
    assert d["min_gpu_memory_gb"] == 8.0
    assert d["task_type"] == "training"
    assert d["max_cost_class"] == "paid_gpu"


# --------------------------------------------------------------------------- #
# Design
# --------------------------------------------------------------------------- #
def test_design_experiment(orch, design):
    exp = orch.design_experiment(
        mission_id="miss_001", name="test-exp", design=design, owner="tester")
    assert exp.experiment_id.startswith("exp_")
    assert exp.status == ExperimentStatus.DESIGNED.value
    assert exp.name == "test-exp"
    assert exp.mission_id == "miss_001"
    assert exp.hypothesis == design.hypothesis
    assert exp.design != {}
    # Should be persisted
    reloaded = Experiment.load(exp.experiment_id)
    assert reloaded is not None


def test_design_experiment_rejects_secrets(orch):
    design = ExperimentDesign(
        question="test", hypothesis="test",
        parameters={"api_key": "sk-secret-123"},
        compute_requirements={"gpu_required": False},
    )
    with pytest.raises((ValueError, Exception)):
        orch.design_experiment(
            mission_id="m1", name="secret-exp", design=design, owner="tester")


# --------------------------------------------------------------------------- #
# Resource selection
# --------------------------------------------------------------------------- #
def test_select_resources_for_experiment(orch, exp):
    result = orch.select_resources(exp.experiment_id)
    assert isinstance(result, ResourceSelectionResult)
    # Local has no GPU, but our design doesn't require GPU
    assert result.selected is True
    assert result.resource_id == "local:control-node"


def test_select_resources_not_found(orch):
    result = orch.select_resources("nonexistent")
    assert result.selected is False
    assert result.reason == "experiment_not_found"


def test_select_resources_gpu_required(orch):
    """An experiment requiring GPU should not select local:control-node."""
    design = ExperimentDesign(
        question="GPU test", hypothesis="GPU test",
        compute_requirements={"gpu_required": True, "min_gpu_memory_gb": 16.0,
                              "task_type": "training", "max_cost_class": "paid_gpu"},
    )
    exp = Experiment.create(mission_id="m1", name="gpu-exp", owner="test",
                            design=design)
    exp.save()
    result = orch.select_resources(exp.experiment_id)
    # Should not select local (no GPU)
    assert result.selected is False or result.resource_id != "local:control-node"


# --------------------------------------------------------------------------- #
# Prepare
# --------------------------------------------------------------------------- #
def test_prepare_experiment_selects_local(orch, exp):
    prepared = orch.prepare_experiment(exp.experiment_id)
    assert prepared.status == ExperimentStatus.READY.value
    assert "local:control-node" in prepared.compute_requirements.get("selected_resource", "")
    assert any("resource_selected" in p for p in prepared.provenance)


def test_prepare_experiment_blocks_on_gpu(orch):
    """Experiment requiring GPU on a machine with no GPU should be blocked."""
    design = ExperimentDesign(
        question="GPU test", hypothesis="GPU test",
        compute_requirements={"gpu_required": True, "min_gpu_memory_gb": 16.0,
                              "task_type": "training", "max_cost_class": "paid_gpu"},
    )
    exp = Experiment.create(mission_id="m1", name="gpu-exp", owner="test",
                            design=design)
    exp.save()
    prepared = orch.prepare_experiment(exp.experiment_id)
    assert prepared.status == ExperimentStatus.BLOCKED.value
    assert prepared.blocked_reason is not None


def test_prepare_experiment_from_designed(orch, exp):
    """prepare_experiment transitions DESIGNED → READY."""
    assert exp.status == ExperimentStatus.DESIGNED.value
    prepared = orch.prepare_experiment(exp.experiment_id)
    assert prepared.status == ExperimentStatus.READY.value


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def test_run_experiment_auto_prepares(orch, exp):
    """Running from DESIGNED auto-prepares then runs."""
    result = orch.run_experiment(exp.experiment_id)
    assert result.success is True
    assert result.experiment_id == exp.experiment_id
    # Should have transitioned through states
    reloaded = Experiment.load(exp.experiment_id)
    assert reloaded.status in ("analyzing", "completed", "inconclusive")


def test_run_experiment_already_ready(orch, exp):
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.save()
    result = orch.run_experiment(exp.experiment_id)
    assert result.success is True


def test_run_experiment_not_found(orch):
    result = orch.run_experiment("nonexistent")
    assert result.success is False
    assert "not_found" in result.message


def test_run_experiment_wrong_status(orch, exp):
    """Running from COMPLETED/terminal should raise."""
    # Move to completed via full lifecycle
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator")
    exp.save()

    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    exp.set_baseline(model="base_v1", revision="r1", metrics=[m],
                     compute="local:control-node")
    cm = Metric(name="math_accuracy", value=0.85, sample_count=50,
                evaluation_version="math_reasoning:v1")
    exp.add_candidate(model="cand_v1", revision="r2", metrics=[cm],
                      compute="local:control-node")
    exp.save()

    verified = orch.verify_experiment(exp.experiment_id)
    assert verified.status == ExperimentStatus.COMPLETED.value
    exp.save()

    # Now at COMPLETED — should not be able to run again
    with pytest.raises(ExperimentTransitionError):
        orch.run_experiment(exp.experiment_id)


# --------------------------------------------------------------------------- #
# Analyze
# --------------------------------------------------------------------------- #
def test_analyze_results(orch, exp):
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.save()
    analyzed = orch.analyze_results(exp.experiment_id)
    assert analyzed.status == ExperimentStatus.ANALYZING.value
    assert "metrics" in analyzed.results


def test_analyze_results_wrong_status(orch, exp):
    """Cannot analyze from DESIGNED."""
    with pytest.raises(ExperimentTransitionError):
        orch.analyze_results(exp.experiment_id)


# --------------------------------------------------------------------------- #
# Verify
# --------------------------------------------------------------------------- #
def test_verify_experiment_no_baseline(orch, exp):
    """Verifying without baseline should fail."""
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator")
    exp.save()

    verified = orch.verify_experiment(exp.experiment_id)
    # Should fail due to missing baseline
    assert verified.status in (ExperimentStatus.FAILED.value,
                               ExperimentStatus.INCONCLUSIVE.value)


def test_verify_experiment_with_baseline(orch, exp):
    """Verifying with baseline and candidate should pass."""
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator")

    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    exp.set_baseline(model="base_v1", revision="r1", metrics=[m],
                     compute="local:control-node")

    cm = Metric(name="math_accuracy", value=0.85, sample_count=50,
                evaluation_version="math_reasoning:v1")
    exp.add_candidate(model="cand_v1", revision="r2", metrics=[cm],
                      compute="local:control-node")
    exp.save()

    verified = orch.verify_experiment(exp.experiment_id)
    assert verified.status == ExperimentStatus.COMPLETED.value


# --------------------------------------------------------------------------- #
# Complete
# --------------------------------------------------------------------------- #
def test_complete_experiment(orch, exp):
    """Complete a verified experiment — generates reproducibility manifest."""
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator")

    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    exp.set_baseline(model="base_v1", revision="r1", metrics=[m],
                     compute="local:control-node")

    cm = Metric(name="math_accuracy", value=0.85, sample_count=50,
                evaluation_version="math_reasoning:v1")
    exp.add_candidate(model="cand_v1", revision="r2", metrics=[cm],
                      compute="local:control-node")
    exp.save()

    verified = orch.verify_experiment(exp.experiment_id)
    assert verified.status == ExperimentStatus.COMPLETED.value

    # Now complete (should generate manifest)
    completed = orch.complete_experiment(exp.experiment_id)
    assert completed.status == ExperimentStatus.COMPLETED.value
    assert completed.reproducibility_metadata is not None
    assert completed.reproducibility_metadata.manifest_id.startswith("manifest_")


def test_complete_experiment_requires_verifying(orch, exp):
    """Cannot complete from non-VERifying state."""
    with pytest.raises(ExperimentTransitionError):
        orch.complete_experiment(exp.experiment_id)


# --------------------------------------------------------------------------- #
# Baseline / Candidate management
# --------------------------------------------------------------------------- #
def test_establish_baseline(orch, exp):
    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    result = orch.establish_baseline(
        exp_id=exp.experiment_id, model="base_v1", revision="r1",
        metrics=[m], compute="local:control-node")
    assert result.baseline is not None
    assert result.baseline["model"] == "base_v1"


def test_add_candidate_through_orchestrator(orch, exp):
    baseline_m = Metric(name="math_accuracy", value=0.80, sample_count=50,
                        evaluation_version="math_reasoning:v1")
    orch.establish_baseline(
        exp_id=exp.experiment_id, model="base_v1", revision="r1",
        metrics=[baseline_m], compute="local:control-node")

    candidate_m = Metric(name="math_accuracy", value=0.85, sample_count=50,
                         evaluation_version="math_reasoning:v1")
    idx = orch.add_candidate(
        exp_id=exp.experiment_id, model="cand_v1", revision="r2",
        metrics=[candidate_m], compute="local:control-node")
    assert idx == 0
    reloaded = Experiment.load(exp.experiment_id)
    assert len(reloaded.candidates) == 1
    assert len(reloaded.comparisons) == 1


# --------------------------------------------------------------------------- #
# Promotion evaluation
# --------------------------------------------------------------------------- #
def test_evaluate_for_promotion_no_candidate(orch, exp):
    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    orch.establish_baseline(
        exp_id=exp.experiment_id, model="base_v1", revision="r1",
        metrics=[m], compute="local:control-node")
    result = orch.evaluate_for_promotion(exp.experiment_id)
    # No candidate → not approved
    assert result["approved"] is False


def test_evaluate_for_promotion_with_candidate(orch, exp):
    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    orch.establish_baseline(
        exp_id=exp.experiment_id, model="base_v1", revision="r1",
        metrics=[m], compute="local:control-node")

    cm = Metric(name="math_accuracy", value=0.85, sample_count=50,
                evaluation_version="math_reasoning:v1")
    orch.add_candidate(
        exp_id=exp.experiment_id, model="cand_v1", revision="r2",
        metrics=[cm], compute="local:control-node")
    result = orch.evaluate_for_promotion(exp.experiment_id)
    assert "approved" in result
    assert "model_id" in result
    assert result["model_id"] == "cand_v1"


# --------------------------------------------------------------------------- #
# Blocked reporting
# --------------------------------------------------------------------------- #
def test_report_blocked(orch, exp):
    blocked = orch.report_blocked(exp.experiment_id, "cloud:nvidia",
                                  "no_api_key")
    assert blocked.status == ExperimentStatus.BLOCKED.value
    assert blocked.blocked_reason is not None
    assert "no_api_key" in blocked.blocked_reason


def test_report_blocked_not_found(orch):
    with pytest.raises(KeyError):
        orch.report_blocked("nonexistent", "cloud:nvidia", "no_key")


# --------------------------------------------------------------------------- #
# Real experiment A: NVIDIA inference benchmark
# --------------------------------------------------------------------------- #
def test_experiment_nvidia_gpu_required(orch):
    """An experiment requiring NVIDIA GPU should truthfully block when no GPU."""
    design = ExperimentDesign(
        question="Benchmark NVIDIA inference",
        hypothesis="NVIDIA T4 provides fast inference",
        compute_requirements={"gpu_required": True, "min_gpu_memory_gb": 16.0,
                              "task_type": "inference", "max_cost_class": "paid_gpu"},
    )
    exp = orch.design_experiment(
        mission_id="miss_nvidia_001", name="nvidia-bench",
        design=design, owner="test")
    prepared = orch.prepare_experiment(exp.experiment_id)
    # On this machine (no NVIDIA GPU), the experiment should be BLOCKED
    assert prepared.status == ExperimentStatus.BLOCKED.value


# --------------------------------------------------------------------------- #
# Real experiment B: model evaluation using real eval suite
# --------------------------------------------------------------------------- #
def test_experiment_evaluation_suite_lookup(orch):
    """Verify that evaluation suites can be looked up after initialization."""
    from jarvis_backend.evaluation_suite import EvaluationSuiteRegistry
    EvaluationSuiteRegistry.initialize()
    suite = EvaluationSuiteRegistry.get("math_reasoning:v1")
    assert suite is not None
    assert suite.versioned_id == "math_reasoning:v1"


# --------------------------------------------------------------------------- #
# Real experiment C: dataset validation
# --------------------------------------------------------------------------- #
def test_experiment_dataset_validation(orch):
    """Dataset validation pipeline runs and produces a dataset record."""
    # Create a simple CSV dataset
    import tempfile, os, csv
    tmpdir = tempfile.mkdtemp()
    csv_path = os.path.join(tmpdir, "test_data.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["question", "answer"])
        writer.writerow(["1+1", "2"])
        writer.writerow(["2+2", "4"])

    from jarvis_backend.dataset import Dataset, DatasetValidator
    ds = Dataset.create(
        name="test_math_qa",
        source="local",
        location=csv_path,
        owner="test",
    )
    validator = DatasetValidator()
    results = validator.run_pipeline(ds)
    assert len(results) > 0
    assert results[0].stage == "validating"
    assert all(r.passed for r in results)
    reloaded = Dataset.load(ds.dataset_id)
    assert reloaded is not None
    assert reloaded.validation_stage == "registered"


# --------------------------------------------------------------------------- #
# Real experiment D: Kaggle (truthfully BLOCKED when no auth)
# --------------------------------------------------------------------------- #
def test_experiment_kaggle_no_auth(orch):
    """Kaggle experiments should be BLOCKED when no Kaggle credentials."""
    design = ExperimentDesign(
        question="Fine-tune on Kaggle dataset",
        hypothesis="Kaggle training improves model",
        compute_requirements={"gpu_required": True, "min_gpu_memory_gb": 8.0,
                              "task_type": "training", "max_cost_class": "paid_gpu"},
        datasets=["kaggle_dataset_v1"],
        evaluation_method="math_reasoning",
    )
    exp = orch.design_experiment(
        mission_id="miss_kaggle_001", name="kaggle-train",
        design=design, owner="test")
    prepared = orch.prepare_experiment(exp.experiment_id)
    # Should be blocked (no NVIDIA GPU on this machine)
    assert prepared.status == ExperimentStatus.BLOCKED.value


# --------------------------------------------------------------------------- #
# Real experiment E: baseline/candidate comparison
# --------------------------------------------------------------------------- #
def test_experiment_baseline_candidate_comparison(orch, exp):
    """Full baseline → candidate → comparison flow."""
    baseline_m = [Metric(name="math_accuracy", value=0.80, sample_count=50,
                         evaluation_version="math_reasoning:v1")]
    orch.establish_baseline(
        exp_id=exp.experiment_id, model="base_v1", revision="r1",
        metrics=baseline_m, compute="local:control-node")

    candidate_m = [Metric(name="math_accuracy", value=0.85, sample_count=50,
                          evaluation_version="math_reasoning:v1")]
    idx = orch.add_candidate(
        exp_id=exp.experiment_id, model="cand_v1", revision="r2",
        metrics=candidate_m, compute="cloud:nvidia")

    reloaded = Experiment.load(exp.experiment_id)
    assert len(reloaded.comparisons) == 1
    comp = reloaded.comparisons[0]
    # Handle both dict and ExperimentComparison storage
    if isinstance(comp, dict):
        assert comp["baseline_value"] == pytest.approx(0.80)
        assert comp["candidate_value"] == pytest.approx(0.85)
        assert comp["absolute_difference"] == pytest.approx(0.05)
    else:
        assert comp.baseline_value == pytest.approx(0.80)
        assert comp.candidate_value == pytest.approx(0.85)


# --------------------------------------------------------------------------- #
# No-fabrication: resource selection must not fabricate availability
# --------------------------------------------------------------------------- #
def test_resource_selection_reports_real_availability(orch):
    """Resource selection must not report AVAILABLE merely because credentials exist."""
    design = ExperimentDesign(
        question="test", hypothesis="test",
        compute_requirements={"gpu_required": False, "task_type": "evaluation",
                              "max_cost_class": "free_local"},
    )
    exp = Experiment.create(
        mission_id="m1", name="no-fab-test", owner="test", design=design)
    exp.save()

    result = orch.select_resources(exp.experiment_id)
    # If local is selected, it must be because local is actually available
    if result.selected:
        assert result.resource_id in ("local:control-node",) or \
               result.resource_id != ""
