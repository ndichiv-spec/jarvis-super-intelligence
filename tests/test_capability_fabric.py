"""Tests for Capability Fabric v1.

Verifies the capability inventory is truthful, that every capability passes the
EXISTING ToolRegistry authorization + scrubbing boundary, that routing selects
the minimum capability set, and that failures stay truthful.
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

from research_engine.capability_tools import (  # noqa: E402
    AVAILABLE,
    NOT_CONFIGURED,
    UNAVAILABLE,
    build_capability_registry,
    capability_inventory,
    live_provider_status,
)
from research_engine.models import RiskLevel  # noqa: E402
from research_engine.tool_registry import ToolContext  # noqa: E402

EXPECTED = {
    "project.inspect", "project.search", "project.test_status",
    "provider.status", "model.status", "job.status", "artifact.inspect",
    "files.read", "files.search", "docker.status",
    "github.inspect", "github.search",
}


@pytest.fixture(scope="module")
def registry():
    return build_capability_registry()


@pytest.fixture()
def ctx() -> ToolContext:
    return ToolContext(request_id="cap-test", user_id="cap-user")


# --------------------------------------------------------------------------- #
# Registration / discovery / schema
# --------------------------------------------------------------------------- #
def test_required_capabilities_registered(registry) -> None:
    available = set(registry.available())
    missing = EXPECTED - available
    assert not missing, f"missing capabilities: {missing}"


def test_every_capability_exposes_canonical_schema(registry) -> None:
    for d in registry.describe():
        assert d["name"], "capability must have a name"
        assert d["description"], f"{d['name']} must describe itself"
        assert isinstance(d["parameters"], dict), \
            f"{d['name']} must expose an input schema"
        assert d["parameters"].get("type") == "object", \
            f"{d['name']} schema must be an object"
        assert d["risk"] in {r.value for r in RiskLevel}


def test_no_shell_gateway_in_capability_tools() -> None:
    import inspect as _inspect

    import research_engine.capability_tools as ct

    source = _inspect.getsource(ct)
    # subprocess is permitted ONLY with an explicit argv and shell=False.
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "os.popen" not in source
    assert "shell=False" in source, "subprocess must be explicitly non-shell"


def test_risk_levels_are_conservative(registry) -> None:
    by_name = {d["name"]: d for d in registry.describe()}
    for read_only in ("project.inspect", "project.search", "provider.status",
                      "model.status", "job.status", "artifact.inspect",
                      "files.read", "files.search"):
        assert by_name[read_only]["risk"] == RiskLevel.READ.value
    assert by_name["docker.status"]["risk"] == RiskLevel.EXEC.value
    for net in ("github.inspect", "github.search"):
        assert by_name[net]["risk"] == RiskLevel.NETWORK.value
        assert by_name[net]["requires_confirmation"] is True, \
            "NETWORK capabilities must keep confirmation"


# --------------------------------------------------------------------------- #
# Truthful inventory
# --------------------------------------------------------------------------- #
def test_inventory_states_are_from_known_set() -> None:
    valid = {AVAILABLE, "DEGRADED", UNAVAILABLE, "OFFLINE", NOT_CONFIGURED}
    inv = capability_inventory()
    assert inv
    for name, meta in inv.items():
        assert meta["state"] in valid, f"{name} has bogus state {meta['state']}"
        assert meta.get("risk") in {r.value for r in RiskLevel}


def test_inventory_covers_expected_capabilities() -> None:
    inv = capability_inventory()
    missing = EXPECTED - set(inv)
    assert not missing, f"inventory omits: {missing}"


def test_unavailable_capability_is_not_claimed_available() -> None:
    """Docker must never be AVAILABLE when the CLI is absent."""
    inv = capability_inventory()
    docker = inv["docker.status"]
    if docker["state"] == AVAILABLE:
        import shutil
        assert shutil.which("docker"), \
            "docker.status AVAILABLE without a docker binary is a lie"


def test_github_not_configured_without_token(monkeypatch) -> None:
    import research_engine.capability_tools as ct

    for var in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    inv = ct.capability_inventory()
    assert inv["github.inspect"]["state"] == NOT_CONFIGURED
    assert inv["github.search"]["state"] == NOT_CONFIGURED


@pytest.mark.integration
@pytest.mark.live_provider
def test_provider_status_is_live_not_static(live_provider_credentials) -> None:
    status = live_provider_status()
    assert status, "provider status must return real data"
    if "_error" in status:
        pytest.skip(f"provider fabric unavailable: {status['_error']}")
    for pid, meta in status.items():
        if pid.startswith("_"):
            continue
        assert "available" in meta
        assert "configured" in meta


# --------------------------------------------------------------------------- #
# Authorization boundary
# --------------------------------------------------------------------------- #
def test_read_capabilities_authorized_for_authenticated_user(registry) -> None:
    for name in ("project.inspect", "provider.status", "job.status",
                 "artifact.inspect", "model.status", "files.search"):
        ok, reason = registry.authorize("cap-user", name)
        assert ok is True, f"{name} denied: {reason}"


def test_network_capability_requires_confirmation(registry) -> None:
    ok, reason = registry.authorize("cap-user", "github.inspect")
    assert ok is False
    assert reason == "requires_user_confirmation"


def test_unknown_capability_denied(registry) -> None:
    ok, reason = registry.authorize("cap-user", "capability.does_not_exist")
    assert ok is False and reason == "TOOL_NOT_REGISTERED"


def test_unauthorized_invocation_is_denied_not_executed(registry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("github.inspect", {"repo": "a/b"}, ctx))
    assert res.success is False
    assert "TOOL_DENIED" in res.error


# --------------------------------------------------------------------------- #
# Real execution
# --------------------------------------------------------------------------- #
def test_provider_status_executes(registry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("provider.status", {}, ctx))
    assert res.success is True
    data = json.loads(res.result)
    assert "providers" in data


def test_job_status_reports_real_empty_state(registry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("job.status", {}, ctx))
    assert res.success is True
    data = json.loads(res.result)
    if data.get("count") == 0:
        assert "note" in data, "empty job list must be explained, not implied"


def test_artifact_status_executes(registry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("artifact.inspect", {}, ctx))
    assert res.success is True
    assert "items" in json.loads(res.result)


def test_docker_status_truthful_when_absent(registry, ctx) -> None:
    import asyncio
    import shutil

    res = asyncio.run(registry.invoke("docker.status", {}, ctx))
    assert res.success is True
    data = json.loads(res.result)
    if not shutil.which("docker"):
        assert data["state"] == UNAVAILABLE
        assert "not installed" in data["reason"].lower() or \
            "not found" in data["reason"].lower()
        # Docker must be reported as optional, never as a pipeline blocker.
        assert data.get("impact"), "absence must state its impact"


def test_files_read_rejects_traversal(registry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("files.read", {"path": "../../../"}, ctx))
    assert res.success is False


def test_files_read_refuses_env(registry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("files.read", {"path": ".env"}, ctx))
    assert res.success is False
    assert "secret" in res.error.lower()


def test_files_search_bounded(registry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke(
        "files.search", {"query": "gateway", "max_results": 5}, ctx))
    data = json.loads(res.result)
    assert data["count"] <= 5


# --------------------------------------------------------------------------- #
# Routing: minimum capability set
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "question,expected",
    [
        ("What JARVIS jobs are currently running?", {"job.status"}),
        ("What model artifacts does JARVIS currently know about?",
         {"artifact.inspect"}),
        ("Check JARVIS provider health", {"provider.status"}),
        ("Which providers are actually usable right now?", {"provider.status"}),
        ("Are the docker containers running?", {"docker.status"}),
    ],
)
def test_capability_routing_selects_minimum(question, expected) -> None:
    from jarvis_backend.project_intel import select_capabilities

    got = {name for name, _ in select_capabilities(question)}
    assert got == expected


@pytest.mark.parametrize(
    "ordinary",
    ["hi", "thanks", "what is 2+2", "summarize this", "tell me a joke",
     "Who are you?", "help me with my homework", "what time is it"],
)
def test_ordinary_chat_selects_no_capabilities(ordinary) -> None:
    from jarvis_backend.project_intel import (
        detect_project_intent,
        select_capabilities,
    )

    assert select_capabilities(ordinary) == []
    assert detect_project_intent(ordinary) is None


def test_capability_request_does_not_trigger_repo_scan() -> None:
    """A jobs question must not pay for a full project inspection."""
    import asyncio

    from jarvis_backend.project_intel import build_evidence_pack

    pack = asyncio.run(build_evidence_pack(
        "What JARVIS jobs are currently running?", "capability",
        user_id="u", request_id="r"))
    assert "job.status" in pack["tools_used"]
    assert "project.inspect" not in pack["tools_used"]
    assert pack["project_overview"] is None
    assert pack.get("job_status") is not None


def test_evidence_pack_includes_capability_inventory() -> None:
    import asyncio

    from jarvis_backend.project_intel import build_evidence_pack

    pack = asyncio.run(build_evidence_pack(
        "Check JARVIS provider health", "capability",
        user_id="u", request_id="r"))
    assert pack["capability_inventory"], "inventory must reach the model"
    assert pack["provider_status"] is not None


# --------------------------------------------------------------------------- #
# Failure honesty
# --------------------------------------------------------------------------- #
def test_malformed_request_fails_truthfully(registry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("files.read", {}, ctx))
    assert res.success is False
    assert res.error


def test_missing_required_argument_not_guessed() -> None:
    import asyncio

    from jarvis_backend.project_intel import build_evidence_pack

    pack = asyncio.run(build_evidence_pack(
        "look at the github repository", "capability",
        user_id="u", request_id="r"))
    # No repo could be extracted -> the capability is skipped with a warning,
    # never invoked with a fabricated argument.
    if "github.inspect" not in pack["tools_used"]:
        assert any("github" in w for w in pack["warnings"])


def test_tool_exception_is_reported_not_hidden(registry, ctx, monkeypatch) -> None:
    import asyncio

    from research_engine.capability_tools import ProviderStatusTool

    def boom():
        raise RuntimeError("fabric exploded")

    monkeypatch.setattr(
        "research_engine.capability_tools.live_provider_status", boom)
    res = asyncio.run(ProviderStatusTool().invoke({}, ctx))
    assert res.success is False
    assert "fabric exploded" in res.error


def test_no_secret_in_capability_results(registry, ctx) -> None:
    import asyncio

    for cap, args in (("provider.status", {}), ("job.status", {}),
                      ("artifact.inspect", {}), ("model.status", {})):
        res = asyncio.run(registry.invoke(cap, args, ctx))
        if not res.success:
            continue
        assert "sk-" not in res.result, f"{cap} leaked an API key"
        assert "hf_" not in res.result, f"{cap} leaked a HF token"


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def test_chat_service_audits_capabilities() -> None:
    from jarvis_backend.chat_service import ChatService

    assert hasattr(ChatService, "_record_project_audit")


def test_project_intelligence_still_green() -> None:
    """The project-intelligence hook must remain wired."""
    from jarvis_backend.chat_service import ChatService

    assert hasattr(ChatService, "_prepare_system")
    assert hasattr(ChatService, "_project_context")
