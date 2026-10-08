"""Phase 10 — Mission Lifecycle state machine tests.

Validates every legal and illegal mission state transition using the
MissionLifecycle state machine.
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

from jarvis_backend.mission import (  # noqa: E402
    Mission,
    MissionBudget,
    MissionStatus,
)
from jarvis_backend.mission_lifecycle import (  # noqa: E402
    MissionLifecycle,
    MissionTransitionError,
    TERMINAL_STATUSES,
    can_transition,
    validate_transition,
)

from jarvis_backend.core import get_store  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _reset_stores():
    """Clean stores before every test to avoid cross-test pollution."""
    get_store("missions").reset()
    get_store("tasks").reset()
    get_store("executions").reset()
    yield
    get_store("missions").reset()
    get_store("tasks").reset()
    get_store("executions").reset()


@pytest.fixture()
def lifecycle():
    return MissionLifecycle()


@pytest.fixture()
def mission() -> Mission:
    """A minimal DRAFT mission with objective + success criteria."""
    m = Mission.create(
        title="Test Mission",
        objective="Test the lifecycle transitions",
        created_by="test_user",
    )
    m.success_criteria = ["Criterion one", "Criterion two"]
    m.priority = "normal"
    m.autonomy_level = 1
    m.risk_level = "low"
    m.budget = MissionBudget(
        max_steps=10, max_tokens=1000, max_cost_usd=5.0,
        max_seconds=60, max_iterations=10,
    )
    m.save()
    return m


# --------------------------------------------------------------------------- #
# Enum sanity
# --------------------------------------------------------------------------- #
def test_all_expected_states_exist():
    expected = {
        "DRAFT", "ACTIVE", "PAUSED", "BLOCKED",
        "WAITING_FOR_APPROVAL", "WAITING_FOR_RESOURCE",
        "VERIFYING", "COMPLETED", "FAILED", "CANCELLED",
    }
    actual = {s.value for s in MissionStatus}
    assert expected == actual


def test_terminal_statuses_are_exactly_three():
    assert {s.value for s in TERMINAL_STATUSES} == {
        "COMPLETED", "FAILED", "CANCELLED",
    }


# --------------------------------------------------------------------------- #
# can_transition
# --------------------------------------------------------------------------- #
def test_draft_to_active_is_allowed(lifecycle):
    assert lifecycle.can_transition(MissionStatus.DRAFT, MissionStatus.ACTIVE)


def test_active_to_verifying_is_allowed(lifecycle):
    assert lifecycle.can_transition(MissionStatus.ACTIVE, MissionStatus.VERIFYING)


def test_verifying_to_completed_is_allowed(lifecycle):
    assert lifecycle.can_transition(MissionStatus.VERIFYING, MissionStatus.COMPLETED)


def test_draft_to_completed_is_rejected(lifecycle):
    assert not lifecycle.can_transition(MissionStatus.DRAFT, MissionStatus.COMPLETED)


def test_completed_to_anything_is_rejected(lifecycle):
    for target in MissionStatus:
        if target == MissionStatus.COMPLETED:
            continue
        assert not lifecycle.can_transition(MissionStatus.COMPLETED, target)


def test_module_level_can_transition_matches_class(lifecycle, mission):
    assert can_transition(MissionStatus.DRAFT, MissionStatus.ACTIVE) == \
        lifecycle.can_transition(MissionStatus.DRAFT, MissionStatus.ACTIVE)


# --------------------------------------------------------------------------- #
# validate_transition
# --------------------------------------------------------------------------- #
def test_draft_to_active_validates(mission):
    mission.status = MissionStatus.DRAFT.value
    # Should not raise
    validate_transition(MissionStatus.DRAFT, MissionStatus.ACTIVE, mission)


def test_draft_to_active_rejects_without_objective(mission):
    mission.status = MissionStatus.DRAFT.value
    mission.objective = ""
    with pytest.raises(MissionTransitionError, match="objective"):
        validate_transition(MissionStatus.DRAFT, MissionStatus.ACTIVE, mission)


def test_draft_to_active_rejects_without_success_criteria(mission):
    mission.status = MissionStatus.DRAFT.value
    mission.success_criteria = []
    with pytest.raises(MissionTransitionError, match="success_criteria"):
        validate_transition(MissionStatus.DRAFT, MissionStatus.ACTIVE, mission)


def test_completed_only_via_verifying(mission):
    mission.status = MissionStatus.ACTIVE.value
    with pytest.raises(MissionTransitionError, match="VERIFYING"):
        validate_transition(MissionStatus.ACTIVE, MissionStatus.COMPLETED, mission)


def test_illegal_transition_raises(mission):
    # ACTIVE → DRAFT is illegal (not in the transition table)
    mission.status = MissionStatus.ACTIVE.value
    with pytest.raises(MissionTransitionError, match="Illegal transition"):
        validate_transition(MissionStatus.ACTIVE, MissionStatus.DRAFT, mission)


def test_noop_transition_is_allowed(mission):
    # Same state → same state is a no-op and always allowed
    validate_transition(MissionStatus.DRAFT, MissionStatus.DRAFT, mission)


def test_terminal_to_any_rejected(mission):
    mission.status = MissionStatus.COMPLETED.value
    with pytest.raises(MissionTransitionError, match="terminal"):
        validate_transition(MissionStatus.COMPLETED, MissionStatus.ACTIVE, mission)


# --------------------------------------------------------------------------- #
# Mission.transition (full integration)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("source", [
    MissionStatus.DRAFT,
    MissionStatus.ACTIVE,
    MissionStatus.PAUSED,
    MissionStatus.BLOCKED,
    MissionStatus.WAITING_FOR_APPROVAL,
    MissionStatus.WAITING_FOR_RESOURCE,
    MissionStatus.VERIFYING,
])
def test_transition_to_cancelled_allowed_from_nonterminal(mission, source):
    mission.status = source.value
    mission.transition(MissionStatus.CANCELLED, actor="test")
    assert mission.status == MissionStatus.CANCELLED.value


def test_transition_to_cancelled_rejected_from_terminal(mission):
    mission.status = MissionStatus.FAILED.value
    with pytest.raises(MissionTransitionError, match="terminal"):
        mission.transition(MissionStatus.ACTIVE, actor="test")


def test_transition_to_failed_allowed_from_active(mission):
    mission.status = MissionStatus.ACTIVE.value
    mission.transition(MissionStatus.FAILED, actor="test")
    assert mission.status == MissionStatus.FAILED.value


def test_transition_records_event_timeline(mission):
    mission.status = MissionStatus.DRAFT.value
    mission.transition(MissionStatus.ACTIVE, actor="kernel")
    timeline = mission.event_timeline()
    assert any(
        e["kind"] == "transition" and e["from"] == "DRAFT"
        and e["to"] == "ACTIVE"
        for e in timeline
    )


# --------------------------------------------------------------------------- #
# Full legal transition chain
# --------------------------------------------------------------------------- #
def test_full_lifecycle_path(mission):
    """DRAFT → ACTIVE → PAUSED → ACTIVE → VERIFYING → COMPLETED."""
    mission.status = MissionStatus.DRAFT.value
    mission.transition(MissionStatus.ACTIVE, actor="kernel")
    assert mission.status == MissionStatus.ACTIVE.value

    mission.transition(MissionStatus.PAUSED, actor="user")
    assert mission.status == MissionStatus.PAUSED.value

    mission.transition(MissionStatus.ACTIVE, actor="user")
    assert mission.status == MissionStatus.ACTIVE.value

    mission.transition(MissionStatus.VERIFYING, actor="kernel")
    assert mission.status == MissionStatus.VERIFYING.value

    mission.transition(MissionStatus.COMPLETED, actor="verifier")
    assert mission.status == MissionStatus.COMPLETED.value


def test_all_transition_paths_covered(lifecycle):
    """Every state in the transition table can reach at least one other state."""
    expected_transitions = [
        (MissionStatus.DRAFT, MissionStatus.ACTIVE),
        (MissionStatus.DRAFT, MissionStatus.CANCELLED),
        (MissionStatus.ACTIVE, MissionStatus.PAUSED),
        (MissionStatus.ACTIVE, MissionStatus.BLOCKED),
        (MissionStatus.ACTIVE, MissionStatus.WAITING_FOR_APPROVAL),
        (MissionStatus.ACTIVE, MissionStatus.WAITING_FOR_RESOURCE),
        (MissionStatus.ACTIVE, MissionStatus.VERIFYING),
        (MissionStatus.ACTIVE, MissionStatus.FAILED),
        (MissionStatus.ACTIVE, MissionStatus.CANCELLED),
        (MissionStatus.PAUSED, MissionStatus.ACTIVE),
        (MissionStatus.PAUSED, MissionStatus.CANCELLED),
        (MissionStatus.BLOCKED, MissionStatus.ACTIVE),
        (MissionStatus.BLOCKED, MissionStatus.CANCELLED),
        (MissionStatus.WAITING_FOR_APPROVAL, MissionStatus.ACTIVE),
        (MissionStatus.WAITING_FOR_APPROVAL, MissionStatus.FAILED),
        (MissionStatus.WAITING_FOR_APPROVAL, MissionStatus.CANCELLED),
        (MissionStatus.WAITING_FOR_RESOURCE, MissionStatus.ACTIVE),
        (MissionStatus.WAITING_FOR_RESOURCE, MissionStatus.BLOCKED),
        (MissionStatus.WAITING_FOR_RESOURCE, MissionStatus.CANCELLED),
        (MissionStatus.VERIFYING, MissionStatus.COMPLETED),
        (MissionStatus.VERIFYING, MissionStatus.FAILED),
        (MissionStatus.VERIFYING, MissionStatus.CANCELLED),
    ]
    for current, target in expected_transitions:
        assert lifecycle.can_transition(current, target), \
            f"Expected {current.value} to {target.value} to be allowed"


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def test_transition_persists_across_reload(mission):
    mission.status = MissionStatus.DRAFT.value
    mission.transition(MissionStatus.ACTIVE, actor="kernel")
    mission.save()

    reloaded = Mission.load(mission.mission_id)
    assert reloaded is not None
    assert reloaded.status == MissionStatus.ACTIVE.value
    assert len(reloaded.event_timeline()) >= 1
