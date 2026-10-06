from __future__ import annotations

import asyncio
import pytest

from jarvis_backend.capability import (
    CapabilityEvent,
    CapabilityStatus,
    EventBus,
    ExecutionContext,
    ExecutionResult,
)
from jarvis_backend.chat_service import ChatService
from jarvis_backend.capabilities.tools.browser_tool import BrowserTool
from jarvis_backend.capabilities.tools import ToolCapability
from jarvis_backend.capabilities.tools.postgresql import PostgreSQLTool
from jarvis_backend.routers import system


def test_chat_discovers_only_explicit_web_search_requests():
    assert ChatService._discover_conversation_action(
        "Search the web for the latest Python release and summarize it"
    ) == {
        "tool": "browser",
        "action": "search",
        "capability_id": "web.search",
        "arguments": {"query": "the latest Python release"},
    }
    assert ChatService._discover_conversation_action("What is the latest Python release?") is None
    assert ChatService._discover_conversation_action("Do not search the web for this") is None
    assert ChatService._discover_conversation_action("Search the web") is None


@pytest.mark.asyncio
async def test_conversation_search_runs_via_registered_orchestrator(monkeypatch):
    class Registry:
        event_bus = EventBus()

        @staticmethod
        def get(name):
            return object() if name == "tool" else None

    class Orchestrator:
        registry = Registry()

        def __init__(self):
            self.call = None

        async def execute_capability(self, capability, request, context):
            self.call = (capability, request, context)
            return ExecutionResult(
                capability="tool",
                success=True,
                data={"results": [{"title": "Python release", "url": "https://python.org/"}]},
                correlation_id=context.correlation_id,
            )

    orchestrator = Orchestrator()
    monkeypatch.setattr("jarvis_backend.capability.get_orchestrator", lambda: orchestrator)

    result = await ChatService()._execute_conversation_action(
        "Search the web for the latest Python release",
        "owner-1",
        "conversation-1",
        "request-1",
    )

    assert result is not None and result["success"] is True
    assert result["data"]["results"][0]["title"] == "Python release"
    capability, request, context = orchestrator.call
    assert capability == "tool"
    assert request == {
        "tool": "browser",
        "action": "search",
        "params": {"query": "the latest Python release"},
    }
    assert context.user_id == "owner-1"
    assert context.session_id == "conversation-1"
    assert context.permissions == ["tool.browser"]
    assert [event["event_type"] for event in result["events"]] == [
        "capability_action_started",
        "capability_action_completed",
    ]
    assert result["events"][-1]["status"] == "completed"


def test_conversation_passes_real_tool_result_to_model_and_persists_it(monkeypatch):
    class Gateway:
        timeout = 5
        max_retries = 0

        def __init__(self):
            self.system = ""

        async def chat(self, messages, model=None, system=None, timeout=None):
            self.system = system or ""
            return {
                "content": "The search returned the Python release page.",
                "model": "test:model",
                "provider": "test",
                "latency_ms": 1,
                "usage": {},
            }

    async def executed_action(self, prompt, user_id, session_id, request_id):
        selection = self._discover_conversation_action(prompt)
        return {
            "selection": selection,
            "success": True,
            "data": {"results": [{"title": "Python release", "url": "https://python.org/"}]},
            "events": [{
                "event_id": request_id,
                "event_type": "capability_action_completed",
                "timestamp": "2026-10-04T00:00:00+00:00",
                "capability_id": "web.search",
                "action": "search",
                "status": "completed",
                "message": "Browser search returned a result.",
            }],
        }

    monkeypatch.setattr(ChatService, "_execute_conversation_action", executed_action)
    gateway = Gateway()
    service = ChatService(gateway=gateway)
    session_id = "capability-runtime-e2e"
    service.create_session("runtime-test-user", session_id)
    response = asyncio.run(service.send_message(
        "runtime-test-user",
        session_id,
        "Search the web for the latest Python release",
    ))

    session = service.get_session("runtime-test-user", session_id)
    assistant = next(message for message in session["messages"] if message["role"] == "assistant")
    assert response["status"] == "COMPLETED"
    assert "<capability_execution>" in gateway.system
    assert '"title": "Python release"' in gateway.system
    assert assistant["tool_calls"][0]["status"] == "completed"
    assert assistant["tool_calls"][0]["result"]["results"][0]["title"] == "Python release"
    assert assistant["runtime_events"][0]["event_type"] == "capability_action_completed"


