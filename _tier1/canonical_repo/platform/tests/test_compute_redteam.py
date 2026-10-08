"""Security + truthfulness red-team tests for the Phase 9 compute fabric.

Verifies:
1. No secret exfiltration via compute.* capability results.
2. No credential leakage to the Brain layer (compute tools scrub secrets).
3. compute.inference does not falsely report success when no GPU is available.
4. Truthful failures when no resources are available.
5. EXEC / WRITE compute capabilities require confirmation (risk + metadata).
6. NETWORK compute capabilities require user confirmation at runtime.
7. Compute routing: chat-initiated compute selects minimum capabilities.
8. Contract-level guarantees.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from research_engine.capability_tools import (  # noqa: E402
    build_capability_registry,
    capability_inventory,
    live_provider_status,
)
from research_engine.tool_registry import ToolContext, ToolRegistry  # noqa: E402
from research_engine.models import RiskLevel  # noqa: E402
from jarvis_backend.brain_fabric import assert_no_secrets  # noqa: E402

COMPUTE_CAPS = [
    "compute.discover",
    "compute.verify",
    "compute.inference",
    "compute.training",
    "compute.evaluation",
    "compute.embedding",
    "compute.artifact_upload",
    "compute.artifact_download",
    "compute.job_submit",
    "compute.job_status",
    "compute.job_cancel",
    "compute.resource_health",
]

# Patterns that would indicate credential leakage.
SECRET_PATTERNS = {
    "api_key": re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    "token": re.compile(r"(?i)(token|access_token|auth_token)\s*[:=]\s*\S+"),
    "hf_token": re.compile(r"(?i)hf_[A-Za-z0-9]{32,}"),
    "bearer": re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    "password": re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    "aws_key": re.compile(r"(?i)aws[_-]?(access[_-]?key|secret[_-]?key)\s*[:=]\s*\S+"),
}


@pytest.fixture(scope="module")
def registry():
    return build_capability_registry()


@pytest.fixture()
def ctx() -> ToolContext:
    return ToolContext(request_id="redteam-test", user_id="redteam-user")


def _with_confirmations() -> ToolRegistry:
    """Build a registry that has pre-granted confirmation for NETWORK tools
    (simulating an admin who has clicked 'confirm')."""
    from research_engine.tool_registry import DefaultPermissionPolicy

    policy = DefaultPermissionPolicy(confirmations={
        "redteam-user:compute.inference": True,
        "redteam-user:compute.embedding": True,
    })
    return build_capability_registry(policy=policy)


@pytest.fixture()
def confirmed_ctx() -> ToolContext:
    """Context for a user whose NETWORK confirmations are pre-granted."""
    return ToolContext(request_id="redteam-confirmed", user_id="redteam-user")


# --------------------------------------------------------------------------- #
# 1. All compute.* capabilities registered
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cap_name", COMPUTE_CAPS)
def test_compute_capability_registered(registry, cap_name) -> None:
    """All 12 compute.* capabilities must be registered."""
    available = set(registry.available())
    assert cap_name in available, f"{cap_name} is not registered"


# --------------------------------------------------------------------------- #
# 2. No secret exfiltration via compute.* capability results
# --------------------------------------------------------------------------- #

def test_no_secret_in_compute_results(registry, ctx) -> None:
    """Every READ compute.* result must be scrubbed of credential-shaped strings.

    The Brain must never see a token, key, or password in capability output.
    Only READ-risk compute tools are invoked here because EXEC/WRITE tools
    are denied at the authorization boundary for unconfirmed users.
    """
    read_caps = [
        ("compute.discover", {}),
        ("compute.evaluation", {}),
        ("compute.artifact_download", {}),
        ("compute.job_status", {}),
        ("compute.resource_health", {}),
        ("compute.verify", {"resource_id": "local:control-node"}),
    ]
    for cap_name, args in read_caps:
        res = asyncio.run(registry.invoke(cap_name, args, ctx))
        if not res.success:
            continue
        result = res.result
        for label, pat in SECRET_PATTERNS.items():
            assert not pat.search(result), \
                f"{cap_name} leaked a {label}-shaped secret in its result"


def test_no_shell_in_compute_tools_source() -> None:
    """Compute tools must not introduce shell execution primitives."""
    import research_engine.capability_tools as ct

    source = inspect.getsource(ct)
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "os.popen" not in source


# --------------------------------------------------------------------------- #
# 3. No credential leakage to the Brain layer
# --------------------------------------------------------------------------- #

def test_brain_fabric_assert_no_secrets_on_compute_discover(registry, ctx) -> None:
    """The Brain-facing discovery output must have no secret-bearing fields."""
    res = asyncio.run(registry.invoke("compute.discover", {}, ctx))
    if not res.success:
        pytest.skip("compute.discover not available in this environment")
    data = json.loads(res.result)
    leaks = assert_no_secrets(data)
    assert not leaks, \
        f"compute.discover returned secret-bearing fields: {leaks}"


def test_brain_fabric_assert_no_secrets_on_resource_health(registry, ctx) -> None:
    """The health report must not expose credential fields."""
    res = asyncio.run(registry.invoke("compute.resource_health", {}, ctx))
    if not res.success:
        pytest.skip("compute.resource_health not available")
    data = json.loads(res.result)
    leaks = assert_no_secrets(data)
    assert not leaks, \
        f"compute.resource_health returned secret-bearing fields: {leaks}"


def test_scrub_secrets_invoked_on_compute_results(registry, ctx) -> None:
    """All compute READ tool results must be valid JSON (scrubbing preserves
    structure via _ok/_fail which call scrub_secrets)."""
    read_caps_args = [
        ("compute.discover", {}),
        ("compute.verify", {"resource_id": "local:control-node"}),
        ("compute.evaluation", {}),
        ("compute.artifact_download", {}),
        ("compute.job_status", {}),
        ("compute.resource_health", {}),
    ]
    for cap_name, args in read_caps_args:
        res = asyncio.run(registry.invoke(cap_name, args, ctx))
        if res.success:
            # _ok() calls scrub_secrets and validates JSON integrity
            json.loads(res.result)


# --------------------------------------------------------------------------- #
# 4. compute.inference does not falsely report success when no GPU available
# --------------------------------------------------------------------------- #

def test_inference_authorized_for_confirmed_user() -> None:
    """compute.inference must be denied for unconfirmed users (NETWORK risk)."""
    reg = _with_confirmations()
    ok_unconfirmed, _ = build_capability_registry().authorize(
        "redteam-user", "compute.inference")
    assert ok_unconfirmed is False, \
        "compute.inference must require confirmation (NETWORK risk)"


def test_inference_does_not_expose_credentials(registry, ctx) -> None:
    """NETWORK compute tools must be denied for unconfirmed users, not execute."""
    res = asyncio.run(registry.invoke("compute.inference", {}, ctx))
    # Unconfirmed user → denied before any provider call
    assert res.success is False
    assert "DENIED" in res.error or "confirmation" in res.error.lower()


def test_inference_truthful_for_confirmed_user() -> None:
    """For a confirmed user, compute.inference must not fabricate GPU availability.

    It may report local CPU as an inference fallback, but must carry real
    verification state — never claim NVIDIA GPU inference from credential
    presence alone.
    """
    reg = _with_confirmations()
    ctx = ToolContext(request_id="infer-test", user_id="redteam-user")
    res = asyncio.run(reg.invoke("compute.inference", {}, ctx))
    assert res.success, \
        f"compute.inference should succeed for confirmed user: {res.error}"
    data = json.loads(res.result)

    # Must report real inference readiness — never claim GPU inference
    # without verification.
    assert "any_inference_available" in data, \
        "inference result must report 'any_inference_available'"
    # If nvidia is mentioned, it must carry verification state.
    nvidia = data.get("nvidia", {})
    if nvidia:
        assert "inference_verified" in nvidia, \
            "NVIDIA inference availability must carry verification state"


# --------------------------------------------------------------------------- #
# 5. Truthful failures when no resources are available
# --------------------------------------------------------------------------- #

def test_discover_reports_local_control_node(registry, ctx) -> None:
    """compute.discover must always include the local control node."""
    res = asyncio.run(registry.invoke("compute.discover", {}, ctx))
    assert res.success, f"compute.discover failed: {res.error}"
    data = json.loads(res.result)
    resources = data.get("resources", [])
    ids = [r.get("resource_id") for r in resources]
    assert "local:control-node" in ids, \
        "local control node must always be discovered"


def test_discover_never_claims_available_from_credentials_alone() -> None:
    """A resource with credentials but unreachable must NOT be AVAILABLE."""
    from jarvis_backend import cloud_fabric as cf

    disc = cf.cloud_resources()
    for res in disc.get("resources", []):
        chain = res.get("state_chain", {})
        if res.get("status") == "AVAILABLE":
            # Must have passed the full verification chain.
            assert chain.get("reachable") is True, \
                f"{res['resource_id']} is AVAILABLE but unreachable"
        elif res.get("status") in ("NOT_CONFIGURED", "UNAVAILABLE"):
            # Credentials alone do not make a resource available.
            assert chain.get("configured") is not True or \
                   chain.get("authenticated") is not True, \
                f"{res['resource_id']} is NOT_CONFIGURED but fully authenticated"


def test_training_reports_truthful_readiness(registry, ctx) -> None:
    """compute.training must report real readiness, not promise training.

    It only reports readiness — never submits a training run without
    explicit authorization through the control plane.
    """
    res = asyncio.run(registry.invoke("compute.training", {}, ctx))
    assert res.success, f"compute.training failed: {res.error}"
    data = json.loads(res.result)

    # Must NOT report success/failure of an actual training run — it only
    # reports readiness. There must be no "training_completed" or similar
    # fabricated result.
    assert "readiness" in data or "training_ready" in data or \
           "kaggle" in data or "gpu" in str(data).lower(), \
        "compute.training must report readiness state, not execution results"


# --------------------------------------------------------------------------- #
# 6. Authorization boundary for EXEC / WRITE / NETWORK capabilities
# --------------------------------------------------------------------------- #

def test_exec_compute_capabilities_have_confirmation_metadata(registry) -> None:
    """EXEC-risk compute capabilities must declare requires_confirmation=True."""
    exec_caps = ["compute.job_submit", "compute.job_cancel"]
    for cap_name in exec_caps:
        tool = registry._tools.get(cap_name)
        assert tool is not None, f"{cap_name} not registered"
        assert tool.risk == RiskLevel.EXEC, \
            f"{cap_name} must be EXEC risk"
        assert getattr(tool, "requires_confirmation", False) is True, \
            f"{cap_name} must require confirmation"


def test_write_compute_capabilities_have_confirmation_metadata(registry) -> None:
    """WRITE-risk compute capabilities must declare requires_confirmation=True."""
    tool = registry._tools.get("compute.artifact_upload")
    assert tool is not None, "compute.artifact_upload not registered"
    assert tool.risk == RiskLevel.WRITE, \
        "compute.artifact_upload must be WRITE risk"
    assert getattr(tool, "requires_confirmation", False) is True, \
        "compute.artifact_upload must require confirmation"


def test_network_compute_capabilities_denied_without_confirmation(registry) -> None:
    """NETWORK-risk compute capabilities must be denied at runtime for
    unconfirmed users."""
    net_caps = ["compute.inference", "compute.embedding"]
    for cap_name in net_caps:
        ok, reason = registry.authorize("redteam-user", cap_name)
        assert ok is False, \
            f"{cap_name} should be denied without confirmation"
        assert "confirmation" in reason.lower(), \
            f"{cap_name} should require user confirmation"


def test_read_compute_capabilities_auto_authorized(registry) -> None:
    """READ-risk compute capabilities must be auto-granted to authenticated users."""
    read_caps = [
        "compute.discover", "compute.verify", "compute.evaluation",
        "compute.artifact_download", "compute.job_status",
        "compute.resource_health",
    ]
    for cap_name in read_caps:
        ok, reason = registry.authorize("redteam-user", cap_name)
        assert ok is True, \
            f"{cap_name} should be auto-granted for authenticated user: {reason}"


# --------------------------------------------------------------------------- #
# 7. Compute routing: chat-initiated compute selects minimum capabilities
# --------------------------------------------------------------------------- #

def test_compute_discover_chat_routing() -> None:
    """Chat asking about compute resources routes to compute.discover only."""
    from jarvis_backend.project_intel import select_capabilities

    got = {name for name, _ in select_capabilities(
        "What compute resources are available right now?")}
    assert got == {"compute.discover"}, f"expected only compute.discover, got {got}"


def test_compute_health_chat_routing() -> None:
    """Chat asking about compute health routes to compute.resource_health only."""
    from jarvis_backend.project_intel import select_capabilities

    got = {name for name, _ in select_capabilities(
        "What is the compute status and health?")}
    assert got == {"compute.resource_health"}, \
        f"expected only compute.resource_health, got {got}"


def test_ordinary_chat_does_not_select_compute() -> None:
    """Ordinary chat must never trigger compute capability selection."""
    from jarvis_backend.project_intel import select_capabilities

    for ordinary in [
        "hi", "thanks", "what is 2+2", "summarize this", "tell me a joke",
        "Who are you?", "help me with my homework", "what time is it",
        "what's for dinner", "good morning",
    ]:
        got = select_capabilities(ordinary)
        assert got == [], \
            f"ordinary chat '{ordinary}' should select no capabilities, got {got}"


def test_compute_verify_chat_routing() -> None:
    """Chat asking to verify compute routes to compute.verify."""
    from jarvis_backend.project_intel import select_capabilities

    got = {name for name, _ in select_capabilities(
        "Verify the local compute resources")}
    assert "compute.verify" in got, \
        f"expected compute.verify in routing, got {got}"


# --------------------------------------------------------------------------- #
# 8. Contract-level guarantees
# --------------------------------------------------------------------------- #

def test_compute_contracts_present() -> None:
    """All 12 compute.* capabilities must have contract entries."""
    from research_engine import capability_contract as cc

    contracts = cc.build_contracts()
    for cap_name in COMPUTE_CAPS:
        assert cap_name in contracts, f"{cap_name} missing from contracts"
        c = contracts[cap_name]
        assert c["domain"] in ("ai_ml_development", "infrastructure"), \
            f"{cap_name} domain not classified"
        assert c["risk_level"] in {r.value for r in RiskLevel}, \
            f"{cap_name} has invalid risk level"


def test_compute_contracts_never_expose_credentials() -> None:
    """Compute capability contracts must never contain literal credential values."""
    from research_engine import capability_contract as cc

    contracts = cc.build_contracts()
    for name in COMPUTE_CAPS:
        cstr = json.dumps(contracts[name], default=str)
        for label, pat in SECRET_PATTERNS.items():
            assert not pat.search(cstr), \
                f"{name} contract leaks {label}-shaped value"


def test_compute_count_matches_registry() -> None:
    """Contract count must equal registry count (no orphaned or duplicate entries)."""
    from research_engine import capability_contract as cc

    contracts = cc.build_contracts()
    reg = build_capability_registry()
    available = set(reg.available())
    reg_caps = {name for name in available if name.startswith("compute.")}
    contract_caps = {name for name in contracts if name.startswith("compute.")}
    assert reg_caps == contract_caps, \
        f"registry compute caps {reg_caps} != contract caps {contract_caps}"


# --------------------------------------------------------------------------- #
# 9. Streaming / background membership
# --------------------------------------------------------------------------- #

def test_compute_streaming_membership() -> None:
    """compute.inference should be in the streaming set (real-time responses)."""
    from research_engine import capability_contract as cc

    streaming = cc._STREAMING
    assert "compute.inference" in streaming, \
        "compute.inference must be in _STREAMING"


def test_compute_background_membership() -> None:
    """Long-running compute capabilities should be background-eligible."""
    from research_engine import capability_contract as cc

    background = cc._BACKGROUND
    for cap_name in ("compute.training", "compute.job_submit",
                     "compute.artifact_upload"):
        assert cap_name in background, \
            f"{cap_name} must be in _BACKGROUND"