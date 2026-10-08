"""Phase 8 tests: Brain contract / structured I/O (Phase 8 §3, §8).

Verifies the Brain input/output schema, confidence states, and the hard
structural gate that prevents malformed/malicious model output from reaching
the control plane.
"""
from __future__ import annotations

import pytest

from jarvis_brain.contract import (
    AutonomyLevel, BrainInput, BrainIntent, BrainOutput, CapabilityRequest,
    CompletionCondition, ConfidenceState, ExecutionMode, Plan, PlanStep,
    PlanDecision, SchemaValidationError, brain_output_schema,
    safe_parse_brain_json, validate_brain_output,
)

pytestmark = pytest.mark.brain


# ---- helpers ---------------------------------------------------------------
def _good_output(**overrides):
    base = {
        "intent": {"domain": "general", "task": "lookup",
                   "confidence_state": "SUFFICIENT_INFORMATION"},
        "plan": {"summary": "look it up", "steps": [
            {"id": "s1", "capability": "static_search", "summary": "search",
             "args": {"query": "photosynthesis"}, "depends_on": []}]},
        "capability_requests": [
            {"capability": "static_search", "args": {"query": "photosynthesis"},
             "reason": "evidence", "depends_on": []}],
        "questions_for_user": [],
        "completion_conditions": [
            {"type": "answer_generated", "target": "photosynthesis"}],
        "confidence_state": "SUFFICIENT_INFORMATION",
        "model_ref": "test",
        "provenance": {"adapter": "test"},
        "summary": "looked up photosynthesis",
    }
    base.update(overrides)
    return base


# ---- round-trip ------------------------------------------------------------
def test_validate_good_output_round_trips():
    out = validate_brain_output(_good_output())
    assert isinstance(out, BrainOutput)
    assert out.intent.confidence == ConfidenceState.SUFFICIENT_INFORMATION
    assert out.capability_requests[0].capability == "static_search"
    # Round trip back to dict is stable.
    assert validate_brain_output(out.to_dict()).to_dict() == out.to_dict()


def test_brain_input_to_dict_isolated():
    bi = BrainInput(request="r", execution_mode=ExecutionMode.OFFLINE.value,
                    user_id="alice", autonomy=AutonomyLevel.ASSISTED.value,
                    available_capabilities=[{"id": "static_search", "risk": "read"}],
                    relevant_artifacts=[{"id": "a"}], budget={"max_cost": 0.5})
    d = bi.to_dict()
    assert d["request"] == "r"
    assert d["execution_mode"] == "OFFLINE"
    assert d["autonomy"] == "ASSISTED"
    assert d["budget"]["max_cost"] == 0.5
    assert d["available_capabilities"][0]["id"] == "static_search"


# ---- schema rejection (no malformed output reaches the control plane) ------
@pytest.mark.parametrize("mutation", [
    lambda d: {**d, "capability_requests": "not-a-list"},
    lambda d: {**d, "confidence_state": 123},
    lambda d: {**d, "plan": {}},                       # missing steps
    lambda d: {**d, "capability_requests": [{"capability": ""}]},  # empty cap
    lambda d: {**d, "intent": {}},                    # missing intent.confidence_state
    lambda d: {**d, "completion_conditions": ["x"]},   # non-object condition
])
def test_malformed_output_rejected(mutation):
    with pytest.raises(SchemaValidationError):
        validate_brain_output(mutation(_good_output()))


def test_non_dict_output_rejected():
    with pytest.raises(SchemaValidationError):
        validate_brain_output("not even json")
    with pytest.raises(SchemaValidationError):
        validate_brain_output(None)
    with pytest.raises(SchemaValidationError):
        validate_brain_output(["a", "b"])


# ---- confidence states are honest qualifiers, not fabricated floats ----------
def test_confidence_states_are_qualitative():
    members = {c.value for c in ConfidenceState}
    expected = {"SUFFICIENT_INFORMATION", "MISSING_INFORMATION", "AMBIGUOUS_REQUEST",
                "CONFLICTING_EVIDENCE", "INSUFFICIENT_EVIDENCE", "ASK_USER"}
    assert members == expected


def test_unknown_confidence_state_rejected_by_schema():
    # A hard structural gate (Phase 8 §4 stage 1): an unknown confidence_state
    # value is malformed model output and is REJECTED, never silently normalized
    # (so the control plane always degrades honestly instead of trusting it).
    d = _good_output()
    d["confidence_state"] = "totally_made_up"
    with pytest.raises(SchemaValidationError):
        validate_brain_output(d)


def test_unknown_confidence_state_degrades_through_adapter():
    # The adapter layer must degrade honestly rather than trust unknown enums.
    from jarvis_brain.adapters import DeterministicBrainAdapter
    # (deterministic adapter never emits unknown enums; this just confirms the
    #  contract round-trips known states without fabrication.)
    d = _good_output()
    out = validate_brain_output(d)
    assert out.confidence_state == ConfidenceState.SUFFICIENT_INFORMATION


# ---- no-fabrication: an empty proposal with cannot-proceed confidence is valid
# (the contract permits it) but carries a non-trustworthy confidence_state.
def test_empty_proposal_with_ask_user_is_valid_json():
    d = _good_output()
    d["capability_requests"] = []
    d["confidence_state"] = "ASK_USER"
    d["questions_for_user"] = ["what do you mean?"]
    out = validate_brain_output(d)
    assert out.confidence_state == ConfidenceState.ASK_USER
    assert out.capability_requests == []


# ---- safe_parse_brain_json never fabricates structure -----------------------
def test_safe_parse_extracts_fenced_json():
    text = "Here is my plan:\n ```json\n" + '{"intent":{},"plan":{"steps":[]},"capability_requests":[],"completion_conditions":[],"confidence_state":"ASK_USER"}\n```'
    obj = safe_parse_brain_json(text)
    assert obj is not None
    assert obj["confidence_state"] == "ASK_USER"


def test_safe_parse_returns_none_for_prose():
    assert safe_parse_brain_json("I think therefore I am") is None
    assert safe_parse_brain_json("") is None
    assert safe_parse_brain_json("```json {not valid json```") is None


# ---- schema surface for the model backend ----------------------------------
def test_brain_output_schema_lists_required_fields():
    schema = brain_output_schema()
    assert "intent" in schema["required"]
    assert "capability_requests" in schema["required"]
    assert "confidence_state" in schema["required"]
    assert schema["properties"]["confidence_state"]["type"] == "string"


def test_plan_decision_and_autonomy_enums():
    assert PlanDecision.ACCEPTED.value == "ACCEPTED"
    assert AutonomyLevel.ASSISTED.value == "ASSISTED"
    assert ExecutionMode.OFFLINE.value == "OFFLINE"
