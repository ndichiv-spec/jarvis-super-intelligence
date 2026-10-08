"""Tests for the remote execution host abstraction.

No cloud VM exists, so these tests exercise the contract, requirement
matching, unavailable-host behaviour, authorization/secret isolation and the
MOCK transport for orchestration logic. A MOCK transport is never reported as
remote_execution_verified.
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

from jarvis_backend import remote_host as rh  # noqa: E402
from jarvis_backend.cloud_fabric import cloud_resources, select_compute  # noqa: E402

STATES = ("configured", "authenticated", "reachable", "healthy",
          "resource_verified", "job_verified", "inference_verified")


@pytest.fixture(autouse=True)
def _no_remote_env(monkeypatch):
    for var in (rh.ENV_HOST, rh.ENV_USER, rh.ENV_IDENTITY):
        monkeypatch.delenv(var, raising=False)


# --------------------------------------------------------------------------- #
# Resource contract
# --------------------------------------------------------------------------- #
def test_resource_contract_fields_present() -> None:
    host = rh.discover()
    data = host.to_dict()
    for field in ("resource_id", "provider", "endpoint", "os", "architecture",
                  "cpu", "memory_gb", "gpu", "gpu_memory_gb", "docker",
                  "docker_version", "status", "health", "capabilities",
                  "cost_class", "last_seen"):
        assert field in data, f"contract missing {field}"


def test_unavailable_fields_stay_none() -> None:
    host = rh.discover()
    if host.status == rh.NOT_CONFIGURED:
        for field in ("cpu", "memory_gb", "gpu", "gpu_memory_gb",
                      "docker_version", "endpoint", "storage_gb"):
            assert getattr(host, field) is None, \
                f"{field} must not be invented for an unconfigured host"


def test_unconfigured_host_is_never_available() -> None:
    host = rh.discover()
    assert host.status == rh.NOT_CONFIGURED
    assert host.is_usable() is False
    assert host.reason and rh.ENV_HOST in host.reason


def test_unconfigured_is_non_blocking() -> None:
    assert rh.remote_status()["blocking"] is False


def test_state_vocabulary_is_existing_only() -> None:
    host = rh.discover()
    for key in (host.state_chain or {}):
        assert key in STATES, f"non-canonical state {key!r}"
    assert rh.STATES == STATES


# --------------------------------------------------------------------------- #
# Transports
# --------------------------------------------------------------------------- #
def test_transport_registry_is_extensible() -> None:
    assert "ssh" in rh.TRANSPORTS
    assert "agent_https" in rh.TRANSPORTS
    for cls in rh.TRANSPORTS.values():
        assert issubclass(cls, rh.Transport)


def test_agent_transport_reports_not_implemented() -> None:
    ok, reason = rh.HttpsAgentTransport().available()
    assert ok is False
    assert "no remote worker agent" in reason.lower()


def test_ssh_transport_uses_fixed_argv_no_shell() -> None:
    import inspect

    src = inspect.getsource(rh.SshTransport)
    assert "shell=True" not in src
    assert "BatchMode=yes" in src, "must not allow interactive prompts"
    # The remote command is a single fixed argument, never interpolated.
    assert "run(self, argv: list[str]" in src


def test_no_competing_env_variables() -> None:
    for var in (rh.ENV_HOST, rh.ENV_USER, rh.ENV_IDENTITY, rh.ENV_TIMEOUT):
        assert var.startswith("JARVIS_DOCKER_REMOTE_"), var


# --------------------------------------------------------------------------- #
# Verification / test job
# --------------------------------------------------------------------------- #
def test_verify_job_without_host_runs_nothing() -> None:
    result = rh.verify_job()
    assert result["ran"] is False
    assert result["status"] == "NOT_CONFIGURED"
    assert result["blocking"] is False


def test_verify_job_reports_real_exit_code_when_run(monkeypatch) -> None:
    """MOCK transport: proves orchestration only, never real verification."""
    calls: list[list[str]] = []

    class MockTransport(rh.Transport):
        name = "mock"

        def __init__(self, host="", user="", identity=None, timeout=20):
            self.host = host

        def available(self):
            return True, "mock"

        def run(self, argv, timeout):
            calls.append(argv)
            return 0, "JARVIS_REMOTE_EXECUTION_OK\n", ""

    monkeypatch.setenv(rh.ENV_HOST, "mock-host:22")
    monkeypatch.setattr(rh, "SshTransport", MockTransport)
    result = rh.verify_job()
    assert result["ran"] is True
    assert result["exit_code"] == 0
    assert "JARVIS_REMOTE_EXECUTION_OK" in result["stdout"]
    assert calls, "MOCK transport must have been exercised"
    # The mock must never be reported as real verification.
    assert result["note"], "result must disclose that mocks are not verification"
    assert "MOCK" in result["note"].upper()


def test_failed_exit_code_is_not_verified(monkeypatch) -> None:
    class FailingTransport(rh.Transport):
        name = "mock"

        def __init__(self, host="", user="", identity=None, timeout=20):
            self.host = host

        def available(self):
            return True, "mock"

        def run(self, argv, timeout):
            return 1, "", "permission denied"

    monkeypatch.setenv(rh.ENV_HOST, "mock-host:22")
    monkeypatch.setattr(rh, "SshTransport", FailingTransport)
    result = rh.verify_job()
    assert result["status"] == "FAILED"
    assert result["exit_code"] == 1


def test_unreachable_host_is_never_available(monkeypatch) -> None:
    """A configured but unreachable host must not report AVAILABLE."""
    monkeypatch.setenv(rh.ENV_HOST, "203.0.113.1:22")  # TEST-NET-3, unroutable
    host = rh.discover()
    assert host.status == rh.UNREACHABLE
    assert host.is_usable() is False
    assert host.reason
    assert host.state_chain.get("configured") is True
    assert host.state_chain.get("authenticated") is not True


# --------------------------------------------------------------------------- #
# Requirement matching
# --------------------------------------------------------------------------- #
def test_unusable_host_fails_every_requirement() -> None:
    host = rh.discover()
    ok, reasons = rh.meets_requirements(host, {})
    assert ok is False
    assert reasons


def test_docker_requirement_rejected_without_host() -> None:
    host = rh.discover()
    ok, reasons = rh.meets_requirements(host, {"docker_required": True})
    assert ok is False
    assert any("docker" in r.lower() for r in reasons)


def test_gpu_requirement_rejected_without_host() -> None:
    host = rh.discover()
    ok, reasons = rh.meets_requirements(host, {"gpu_required": True})
    assert ok is False


def test_meets_requirements_on_verified_mock_host() -> None:
    """MOCK: validates matching logic only, not a real host."""
    host = rh.RemoteExecutionHost(
        status=rh.AVAILABLE, os="Linux", cpu_cores=8, memory_gb=16.0,
        docker=True, gpu="mock-gpu", gpu_memory_gb=24.0,
        state_chain={"configured": True, "authenticated": True,
                     "reachable": True, "resource_verified": True},
    )
    assert host.is_usable() is True
    ok, why = rh.meets_requirements(host, {"docker_required": True,
                                            "gpu_required": True,
                                            "gpu_memory_required": 24,
                                            "cpu_required": 4,
                                            "memory_required": 8})
    assert ok is True, why
    ok, why = rh.meets_requirements(host, {"gpu_memory_required": 80})
    assert ok is False
    assert any("gpu_memory" in r for r in why)


# --------------------------------------------------------------------------- #
# compute.select integration
# --------------------------------------------------------------------------- #
def test_remote_host_appears_in_resource_inventory() -> None:
    ids = {r["resource_id"] for r in cloud_resources()["resources"]}
    assert "remote_execution_host" in ids


def test_remote_host_never_available_without_config() -> None:
    entry = next(r for r in cloud_resources()["resources"]
                 if r["resource_id"] == "remote_execution_host")
    assert entry["status"] == rh.NOT_CONFIGURED
    assert entry["blocking"] is False
    assert entry["capabilities"] == []


@pytest.mark.parametrize(
    "requirements,expected",
    [
        ({"task": "analyze a small CSV file"}, "local:control-node"),
        ({"task": "production inference", "gpu_required": True,
          "network_required": True}, "cloud:nvidia"),
    ],
)
def test_existing_routing_unchanged(requirements, expected) -> None:
    assert select_compute(requirements)["selected"] == expected


def test_gpu_training_routes_to_a_verified_gpu_resource() -> None:
    """GPU training must reach a real GPU provider, not the laptop.

    An integrated display GPU must never satisfy a GPU requirement.
    """
    r = select_compute({"task": "fine-tune a LoRA adapter",
                        "gpu_required": True, "network_required": True})
    assert r["selected"] is not None
    assert r["selected"] != "local:control-node", \
        "an integrated GPU must not satisfy gpu_required"
    assert r["local_viable"] is False
    assert "GPU" in (r["local_block_reason"] or "")


def test_integrated_gpu_is_not_a_compute_gpu() -> None:
    from jarvis_backend.cloud_fabric import _is_compute_gpu

    assert _is_compute_gpu("Intel(R) HD Graphics 520") is False
    assert _is_compute_gpu("Sharing Monitor; Intel(R) HD Graphics 520") is False
    assert _is_compute_gpu("Microsoft Basic Display Adapter") is False
    assert _is_compute_gpu(None) is False
    assert _is_compute_gpu("NVIDIA RTX 4090") is True


def test_docker_requirement_stays_resource_unavailable() -> None:
    r = select_compute({"task": "run integration tests",
                        "docker_required": True})
    assert r["selected"] is None
    assert "RESOURCE_UNAVAILABLE" in r["infeasible_reason"]


# --------------------------------------------------------------------------- #
# Cost controls + deployment contracts
# --------------------------------------------------------------------------- #
def test_cost_controls_forbid_auto_provisioning() -> None:
    cc = rh.remote_status()["cost_controls"]
    assert cc["auto_start"] is False
    assert cc["auto_provision"] is False
    assert "running" in cc["lifecycle_states"]
    assert "terminated" in cc["lifecycle_states"]


def test_brain_and_browser_not_deployed() -> None:
    d = rh.remote_status()["deployment_contracts"]
    assert d["brain"]["deployed"] is False
    assert d["browser_worker"]["deployed"] is False
    assert d["job_worker"]["deployed"] is False


def test_no_credentials_exposed() -> None:
    import re

    blob = json.dumps(rh.remote_status())
    for pattern in (r"hf_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{16,}",
                    r"nvapi-[A-Za-z0-9]{16,}", "PRIVATE KEY", "Bearer "):
        assert re.search(pattern, blob) is None


def test_module_provisions_nothing() -> None:
    src = (ROOT / "jarvis_backend" / "remote_host.py").read_text(encoding="utf-8")
    for banned in ("boto3", "google.cloud", "azure", "create_instances",
                   "run_instances", "ssh-keygen", "scp ", "rsync "):
        assert banned not in src, f"remote_host must not perform {banned}"
    assert "shell=True" not in src


# --------------------------------------------------------------------------- #
# Capabilities + routes
# --------------------------------------------------------------------------- #
def test_remote_capabilities_registered_read_only() -> None:
    from research_engine.capability_tools import build_capability_registry
    from research_engine.models import RiskLevel

    by_name = {d["name"]: d for d in build_capability_registry().describe()}
    for cap in ("remote.compute.status", "remote.compute.health",
                "remote.compute.resources", "remote.compute.verify",
                "docker.remote.status", "docker.remote.images",
                "docker.remote.containers", "docker.remote.logs",
                "docker.remote.health"):
        assert cap in by_name, f"missing {cap}"
        assert by_name[cap]["risk"] == RiskLevel.READ.value
        assert by_name[cap]["parameters"].get("type") == "object"


def test_remote_capabilities_execute_without_host() -> None:
    import asyncio

    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    registry = build_capability_registry()
    ctx = ToolContext(request_id="rh", user_id="u")
    for cap in ("remote.compute.status", "remote.compute.health",
                "remote.compute.resources", "remote.compute.verify",
                "docker.remote.status"):
        res = asyncio.run(registry.invoke(cap, {}, ctx))
        assert res.success is True, f"{cap}: {res.error}"
        assert json.loads(res.result)


def test_remote_routes_exist() -> None:
    src = (ROOT / "jarvis_backend" / "routers" / "control_plane.py").read_text(
        encoding="utf-8")
    for route in ('"/remote/status"', '"/remote/resources"', '"/remote/verify"'):
        assert route in src
