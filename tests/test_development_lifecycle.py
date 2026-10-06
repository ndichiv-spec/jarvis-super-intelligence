"""Tests for the stage-based lifecycle + continuation engine.

Covers: stage calculation, first-incomplete detection, Brain/Silverwing
independence, contradiction recording, approval gating, secret redaction and
routing eligibility.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from jarvis_backend import brain_fabric as bf  # noqa: E402

STAGES = ("SOURCE", "TRAINING", "CHECKPOINT", "ARTIFACT", "EVALUATION",
          "PROMOTION", "DEPLOYMENT", "INFERENCE")
VALID = {bf.COMPLETE, bf.NOT_STARTED, bf.MISSING, bf.BLOCKED}


@pytest.fixture(scope="module")
def brain():
    return bf.brain_lifecycle()


@pytest.fixture(scope="module")
def silverwing():
    return bf.silverwing_lifecycle()


# --------------------------------------------------------------------------- #
# Stage calculation
# --------------------------------------------------------------------------- #
def test_lifecycle_stage_order_is_canonical() -> None:
    assert bf.LIFECYCLE_STAGES == STAGES


def test_brain_has_every_stage_with_valid_state(brain) -> None:
    for stage in STAGES:
        assert stage in brain["stages"], f"missing stage {stage}"
        assert brain["stages"][stage]["status"] in VALID


def test_silverwing_has_every_stage_with_valid_state(silverwing) -> None:
    for stage in STAGES:
        assert stage in silverwing["stages"]
        assert silverwing["stages"][stage]["status"] in VALID


def test_incomplete_stages_always_carry_a_reason(brain, silverwing) -> None:
    for payload in (brain, silverwing):
        for stage, meta in payload["stages"].items():
            if meta["status"] != bf.COMPLETE:
                assert meta.get("reason"), f"{payload['system']}.{stage} " \
                                            "is incomplete with no reason"


def test_complete_stages_have_no_failure_reason(brain) -> None:
    for stage, meta in brain["stages"].items():
        if meta["status"] == bf.COMPLETE:
            assert meta.get("reason") is None


# --------------------------------------------------------------------------- #
# Continuation detection
# --------------------------------------------------------------------------- #
def test_first_incomplete_is_the_earliest_incomplete_stage(brain) -> None:
    first = brain["first_incomplete_stage"]
    if first is None:
        assert all(brain["stages"][s]["status"] == bf.COMPLETE for s in STAGES)
        return
    assert brain["stages"][first]["status"] != bf.COMPLETE
    for stage in STAGES:
        if STAGES.index(stage) < STAGES.index(first):
            assert brain["stages"][stage]["status"] == bf.COMPLETE, \
                f"{stage} precedes {first} but is not complete"


def test_next_action_is_derived_not_invented(brain, silverwing) -> None:
    for payload in (brain, silverwing):
        action = payload["next_action"]
        assert action["action"]
        assert action.get("detail")
        assert isinstance(action["requires_approval"], bool)


def test_next_action_stage_matches_first_incomplete(brain) -> None:
    action = brain["next_action"]
    if brain["first_incomplete_stage"] and "stage" in action:
        assert action["stage"] == brain["first_incomplete_stage"]


def test_high_risk_next_actions_require_approval(brain) -> None:
    action = brain["next_action"]["action"]
    if action in bf.APPROVAL_REQUIRED:
        assert brain["next_action"]["requires_approval"] is True


def test_safe_next_actions_exist_for_degraded_systems() -> None:
    dev = bf.development_status()
    assert dev["next_actions"]["silverwing"]["action"] == \
        "start_silverwing_runtime"
    assert dev["next_actions"]["silverwing"]["requires_approval"] is False


# --------------------------------------------------------------------------- #
# Brain / Silverwing independence
# --------------------------------------------------------------------------- #
def test_brain_and_silverwing_are_independent(brain, silverwing) -> None:
    assert brain["system"] == "brain"
    assert silverwing["system"] == "silverwing"
    # Independent stage outcomes, not a shared verdict.
    assert brain["stages"] is not silverwing["stages"]
    assert brain.get("routing_eligible") is not None
    assert silverwing.get("routing_eligible") is not None


def test_routing_requires_promotion_and_deployment(brain) -> None:
    promo = brain["stages"]["PROMOTION"]["status"]
    deploy = brain["stages"]["DEPLOYMENT"]["status"]
    if brain["routing_eligible"]:
        assert promo == bf.COMPLETE
        assert deploy == bf.COMPLETE


def test_brain_not_routable_while_promotion_blocked(brain) -> None:
    if brain["stages"]["PROMOTION"]["status"] != bf.COMPLETE:
        assert brain["routing_eligible"] is False


# --------------------------------------------------------------------------- #
# Contradictions
# --------------------------------------------------------------------------- #
def test_contradictions_are_recorded_not_silently_fixed() -> None:
    found = bf.contradictions()
    assert isinstance(found, list)
    for c in found:
        assert c["id"]
        assert "recorded" in c and "live" in c
        assert c.get("resolution"), "every contradiction needs a disposition"


def test_qwen_base_model_discrepancy_is_recorded() -> None:
    ids = {c["id"] for c in bf.contradictions()}
    assert "base_model_naming" in ids, \
        "the Qwen3-4B vs Qwen3-4B-Base discrepancy must be surfaced"


def test_history_files_not_rewritten() -> None:
    """The engine must never mutate recorded history."""
    for rel in ("pipeline/pipeline_report.json",
                "checkpoints/jarvis-brain-sft-kaggle-v6-step-000030.json",
                "publish/jarvis-brain-sft-kaggle-v6.publish.json"):
        p = bf.BRAIN_ARTIFACTS / rel
        assert p.is_file(), f"{rel} must still exist unmodified"


# --------------------------------------------------------------------------- #
# Secret redaction
# --------------------------------------------------------------------------- #
def test_development_status_has_no_credentials() -> None:
    blob = json.dumps(bf.development_status())
    import re

    for pattern in (r"hf_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{16,}",
                    r"nvapi-[A-Za-z0-9]{16,}", "Bearer "):
        assert re.search(pattern, blob) is None, f"credential leaked: {pattern}"


def test_lifecycle_payloads_have_no_secrets(brain, silverwing) -> None:
    for payload in (brain, silverwing):
        assert bf.assert_no_secrets(payload) == []


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
def test_lifecycle_capabilities_registered_and_read_only() -> None:
    from research_engine.capability_tools import build_capability_registry
    from research_engine.models import RiskLevel

    by_name = {d["name"]: d for d in build_capability_registry().describe()}
    for cap in ("kaggle.status", "kaggle.jobs", "huggingface.status",
                "huggingface.artifacts", "nvidia.models", "nvidia.inference",
                "brain.lifecycle", "silverwing.lifecycle",
                "development.status", "development.next_action",
                "development.verify"):
        assert cap in by_name, f"missing capability {cap}"
        assert by_name[cap]["risk"] == RiskLevel.READ.value
    # Docker legitimately shells out to a fixed docker argv, so it is EXEC.
    assert by_name["docker.status"]["risk"] == RiskLevel.EXEC.value


def test_lifecycle_capabilities_execute() -> None:
    import asyncio

    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    registry = build_capability_registry()
    ctx = ToolContext(request_id="lc", user_id="u")
    for cap in ("brain.lifecycle", "silverwing.lifecycle",
                "development.next_action"):
        res = asyncio.run(registry.invoke(cap, {}, ctx))
        assert res.success is True, f"{cap}: {res.error}"
        assert json.loads(res.result)


def test_next_action_capability_reports_contradictions() -> None:
    import asyncio

    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    res = asyncio.run(build_capability_registry().invoke(
        "development.next_action", {},
        ToolContext(request_id="na", user_id="u")))
    data = json.loads(res.result)
    assert "brain" in data and "silverwing" in data
    assert "contradictions" in data


# --------------------------------------------------------------------------- #
# Control plane
# --------------------------------------------------------------------------- #
def test_development_routes_exist() -> None:
    src = (ROOT / "jarvis_backend" / "routers" / "control_plane.py").read_text(
        encoding="utf-8")
    for route in ('"/development/status"', '"/development/brain"',
                  '"/development/silverwing"', '"/development/next-action"',
                  '"/deployments"'):
        assert route in src, f"missing route {route}"


def test_no_expensive_or_mutating_operations() -> None:
    src = (ROOT / "jarvis_backend" / "brain_fabric.py").read_text(encoding="utf-8")
    for banned in ("kernel_push", "competitions push", "hf_hub_download",
                   "upload_file", "docker run", "docker compose up"):
        assert banned not in src
