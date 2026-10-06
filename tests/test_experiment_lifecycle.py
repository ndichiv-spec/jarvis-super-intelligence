"""Phase 11 — Experiment lifecycle state machine tests.

Tests the ExperimentLifecycle state machine and Experiment.transition()
integration, ensuring all legal and illegal transitions behave correctly.
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
    ExperimentLifecycle,
    ExperimentStatus,
    ExperimentTransitionError,
)


@pytest.fixture(autouse=True)
def _reset_stores():
    get_store("experiments").reset()
    yield
    get_store("experiments").reset()


@pytest.fixture()
def lifecycle():
    return ExperimentLifecycle()


@pytest.fixture()
def exp():
    from jarvis_backend.experiment import ExperimentDesign
    design = ExperimentDesign(
        question="Test question",
        hypothesis="Test hypothesis",
        independent_variables=["x"],
        controls=["seed"],
        datasets=["ds1"],
        models=["model1"],
        evaluation_method="test_suite",
        compute_requirements={"gpu_required": False, "task_type": "evaluation"},
    )
    e = Experiment.create(
        mission_id="m1",
        name="lifecycle_test",
        objective=design.question,
        owner="test",
        design=design,
    )
    return e


# --------------------------------------------------------------------------- #
# Legal transition matrix
# --------------------------------------------------------------------------- #
def test_designed_to_ready(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.READY)


def test_designed_to_blocked(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.BLOCKED)


def test_designed_to_cancelled(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.CANCELLED)


def test_designed_to_failed(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.FAILED)


def test_ready_to_running(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.READY, ExperimentStatus.RUNNING)


def test_ready_to_blocked(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.READY, ExperimentStatus.BLOCKED)


def test_running_to_analyzing(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.RUNNING, ExperimentStatus.ANALYZING)


def test_running_to_failed(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.RUNNING, ExperimentStatus.FAILED)


def test_analyzing_to_verifying(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.ANALYZING, ExperimentStatus.VERIFYING)


def test_analyzing_to_inconclusive(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.ANALYZING, ExperimentStatus.INCONCLUSIVE)


def test_verifying_to_completed(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.VERIFYING, ExperimentStatus.COMPLETED)


def test_verifying_to_failed(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.VERIFYING, ExperimentStatus.FAILED)


def test_blocked_to_ready(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.BLOCKED, ExperimentStatus.READY)


def test_blocked_to_designed(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.BLOCKED, ExperimentStatus.DESIGNED)


def test_blocked_to_cancelled(lifecycle):
    assert lifecycle.can_transition(ExperimentStatus.BLOCKED, ExperimentStatus.CANCELLED)


# --------------------------------------------------------------------------- #
# Illegal transitions
# --------------------------------------------------------------------------- #
def test_designed_to_running_illegal(lifecycle):
    assert not lifecycle.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.RUNNING)


def test_designed_to_analyzing_illegal(lifecycle):
    assert not lifecycle.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.ANALYZING)


def test_designed_to_verifying_illegal(lifecycle):
    assert not lifecycle.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.VERIFYING)


def test_designed_to_completed_illegal(lifecycle):
    assert not lifecycle.can_transition(ExperimentStatus.DESIGNED, ExperimentStatus.COMPLETED)


def test_ready_to_completed_illegal(lifecycle):
    assert not lifecycle.can_transition(ExperimentStatus.READY, ExperimentStatus.COMPLETED)


def test_running_to_completed_illegal(lifecycle):
    assert not lifecycle.can_transition(ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED)


def test_completed_to_anything_illegal(lifecycle):
    for target in ExperimentStatus:
        if target == ExperimentStatus.COMPLETED:
            continue
        assert not lifecycle.can_transition(ExperimentStatus.COMPLETED, target)


def test_failed_to_anything_illegal(lifecycle):
    for target in ExperimentStatus:
        if target == ExperimentStatus.FAILED:
            continue
        assert not lifecycle.can_transition(ExperimentStatus.FAILED, target)


def test_cancelled_to_anything_illegal(lifecycle):
    for target in ExperimentStatus:
        if target == ExperimentStatus.CANCELLED:
            continue
        assert not lifecycle.can_transition(ExperimentStatus.CANCELLED, target)


# --------------------------------------------------------------------------- #
# Terminal status detection
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status,expected", [
    (ExperimentStatus.COMPLETED, True),
    (ExperimentStatus.FAILED, True),
    (ExperimentStatus.CANCELLED, True),
    (ExperimentStatus.INCONCLUSIVE, True),
    (ExperimentStatus.DESIGNED, False),
    (ExperimentStatus.READY, False),
    (ExperimentStatus.RUNNING, False),
    (ExperimentStatus.ANALYZING, False),
    (ExperimentStatus.VERIFYING, False),
    (ExperimentStatus.BLOCKED, False),
])
def test_is_terminal(lifecycle, status, expected):
    assert lifecycle.is_terminal(status) == expected


# --------------------------------------------------------------------------- #
# String-based transition checks
# --------------------------------------------------------------------------- #
def test_can_transition_str_valid(lifecycle):
    assert lifecycle.can_transition_str("designed", "ready") is True
    assert lifecycle.can_transition_str("designed", "blocked") is True


def test_can_transition_str_invalid(lifecycle):
    assert lifecycle.can_transition_str("designed", "completed") is False
    assert lifecycle.can_transition_str("completed", "running") is False


def test_can_transition_str_invalid_status(lifecycle):
    assert lifecycle.can_transition_str("nonexistent", "ready") is False


# --------------------------------------------------------------------------- #
# validate_transition preconditions
# --------------------------------------------------------------------------- #
def test_validate_transition_design_required(lifecycle, exp):
    """READY requires a design — exp has design from design fixture,
    but an empty-design experiment should fail."""
    exp_no_design = Experiment.create(mission_id="m", name="no_design", owner="test")
    with pytest.raises(ExperimentTransitionError, match="design"):
        lifecycle.validate_transition(ExperimentStatus.DESIGNED, ExperimentStatus.READY,
                                     experiment=exp_no_design)


def test_validate_transition_design_satisfied(lifecycle, exp):
    """Transition should pass when design is present."""
    # Should not raise
    lifecycle.validate_transition(ExperimentStatus.DESIGNED, ExperimentStatus.READY,
                                 experiment=exp)


def test_validate_transition_baseline_required(lifecycle, exp):
    """VERIFYING requires a baseline."""
    with pytest.raises(ExperimentTransitionError, match="baseline"):
        lifecycle.validate_transition(ExperimentStatus.ANALYZING,
                                     ExperimentStatus.VERIFYING,
                                     experiment=exp)


def test_validate_transition_baseline_satisfied(lifecycle):
    """Transition to VERIFYING should pass when baseline is set."""
    from jarvis_backend.experiment import Metric
    exp = Experiment.create(mission_id="m", name="with_baseline", owner="test")
    m = Metric(name="acc", value=0.80, sample_count=50, evaluation_version="v1")
    exp.set_baseline(model="base", revision="r1", metrics=[m], compute="local")
    # Should not raise
    lifecycle.validate_transition(ExperimentStatus.ANALYZING,
                                 ExperimentStatus.VERIFYING,
                                 experiment=exp)


def test_validate_transition_illegal_raises(lifecycle, exp):
    with pytest.raises(ExperimentTransitionError, match="Illegal"):
        lifecycle.validate_transition(ExperimentStatus.DESIGNED,
                                     ExperimentStatus.COMPLETED,
                                     experiment=exp)


# --------------------------------------------------------------------------- #
# Full lifecycle path through states
# --------------------------------------------------------------------------- #
def test_full_lifecycle_no_baseline_blocks_verifying(exp):
    """DESIGNED → READY → RUNNING → ANALYZING → blocked at VERIFYING (no baseline)."""
    exp.transition(ExperimentStatus.READY, actor="test")
    exp.transition(ExperimentStatus.RUNNING, actor="test")
    exp.transition(ExperimentStatus.ANALYZING, actor="test")
    # Cannot transition to VERIFYING without baseline
    with pytest.raises(ExperimentTransitionError, match="baseline"):
        exp.transition(ExperimentStatus.VERIFYING, actor="test")


def test_full_lifecycle_with_baseline_completes(exp):
    """DESIGNED → READY → RUNNING → ANALYZING → set baseline → VERIFYING → COMPLETED."""
    from jarvis_backend.experiment import Metric
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator")

    m = Metric(name="math_accuracy", value=0.80, sample_count=50,
               evaluation_version="math_reasoning:v1")
    exp.set_baseline(model="base_v1", revision="r1", metrics=[m],
                     compute="local:control-node")

    exp.transition(ExperimentStatus.VERIFYING, actor="orchestrator")
    exp.transition(ExperimentStatus.COMPLETED, actor="verifier")
    assert exp.status == ExperimentStatus.COMPLETED.value


def test_lifecycle_blocked_recovery(exp):
    """DESIGNED → BLOCKED → READY → RUNNING → CANCELLED."""
    exp.transition(ExperimentStatus.BLOCKED, actor="orchestrator", notes="No GPU")
    assert exp.status == ExperimentStatus.BLOCKED.value
    exp.transition(ExperimentStatus.READY, actor="orchestrator", notes="GPU available")
    assert exp.status == ExperimentStatus.READY.value
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.CANCELLED, actor="user", notes="Stopped")
    assert exp.status == ExperimentStatus.CANCELLED.value


def test_lifecycle_failure_chain(exp):
    """DESIGNED → READY → RUNNING → FAILED."""
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.FAILED, actor="orchestrator", notes="Job crashed")
    assert exp.status == ExperimentStatus.FAILED.value
    assert exp.is_terminal


def test_lifecycle_inconclusive_chain(exp):
    """DESIGNED → READY → RUNNING → ANALYZING → INCONCLUSIVE."""
    exp.transition(ExperimentStatus.READY, actor="orchestrator")
    exp.transition(ExperimentStatus.RUNNING, actor="orchestrator")
    exp.transition(ExperimentStatus.ANALYZING, actor="orchestrator")
    exp.transition(ExperimentStatus.INCONCLUSIVE, actor="verifier",
                  notes="Results ambiguous")
    assert exp.status == ExperimentStatus.INCONCLUSIVE.value
    assert exp.is_terminal


# --------------------------------------------------------------------------- #
# Event timeline
# --------------------------------------------------------------------------- #
def test_event_timeline_records_transitions(exp):
    exp.transition(ExperimentStatus.READY, actor="test", notes="Ready")
    exp.transition(ExperimentStatus.RUNNING, actor="test", notes="Running")
    events = exp.event_timeline_list()
    transitions = [e for e in events if e["kind"] == "transition"]
    assert len(transitions) == 2
    assert transitions[0]["from"] == "designed"
    assert transitions[0]["to"] == "ready"
    assert transitions[1]["from"] == "ready"
    assert transitions[1]["to"] == "running"


def test_event_timeline_records_baseline():
    from jarvis_backend.experiment import Metric
    exp = Experiment.create(mission_id="m", name="baseline_test", owner="test")
    m = Metric(name="acc", value=0.80, sample_count=50, evaluation_version="v1")
    exp.set_baseline(model="base", revision="r1", metrics=[m], compute="local")
    events = exp.event_timeline_list()
    baseline_events = [e for e in events if e["kind"] == "baseline"]
    assert len(baseline_events) == 1


# --------------------------------------------------------------------------- #
# valid_transitions property
# --------------------------------------------------------------------------- #
def test_valid_transitions_property_returns_dict(lifecycle):
    transitions = lifecycle.valid_transitions  # property
    assert isinstance(transitions, dict)
    assert "designed" in transitions
    assert "ready" in transitions
    assert isinstance(transitions["designed"], list)
    assert "ready" in transitions["designed"]


def test_terminal_states_method_returns_list(lifecycle):
    states = lifecycle.terminal_states()
    assert isinstance(states, list)
    assert "completed" in states
    assert "failed" in states
