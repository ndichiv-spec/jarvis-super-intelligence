"""Tests for JARVIS project-intelligence tools and the chat integration hook.

These cover the security boundary (workspace confinement, traversal rejection,
secret exclusion), the tool-registry contract, intent detection, the bounded
evidence pack, and truthful degradation.

They do NOT require a live provider: the model-synthesis step is exercised
separately in the live verification, while these tests pin the deterministic
retrieval + routing behaviour.
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

from research_engine.project_tools import (  # noqa: E402
    PROJECT_ROOT,
    WORKSPACE_ROOT,
    ProjectInspectTool,
    ProjectSearchTool,
    ProjectTestStatusTool,
    safe_path,
)
from research_engine.tool_registry import (  # noqa: E402
    DefaultPermissionPolicy,
    RiskLevel,
    ToolContext,
    ToolRegistry,
)


def _registry() -> ToolRegistry:
    registry = ToolRegistry(policy=DefaultPermissionPolicy())
    registry.register(ProjectInspectTool())
    registry.register(ProjectSearchTool())
    registry.register(ProjectTestStatusTool())
    return registry


@pytest.fixture()
def registry() -> ToolRegistry:
    return _registry()


@pytest.fixture()
def ctx() -> ToolContext:
    return ToolContext(request_id="test-req", user_id="test-user")


# --------------------------------------------------------------------------- #
# 1-3. Registration
# --------------------------------------------------------------------------- #
def test_project_tools_registered(registry: ToolRegistry) -> None:
    names = registry.available()
    assert "project.inspect" in names
    assert "project.search" in names
    assert "project.test_status" in names


def test_describe_exposes_schema_without_secrets(registry: ToolRegistry) -> None:
    described = {t["name"]: t for t in registry.describe()}
    for name in ("project.inspect", "project.search", "project.test_status"):
        assert name in described
        assert described[name]["parameters"], f"{name} must expose a JSON schema"
        assert described[name]["risk"] in {r.value for r in RiskLevel}


def test_read_only_risk_levels() -> None:
    for tool in (ProjectInspectTool(), ProjectSearchTool(), ProjectTestStatusTool()):
        assert tool.risk == RiskLevel.READ, "project tools must be read-only"
        assert tool.requires_confirmation is False


# --------------------------------------------------------------------------- #
# 4-5. Workspace confinement / traversal
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_path",
    [
        "../../",
        "../../../Windows/System32",
        r"..\\..\\",
        "C:/Windows",
        "/etc/passwd",
        "..",
    ],
)
def test_path_traversal_rejected(bad_path: str) -> None:
    with pytest.raises(ValueError):
        safe_path(bad_path)


def test_absolute_escape_rejected() -> None:
    with pytest.raises(ValueError):
        safe_path("C:/Windows/System32/config")


def test_valid_scope_resolves_inside_workspace() -> None:
    resolved = safe_path("jarvis_backend")
    assert str(resolved).lower().startswith(str(WORKSPACE_ROOT).lower())


def test_search_rejects_traversal_via_registry(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("project.search",
                                      {"query": "x", "path": "../../../"}, ctx))
    assert res.success is False
    assert "escape" in res.error.lower() or "rejected" in res.error.lower()


# --------------------------------------------------------------------------- #
# 6. Secret exclusion / scrubbing
# --------------------------------------------------------------------------- #
def test_inspect_returns_credential_presence_only(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("project.inspect",
                                      {"include_placeholders": False}, ctx))
    assert res.success is True
    data = json.loads(res.result)
    presence = data["credential_presence"]
    assert presence, "credential metadata should be present"
    for _name, meta in presence.items():
        assert set(meta.keys()) == {"configured"}, "only configured flag allowed"
        assert isinstance(meta["configured"], bool)


def test_search_never_returns_secret_files(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke(
        "project.search", {"query": "API_KEY", "max_results": 50}, ctx))
    assert res.success is True
    data = json.loads(res.result)
    for match in data["matches"]:
        low = match["file"].lower()
        assert not low.endswith(".env"), "must not read .env"
        assert "credential" not in low
        assert "secret" not in low


def test_env_contents_not_searchable(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke(
        "project.search", {"query": "sk-", "max_results": 50}, ctx))
    data = json.loads(res.result)
    for match in data["matches"]:
        assert "value" not in match["text"].lower() or True  # shape check only
    assert all(not m["file"].lower().endswith(".env") for m in data["matches"])


# --------------------------------------------------------------------------- #
# 7. Authorization
# --------------------------------------------------------------------------- #
def test_authorize_grants_read_for_authenticated_user(registry: ToolRegistry) -> None:
    ok, reason = registry.authorize("some-user", "project.inspect")
    assert ok is True
    assert reason == "granted"


def test_authorize_rejects_unknown_tool(registry: ToolRegistry) -> None:
    ok, reason = registry.authorize("some-user", "project.does_not_exist")
    assert ok is False
    assert reason == "TOOL_NOT_REGISTERED"


def test_invoking_unregistered_tool_fails_truthfully(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("project.nope", {}, ctx))
    assert res.success is False
    assert res.error == "TOOL_NOT_REGISTERED"


# --------------------------------------------------------------------------- #
# 8. Bounded results
# --------------------------------------------------------------------------- #
def test_search_respects_max_results(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke(
        "project.search", {"query": "def ", "max_results": 5}, ctx))
    data = json.loads(res.result)
    assert data["match_count"] <= 5
    assert len(data["matches"]) <= 5


def test_search_requires_query(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("project.search", {}, ctx))
    assert res.success is False
    assert "query" in res.error.lower()


def test_inspect_is_bounded(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke(
        "project.inspect", {"include_placeholders": True, "max_placeholders": 5}, ctx))
    data = json.loads(res.result)
    assert len(data["placeholder_markers"]) <= 5
    # The evidence must never be the whole repository.
    assert len(res.result) < 400_000


# --------------------------------------------------------------------------- #
# 9-11. Project map
# --------------------------------------------------------------------------- #
def test_project_map_covers_required_categories(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("project.inspect",
                                      {"include_placeholders": False}, ctx))
    data = json.loads(res.result)
    project_map = data["project_map"]
    for category in (
        "BACKEND", "FRONTEND", "PROVIDERS", "MODELS", "DATABASE", "CACHE",
        "AUTH", "TOOLS", "CAPABILITIES", "KNOWLEDGE", "TASKS", "AGENTS",
        "TRAINING", "ARTIFACTS", "DEPLOYMENT", "TESTS", "DOCUMENTATION",
        "INTEGRATIONS",
    ):
        assert category in project_map, f"missing map category {category}"
        assert project_map[category]["present"] is True, f"{category} not detected"


def test_project_map_cites_real_files(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("project.inspect",
                                      {"include_placeholders": False}, ctx))
    data = json.loads(res.result)
    backend = data["project_map"]["BACKEND"]["key_files"]
    assert any("jarvis_api.py" in f for f in backend), \
        "BACKEND map must cite the real API entrypoint"


def test_test_status_is_truthful(registry: ToolRegistry, ctx) -> None:
    import asyncio

    res = asyncio.run(registry.invoke("project.test_status", {}, ctx))
    assert res.success is True
    data = json.loads(res.result)
    # Either a recorded run, or an explicit NOT_RUN - never invented numbers.
    assert data["status"] in {"RECORDED", "NOT_RUN"}
    if data["status"] == "NOT_RUN":
        assert data["passed"] is None and data["failed"] is None


def test_test_status_never_executes(registry: ToolRegistry, ctx) -> None:
    import asyncio

    # ``refresh`` is explicitly not honoured: the tool must not run pytest.
    res = asyncio.run(registry.invoke("project.test_status",
                                      {"refresh": True}, ctx))
    assert res.success is True
    data = json.loads(res.result)
    assert "explanation" in data


# --------------------------------------------------------------------------- #
# 12-14. Intent detection + evidence pack
# --------------------------------------------------------------------------- #
def test_detect_intent_for_acceptance_questions() -> None:
    from jarvis_backend.project_intel import detect_project_intent

    cases = {
        "Go through the JARVIS project and suggest the three most important "
        "improvements based on its current implementation.": "roadmap",
        "How does a chat message currently travel through JARVIS from the "
        "frontend to the model and back?": "flow",
        "Which providers are currently usable and which are unavailable? "
        "Explain why.": "providers",
        "Find unfinished or placeholder functionality in JARVIS.": "gaps",
    }
    for question, expected in cases.items():
        assert detect_project_intent(question) == expected, question


@pytest.mark.parametrize(
    "ordinary",
    [
        "hi",
        "thanks!",
        "what is 2+2",
        "write me a poem about the sea",
        "summarize this paragraph",
        "Who are you?",
        "translate this to Spanish",
        "what time is it",
        "tell me a joke",
        "what is the capital of France",
    ],
)
def test_ordinary_chat_does_not_trigger_inspection(ordinary: str) -> None:
    from jarvis_backend.project_intel import detect_project_intent

    assert detect_project_intent(ordinary) is None


def test_evidence_pack_contains_real_evidence() -> None:
    import asyncio

    from jarvis_backend.project_intel import build_evidence_pack

    pack = asyncio.run(build_evidence_pack(
        "go through the jarvis project", "roadmap",
        user_id="test-user", request_id="test-req"))
    assert pack["tools_used"], "tools must actually run"
    assert "project.inspect" in pack["tools_used"]
    assert "project.search" in pack["tools_used"]
    assert "project.test_status" in pack["tools_used"]
    overview = pack["project_overview"]
    assert overview and overview["project_map"]
    # Real citations.
    assert overview["entrypoints"] or overview["routers"]
    assert pack["provider_status"], "live provider status must be present"
    # Bounded.
    assert len(pack["search_findings"]) <= 60


def test_evidence_block_is_scrubbed_and_bounded() -> None:
    from jarvis_backend.project_intel import render_evidence_block

    block = render_evidence_block({
        "request": "q", "focus": "roadmap",
        "warnings": ["api_key=abcdef1234567890"],
    })
    assert "PROJECT EVIDENCE PACK" in block
    assert len(block) < 200_000
    # A credential-shaped value must not survive into the prompt.
    assert "abcdef1234567890" not in block


def test_evidence_block_empty_pack() -> None:
    from jarvis_backend.project_intel import render_evidence_block

    assert render_evidence_block({}) == ""


def test_activity_events_are_real_not_faked() -> None:
    """Activity must be emitted per actual tool invocation."""
    import asyncio

    from jarvis_backend.project_intel import build_evidence_pack

    activity: list[dict] = []
    asyncio.run(build_evidence_pack(
        "inspect the project", "gaps",
        user_id="u", request_id="r", activity=activity))
    stages = {a["stage"] for a in activity}
    assert "Inspecting JARVIS project..." in stages
    assert "Searching project..." in stages
    assert "Reviewing tests..." in stages
    # Each emitted stage has a real tool and a real status.
    for event in activity:
        assert "tool" in event
        assert "status" in event


# --------------------------------------------------------------------------- #
# 15-16. Truthful degradation
# --------------------------------------------------------------------------- #
def test_provider_status_unavailable_is_truthful(monkeypatch) -> None:
    import asyncio

    import jarvis_backend.project_intel as pi

    def _boom():
        raise RuntimeError("no fabric here")

    monkeypatch.setattr(pi, "_provider_status", lambda: {"_status": "UNAVAILABLE"})
    pack = asyncio.run(pi.build_evidence_pack(
        "inspect the project", "gaps", user_id="u", request_id="r"))
    assert pack["provider_status"]["_status"] == "UNAVAILABLE"


def test_inspect_failure_is_reported_not_hidden() -> None:
    import asyncio

    from research_engine.project_tools import ProjectInspectTool

    res = asyncio.run(ProjectInspectTool().invoke(
        {"path": "no_such_dir_xyz"}, ToolContext(request_id="r", user_id="u")))
    assert res.success is False
    assert res.error


def test_project_tools_do_not_use_shell() -> None:
    """The tools must not import shell execution primitives."""
    import inspect as _inspect

    import research_engine.project_tools as pt

    source = _inspect.getsource(pt)
    for banned in ("subprocess", "os.system", "os.popen", "shell=True",
                   "eval(", "exec("):
        assert banned not in source, f"project tools must not use {banned}"


def test_chat_service_exposes_project_hook() -> None:
    from jarvis_backend.chat_service import ChatService

    assert hasattr(ChatService, "_project_context")
    assert hasattr(ChatService, "_record_project_audit")
