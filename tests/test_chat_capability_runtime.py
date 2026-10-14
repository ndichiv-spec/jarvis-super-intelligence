from __future__ import annotations

import asyncio
import uuid
import pytest

from jarvis_backend.capability import (
    CapabilityEvent,
    CapabilityStatus,
    EventBus,
    ExecutionContext,
    ExecutionResult,
)
from jarvis_backend.chat_service import ChatService
from jarvis_backend.errors import ChatError, ErrorCategory
from jarvis_backend.browser_engine import HttpBrowserEngine
from jarvis_backend.capabilities.tools.browser_tool import BrowserTool
from jarvis_backend.capabilities.tools import ToolCapability
from jarvis_backend.capabilities.tools.postgresql import PostgreSQLTool
from jarvis_backend.routers import system


def test_chat_discovers_explicit_search_and_clear_research_requests():
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
    assert ChatService._discover_conversation_action(
        "Research the best available options for training my own AI model"
    ) == {
        "tool": "browser",
        "action": "search",
        "capability_id": "web.search",
        "arguments": {"query": "the best available options for training my own AI model"},
    }
    assert ChatService._discover_conversation_action(
        "Find a way for me to watch the movie Solaris"
    )["arguments"]["query"] == "watch the movie Solaris"
    assert ChatService._discover_conversation_action(
        "Tell me a story about research"
    ) is None


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
    monkeypatch.setattr("jarvis_backend.core.has_permission", lambda user, permission: permission == "tool.browser")

    result = await ChatService()._execute_conversation_action(
        "Search the web for the latest Python release",
        "owner-1",
        "conversation-1",
        "request-1",
        principal={"id": "owner-1"},
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

    async def executed_action(self, prompt, user_id, session_id, request_id, *, principal=None):
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


def test_search_results_remain_useful_and_marked_partial_when_models_are_unavailable(monkeypatch):
    class Gateway:
        timeout = 1
        max_retries = 0

        async def chat(self, *args, **kwargs):
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "No model provider is available.",
            )

    async def observed_search(self, prompt, user_id, session_id, request_id, *, principal=None):
        return {
            "selection": self._discover_conversation_action(prompt),
            "execution_id": "exec-test",
            "success": True,
            "data": {
                "result_count": 1,
                "results": [{"title": "Docs", "url": "https://docs.python.org/"}],
                "provenance": {"providers": ["duckduckgo"]},
            },
            "events": [],
        }

    monkeypatch.setattr(ChatService, "_execute_conversation_action", observed_search)
    service = ChatService(gateway=Gateway())
    session_id = f"world-partial-{uuid.uuid4()}"
    service.create_session("world-test-owner", session_id)

    response = asyncio.run(service.send_message(
        "world-test-owner",
        session_id,
        "Research the Python documentation",
    ))

    assert response["status"] == "COMPLETED"
    assert response["execution_status"] == "partially_completed"
    assert "not been independently checked" in response["message"]
    assert response["sources"] == ["https://docs.python.org/"]
    assistant = next(
        message for message in service.get_session("world-test-owner", session_id)["messages"]
        if message["role"] == "assistant"
    )
    assert assistant["metadata"]["verification"] == "search_provider_response_only"
    assert assistant["tool_calls"][0]["status"] == "completed"


def test_browser_tool_does_not_claim_success_for_failed_http_fetch(monkeypatch):
    class Engine:
        @staticmethod
        def fetch(url, options):
            return {"url": url, "status": 503, "html": "", "error": "upstream unavailable"}

    tool = BrowserTool()
    tool._engine = Engine()

    result = asyncio.run(tool.execute("fetch", {"url": "https://example.test/"}, context=None))
    assert result["success"] is False
    assert result["error_type"] == "PAGE_REQUEST_FAILED"
    assert "upstream unavailable" in result["error"]


def test_browser_tool_search_uses_canonical_engine_and_reports_provenance():
    class Engine:
        @staticmethod
        def search(query, max_results, timeout):
            assert query == "model training"
            assert max_results == 10
            assert timeout == 15
            return [{
                "title": "Training guide",
                "url": "https://docs.example.org/train",
                "snippet": "Supported training methods",
                "provider": "duckduckgo",
                "rank": 1,
            }]

    tool = BrowserTool()
    tool._engine = Engine()
    result = asyncio.run(tool.execute("search", {"query": "model training"}, context=None))

    assert result["success"] is True
    assert result["data"]["result_count"] == 1
    assert result["data"]["provenance"] == {
        "capability": "HttpBrowserEngine.search",
        "providers": ["duckduckgo"],
        "result_urls_validated": 1,
        "page_content_fetched": False,
    }


def test_browser_engine_distinguishes_empty_search_from_provider_outage(monkeypatch):
    engine = HttpBrowserEngine()
    monkeypatch.setattr(engine, "_ddg_lite_search", lambda *args: [])
    monkeypatch.setattr(engine, "_wikipedia_search", lambda *args: [])
    assert engine.search("a query") == []

    def unavailable(*args):
        raise OSError("provider offline")

    monkeypatch.setattr(engine, "_ddg_lite_search", unavailable)
    monkeypatch.setattr(engine, "_wikipedia_search", unavailable)
    with pytest.raises(RuntimeError, match="All configured web-search providers failed"):
        engine.search("a query")


@pytest.mark.asyncio
async def test_conversation_search_is_blocked_without_server_permission(monkeypatch):
    class Registry:
        event_bus = EventBus()

        @staticmethod
        def get(name):
            return object() if name == "tool" else None

    class Orchestrator:
        registry = Registry()

        async def execute_capability(self, *args, **kwargs):
            raise AssertionError("Unauthorized browser search must not execute.")

    monkeypatch.setattr("jarvis_backend.capability.get_orchestrator", lambda: Orchestrator())
    monkeypatch.setattr("jarvis_backend.core.has_permission", lambda user, permission: False)

    result = await ChatService()._execute_conversation_action(
        "Research the latest release of Python",
        "guest-1",
        "conversation-1",
        "request-1",
        principal={"id": "guest-1", "roles": ["viewer"]},
    )

    assert result["success"] is False
    assert result["error_type"] == "AUTHORIZATION_FAILED"
    assert result["events"][0]["status"] == "denied"


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
