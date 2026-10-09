from __future__ import annotations

import asyncio
import os

import pytest

from jarvis_backend import chat_service as chat_module
from jarvis_backend.world_resolver import (
    ExecutionSelection,
    WorldResolverAdapter,
    has_prior_media_results,
    render_media_results,
    render_world_results,
    resolve_execution_surface,
    resolve_media_followup,
    resolve_presentation,
    resolve_result_followup,
    resolve_world_intent,
)


def test_media_request_resolves_to_bounded_web_search():
    intent = resolve_world_intent("JARVIS, I want to watch Avengers movies.")

    assert intent is not None
    assert intent.kind == "media.discovery"
    assert intent.subject == "Avengers"
    assert intent.operation == "media.discovery"
    assert intent.query == "Avengers movies official streaming availability where to watch"


def test_non_media_conversation_does_not_resolve():
    assert resolve_world_intent("Tell me a joke.") is None
    assert resolve_world_intent("Watch the server logs.") is None


def test_unregistered_playback_is_resolved_as_unsupported_not_discovery():
    intent = resolve_world_intent("I want to play Avengers movie on Netflix.")
    assert intent is not None
    assert intent.operation == "media.playback"

    from research_engine.capability_contract import build_contracts
    from research_engine.capability_tools import build_capability_registry

    registry = build_capability_registry()
    contracts = build_contracts(registry, inventory={})
    selection = resolve_execution_surface(
        intent.operation, registry, contracts, user_id="user-1",
        permissions={"web:read"},
    )
    assert selection.status == "unavailable"
    assert "No registered execution surface" in selection.reason

    adapter = WorldResolverAdapter(intent, selection)
    output = asyncio.run(adapter.propose(
        type("Input", (), {"request": "Play Avengers movie on Netflix."})(),
        None,
    ))
    assert output.capability_requests == []
    assert output.confidence_state.value == "INSUFFICIENT_EVIDENCE"


def test_registered_web_and_workspace_operations_resolve_from_capability_metadata():
    web_intent = resolve_world_intent(
        "Research the latest JARVIS runtime event persistence options."
    )
    workspace_intent = resolve_world_intent(
        "Search this JARVIS project for runtime event persistence."
    )

    assert web_intent is not None
    assert web_intent.operation == "web.search"
    assert web_intent.query == "the latest JARVIS runtime event persistence options"
    assert workspace_intent is not None
    assert workspace_intent.operation == "workspace.search"
    assert workspace_intent.query == "runtime event persistence"
    assert workspace_intent.result_renderer == "workspace_matches"


def test_registered_workspace_surface_operates_offline_and_presents_observed_matches():
    import json

    from research_engine.capability_contract import build_contracts
    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    registry = build_capability_registry()
    contracts = build_contracts(
        registry,
        inventory={"project.search": {"state": "AVAILABLE"}},
    )
    intent = resolve_world_intent(
        "Search this JARVIS project for class ProjectSearchTool.", contracts,
    )
    assert intent is not None
    selection = resolve_execution_surface(
        intent.operation,
        registry,
        contracts,
        user_id="local-user",
        permissions={"project:read"},
        network_available=False,
    )
    assert selection.status == "selected"
    assert selection.capability_id == "project.search"
    assert selection.execution_surface == "core_workspace"

    result = asyncio.run(registry.invoke(
        selection.capability_id,
        {
            "query": intent.query,
            "path": "research_engine",
            "max_results": 10,
        },
        ToolContext(
            user_id="local-user",
            permissions={"project:read"},
            request_id="workspace-search-request",
        ),
    ))
    assert result.success
    payload = json.loads(result.result)
    assert payload["match_count"] > 0

    message, sources = render_world_results(
        intent, result.artifacts,
        evidence=[{"success": True, "result": result.result}],
    )
    assert "I searched the configured JARVIS workspace" in message
    assert "project_tools.py" in message
    assert sources == []


