"""Deterministic Cloud Hardware Fabric contract and routing tests."""
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

from jarvis_backend import cloud_fabric as cf  # noqa: E402

STATES = ("configured", "authenticated", "reachable", "healthy",
          "resource_verified", "job_verified", "inference_verified")


@pytest.fixture(autouse=True)
def _offline_probes(isolated_cloud_fabric):
    return isolated_cloud_fabric


@pytest.fixture
def hardware(_offline_probes):
    return cf.local_hardware()


@pytest.fixture
def resources(_offline_probes):
    return cf.cloud_resources()


# --------------------------------------------------------------------------- #
# Hardware truthfulness
# --------------------------------------------------------------------------- #
def test_local_hardware_reports_real_fields(hardware) -> None:
    for field in ("cpu", "ram_gb", "os", "architecture", "role",
                  "virtualization", "docker", "network"):
        assert field in hardware, f"hardware profile missing {field}"
    assert hardware["role"] == "control_plane"


def test_virtualization_detected_truthfully(hardware) -> None:
    v = hardware["virtualization"]
    assert isinstance(v["supported"], bool)
    assert v["supported"] == (v["firmware_enabled"] and v["slat"])
    if not v["supported"]:
        assert v["reason"], "unsupported virtualization must state why"


def test_docker_state_is_truthful(hardware) -> None:
    d = hardware["docker"]
    assert isinstance(d["installed"], bool)
    if not d["installed"]:
        assert d["cli"] is None


def test_unsuitable_workloads_are_declared(hardware) -> None:
    if not hardware["virtualization"]["supported"]:
        assert "containers" in hardware["not_suited_for"]


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #
def test_only_real_resources_registered(resources) -> None:
    ids = {r["resource_id"] for r in resources["resources"]}
    for expected in ("local:control-node", "cloud:nvidia", "cloud:kaggle",
                     "cloud:huggingface"):
        assert expected in ids


def test_unavailable_resource_is_not_claimed_available(resources) -> None:
    for r in resources["resources"]:
        if r["status"] not in {"AVAILABLE", "DEGRADED"}:
            assert not r.get("capabilities"), \
                f"{r['resource_id']} unavailable but advertises capabilities"
            assert r.get("reason") or r.get("state_chain"), \
                f"{r['resource_id']} unavailable with no explanation"


def test_docker_resource_is_non_blocking(resources) -> None:
    docker = next(r for r in resources["resources"]
                  if r["resource_id"] == "docker:execution")
    assert docker["blocking"] is False, \
        "absence of Docker must never block the platform"


def test_state_chain_uses_granular_vocabulary(resources) -> None:
    for r in resources["resources"]:
        for key in (r.get("state_chain") or {}):
            assert key in STATES, f"non-canonical state {key!r}"


def test_no_credentials_in_resources(resources) -> None:
    import re

    blob = json.dumps(resources)
    for pattern in (r"hf_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{16,}",
                    r"nvapi-[A-Za-z0-9]{16,}", "Bearer "):
        assert re.search(pattern, blob) is None


# --------------------------------------------------------------------------- #
# Compute selection
# --------------------------------------------------------------------------- #
def test_modest_workload_stays_local() -> None:
    r = cf.select_compute({"task": "analyze a small CSV file"})
    assert r["selected"] == "local:control-node"
    assert r["local_viable"] is True


def test_gpu_training_selects_a_verified_gpu_resource() -> None:
    """Selection follows verified provider snapshots, not live connectivity."""
    r = cf.select_compute({"task": "fine-tune a LoRA adapter",
                           "gpu_required": True, "network_required": True})
    assert r["selected"] is not None, "no GPU resource available"
    res = cf.cloud_resources()["by_id"][r["selected"]]
    assert res.get("gpu"), "selected resource must expose a GPU"
    assert res["status"] in {"AVAILABLE", "DEGRADED"}
    assert r["requires_approval"] is True, "training must require approval"


def test_ephemeral_training_prefers_training_resource_when_available() -> None:
    """Kaggle is preferred for training when the snapshot says it is available."""
    disc = cf.cloud_resources()["by_id"]
    kaggle = disc.get("cloud:kaggle")
    if not kaggle or kaggle["status"] != "AVAILABLE":
        pytest.skip("Kaggle is not connected right now")
    r = cf.select_compute({"task": "fine-tune a LoRA adapter",
                           "gpu_required": True, "network_required": True})
    assert r["selected"] == "cloud:kaggle"


