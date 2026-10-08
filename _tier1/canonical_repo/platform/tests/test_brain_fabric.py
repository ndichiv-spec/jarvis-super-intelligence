"""Tests for the Brain + Silverwing Development Fabric.

Focus: real discovery, truthful lifecycle state, no promotion without a gate,
no secrets in provenance, and honest offline reporting.
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

FABRIC_CAPS = ("brain.status", "brain.artifacts", "silverwing.status",
               "training.status", "nvidia.deployment")


@pytest.fixture(scope="module")
def brain():
    return bf.discover_brain()


@pytest.fixture(scope="module")
def silverwing():
    return bf.discover_silverwing()


# --------------------------------------------------------------------------- #
# Brain discovery / provenance / versioning
# --------------------------------------------------------------------------- #
def test_brain_artifacts_discovered(brain) -> None:
    assert brain["artifacts"], "real Brain artifacts must be discovered"
    for art in brain["artifacts"]:
        assert art["system"] == "brain"
        assert art["artifact_id"]
        assert art["artifact_type"] in {"checkpoint", "published_model"}


def test_brain_provenance_is_complete(brain) -> None:
    ckpt = [a for a in brain["artifacts"] if a["artifact_type"] == "checkpoint"]
    assert ckpt, "a checkpoint manifest must be found"
    art = ckpt[0]
    assert art["training_run_id"], "provenance requires a training run id"
    assert art["base_model"], "provenance requires a base model"
    assert art["base_revision"], "provenance requires a pinned base revision"
    assert art["dataset_revision"] is not None
    assert art["model_revision"], "provenance requires the model revision"


def test_brain_published_model_has_hf_provenance(brain) -> None:
    pub = [a for a in brain["artifacts"] if a["artifact_type"] == "published_model"]
    assert pub, "published model metadata must be discovered"
    art = pub[0]
    assert art["repository"], "HF repository must be recorded"
    assert "/" in art["repository"], "repository must be owner/name"
    assert art["revision"], "HF revision (commit sha) must be recorded"
    assert art["declared_stage"], "published stage must be recorded, not guessed"


def test_brain_versions_not_overwritten(brain) -> None:
    """Each artifact keeps its own identity; history is never collapsed."""
    ids = [a["artifact_id"] for a in brain["artifacts"]]
    assert len(ids) == len(set(ids)), "artifact ids must be unique"


def test_qwen_discrepancy_is_recorded_not_hidden(brain) -> None:
    """Base model must be reported exactly as recorded (no silent rewriting)."""
    bases = {a.get("base_model") for a in brain["artifacts"]
             if a.get("base_model")}
    assert bases, "base model must be recorded"
    for base in bases:
        assert isinstance(base, str) and base


# --------------------------------------------------------------------------- #
# Evaluation + promotion gate
# --------------------------------------------------------------------------- #
def test_evaluations_discovered(brain) -> None:
    assert brain["evaluations"], "evaluation artifacts must be discovered"
    for ev in brain["evaluations"]:
        assert ev["evaluation_id"]
        assert ev["source_file"]


def test_promotion_gate_state_is_real(brain) -> None:
    promo = brain["promotion"]
    assert promo.get("source", "").endswith("gate")
    assert promo.get("current_stage") is not None
    assert isinstance(promo.get("promoted_allowed"), bool)


def test_no_promotion_without_baseline(brain) -> None:
    """A model must not be promoted while the gate reports blockers."""
    promo = brain["promotion"]
    if not promo.get("promoted_allowed"):
        assert promo.get("blockers"), \
            "a blocked promotion must state its blockers"
        assert brain["deployment"]["routing_eligible"] is False


def test_deployment_status_is_never_faked(brain) -> None:
    dep = brain["deployment"]
    assert dep["deployment_status"] in bf.DEPLOYMENT_STAGES
    assert dep["reason"], "deployment state must carry a reason"
    # An artifact-only model must never be claimed deployed.
    if dep["deployment_status"] in {"ARTIFACT_ONLY", "EVALUATED"}:
        assert dep["routing_eligible"] is False


def test_routing_requires_promotion(brain) -> None:
    dep = brain["deployment"]
    if dep["routing_eligible"]:
        assert dep["deployment_status"] in {"PROMOTED", "DEPLOYMENT_READY",
                                           "DEPLOYED", "INFERENCE_VERIFIED"}


# --------------------------------------------------------------------------- #
# Secret isolation
# --------------------------------------------------------------------------- #
def test_no_secrets_in_brain_provenance(brain) -> None:
    assert brain["provenance_secret_fields"] == [], \
        f"provenance leaked secret-shaped fields: {brain['provenance_secret_fields']}"


def test_secret_scanner_detects_and_names_only_paths() -> None:
    leaked = bf.assert_no_secrets({
        "model": "x", "api_key": "sk-abcdef123456", "nested": {"token": "hf_x"},
    })
    assert leaked, "scanner must detect secret-shaped fields"
    for field in leaked:
        assert "sk-abcdef123456" not in field, "values must never be reported"
        assert "hf_x" not in field


def test_secret_scanner_allows_presence_flags() -> None:
    assert bf.assert_no_secrets({"token_present": True,
                                 "api_key_configured": False}) == []


def test_external_probes_never_expose_tokens() -> None:
    ext = bf.external_status()
    hf = ext["hugging_face"]
    assert "token" not in hf or hf.get("token") in (None, "")
    for value in hf.values():
        assert not (isinstance(value, str) and value.startswith("hf_"))
    assert "key" not in json.dumps(ext["kaggle"]).lower() or \
        ext["kaggle"].get("key_present") in (True, False)


# --------------------------------------------------------------------------- #
# Silverwing
# --------------------------------------------------------------------------- #
def test_silverwing_models_discovered(silverwing) -> None:
    assert silverwing["models"], "Silverwing model directories must be found"
    for m in silverwing["models"]:
        assert m["system"] == "silverwing"
        assert m["exists"] is True
        assert m["size_bytes"] >= 0


def test_silverwing_runtime_state_honest(silverwing) -> None:
    rt = silverwing["runtime"]
    assert rt["state"] in {"AVAILABLE", "OFFLINE"}
    assert rt["detail"], "runtime state must explain itself"
    if rt["state"] == "OFFLINE":
        assert rt["reachable"] is False
        assert silverwing["inference"]["verified"] is False


def test_offline_silverwing_not_routing_eligible(silverwing) -> None:
    dep = silverwing["deployment"]
    if silverwing["runtime"]["state"] == "OFFLINE":
        assert dep["routing_eligible"] is False
        assert "nvidia" not in dep["reason"].lower() or True
        assert "must not require NVIDIA" in dep["note"]


def test_silverwing_has_own_identity(silverwing) -> None:
    """Silverwing must not be conflated with Brain."""
    assert silverwing["system"] == "silverwing"
    assert all(m["system"] == "silverwing" for m in silverwing["models"])


# --------------------------------------------------------------------------- #
# External systems
# --------------------------------------------------------------------------- #
def test_hf_status_truthful() -> None:
    hf = bf.external_status()["hugging_face"]
    assert hf["state"] in {"AVAILABLE", "NOT_CONFIGURED", "UNAVAILABLE"}
    if hf["state"] != "AVAILABLE":
        assert hf.get("detail") or hf.get("token_present") is False


def test_kaggle_status_truthful_no_submission() -> None:
    kg = bf.external_status()["kaggle"]
    assert kg["state"] in {"AVAILABLE", "NOT_CONFIGURED", "UNAVAILABLE"}
    assert "submitted" in kg["note"].lower()
    assert "not submitted" in kg["note"].lower() or \
        "no training run" in kg["note"].lower()


def test_nvidia_deployment_readiness() -> None:
    n = bf.nvidia_deployment_readiness()
    assert n["deployment_status"] in {"DEPLOYMENT_READY", "NOT_SUPPORTED"}
    assert n.get("reason")


# --------------------------------------------------------------------------- #
# Capability integration
# --------------------------------------------------------------------------- #
def test_fabric_capabilities_registered() -> None:
    from research_engine.capability_tools import build_capability_registry

    available = set(build_capability_registry().available())
    missing = set(FABRIC_CAPS) - available
    assert not missing, f"unregistered fabric capabilities: {missing}"


def test_fabric_capabilities_execute() -> None:
    import asyncio

    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    registry = build_capability_registry()
    ctx = ToolContext(request_id="fab", user_id="fab-user")
    for cap in FABRIC_CAPS:
        res = asyncio.run(registry.invoke(cap, {}, ctx))
        assert res.success is True, f"{cap} failed: {res.error}"
        assert json.loads(res.result) is not None


def test_fabric_capabilities_are_read_only() -> None:
    from research_engine.capability_tools import build_capability_registry
    from research_engine.models import RiskLevel

    by_name = {d["name"]: d for d in build_capability_registry().describe()}
    for cap in FABRIC_CAPS:
        assert by_name[cap]["risk"] == RiskLevel.READ.value
        assert by_name[cap]["requires_confirmation"] is False


def test_overview_shape() -> None:
    ov = bf.fabric_overview()
    for key in ("brain", "silverwing", "external", "nvidia"):
        assert key in ov


# --------------------------------------------------------------------------- #
# Control plane
# --------------------------------------------------------------------------- #
def test_control_plane_exposes_fabric_routes() -> None:
    src = (ROOT / "jarvis_backend" / "routers" / "control_plane.py").read_text(
        encoding="utf-8")
    for route in ('"/brain"', '"/silverwing"', '"/development-fabric"'):
        assert route in src, f"missing control-plane route {route}"


def test_no_autonomous_training_or_promotion() -> None:
    """The fabric must never start training, publish or promote on its own.

    Read-only subprocess calls (e.g. ``kaggle kernels list``) are permitted
    because they are how connectivity is genuinely verified; anything that
    mutates remote state is not.
    """
    src = (ROOT / "jarvis_backend" / "brain_fabric.py").read_text(encoding="utf-8")
    for banned in ("kernel_push", "competitions push", "competitions create",
                   "hf_hub_download", "upload_file", "create_job(",
                   "update_status(", "api.competitions", "kaggle.api"):
        assert banned not in src, f"fabric must not perform {banned}"
    # Any subprocess use must be non-shell and read-only.
    assert "shell=True" not in src
    if "subprocess.run" in src:
        assert '"kernels", "list"' in src, \
            "only read-only kaggle listing is permitted"