def test_resolver_requires_verified_service_authentication_when_declared():
    class Registry:
        def authorize(self, *args, **kwargs):
            return True, "granted"

    contract = {
        "operations": ["service.inspect"],
        "operation_arguments": {"service.inspect": {"query": "$query"}},
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "availability": "AVAILABLE",
        "execution_surface": "service_api",
        "observability": "audit",
        "authentication_required": True,
        "service_dependencies": ["mail_service"],
    }
    contracts = {"mail.inspect": contract}

    assert resolve_execution_surface(
        "service.inspect", Registry(), contracts, user_id="user-1",
    ).status == "unavailable"
    selected = resolve_execution_surface(
        "service.inspect",
        Registry(),
        contracts,
        user_id="user-1",
        authenticated_services={"mail_service"},
    )
    assert selected.status == "selected"
    assert selected.capability_id == "mail.inspect"


def test_contract_permissions_are_enforced_by_the_invocation_registry():
    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import DefaultPermissionPolicy

    registry = build_capability_registry(
        policy=DefaultPermissionPolicy(
            confirmations={"user-1:github.search": True},
        ),
    )
    allowed, reason = registry.authorize(
        "user-1", "github.search", permissions=set(),
    )
    assert not allowed
    assert reason == "PERMISSION_DENIED:github:read"
    assert registry.authorize(
        "user-1", "project.search", permissions=set(),
    ) == (False, "PERMISSION_DENIED:project:read")
    assert registry.authorize(
        "user-1", "project.search", permissions={"project:read"},
    )[0]