def test_gpu_inference_selects_nvidia() -> None:
    r = cf.select_compute({"task": "production inference",
                           "gpu_required": True, "network_required": True})
    assert r["selected"] == "cloud:nvidia"


def test_persistent_gpu_prefers_serving_over_training() -> None:
    r = cf.select_compute({"task": "serve model", "gpu_required": True,
                           "persistent_runtime": True,
                           "network_required": True})
    assert r["selected"] == "cloud:nvidia"


def test_docker_requirement_reports_infeasible_truthfully() -> None:
    r = cf.select_compute({"task": "run integration tests",
                           "docker_required": True})
    if r["selected"] is None:
        assert r["infeasible_reason"], "infeasible selection must state why"
        assert "RESOURCE_UNAVAILABLE" in r["infeasible_reason"]
    else:
        assert "docker" in r["selected"] or "execution" in r["selected"]


def test_every_candidate_records_eligibility_and_reasons() -> None:
    r = cf.select_compute({"task": "anything", "gpu_required": True})
    for entry in r["evaluated"]:
        assert "eligible" in entry
        if not entry["eligible"]:
            assert entry["reasons"], \
                f"{entry['resource_id']} ineligible with no reason"


def test_offline_task_does_not_require_network() -> None:
    r = cf.select_compute({"task": "inspect the project",
                           "network_required": False})
    assert r["selected"] == "local:control-node"


# --------------------------------------------------------------------------- #
# Execution mode
# --------------------------------------------------------------------------- #
def test_execution_mode_uses_isolated_network_snapshot() -> None:
    m = cf.execution_mode()
    assert m["mode"] in {"online", "degraded", "offline"}
    assert isinstance(m["internet_reachable"], bool)
    assert m["local_still_useful"] is True, \
        "lack of Docker must not make JARVIS useless"


def test_degraded_path_lists_real_offline_capabilities() -> None:
    m = cf.execution_mode()
    assert m["degraded_path"]["fallbacks"], "offline fallbacks must be listed"


def test_execution_mode_never_fabricates_cloud() -> None:
    m = cf.execution_mode()
    if not m["internet_reachable"]:
        assert m["mode"] != "online"


# --------------------------------------------------------------------------- #
# Capabilities + endpoints
# --------------------------------------------------------------------------- #
def test_cloud_capabilities_registered_read_only() -> None:
    from research_engine.capability_tools import build_capability_registry
    from research_engine.models import RiskLevel

    by_name = {d["name"]: d for d in build_capability_registry().describe()}
    for cap in ("cloud.status", "cloud.resources", "compute.select",
                "cloud.execution_mode"):
        assert cap in by_name, f"missing {cap}"
        assert by_name[cap]["risk"] == RiskLevel.READ.value
        assert by_name[cap]["parameters"].get("type") == "object"


def test_cloud_capabilities_execute() -> None:
    import asyncio

    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    registry = build_capability_registry()
    ctx = ToolContext(request_id="cf", user_id="u")
    for cap, args in (("cloud.status", {}), ("cloud.resources", {}),
                      ("cloud.execution_mode", {}),
                      ("compute.select", {"task": "analyze a CSV"})):
        res = asyncio.run(registry.invoke(cap, args, ctx))
        assert res.success is True, f"{cap}: {res.error}"
        assert json.loads(res.result)


def test_cloud_routes_exist() -> None:
    src = (ROOT / "jarvis_backend" / "routers" / "control_plane.py").read_text(
        encoding="utf-8")
    for route in ('"/cloud/status"', '"/cloud/compute/select"'):
        assert route in src


def test_fabric_creates_no_persistent_store() -> None:
    """Discovery must not invent a database or provision cloud resources."""
    src = (ROOT / "jarvis_backend" / "cloud_fabric.py").read_text(encoding="utf-8")
    for banned in ("create_engine", "boto3", "google.cloud", "azure",
                   "docker run", "ssh ", "ec2", "run_instances"):
        assert banned not in src, f"cloud fabric must not perform {banned}"
    assert "shell=True" not in src
