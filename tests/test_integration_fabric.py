"""Tests for the Kaggle + Hugging Face + NVIDIA + Docker integration fabric.

Focus: truthful state distinction, no credential exposure, derived (never
fabricated) continuations, approval gating, and optionality of Docker.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from research_engine import capability_tools  # noqa: E402

from jarvis_backend import brain_fabric as bf  # noqa: E402

LADDER = ("configured", "authenticated", "reachable", "healthy",
          "inference_verified", "artifact_exists", "evaluated", "promoted",
          "deployed")


@pytest.fixture(autouse=True)
def _offline_external_probes(monkeypatch, request):
    if request.node.get_closest_marker("live_provider"):
        return
    monkeypatch.setattr(bf, "_kaggle_real_status", lambda: {
        "credential_file_present": False,
        "cli_installed": False,
        "connected": False,
        "state": "NOT_CONFIGURED",
        "read_only": True,
        "submitted": False,
        "kernel_count": 0,
    })
    monkeypatch.setattr(bf, "_hf_real_status", lambda: {
        "token_present": False,
        "connected": False,
        "state": "NOT_CONFIGURED",
        "error": "No provider credentials in the unit-test snapshot",
        "repositories": {},
    })
    monkeypatch.setattr(capability_tools, "live_provider_status", lambda: {
        "nvidia": {
            "configured": True,
            "authenticated": True,
            "reachable": True,
            "available": True,
            "health_status": "healthy",
            "inference_verified": True,
        },
    })
    monkeypatch.setattr(bf, "docker_status", lambda: {
        "state": "UNAVAILABLE",
        "reason": "Docker is unavailable in this unit-test snapshot",
        "required_action": "No action is required for unit tests",
        "impact": "No effect on core lifecycle",
    })


@pytest.fixture
def matrix(_offline_external_probes):
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
    for pattern in (r"hf_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{16,}",
                    r"nvapi-[A-Za-z0-9]{16,}", "Bearer ", "KAGGLE_KEY="):
        assert re.search(pattern, blob) is None, \
            f"credential-shaped value leaked: {pattern}"


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


def test_test_mode_disables_external_provider_probes(monkeypatch) -> None:
    import subprocess
    import urllib.request

    def unexpected_probe(*args, **kwargs):
        pytest.fail("a provider probe ran in test mode")

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.delenv("JARVIS_RUN_LIVE_PROVIDER_TESTS", raising=False)
    monkeypatch.delenv("JARVIS_LIVE_PROVIDER_TEST_ACTIVE", raising=False)
    monkeypatch.setenv("HF_TOKEN", "test-only-token")
    monkeypatch.setattr("dotenv.load_dotenv", unexpected_probe)
    monkeypatch.setattr(urllib.request, "urlopen", unexpected_probe)
    monkeypatch.setattr(subprocess, "run", unexpected_probe)
    monkeypatch.setattr(Path, "home", unexpected_probe)

    hf = bf._hf_probe()
    kaggle = bf._kaggle_probe()
    assert hf["state"] == "NOT_CONFIGURED"
    assert hf["token_present"] is False
    assert kaggle["state"] == "NOT_CONFIGURED"
    assert kaggle["credential_file_present"] is False


def test_kaggle_detects_credential_file_not_only_env(monkeypatch, tmp_path) -> None:
    """A fake credential file is detected without invoking the live CLI."""
    import shutil
    import subprocess

    monkeypatch.delenv("JARVIS_TEST_MODE", raising=False)
    kaggle_home = tmp_path / ".kaggle"
    kaggle_home.mkdir()
    (kaggle_home / "kaggle.json").write_text(
        json.dumps({"username": "test-user", "key": "test-key"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(shutil, "which", lambda _name: "kaggle.exe")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="ref,title\n", stderr=""),
    )
    kg = bf._kaggle_probe()
    assert "credential_file_present" in kg
    assert kg["credential_file_present"] is True
    assert kg["key_present"] is True
    blob = json.dumps(kg)
    assert '"key":' not in blob, "raw Kaggle key must never be returned"
    assert kg.get("key_length", 0) > 0


@pytest.mark.integration
@pytest.mark.live_provider
def test_hf_reports_live_revision_and_flags_mismatch(
    monkeypatch, live_provider_credentials
) -> None:
    if not {"HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN",
            "JARVIS_HF_TOKEN"}.intersection(live_provider_credentials):
        pytest.skip("Set an HF token in the environment for live HF verification.")
    monkeypatch.setattr(bf, "_HF_CACHE", None)
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
    for pattern in (r"hf_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{16,}",
                    r"nvapi-[A-Za-z0-9]{16,}"):
        assert re.search(pattern, blob) is None


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