def test_chat_reports_unsupported_playback_without_invoking_a_tool(client, auth_headers):
    response = client.post(
        "/api/chat",
        json={
            "session_id": "unsupported-playback-session",
            "client_message_id": "unsupported-playback-request",
            "message": "Play Avengers movie on Netflix.",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["message"].startswith("I couldn't perform media.playback")
    assert "No registered execution surface" in reply["message"]
    assert reply["sources"] == []
    assert reply["tool_calls"][0]["status"] == "failed"

    from jarvis_backend.routers import commands

    command = commands._commands()[reply["runtime_command_id"]]
    assert command["selected_capability_id"] is None
    assert command["resolution_status"] == "unavailable"


def test_canonical_request_id_reaches_tool_context_as_correlation_id():
    from jarvis_brain.orchestrator import BrainOrchestrator

    orchestrator = object.__new__(BrainOrchestrator)
    orchestrator.permissions = set()
    orchestrator.user_id = "user-1"
    orchestrator.principal = {"id": "user-1"}
    orchestrator.request_id = "http-request-1"

    context = orchestrator._tool_context()

    assert context.request_id != "http-request-1"
    assert context.correlation_id == "http-request-1"


def test_world_adapter_proposes_only_live_search_with_evidence_condition():
    intent = resolve_world_intent("Find Avengers movies.")
    assert intent is not None
    adapter = WorldResolverAdapter(
        intent,
        ExecutionSelection(
            operation="media.discovery",
            status="selected",
            capability_id="search_web",
            execution_surface="browser",
            contract={
                "operation_arguments": {
                    "media.discovery": {
                        "query": "$query",
                        "max_results": 8,
                        "extract": False,
                    },
                },
            },
        ),
    )
    output = asyncio.run(adapter.propose(type("Input", (), {"request": "Find Avengers movies."})(), None))

    assert [request.capability for request in output.capability_requests] == ["search_web"]
    assert output.capability_requests[0].args["query"] == intent.query
    assert output.completion_conditions[0].type == "source_observed"


def test_execution_resolver_selects_best_authorized_surface_without_browser_bias():
    class Registry:
        def authorize(self, user_id, capability_id, **kwargs):
            return capability_id != "denied.search", "denied"

    contracts = {
        "browser.search": {
            "operations": ["media.discovery"],
            "operation_arguments": {"media.discovery": {"query": "$query"}},
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "availability": "AVAILABLE",
            "health": "degraded",
            "execution_surface": "browser",
            "network_requirements": "required",
            "endpoint_requirements": [],
            "cost_model": "network_read",
            "latency_ms": 500,
            "observability": "audit",
        },
        "api.search": {
            "operations": ["media.discovery"],
            "operation_arguments": {"media.discovery": {"term": "$query"}},
            "input_schema": {
                "type": "object",
                "properties": {"term": {"type": "string"}},
                "required": ["term"],
            },
            "availability": "AVAILABLE",
            "health": "healthy",
            "execution_surface": "direct_api",
            "network_requirements": "required",
            "endpoint_requirements": [],
            "cost_model": "network_read",
            "latency_ms": 100,
            "observability": "audit",
        },
        "denied.search": {
            "operations": ["media.discovery"],
            "operation_arguments": {"media.discovery": {"query": "$query"}},
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "availability": "AVAILABLE",
            "health": "healthy",
            "execution_surface": "connector",
            "network_requirements": "required",
            "endpoint_requirements": [],
            "cost_model": "network_read",
            "latency_ms": 1,
            "observability": "audit",
        },
    }

    selection = resolve_execution_surface(
        "media.discovery",
        Registry(),
        contracts,
        user_id="user-1",
        permissions={"web:read"},
    )

    assert selection.status == "selected"
    assert selection.capability_id == "api.search"
    assert selection.execution_surface == "direct_api"
    assert selection.network_state == "unknown"
    assert [item.capability_id for item in selection.alternatives] == [
        "browser.search",
    ]

    intent = resolve_world_intent("Find Avengers movies.")
    assert intent is not None
    chosen = []
    adapter = WorldResolverAdapter(intent, selection, on_select=chosen.append)
    brain_input = type("Input", (), {"request": "Find Avengers movies."})()
    first = asyncio.run(adapter.propose(brain_input, None))
    second = asyncio.run(adapter.propose(brain_input, None))

    assert first.capability_requests[0].capability == "api.search"
    assert first.capability_requests[0].args == {"term": intent.query}
    assert second.capability_requests[0].capability == "browser.search"
    assert [item.capability_id for item in chosen] == [
        "api.search", "browser.search",
    ]


def test_execution_resolver_reports_unavailable_when_network_is_offline():
    class Registry:
        def authorize(self, *args, **kwargs):
            return True, "granted"

    contracts = {
        "api.search": {
            "operations": ["media.discovery"],
            "operation_arguments": {"media.discovery": {"query": "$query"}},
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "availability": "AVAILABLE",
            "health": "healthy",
            "execution_surface": "direct_api",
            "network_requirements": "required",
            "endpoint_requirements": [],
            "cost_model": "network_read",
            "observability": "audit",
        },
    }

    selection = resolve_execution_surface(
        "media.discovery",
        Registry(),
        contracts,
        user_id="user-1",
        network_available=False,
    )

    assert selection.status == "unavailable"
    assert selection.network_state == "offline"
    assert "network connection" in selection.reason


def test_source_observed_completion_requires_public_https_artifact():
    from jarvis_brain.orchestrator import BrainOrchestrator
    from research_engine.models import ToolResult

    condition = type("Condition", (), {"type": "source_observed"})()
    no_sources = ToolResult(
        tool_id="test", name="search", success=True, result="no results",
        artifacts=[{"title": "Local result", "url": "https://127.0.0.1/private"}],
    )
    public_source = ToolResult(
        tool_id="test", name="search", success=True,
        artifacts=[{"title": "Source", "url": "https://example.com/page"}],
    )
    orchestrator = object.__new__(BrainOrchestrator)

    assert orchestrator._evaluate_completion([condition], [no_sources]) == ""
    assert orchestrator._evaluate_completion(
        [condition], [public_source],
    ) == "source_observed"


def test_registered_web_capability_declares_resolver_metadata():
    from research_engine.capability_contract import build_contracts
    from research_engine.capability_tools import build_capability_registry

    contract = build_contracts(build_capability_registry())["search_web"]

    assert contract["execution_surface"] == "http_browser_engine"
    assert "media.discovery" in contract["operations"]
    assert contract["network_requirements"] == "required"
    assert contract["data_classification"] == "public"
    assert contract["requires_confirmation"] is True
    assert contract["operation_arguments"]["media.discovery"]["query"] == "$query"
    assert contract["health"] == "unknown"
    assert contract["latency_ms"] is None
    assert contract["cost_model"] == "unknown"
    assert contract["operation_output_requirements"]["media.discovery"] == [
        "artifacts.url", "artifacts.title",
    ]

    workspace = build_contracts(
        build_capability_registry(),
        inventory={"project.search": {"state": "AVAILABLE"}},
    )["project.search"]
    assert workspace["execution_surface"] == "core_workspace"
    assert workspace["input_schema"]["properties"]["query"]["type"] == "string"
    assert workspace["output_schema"]["properties"]["result"]["type"] == "string"
    assert workspace["required_permissions"] == ["project:read"]


def test_registered_intent_metadata_drives_non_media_operation_resolution():
    contracts = {
        "catalog.lookup": {
            "operation_intents": {
                "catalog.lookup": {
                    "semantic_type": "catalog.lookup",
                    "match_patterns": [r"\blook\s+up\b", r"\bcatalog\b"],
                    "subject_pattern": r"look up (?P<subject>.+) in the catalog\.?",
                    "query_template": "catalog:{subject}",
                },
            },
        },
    }

    intent = resolve_world_intent("Look up warp cores in the catalog.", contracts)

    assert intent is not None
    assert intent.kind == "catalog.lookup"
    assert intent.operation == "catalog.lookup"
    assert intent.subject == "warp cores"
    assert intent.query == "catalog:warp cores"


def test_media_results_only_render_public_https_sources():
    intent = resolve_world_intent("watch Avengers movies")
    assert intent is not None
    message, sources = render_media_results(intent, [
        {"title": "Official page", "url": "https://www.example.com/avengers", "snippet": "Info"},
        {"title": "Unsafe local", "url": "https://127.0.0.1/private", "snippet": "No"},
        {"title": "Unencrypted", "url": "http://example.com/watch", "snippet": "No"},
        {"title": "Bad port", "url": "https://example.com:444/page", "snippet": "No"},
    ])

    assert sources == ["https://www.example.com/avengers"]
    assert "[Official page](https://www.example.com/avengers)" in message
    assert "I have not started playback." in message
    assert "127.0.0.1" not in message
    assert "playback is not currently supported" in message


def test_presentation_follows_intent_and_observed_result():
    intent = resolve_world_intent("watch Avengers movies")
    assert intent is not None

    assert resolve_presentation(intent, [])["environment"] == "conversation"
    assert resolve_presentation(intent, [{
        "title": "Example", "url": "https://example.com",
    }]) == {
        "environment": "conversation",
        "renderer": "conversation_links",
        "semantic_type": "media.discovery",
    }


def test_followup_selects_only_a_prior_completed_discovery_result():
    history = [{
        "role": "assistant",
        "content": (
            "I found:\n- [First](https://one.example/)\n"
            "- [Second](https://two.example/)"
        ),
        "tool_calls": [{"name": "search_web", "status": "completed"}],
    }]

    assert has_prior_media_results(history)
    assert resolve_media_followup("Open the second one.", history) == (
        "Second", "https://two.example/",
    )
    assert resolve_media_followup("Open the third one.", history) is None
    assert resolve_result_followup("Open the second one.", history) == (
        "Second", "https://two.example/",
    )


def test_execution_resolver_rejects_schema_incompatible_and_unobservable_surfaces():
    class Registry:
        def authorize(self, *args, **kwargs):
            return True, "granted"

    contracts = {
        "bad.schema": {
            "operations": ["media.discovery"],
            "operation_arguments": {"media.discovery": {"query": "$query"}},
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "integer"}},
                "required": ["query"],
            },
            "availability": "AVAILABLE",
            "execution_surface": "http_api",
            "observability": "canonical_runtime_events",
        },
        "unknown.surface": {
            "operations": ["media.discovery"],
            "operation_arguments": {"media.discovery": {"query": "$query"}},
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "availability": "AVAILABLE",
            "execution_surface": "unknown",
            "observability": "unknown",
        },
    }

    selection = resolve_execution_surface(
        "media.discovery", Registry(), contracts, user_id="user-1",
    )

    assert selection.status == "unavailable"
    assert "incompatible" in selection.reason
    assert "surface" in selection.reason


