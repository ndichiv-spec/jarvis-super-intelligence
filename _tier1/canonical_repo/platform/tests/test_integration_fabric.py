"""Tests for the Kaggle + Hugging Face + NVIDIA + Docker integration fabric.

Focus: truthful state distinction, no credential exposure, derived (never
fabricated) continuations, approval gating, and optionality of Docker.
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

LADDER = ("configured", "authenticated", "reachable", "healthy",
          "inference_verified", "artifact_exists", "evaluated", "promoted",
          "deployed")


@pytest.fixture(scope="module")
def matrix():
    return bf.integration_matrix()


# --------------------------------------------------------------------------- #
# Truthfulness ladder
# --------------------------------------------------------------------------- #
def test_distinctions_are_explicit() -> None:
    assert set(bf.DISTINCTIONS) == set(LADDER)
    assert bf.DISTINCTIONS == LADDER


def test_matrix_covers_all_four_systems_plus_models(matrix) -> None:
    for svc in ("kaggle", "hugging_face", "nvidia", "docker"):
        assert svc in matrix["services"], f"missing service {svc}"
        assert "role" in matrix["services"][svc]
    for sysname in ("kaggle", "hugging_face", "nvidia", "docker", "brain",
                    "silverwing"):
        assert sysname in matrix["continuations"]


def test_states_are_booleans_or_none_not_inferred_strings(matrix) -> None:
    for svc, meta in matrix["services"].items():
        for field in ("configured", "authenticated", "reachable", "available"):
            assert field in meta, f"{svc} missing {field}"
            assert meta[field] in (True, False, None), \
                f"{svc}.{field} must be a tri-state boolean, got {meta[field]!r}"


def test_configured_does_not_imply_authenticated(matrix) -> None:
    """configured != authenticated must be representable, never collapsed."""
    for svc, meta in matrix["services"].items():
        if meta.get("configured") and meta.get("authenticated") is False:
            assert meta.get("available") is not True, \
                f"{svc}: available must not follow from configured alone"


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #
def test_roles_are_correct(matrix) -> None:
    roles = {k: v["role"].lower() for k, v in matrix["services"].items()}
    assert "training" in roles["kaggle"]
    assert "storage" in roles["hugging_face"] or "artifact" in roles["hugging_face"]
    assert "inference" in roles["nvidia"]
    assert "runtime" in roles["docker"] or "packaging" in roles["docker"]


# --------------------------------------------------------------------------- #
# Credential isolation
# --------------------------------------------------------------------------- #
def test_no_credential_values_in_matrix(matrix) -> None:
    blob = json.dumps(matrix)
    for pattern in ("hf_", "sk-", "nvapi-", "Bearer ", "KAGGLE_KEY="):
        assert pattern not in blob, f"credential-shaped value leaked: {pattern}"


def test_approval_actions_never_silent() -> None:
    for action in ("submit_training_run", "publish_artifact", "promote_model",
                   "deploy_model", "install_docker"):
        assert action in bf.APPROVAL_REQUIRED


def test_risky_continuations_require_approval(matrix) -> None:
    for name, cont in matrix["continuations"].items():
        if cont["next_step"] in bf.APPROVAL_REQUIRED:
            assert cont["requires_approval"] is True, \
                f"{name}.{cont['next_step']} must require approval"


# --------------------------------------------------------------------------- #
# Continuations are derived, not fabricated
# --------------------------------------------------------------------------- #
def test_every_continuation_has_detail(matrix) -> None:
    for name, cont in matrix["continuations"].items():
        assert cont.get("next_step"), f"{name} has no next step"
        assert cont.get("next_detail"), f"{name} next step has no justification"


def test_safe_and_approval_sets_are_consistent(matrix) -> None:
    for item in matrix["safe_next_actions"]:
        sysname, step = item.split(".", 1)
        assert matrix["continuations"][sysname]["next_step"] == step
    for item in matrix["requires_approval"]:
        sysname, step = item.split(".", 1)
        assert matrix["continuations"][sysname]["next_step"] == step


def test_blocked_systems_are_listed(matrix) -> None:
    for name in matrix["blocked"]:
        assert matrix["continuations"][name]["blocked"] is True


# --------------------------------------------------------------------------- #
# Docker is optional
# --------------------------------------------------------------------------- #
def test_docker_never_blocks_the_pipeline() -> None:
    assert bf.docker_status().get("state") in {"UNAVAILABLE", "DEGRADED",
                                               "AVAILABLE", "OFFLINE"}
    pr = bf.pipeline_readiness()
    assert pr["links"]["docker_optional"]["blocking"] is False


def test_docker_absence_explains_impact_and_action() -> None:
    d = bf.docker_status()
    if d["state"] == "UNAVAILABLE":
        assert d.get("reason")
        assert d.get("required_action")
        assert d.get("impact")


def test_pipeline_verdict_truthful() -> None:
    pr = bf.pipeline_readiness()
    assert isinstance(pr["core_pipeline_ready"], bool)
    if pr["core_pipeline_ready"]:
        assert not pr["blocked_links"]
    else:
        assert pr["blocked_links"]


# --------------------------------------------------------------------------- #
# Kaggle / HF specifics
# --------------------------------------------------------------------------- #
def test_kaggle_status_has_no_submission() -> None:
    kg = bf._kaggle_real_status()
    assert kg["submitted"] is False
    assert kg["read_only"] is True


def test_kaggle_detects_credential_file_not_only_env() -> None:
    """The env-var-only probe produced a false negative; kaggle.json counts."""
    kg = bf._kaggle_real_status()
    assert "credential_file_present" in kg
    if kg["credential_file_present"]:
        assert kg["key_present"] is True
        # Presence/length metadata is fine; a field literally named "key"
        # carrying the credential is not.
        blob = json.dumps(kg)
        assert '"key":' not in blob, "raw Kaggle key must never be returned"
        assert kg.get("key_length") == 37 or kg.get("key_length", 0) > 0


def test_hf_reports_live_revision_and_flags_mismatch() -> None:
    hf = bf._hf_real_status()
    if hf.get("state") != "AVAILABLE":
        pytest.skip("HF not authenticated")
    for repo, meta in (hf.get("repositories") or {}).items():
        assert "local_recorded_revision" in meta
        if meta.get("exists"):
            assert meta.get("live_revision")
            if meta.get("revision_mismatch"):
                assert "not resolved automatically" in meta["mismatch_note"]


# --------------------------------------------------------------------------- #
# Brain / Silverwing lifecycle
# --------------------------------------------------------------------------- #
def test_brain_not_promoted_without_gate() -> None:
    brain = bf.discover_brain()
    promo = brain["promotion"]
    if not promo.get("promoted_allowed"):
        assert promo.get("blockers")
        assert brain["deployment"]["routing_eligible"] is False


def test_silverwing_continuation_reflects_offline() -> None:
    sw = bf.discover_silverwing()
    cont = bf._silverwing_continuation(sw)
    if sw["runtime"]["state"] == "OFFLINE":
        assert cont["next_step"] == "start_silverwing_runtime"
        assert cont["blocked"] is True


# --------------------------------------------------------------------------- #
# Capabilities + endpoints
# --------------------------------------------------------------------------- #
def test_integration_capabilities_registered() -> None:
    from research_engine.capability_tools import build_capability_registry

    available = set(build_capability_registry().available())
    for cap in ("fabric.integrations", "fabric.pipeline", "training.status",
                "nvidia.deployment", "docker.status", "brain.status",
                "silverwing.status"):
        assert cap in available, f"missing capability {cap}"


def test_integration_capability_executes_without_secrets() -> None:
    import asyncio

    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    registry = build_capability_registry()
    res = asyncio.run(registry.invoke(
        "fabric.integrations", {}, ToolContext(request_id="ig", user_id="u")))
    assert res.success is True
    blob = res.result
    for pattern in ("hf_", "sk-", "nvapi-"):
        assert pattern not in blob


def test_control_plane_integration_routes_exist() -> None:
    src = (ROOT / "jarvis_backend" / "routers" / "control_plane.py").read_text(
        encoding="utf-8")
    for route in ('"/integrations"', '"/integrations/{system}"',
                  '"/development-pipeline"', '"/brain"', '"/silverwing"'):
        assert route in src, f"missing route {route}"


def test_fabric_never_submits_or_promotes_automatically() -> None:
    src = (ROOT / "jarvis_backend" / "brain_fabric.py").read_text(encoding="utf-8")
    for banned in ("kernel_push", "competitions push", "hf_hub_download",
                   "create_job(", "update_status("):
        assert banned not in src, f"fabric must not perform {banned}"