def test_browser_tool_does_not_claim_success_for_failed_http_fetch(monkeypatch):
    class Engine:
        @staticmethod
        def fetch(url, options):
            return {"url": url, "status": 503, "html": "", "error": "upstream unavailable"}

    tool = BrowserTool()
    tool._engine = Engine()

    result = asyncio.run(tool.execute("search", {"query": "test"}, context=None))
    assert result["success"] is False
    assert result["error_type"] == "PAGE_REQUEST_FAILED"
    assert "upstream unavailable" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE accounts SET admin = true",
        "WITH removed AS (DELETE FROM accounts RETURNING *) SELECT * FROM removed",
        "SELECT 1; DROP TABLE accounts",
    ],
)
async def test_postgresql_tool_rejects_non_readonly_or_multiple_statements(sql):
    result = await PostgreSQLTool().execute("query", {"query": sql}, context=None)
    assert result["success"] is False
    assert result["error_type"] == "SECURITY_VIOLATION"


@pytest.mark.asyncio
async def test_tool_capability_requires_confirmation_for_github_writes():
    class GitHub:
        called = False

        async def execute(self, action, params, context):
            self.called = True
            return {"success": True}

    capability = ToolCapability()
    github = GitHub()
    capability._registered_tools = {"github": github}
    context = ExecutionContext(
        user_id="owner-1",
        session_id="conversation-1",
        permissions=["tool.github"],
    )
    result = await capability.execute(
        {"tool": "github", "action": "create_issue", "params": {"title": "test"}},
        context,
    )
    assert result.success is False
    assert result.error_type == "CONFIRMATION_REQUIRED"
    assert github.called is False

    result = await capability.execute(
        {
            "tool": "github",
            "action": "update_file",
            "params": {
                "owner": "acme",
                "repo": "platform",
                "path": "README.md",
                "content": "change",
                "message": "Update docs",
            },
        },
        context,
    )
    assert result.success is False
    assert result.error_type == "CONFIRMATION_REQUIRED"
    assert github.called is False


@pytest.mark.asyncio
async def test_runtime_inventory_reports_real_tool_status_and_owner_events(monkeypatch):
    event_bus = EventBus()
    event_bus.emit(CapabilityEvent(
        event_type="capability_action_completed",
        user_id="owner-1",
        capability="web.search",
        status="completed",
    ))
    event_bus.emit(CapabilityEvent(
        event_type="capability_action_completed",
        user_id="other-user",
        capability="web.search",
        status="completed",
    ))

    class ToolRuntime:
        async def health(self):
            return {
                "status": CapabilityStatus.READY,
                "tools": {
                    "browser": {
                        "status": "ok",
                        "healthy": True,
                        "host": "private-host",
                    },
                },
            }

        async def discover_actions(self):
            return [{
                "id": "browser",
                "name": "browser",
                "description": "public web",
                "permissions": ["tool.browser"],
                "actions": [{
                    "id": "search",
                    "execution_supported": True,
                    "input_schema": {"type": "object"},
                }],
            }]

    class Registry:
        def get(self, name):
            return ToolRuntime() if name == "tool" else None

        def __init__(self):
            self.event_bus = event_bus

    monkeypatch.setattr("jarvis_backend.capability.get_registry", lambda: Registry())
    result = await system.capability_runtime({"id": "owner-1"})
    assert result["execution_supported"] is True
    assert result["tools"][0]["status"] == "ready"
    assert result["tools"][0]["connection"]["reachable"] is True
    assert "host" not in result["tools"][0]["health"]
    assert len(result["events"]) == 1
    assert result["events"][0]["user_id"] == "owner-1"