def test_chat_media_request_reuses_durable_command_and_returns_real_artifacts(
    monkeypatch,
):
    from jarvis_backend.routers import commands

    session_id = "world-resolver-chat"
    user_id = "testuser"
    chat_module.chat_service.create_session(user_id, session_id)
    fake_command = {
        "command_id": "durable-world-command",
        "selected_capability_id": "search_web",
        "status": "COMPLETED",
        "result": {
            "evidence": [{
                "name": "search_web",
                "success": True,
                "artifacts": [{
                    "title": "Example streaming information",
                    "url": "https://www.example.com/avengers",
                    "snippet": "A result observed from the live search tool.",
                }, {
                    "title": "Second example result",
                    "url": "https://www.example.org/avengers",
                    "snippet": "Another observed web result.",
                }],
            }],
        },
    }

    async def create_command(body, caller):
        assert body.conversation_id == session_id
        assert body.request_id == "media-request-1"
        assert caller["id"] == user_id
        return {"command_id": fake_command["command_id"]}

    monkeypatch.setattr(commands, "_create_command", create_command)
    monkeypatch.setattr(commands, "_commands", lambda: {
        fake_command["command_id"]: fake_command,
    })
    monkeypatch.setattr(
        chat_module.chat_service,
        "gateway",
        type("NoProvider", (), {
            "chat": lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("media discovery must not use model-generated claims")
            )
        })(),
    )

    result = asyncio.run(chat_module.chat_service.send_message(
        user_id,
        session_id,
        "JARVIS, I want to watch Avengers movies.",
        client_message_id="media-request-1",
        principal={"id": user_id, "roles": ["user"]},
    ))

    assert result["status"] == "COMPLETED"
    assert result["sources"] == [
        "https://www.example.com/avengers",
        "https://www.example.org/avengers",
    ]
    assert result["runtime_command_id"] == fake_command["command_id"]
    assert result["tool_calls"][0]["name"] == "search_web"

    followup = asyncio.run(chat_module.chat_service.send_message(
        user_id,
        session_id,
        "Open the second one.",
        client_message_id="media-request-2",
        principal={"id": user_id, "roles": ["user"]},
    ))
    assert "https://www.example.org/avengers" in followup["message"]
    assert followup["sources"] == ["https://www.example.org/avengers"]
    assert followup["tool_calls"] == []


