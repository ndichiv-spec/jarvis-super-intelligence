"""Phase 11 — Experiment model tests.

Validates the Experiment dataclass, ExperimentDesign, Metric,
ExperimentComparison, ReproducibilityManifest, ExperimentBudget,
ExperimentLifecycle, and persistence.
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
    ExperimentBudget,
    ExperimentComparison,
    ExperimentDesign,
    ExperimentEvent,
    ExperimentLifecycle,
    ExperimentStatus,
    ExperimentTransitionError,
    Metric,
    ReproducibilityManifest,
    _short_uuid,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _reset_stores():
    get_store("experiments").reset()
    yield
    get_store("experiments").reset()


@pytest.fixture()
def design():
    return ExperimentDesign(
        question="Does additional mathematical reasoning data improve JARVIS accuracy?",
        hypothesis="Adding high-quality verified reasoning examples improves benchmark accuracy",
        independent_variables=["training_data_size", "training_method"],
        dependent_variables=["math_accuracy", "val_ppl"],
        controls=["random_seed", "model_architecture", "eval_suite_version"],
        datasets=["math_train_v1", "eval_bench_v1"],
        models=["baseline_model", "candidate_model"],
        parameters={"learning_rate": 0.0001, "batch_size": 32},
        expected_outcomes={"math_accuracy_delta": "+5%"},
        success_criteria=["math_accuracy > 0.85 and no regression on code"],
        failure_criteria=["math_accuracy < 0.80", "val_ppl > 20"],
        evaluation_method="math_reasoning suite v1.0",
        compute_requirements={"gpu_required": True, "min_gpu_memory_gb": 8.0,
                              "task_type": "training", "max_cost_class": "paid_gpu"},
    )


@pytest.fixture()
def exp(design):
    e = Experiment.create(
        mission_id="miss_test_001",
        name="math-reasoning-improvement",
        objective=design.question,
        owner="test_user",
        design=design,
    )
    return e


# --------------------------------------------------------------------------- #
# ExperimentStatus enum
# --------------------------------------------------------------------------- #
def test_all_expected_statuses_exist():
    expected = {"designed", "ready", "running", "analyzing", "verifying",
                "completed", "failed", "cancelled", "inconclusive", "blocked"}
    actual = {s.value for s in ExperimentStatus}
    assert expected == actual


def test_terminal_statuses():
    lifecycle = ExperimentLifecycle()
    terminal = lifecycle.terminal_states()
    assert "completed" in terminal
    assert "failed" in terminal
    assert "cancelled" in terminal
    assert "inconclusive" in terminal
    # Non-terminal states should NOT be terminal
    assert "designed" not in terminal
    assert "running" not in terminal
    assert "blocked" not in terminal


# --------------------------------------------------------------------------- #
# ExperimentDesign
# --------------------------------------------------------------------------- #
def test_design_to_from_dict_roundtrip(design):
    d = design.to_dict()
    assert d["question"] == design.question
    assert d["hypothesis"] == design.hypothesis
    assert d["independent_variables"] == ["training_data_size", "training_method"]
    assert d["controls"] == ["random_seed", "model_architecture", "eval_suite_version"]
    assert d["compute_requirements"]["gpu_required"] is True

    reloaded = ExperimentDesign.from_dict(d)
    assert reloaded.question == design.question
    assert reloaded.independent_variables == design.independent_variables
    assert reloaded.compute_requirements["gpu_required"] is True


def test_design_from_dict_empty():
    d = ExperimentDesign.from_dict({})
    assert d.question == ""
    assert d.independent_variables == []
    assert d.compute_requirements == {}


# --------------------------------------------------------------------------- #
# Metric
# --------------------------------------------------------------------------- #
def test_metric_to_from_dict():
    m = Metric(
        name="math_accuracy", value=0.87, unit="ratio",
        higher_is_better=True, sample_count=50,
        evaluation_version="math_reasoning:v1",
        provenance=["eval_run_001", "artifact_001"],
    )
    d = m.to_dict()
    assert d["name"] == "math_accuracy"
    assert d["value"] == 0.87
    assert d["unit"] == "ratio"
    assert d["higher_is_better"] is True
    assert d["sample_count"] == 50
    assert d["evaluation_version"] == "math_reasoning:v1"
    assert d["provenance"] == ["eval_run_001", "artifact_001"]

    r = Metric.from_dict(d)
    assert r.name == "math_accuracy"
    assert r.value == 0.87
    assert r.higher_is_better is True
    assert r.sample_count == 50


def test_metric_from_dict_minimal():
    m = Metric.from_dict({"name": "loss", "value": 2.5})
    assert m.name == "loss"
    assert m.value == 2.5
    assert m.higher_is_better is True  # default
    assert m.sample_count == 0


# --------------------------------------------------------------------------- #
# ExperimentComparison
# --------------------------------------------------------------------------- #
def test_comparison_from_metrics():
    baseline = Metric(name="math_accuracy", value=0.80, unit="ratio",
                      sample_count=50, evaluation_version="suite:v1")
    candidate = Metric(name="math_accuracy", value=0.85, unit="ratio",
                       sample_count=50, evaluation_version="suite:v1")
    comp = ExperimentComparison.from_metrics(baseline, candidate)
    assert comp is not None
    assert comp.metric_name == "math_accuracy"
    assert comp.baseline_value == pytest.approx(0.80)
    assert comp.candidate_value == pytest.approx(0.85)
    assert comp.absolute_difference == pytest.approx(0.05)
    assert comp.relative_difference == pytest.approx(0.0625)
    assert comp.sample_count == 100
    assert comp.evaluation_version == "suite:v1"


def test_comparison_from_metrics_different_names():
    baseline = Metric(name="acc", value=0.80, sample_count=10, evaluation_version="v1")
    candidate = Metric(name="loss", value=0.85, sample_count=10, evaluation_version="v1")
    assert ExperimentComparison.from_metrics(baseline, candidate) is None


def test_comparison_from_metrics_different_versions():
    baseline = Metric(name="acc", value=0.80, sample_count=10, evaluation_version="v1")
    candidate = Metric(name="acc", value=0.85, sample_count=10, evaluation_version="v2")
    assert ExperimentComparison.from_metrics(baseline, candidate) is None


def test_comparison_from_metrics_zero_sample():
    baseline = Metric(name="acc", value=0.80, sample_count=0, evaluation_version="v1")
    candidate = Metric(name="acc", value=0.85, sample_count=10, evaluation_version="v1")
    assert ExperimentComparison.from_metrics(baseline, candidate) is None


def test_comparison_to_from_dict():
    comp = ExperimentComparison(
        metric_name="math_accuracy", baseline_value=0.80, candidate_value=0.85,
        absolute_difference=0.05, relative_difference=0.0625,
        sample_count=100, evaluation_version="suite:v1",
    )
    d = comp.to_dict()
    r = ExperimentComparison.from_dict(d)
    assert r.metric_name == "math_accuracy"
    assert r.baseline_value == pytest.approx(0.80)
    assert r.relative_difference == pytest.approx(0.0625)


# --------------------------------------------------------------------------- #
# ReproducibilityManifest
# --------------------------------------------------------------------------- #
def test_manifest_to_from_dict():
    m = ReproducibilityManifest(
        code_revision="abc123",
        dataset_versions=[{"dataset_id": "ds1", "version": "v1", "hash": "h1"}],
        model_versions=[{"model": "m1", "revision": "r1"}],
        configuration={"lr": 0.001},
        hyperparameters={"batch_size": 32},
        evaluation_suite="math_reasoning:v1",
        compute_resource="cloud:nvidia",
        environment={"python": "3.11"},
        random_seed=42,
        software_versions={"torch": "2.0"},
        artifacts=["a1", "a2"],
        metrics=[{"name": "acc", "value": 0.85}],
    )
    d = m.to_dict()
    assert d["code_revision"] == "abc123"
    assert d["dataset_versions"][0]["dataset_id"] == "ds1"
    assert d["random_seed"] == 42
    assert d["software_versions"]["torch"] == "2.0"
    assert d["manifest_id"].startswith("manifest_")

    r = ReproducibilityManifest.from_dict(d)
    assert r.code_revision == "abc123"
    assert r.random_seed == 42
    assert r.metrics[0]["name"] == "acc"
    assert r.manifest_id == m.manifest_id


# --------------------------------------------------------------------------- #
# ExperimentBudget
# --------------------------------------------------------------------------- #
def test_budget_to_from_dict():
    b = ExperimentBudget(max_cost_usd=10.0, max_seconds=600, max_jobs=3, max_steps=50)
    d = b.to_dict()
    assert d["max_cost_usd"] == 10.0
    assert d["max_seconds"] == 600
    r = ExperimentBudget.from_dict(d)
    assert r.max_cost_usd == 10.0
    assert r.max_steps == 50


# --------------------------------------------------------------------------- #
# ExperimentLifecycle
# --------------------------------------------------------------------------- #
def test_lifecycle_can_transition_designed_to_ready():
    lc = ExperimentLifecycle()
    assert lc.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.READY)


def test_lifecycle_can_transition_ready_to_running():
    lc = ExperimentLifecycle()
    assert lc.can_transition(ExperimentStatus.READY, ExperimentStatus.RUNNING)


def test_lifecycle_can_transition_running_to_analyzing():
    lc = ExperimentLifecycle()
    assert lc.can_transition(ExperimentStatus.RUNNING, ExperimentStatus.ANALYZING)


def test_lifecycle_can_transition_analyzing_to_verifying():
    lc = ExperimentLifecycle()
    assert lc.can_transition(ExperimentStatus.ANALYZING, ExperimentStatus.VERIFYING)


def test_lifecycle_can_transition_verifying_to_completed():
    lc = ExperimentLifecycle()
    assert lc.can_transition(ExperimentStatus.VERIFYING, ExperimentStatus.COMPLETED)


def test_lifecycle_cannot_transition_designed_to_completed():
    lc = ExperimentLifecycle()
    assert not lc.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.COMPLETED)


def test_lifecycle_cannot_transition_to_terminal():
    lc = ExperimentLifecycle()
    assert not lc.can_transition(ExperimentStatus.COMPLETED, ExperimentStatus.RUNNING)
    assert not lc.can_transition(ExperimentStatus.FAILED, ExperimentStatus.READY)


def test_lifecycle_can_transition_str():
    lc = ExperimentLifecycle()
    assert lc.can_transition_str("designed", "ready")
    assert not lc.can_transition_str("designed", "completed")


def test_lifecycle_validate_transition_requires_baseline(exp):
    lc = ExperimentLifecycle()
    # ANALYZING → VERIFYING should require baseline; exp has no baseline
    with pytest.raises(ExperimentTransitionError, match="baseline"):
        lc.validate_transition(ExperimentStatus.ANALYZING, ExperimentStatus.VERIFYING,
                               experiment=exp)


def test_lifecycle_valid_transitions_designed():
    lc = ExperimentLifecycle()
    transitions = lc.valid_transitions  # property, not method
    assert "ready" in transitions["designed"]
    assert "blocked" in transitions["designed"]
    assert "cancelled" in transitions["designed"]


def test_lifecycle_valid_transitions_blocked_to_ready():
    lc = ExperimentLifecycle()
    transitions = lc.valid_transitions
    assert "ready" in transitions["blocked"]
    assert "designed" in transitions["blocked"]


# --------------------------------------------------------------------------- #
# Experiment persistence
# --------------------------------------------------------------------------- #
def test_experiment_create_sets_defaults(exp):
    assert exp.experiment_id.startswith("exp_")
    assert exp.status == ExperimentStatus.DESIGNED.value
    assert exp.objective == "Does additional mathematical reasoning data improve JARVIS accuracy?"
    assert exp.hypothesis != ""
    assert exp.design != {}  # design was stored from the design fixture


def test_experiment_save_and_load(exp):
    exp.save()
    reloaded = Experiment.load(exp.experiment_id)
    assert reloaded is not None
    assert reloaded.experiment_id == exp.experiment_id
    assert reloaded.name == exp.name
    assert reloaded.mission_id == exp.mission_id
    assert reloaded.status == exp.status


def test_experiment_load_nonexistent():
    assert Experiment.load("nonexistent_exp_id") is None


def test_experiment_list_all():
    e1 = Experiment.create(mission_id="m1", name="exp1", owner="test")
    e1.save()
    e2 = Experiment.create(mission_id="m2", name="exp2", owner="test")
    e2.save()
    all_exps = Experiment.list_all()
    ids = [e.experiment_id for e in all_exps]
    assert e1.experiment_id in ids
    assert e2.experiment_id in ids


def test_experiment_list_by_mission():
    e1 = Experiment.create(mission_id="miss_001", name="exp1", owner="test")
    e1.save()
    e2 = Experiment.create(mission_id="miss_001", name="exp2", owner="test")
    e2.save()
    e3 = Experiment.create(mission_id="miss_002", name="exp3", owner="test")
    e3.save()
    m1_exps = Experiment.list_by_mission("miss_001")
    assert len(m1_exps) == 2
    assert all(e.mission_id == "miss_001" for e in m1_exps)


# --------------------------------------------------------------------------- #
# Experiment transition
# --------------------------------------------------------------------------- #
def test_transition_designed_to_ready(exp):
    exp.transition(ExperimentStatus.READY, actor="test", notes="Resources ready")
    assert exp.status == ExperimentStatus.READY.value
    events = exp.event_timeline_list()
    assert any(e["kind"] == "transition" and e["to"] == "ready" for e in events)


def test_transition_illegal_designed_to_completed(exp):
    with pytest.raises(ExperimentTransitionError):
        exp.transition(ExperimentStatus.COMPLETED, actor="test")


def test_transition_to_cancelled_from_designed(exp):
    exp.transition(ExperimentStatus.CANCELLED, actor="test", notes="Cancelled")
    assert exp.status == ExperimentStatus.CANCELLED.value


def test_transition_from_terminal_rejected(exp):
    # First get to a terminal state
    exp.transition(ExperimentStatus.CANCELLED, actor="test", notes="Cancelled")
    assert exp.status == ExperimentStatus.CANCELLED.value
    with pytest.raises(ExperimentTransitionError):
        exp.transition(ExperimentStatus.READY, actor="test")


def test_transition_blocked_to_ready(exp):
    exp.transition(ExperimentStatus.BLOCKED, actor="test", notes="No GPU")
    assert exp.status == ExperimentStatus.BLOCKED.value
    exp.transition(ExperimentStatus.READY, actor="test", notes="GPU now available")
    assert exp.status == ExperimentStatus.READY.value


def test_is_terminal_property(exp):
    # is_terminal is a property, not a method
    assert exp.is_terminal is False
    exp.transition(ExperimentStatus.CANCELLED, actor="test")
    assert exp.is_terminal is True


def test_status_enum_property(exp):
    # status_enum is a property, not a method
    assert exp.status_enum == ExperimentStatus.DESIGNED
    exp.transition(ExperimentStatus.READY, actor="test")
    assert exp.status_enum == ExperimentStatus.READY


# --------------------------------------------------------------------------- #
# Full lifecycle chain
# --------------------------------------------------------------------------- #
def test_full_lifecycle_chain(exp):
    """DESIGNED → READY → RUNNING → ANALYZING → VERIFYING → COMPLETED."""
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    assert exp.status == ExperimentStatus.READY.value

    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    assert exp.status == ExperimentStatus.RUNNING.value

    exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator")
    assert exp.status == ExperimentStatus.ANALYZING.value

    # Cannot go to VERIFYING without baseline
    with pytest.raises(ExperimentTransitionError, match="baseline"):
        exp.transition(ExperimentStatus.VERIFYING, actor="orchestrator")


def test_full_lifecycle_chain_with_baseline(exp):
    """DESIGNED → READY → RUNNING → ANALYZING → (set baseline) → VERIFYING → COMPLETED."""
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator")

    # Set baseline
    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    exp.set_baseline(model="base_v1", revision="r1", metrics=[m],
                     compute="local:control-node")

    exp.transition(ExperimentStatus.VERIFYING, actor="orchestrator")
    assert exp.status == ExperimentStatus.VERIFYING.value

    exp.transition(ExperimentStatus.COMPLETED, actor="orchestrator")
    assert exp.status == ExperimentStatus.COMPLETED.value


# --------------------------------------------------------------------------- #
# Baseline / Candidate
# --------------------------------------------------------------------------- #
def test_set_baseline(exp):
    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    exp.set_baseline(model="base_v1", revision="r1", metrics=[m],
                     compute="local:control-node")
    assert exp.baseline is not None
    assert exp.baseline["model"] == "base_v1"
    assert exp.baseline["revision"] == "r1"
    assert len(exp.baseline["metrics"]) == 1
    assert exp.baseline["compute"] == "local:control-node"
    assert len(exp.provenance) > 0


def test_add_candidate(exp):
    baseline_m = Metric(name="math_accuracy", value=0.80, sample_count=50,
                        evaluation_version="math_reasoning:v1")
    exp.set_baseline(model="base_v1", revision="r1", metrics=[baseline_m],
                     compute="local:control-node")

    candidate_m = Metric(name="math_accuracy", value=0.85, sample_count=50,
                         evaluation_version="math_reasoning:v1")
    idx = exp.add_candidate(model="cand_v1", revision="r2", metrics=[candidate_m],
                            compute="cloud:nvidia")
    assert idx == 0
    assert exp.candidates[0]["model"] == "cand_v1"
    assert len(exp.candidates) == 1
    assert len(exp.comparisons) == 1  # comparison computed from metrics


def test_add_candidate_without_baseline(exp):
    """Adding a candidate without a baseline does not raise but produces no comparisons."""
    m = Metric(name="math_accuracy", value=0.85, sample_count=50,
               evaluation_version="math_reasoning:v1")
    idx = exp.add_candidate(model="cand_v1", revision="r2", metrics=[m],
                            compute="cloud:nvidia")
    assert idx == 0
    assert len(exp.candidates) == 1
    assert len(exp.comparisons) == 0  # no baseline → no comparisons


def test_compute_comparison_method(exp):
    baseline_m = [Metric(name="math_accuracy", value=0.80, sample_count=50,
                         evaluation_version="math_reasoning:v1")]
    candidate_m = [Metric(name="math_accuracy", value=0.85, sample_count=50,
                          evaluation_version="math_reasoning:v1")]
    comps = exp.compute_comparison(baseline_m, candidate_m)
    assert len(comps) == 1
    assert comps[0].metric_name == "math_accuracy"
    assert comps[0].baseline_value == pytest.approx(0.80)


def test_compute_comparison_no_matching_metrics(exp):
    baseline_m = [Metric(name="acc", value=0.80, sample_count=10, evaluation_version="v1")]
    candidate_m = [Metric(name="loss", value=0.85, sample_count=10, evaluation_version="v1")]
    comps = exp.compute_comparison(baseline_m, candidate_m)
    assert len(comps) == 0


# --------------------------------------------------------------------------- #
# ExperimentEvent
# --------------------------------------------------------------------------- #
def test_event_to_from_dict():
    e = ExperimentEvent(
        event_id="evt_001", experiment_id="exp_001",
        at="2024-01-01T00:00:00", kind="transition",
        status_from="designed", status_to="ready", detail="Resources selected",
        actor="test",
    )
    d = e.to_dict()
    assert d["event_id"] == "evt_001"
    assert d["kind"] == "transition"
    assert d["from"] == "designed"
    assert d["to"] == "ready"

    r = ExperimentEvent.from_dict(d)
    assert r.kind == "transition"
    assert r.status_from == "designed"


# --------------------------------------------------------------------------- #
# No-fabrication: experiment must not have fake metrics
# --------------------------------------------------------------------------- #
def test_experiment_has_no_fabricated_metrics(exp):
    """An experiment with no real evaluation should have no non-zero metrics
    with zero sample_count."""
    assert exp.baseline is None
    assert exp.candidates == []
    assert exp.comparisons == []


# --------------------------------------------------------------------------- #
# Short UUID
# --------------------------------------------------------------------------- #
def test_short_uuid_unique():
    a = _short_uuid()
    b = _short_uuid()
    assert a != b
    assert len(a) == 12
    assert len(b) == 12
