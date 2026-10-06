"""Phase 10 — Mission model tests.

Verifies the Mission dataclass: field presence, persistence (save/load),
serialization (to_dict/from_dict round-trip), and budget enforcement.
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
from jarvis_backend.mission import (  # noqa: E402
    Mission,
    MissionBudget,
    MissionStatus,
    AutonomyLevel,
    MissionPriority,
    ExecutionMode,
    RiskLevel,
    MissionEvent,
    MissionDecision,
    MissionCheckpoint,
)

EXPECTED_FIELDS = [
    "mission_id", "title", "objective", "constraints", "success_criteria",
    "failure_criteria", "priority", "autonomy_level", "risk_level", "budget",
    "allowed_capabilities", "required_capabilities", "execution_mode", "status",
    "created_by", "created_at", "updated_at", "deadline", "context_snapshot",
    "current_phase", "parent_mission", "tasks", "artifacts", "evidence",
    "decisions", "checkpoints", "metrics",
]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _reset_stores():
    get_store("missions").reset()
    get_store("tasks").reset()
    get_store("executions").reset()
    yield
    get_store("missions").reset()
    get_store("tasks").reset()
    get_store("executions").reset()


@pytest.fixture()
def mission() -> Mission:
    m = Mission.create(
        title="Improve Math Reasoning",
        objective="Investigate why JARVIS performs poorly on mathematical reasoning and "
                  "produce an evidence-backed improvement plan.",
        created_by="test_user",
    )
    m.success_criteria = ["Root cause identified", "Improvement plan drafted"]
    m.failure_criteria = ["No improvement possible within budget"]
    m.constraints = ["No credential exfiltration"]
    m.priority = MissionPriority.HIGH.value
    m.risk_level = RiskLevel.MEDIUM.value
    m.autonomy_level = AutonomyLevel.LEVEL_1.value
    m.allowed_capabilities = ["model.status", "project.status"]
    m.required_capabilities = ["project.inspect"]
    m.budget = MissionBudget(
        max_steps=50, max_tokens=5000, max_cost_usd=10.0,
        max_seconds=300, max_iterations=5,
    )
    m.deadline = "2026-12-31T23:59:59Z"
    m.save()
    return m


# --------------------------------------------------------------------------- #
# Field presence
# --------------------------------------------------------------------------- #
def test_mission_has_all_expected_fields():
    actual = set(Mission.__dataclass_fields__.keys())
    for field in EXPECTED_FIELDS:
        assert field in actual, f"Missing field: {field}"


def test_mission_has_all_field_types():
    for field_name, field in Mission.__dataclass_fields__.items():
        assert field.type is not None or field.default is not None, \
            f"Field {field_name} has no type hint"


# --------------------------------------------------------------------------- #
# Mission.create factory
# --------------------------------------------------------------------------- #
def test_create_assigns_unique_id():
    m1 = Mission.create(title="A", objective="obj A", created_by="u")
    m2 = Mission.create(title="B", objective="obj B", created_by="u")
    assert m1.mission_id != m2.mission_id
    assert m1.mission_id.startswith("mission_")


def test_create_sets_default_status_draft():
    m = Mission.create(title="A", objective="obj", created_by="u")
    assert m.status == MissionStatus.DRAFT.value


def test_create_sets_timestamps():
    m = Mission.create(title="A", objective="obj", created_by="u")
    assert m.created_at is not None
    assert m.updated_at is not None


def test_create_records_creation_event():
    m = Mission.create(title="A", objective="obj", created_by="u")
    events = m.event_timeline()
    assert any(e["kind"] == "created" for e in events)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def test_save_and_load_roundtrip(mission):
    loaded = Mission.load(mission.mission_id)
    assert loaded is not None
    assert loaded.title == mission.title
    assert loaded.objective == mission.objective
    assert loaded.success_criteria == mission.success_criteria
    assert loaded.status == mission.status
    assert loaded.created_by == mission.created_by


def test_load_nonexistent_returns_none():
    assert Mission.load("mission_nonexistent_id") is None


def test_list_all_returns_all_saved():
    m1 = Mission.create(title="M1", objective="o1", created_by="u")
    m1.save()
    m2 = Mission.create(title="M2", objective="o2", created_by="u")
    m2.save()
    all_missions = Mission.list_all()
    ids = {m.mission_id for m in all_missions}
    assert m1.mission_id in ids
    assert m2.mission_id in ids


def test_is_terminal_false_for_draft():
    m = Mission.create(title="A", objective="obj", created_by="u")
    assert not m.is_terminal


def test_is_terminal_true_for_completed():
    m = Mission.create(title="A", objective="obj", created_by="u")
    m.success_criteria = ["ok"]
    m.transition(MissionStatus.ACTIVE, actor="test")
    m.transition(MissionStatus.VERIFYING, actor="test")
    m.transition(MissionStatus.COMPLETED, actor="test")
    assert m.is_terminal


def test_is_terminal_true_for_failed():
    m = Mission.create(title="A", objective="obj", created_by="u")
    m.success_criteria = ["ok"]
    m.transition(MissionStatus.ACTIVE, actor="test")
    m.transition(MissionStatus.FAILED, actor="test")
    assert m.is_terminal


def test_is_terminal_true_for_cancelled():
    m = Mission.create(title="A", objective="obj", created_by="u")
    m.transition(MissionStatus.CANCELLED, actor="test")
    assert m.is_terminal


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def test_to_dict_contains_all_fields(mission):
    d = mission.to_dict()
    for field in EXPECTED_FIELDS:
        assert field in d, f"to_dict missing field: {field}"


def test_to_dict_serializes_budget(mission):
    d = mission.to_dict()
    assert isinstance(d["budget"], dict)
    assert d["budget"]["max_steps"] == 50
    assert d["budget"]["max_cost_usd"] == 10.0


def test_from_dict_roundtrip(mission):
    d = mission.to_dict()
    m2 = Mission.from_dict(d)
    assert m2.mission_id == mission.mission_id
    assert m2.title == mission.title
    assert m2.objective == mission.objective
    assert m2.success_criteria == mission.success_criteria
    assert m2.constraints == mission.constraints
    assert m2.status == mission.status
    assert m2.autonomy_level == mission.autonomy_level
    assert m2.current_phase == mission.current_phase


def test_to_dict_from_dict_preserves_checkpoints(mission):
    mission.checkpoint(cycle=1, phase="understand", notes="test checkpoint")
    mission.checkpoint(cycle=2, phase="plan", notes="second checkpoint")
    mission.save()
    d = mission.to_dict()
    m2 = Mission.from_dict(d)
    assert len(m2.checkpoints) == len(mission.checkpoints)
    assert m2.checkpoints[0]["notes"] == "test checkpoint"


def test_to_dict_from_dict_preserves_event_timeline(mission):
    mission.transition(MissionStatus.ACTIVE, actor="test")
    d = mission.to_dict()
    m2 = Mission.from_dict(d)
    timeline = m2.event_timeline()
    assert len(timeline) >= 1
    assert any(e["from"] == "DRAFT" and e["to"] == "ACTIVE" for e in timeline)


# --------------------------------------------------------------------------- #
# MissionBudget
# --------------------------------------------------------------------------- #
def test_budget_default_values():
    b = MissionBudget()
    assert b.max_steps > 0
    assert b.max_seconds > 0


def test_budget_serialization():
    b = MissionBudget(
        max_steps=100, max_tokens=5000, max_cost_usd=25.0,
        max_seconds=600, max_iterations=20,
    )
    d = b.to_dict()
    b2 = MissionBudget.from_dict(d)
    assert b2.max_steps == 100
    assert b2.max_tokens == 5000
    assert b2.max_cost_usd == 25.0
    assert b2.max_seconds == 600
    assert b2.max_iterations == 20


# --------------------------------------------------------------------------- #
# MissionCheckpoint
# --------------------------------------------------------------------------- #
def test_checkpoint_records_cognitive_state(mission):
    state_snapshot = {"cycle": 1, "phase": "plan", "confidence": 0.8}
    cid = mission.checkpoint(
        cycle=1, phase="plan", cognitive_state=state_snapshot,
        notes="first checkpoint",
    )
    assert cid.startswith("ckpt_")
    ckpts = mission.checkpoints
    assert len(ckpts) == 1
    assert ckpts[0]["cycle"] == 1
    assert ckpts[0]["phase"] == "plan"
    assert ckpts[0]["cognitive_state"]["cycle"] == 1


def test_latest_checkpoint_returns_most_recent(mission):
    mission.checkpoint(cycle=1, phase="perceive", notes="first")
    mission.checkpoint(cycle=2, phase="understand", notes="second")
    latest = mission.latest_checkpoint()
    assert latest is not None
    assert latest["cycle"] == 2
    assert latest["notes"] == "second"


def test_latest_checkpoint_none_when_empty(mission):
    assert mission.latest_checkpoint() is None


# --------------------------------------------------------------------------- #
# AutonomyLevel
# --------------------------------------------------------------------------- #
def test_autonomy_level_values():
    assert AutonomyLevel.LEVEL_0.value == 0
    assert AutonomyLevel.LEVEL_1.value == 1
    assert AutonomyLevel.LEVEL_2.value == 2
    assert AutonomyLevel.LEVEL_3.value == 3


def test_autonomy_level_four_levels():
    levels = {e.value for e in AutonomyLevel}
    assert levels == {0, 1, 2, 3}


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
def test_execution_mode_enum():
    modes = {e.value for e in ExecutionMode}
    assert {"online", "offline", "degraded"} == modes


def test_mission_priority_enum():
    priorities = {e.value for e in MissionPriority}
    assert {"low", "normal", "high", "critical"} == priorities


def test_risk_level_enum():
    risks = {e.value for e in RiskLevel}
    assert {"low", "medium", "high", "critical"} == risks


# --------------------------------------------------------------------------- #
# MissionDecision
# --------------------------------------------------------------------------- #
def test_mission_records_decision(mission):
    decision = MissionDecision(
        decision_id="dec_1",
        at="2026-01-01T00:00:00Z",
        kind="selected_compute",
        rationale="local hardware sufficient",
        outcome={"resource": "local:control-node"},
        evidence_refs=[],
        actor="cognitive_kernel",
    )
    mission.decisions.append(decision.to_dict())
    assert len(mission.decisions) == 1
    assert mission.decisions[0]["kind"] == "selected_compute"


# --------------------------------------------------------------------------- #
# Event timeline
# --------------------------------------------------------------------------- #
def test_event_timeline_records_all_events(mission):
    timeline = mission.event_timeline()
    # Created event should be present
    assert any(e["kind"] == "created" for e in timeline)
    assert len(timeline) >= 1


def test_event_timeline_grows_with_transitions(mission):
    initial_count = len(mission.event_timeline())
    mission.transition(MissionStatus.ACTIVE, actor="kernel")
    new_count = len(mission.event_timeline())
    assert new_count == initial_count + 1