def test_approved_tool_confirmation_is_scoped_to_policy_instance():
    from research_engine.tool_registry import (
        BrowserSearchTool,
        DefaultPermissionPolicy,
        ToolRegistry,
    )

    policy = DefaultPermissionPolicy()
    registry = ToolRegistry(policy=policy)
    registry.register(BrowserSearchTool())
    assert not registry.authorize(
        "user-1", "search_web",
        permissions={"web:read"},
    )[0]
    policy.record_confirmation("user-1", "search_web")
    assert registry.authorize(
        "user-1", "search_web",
        permissions={"web:read"},
    )[0]
    assert not registry.authorize(
        "user-2", "search_web",
        permissions={"web:read"},
    )[0]
    assert not registry.authorize("user-1", "search_web", permissions=set())[0]


def test_command_events_include_canonical_owner_scoped_correlation(monkeypatch):
    from jarvis_backend.routers import commands

    class Store:
        def __init__(self):
            self.data = {
                "cmd-1": {
                    "command_id": "cmd-1",
                    "execution_kind": "world_resolver",
                    "request_id": "req-1",
                    "conversation_id": "session-1",
                    "user_id": "user-1",
                    "requested_capability_id": "media.discovery",
                    "active_execution_id": "exec-1",
                    "events": [],
                    "plan_id": "plan-1",
                },
            }

        def load(self):
            return self.data

        def save(self):
            return None

    store = Store()
    captured = {}

    def append_event(**kwargs):
        captured.update(kwargs)
        return {
            "event_id": "event-1",
            "sequence": 7,
            "timestamp": 1.0,
        }

    monkeypatch.setattr(commands, "get_store", lambda name: store)
    monkeypatch.setattr(commands.jarvis_runtime, "append_event", append_event)

    commands._append_event(
        "cmd-1",
        "presentation.updated",
        presentation={"environment": "web_results"},
        result_count=2,
    )

    payload = captured["payload"]
    assert payload["request_id"] == "req-1"
    assert payload["session_id"] == "session-1"
    assert payload["conversation_id"] == "session-1"
    assert payload["capability_id"] == "media.discovery"
    assert payload["execution_id"] == "exec-1"
    assert payload["endpoint_id"] is None
    assert payload["source"] == "world_resolver"
    assert payload["presentation"] == {"environment": "web_results"}
    assert payload["correlation"]["command_id"] == "cmd-1"
    assert store.data["cmd-1"]["events"][-1]["sequence"] == 7


def test_runtime_event_order_records_selection_execution_result_and_presentation(monkeypatch):
    from jarvis_brain.audit import AuditEvent
    from jarvis_backend.routers import commands

    class Store:
        def __init__(self):
            self.data = {
                "cmd-1": {
                    "command_id": "cmd-1",
                    "execution_kind": "world_resolver",
                    "request_id": "req-1",
                    "conversation_id": "session-1",
                    "user_id": "user-1",
                    "requested_capability_id": "media.discovery",
                    "selected_capability_id": "search_web",
                    "execution_surface": "http_browser_engine",
                    "events": [],
                    "plan_id": "plan-1",
                    "started_at": None,
                    "capabilities": [],
                },
            }

        def load(self):
            return self.data

        def save(self):
            return None

    store = Store()
    sequence = 0

    def append_event(**kwargs):
        nonlocal sequence
        sequence += 1
        return {
            "event_id": f"event-{sequence}",
            "sequence": sequence,
            "timestamp": float(sequence),
        }

    monkeypatch.setattr(commands, "get_store", lambda name: store)
    monkeypatch.setattr(commands.jarvis_runtime, "append_event", append_event)

    commands._append_event(
        "cmd-1", "world.execution.selected",
        capability_id="search_web", execution_surface="http_browser_engine",
    )
    record = commands._audit_callback("cmd-1")
    record(AuditEvent(
        at="now", event="CAPABILITY_STARTED", capability="search_web",
        task_id="cmd-1",
    ))
    record(AuditEvent(
        at="now", event="CAPABILITY_COMPLETED", capability="search_web",
        success=True, task_id="cmd-1",
    ))
    commands._append_event("cmd-1", "world.result.observed", result_count=2)
    commands._append_event(
        "cmd-1", "presentation.updated",
        presentation={"environment": "conversation", "renderer": "conversation_links"},
    )

    events = store.data["cmd-1"]["events"]
    names = [event["event"] for event in events]
    assert names == [
        "world.execution.selected",
        "capability_started",
        "world.execution.started",
        "capability_completed",
        "world.execution.completed",
        "world.result.observed",
        "presentation.updated",
    ]
    assert [event["sequence"] for event in events] == list(range(1, 8))
    assert all(event["correlation"]["command_id"] == "cmd-1" for event in events)


def test_world_command_is_scoped_to_single_operation(monkeypatch):
    from jarvis_backend.routers import commands

    class Store:
        def __init__(self):
            self.data = {}

        def load(self):
            return self.data

        def save(self):
            return None

    store = Store()
    scheduled = []
    monkeypatch.setattr(commands, "get_store", lambda name: store)
    monkeypatch.setattr(
        commands.jarvis_runtime,
        "get_execution_by_idempotency_key",
        lambda key: None,
    )
    monkeypatch.setattr(
        commands.jarvis_runtime,
        "create_execution",
        lambda **kwargs: {"execution_id": "exec-1"},
    )
    monkeypatch.setattr(commands, "_append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        commands,
        "_schedule_command",
        lambda command_id, user, autonomy: scheduled.append(autonomy),
    )

    command = asyncio.run(commands._create_command(
        commands.CommandCreate(
            goal="I want to watch Avengers movies.",
            conversation_id="session-1",
            request_id="req-1",
        ),
        {"id": "user-1", "roles": ["user"]},
    ))

    assert command["execution_kind"] == "world_resolver"
    assert command["requested_capability_id"] == "media.discovery"
    assert command["execution_scope"] == "single_operation"
    assert command["autonomy"] == "SUPERVISED"
    assert command["execution_autonomy"] == "AUTONOMOUS"
    assert scheduled == ["AUTONOMOUS"]


def test_runtime_core_readiness_does_not_depend_on_mcp_or_ai_endpoints(monkeypatch):
    from jarvis_backend import mcp_runtime, runtime_status

    async def available(**kwargs):
        return {"status": "AVAILABLE"}

    async def degraded_mcp():
        return {"status": "DEGRADED"}

    for check_name in (
        "check_auth_status",
        "check_chat_status",
        "check_database_status",
        "check_openai_status",
        "check_google_status",
        "check_nvidia_status",
        "check_brain_status",
        "check_silverwing_status",
        "check_kaggle_status",
        "check_huggingface_status",
    ):
        monkeypatch.setattr(runtime_status, check_name, available)
    monkeypatch.setattr(mcp_runtime, "mcp_status", degraded_mcp)

    status = asyncio.run(runtime_status.build_canonical_runtime_status())

    assert status["core_state"] == "AVAILABLE"
    assert status["service_readiness"] == "READY"
    assert status["service_states"]["MCP"]["status"] == "DEGRADED"
    assert status["endpoint_states"]["brain"] == "AVAILABLE"
    assert status["network_state"] == "UNPROBED"


def test_guessed_command_results_and_runtime_events_are_owner_scoped(client):
    from jarvis_backend.core import create_token, get_store
    from jarvis_backend.chat_service import ChatError

    users = get_store("users")
    user_records = users.load()
    for user_id in ("world-owner", "world-other"):
        user_records[user_id] = {
            "id": user_id,
            "email": f"{user_id}@jarvis.local",
            "username": user_id,
            "status": "active",
            "is_active": True,
            "roles": ["user"],
        }
    users.save()

    def headers(user_id):
        return {
            "Authorization": f"Bearer {create_token({'sub': user_id, 'user_id': user_id})}",
        }

    commands = get_store("commands")
    commands.load()["world-owned-command"] = {
        "command_id": "world-owned-command",
        "user_id": "world-owner",
        "conversation_id": "world-owner-session",
        "status": "COMPLETED",
        "execution_ids": [],
        "events": [{
            "event": "world.result.observed",
            "data": {"url": "https://private.example/result"},
        }],
        "result": {"evidence": [{"name": "search_web", "artifacts": [{
            "title": "Owner result",
            "url": "https://private.example/result",
        }]}]},
    }
    commands.save()

    for endpoint in (
        "/api/v1/commands/world-owned-command",
        "/api/v1/commands/world-owned-command/executions",
        "/api/v1/commands/world-owned-command/events",
    ):
        assert client.get(endpoint, headers=headers("world-owner")).status_code == 200
        assert client.get(endpoint, headers=headers("world-other")).status_code == 404

    owner_session = chat_module.chat_service.create_session(
        "world-owner", "world-owner-session",
    )
    owner_session["messages"].append({
        "role": "assistant",
        "content": "[Owner result](https://private.example/result)",
        "tool_calls": [{
            "operation": "media.discovery", "status": "completed",
        }],
    })
    get_store("chat_sessions").save()

    assert resolve_result_followup(
        "Open the first result.",
        chat_module.chat_service.get_session(
            "world-owner", "world-owner-session",
        )["messages"],
    ) == ("Owner result", "https://private.example/result")
    with pytest.raises(ChatError) as error:
        chat_module.chat_service.get_session(
            "world-other", "world-owner-session",
        )
    assert error.value.status_code == 403


@pytest.mark.skipif(
    os.environ.get("JARVIS_BROWSER_SEARCH_ENABLED", "").lower()
    not in {"1", "true", "yes", "on"},
    reason="JARVIS_BROWSER_SEARCH_ENABLED=1 required for live execution",
)
def test_live_chat_executes_and_presents_real_discovery_results(client, auth_headers):
    session_id = "live-world-execution"
    response = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "client_message_id": "live-world-request",
            "message": "Find Avengers movies.",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["status"] == "COMPLETED"
    assert reply["sources"]
    assert all(source.startswith("https://") for source in reply["sources"])
    assert "playback is not currently supported" in reply["message"]
    presentation = reply["presentation"]
    assert presentation["contract_version"] == "1.1"
    assert presentation["objective"] == "research"
    assert presentation["correlation"]["request_id"] == "live-world-request"
    assert presentation["correlation"]["session_id"] == session_id
    assert presentation["correlation"]["conversation_id"] == session_id
    assert presentation["correlation"]["command_id"] == reply["runtime_command_id"]
    assert presentation["task_state"]["status"] == "completed"
    assert presentation["source_provenance"]
    assert all(
        source["source_type"] == "public_web"
        and source["observed_at"].endswith("+00:00")
        for source in presentation["source_provenance"]
    )
    source_component = next(
        component for component in presentation["components"]
        if component["type"] == "research.source_list"
    )
    assert {item["url"] for item in source_component["items"]} == set(reply["sources"])

    command_id = reply["runtime_command_id"]
    command_response = client.get(
        f"/api/v1/commands/{command_id}", headers=auth_headers,
    )
    assert command_response.status_code == 200
    command = command_response.json()
    assert command["selected_capability_id"] == "search_web"

    event_response = client.get(
        f"/api/v1/commands/{command_id}/events", headers=auth_headers,
    )
    assert event_response.status_code == 200
    event_names = [
        event.get("type") or event.get("event") or event.get("event_type")
        for event in event_response.json()["events"]
    ]
    required_events = [
        "world.resolve.started",
        "world.execution.selected",
        "world.execution.started",
        "world.execution.completed",
        "world.result.observed",
        "presentation.updated",
    ]
    assert all(name in event_names for name in required_events), event_names
    positions = [event_names.index(name) for name in required_events]
    assert positions == sorted(positions)
    presentation_event = next(
        event for event in event_response.json()["events"]
        if (event.get("type") or event.get("event") or event.get("event_type"))
        == "presentation.updated"
    )
    assert presentation_event["payload"]["presentation"] == presentation

    history = client.get(
        f"/api/chat/history/{session_id}", headers=auth_headers,
    )
    assert history.status_code == 200
    assert any(
        message.get("role") == "assistant"
        and message.get("content") == reply["message"]
        and message.get("presentation") == presentation
        for message in history.json()["messages"]
    )

    followup = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "client_message_id": "live-world-followup",
            "message": "Open the second result.",
        },
        headers=auth_headers,
    )
    assert followup.status_code == 200, followup.text
    assert followup.json()["sources"]
    assert followup.json()["sources"][0] == reply["sources"][1]
    assert followup.json()["presentation"]["correlation"]["session_id"] == session_id

    research = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "client_message_id": "live-world-web-search",
            "message": "Research current JARVIS runtime event persistence options.",
        },
        headers=auth_headers,
    )
    assert research.status_code == 200, research.text
    research_reply = research.json()
    assert research_reply["status"] == "COMPLETED"
    assert research_reply["sources"]
    assert research_reply["presentation"]["objective"] == "research"
    research_command = client.get(
        f"/api/v1/commands/{research_reply['runtime_command_id']}",
        headers=auth_headers,
    ).json()
    assert research_command["requested_capability_id"] == "web.search"
    assert research_command["selected_capability_id"] == "search_web"
