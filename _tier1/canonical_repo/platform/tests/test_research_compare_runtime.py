from __future__ import annotations

import asyncio

import pytest

from research_engine.models import ToolResult
from research_engine.tool_registry import (
    DefaultPermissionPolicy,
    ResearchCompareTool,
    ToolContext,
    ToolRegistry,
)


def _source_artifacts():
    return [{
        "title": "Observed public report",
        "url": "https://example.org/report",
        "snippet": "The report describes a measured change.",
        "retrieved_at": "2026-10-09T12:00:00+00:00",
        "provider": "fixture-search",
    }]


def _registry() -> ToolRegistry:
    return ToolRegistry(
        DefaultPermissionPolicy(
            confirmations={"research-user:research.compare": True},
        ),
    ).register(ResearchCompareTool())


def test_compare_intent_resolves_to_registered_capability():
    from jarvis_backend.world_resolver import resolve_world_intent

    intent = resolve_world_intent(
        "Research recent battery advances, consult the configured AI systems "
        "independently, compare their conclusions, and prepare a sourced report."
    )

    assert intent is not None
    assert intent.operation == "research.compare"
    assert intent.subject == "recent battery advances"


def test_compare_capability_returns_attributed_independent_provider_responses(
    monkeypatch,
):
    import research_engine.tool_registry as tools

    received_prompts: list[tuple[str, str]] = []

    async def search(self, args, ctx):
        assert args == {
            "query": "recent battery advances",
            "max_results": 5,
            "extract": False,
        }
        return ToolResult(
            tool_id=ctx.request_id,
            name="search_web",
            success=True,
            result="one observed result",
            metrics={"provider": "fixture-search"},
            artifacts=_source_artifacts(),
        )

    async def consult(
        model_reference: str,
        prompt: str,
        system_prompt: str | None = None,
    ):
        received_prompts.append((model_reference, prompt))
        provider, model = model_reference.split(":", 1)
        return {
            "provider": provider,
            "model": model,
            "usage": {"total_cost_usd": 0.02},
            "content": (
                f"Synthesis from {provider}."
                if system_prompt and "synthesis model" in system_prompt
                else f"Analysis from {provider}."
            ),
        }

    monkeypatch.setattr(tools.BrowserSearchTool, "invoke", search)
    monkeypatch.setattr(
        tools, "_comparison_candidates",
        lambda: ([("openai", "openai:model-a"), ("google", "google:model-b")], 2),
    )
    monkeypatch.setattr(tools, "_invoke_gateway_consult", consult)

    result = asyncio.run(_registry().invoke(
        "research.compare",
        {"query": "recent battery advances"},
        ToolContext(
            user_id="research-user",
            permissions={"web:read", "model:consult"},
            principal={"id": "research-user"},
        ),
    ))

    assert result.success
    assert result.metrics["completion"] == "complete"
    assert result.metrics["consultations_succeeded"] == 2
    assert result.metrics["synthesis_status"] == "completed"
    assert result.metrics["provider_calls"] == 3
    assert result.metrics["cost_model"] == "provider"
    assert result.metrics["total_cost_usd"] == 0.06
    assert "openai · model-a" in result.result
    assert "google · model-b" in result.result
    assert "Synthesis from openai." in result.result
    assert "## JARVIS synthesis" in result.result
    assert "No image or chart was generated" in result.result
    assert len(received_prompts) == 3
    assert received_prompts[0][1] == received_prompts[1][1]
    assert "Independent provider consultations" in received_prompts[2][1]
    assert all(
        "Analysis from" not in prompt for _, prompt in received_prompts[:2]
    )
    assert "Analysis from openai." in received_prompts[2][1]
    assert "Analysis from google." in received_prompts[2][1]
    assert result.artifacts == _source_artifacts()


def test_compare_capability_reports_partial_when_no_providers_are_healthy(
    monkeypatch,
):
    import research_engine.tool_registry as tools

    async def search(self, args, ctx):
        return ToolResult(
            tool_id=ctx.request_id,
            name="search_web",
            success=True,
            result="one observed result",
            artifacts=_source_artifacts(),
        )

    async def unexpected_consult(*_args):
        raise AssertionError("must not call an unavailable provider")

    monkeypatch.setattr(tools.BrowserSearchTool, "invoke", search)
    monkeypatch.setattr(tools, "_comparison_candidates", lambda: ([], 0))
    monkeypatch.setattr(tools, "_invoke_gateway_consult", unexpected_consult)

    result = asyncio.run(_registry().invoke(
        "research.compare",
        {"query": "recent battery advances"},
        ToolContext(
            user_id="research-user",
            permissions={"web:read", "model:consult"},
            principal={"id": "research-user"},
        ),
    ))

    assert result.success
    assert result.metrics["completion"] == "partial"
    assert "No independent provider response was obtained" in result.result
    assert "No consensus is claimed" in result.result
    assert result.artifacts == _source_artifacts()


def test_compare_does_not_claim_zero_configured_providers_on_discovery_error(
    monkeypatch,
):
    import research_engine.tool_registry as tools

    async def search(self, args, ctx):
        return ToolResult(
            tool_id=ctx.request_id,
            name="search_web",
            success=True,
            result="one observed result",
            artifacts=_source_artifacts(),
        )

    def unavailable_discovery():
        raise RuntimeError("provider registry unavailable")

    async def unexpected_consult(*_args):
        raise AssertionError("must not call a provider without discovery")

    monkeypatch.setattr(tools.BrowserSearchTool, "invoke", search)
    monkeypatch.setattr(tools, "_comparison_candidates", unavailable_discovery)
    monkeypatch.setattr(tools, "_invoke_gateway_consult", unexpected_consult)

    result = asyncio.run(_registry().invoke(
        "research.compare",
        {"query": "recent battery advances"},
        ToolContext(
            user_id="research-user",
            permissions={"web:read", "model:consult"},
            principal={"id": "research-user"},
        ),
    ))

    assert result.success
    assert result.metrics["completion"] == "partial"
    assert result.metrics["configured_providers"] is None
    assert "Provider discovery failed" in result.result
    assert "0 providers were configured" not in result.result


def test_compare_reports_partial_provider_and_synthesis_failures(monkeypatch):
    import research_engine.tool_registry as tools

    async def search(self, args, ctx):
        return ToolResult(
            tool_id=ctx.request_id,
            name="search_web",
            success=True,
            result="one observed result",
            artifacts=_source_artifacts(),
        )

    async def consult(
        model_reference: str,
        prompt: str,
        system_prompt: str | None = None,
    ):
        if "Independent provider consultations" in prompt:
            raise asyncio.TimeoutError()
        if model_reference.startswith("google:"):
            raise asyncio.TimeoutError()
        return {
            "provider": "openai",
            "model": "model-a",
            "content": "One attributed analysis.",
        }

    monkeypatch.setattr(tools.BrowserSearchTool, "invoke", search)
    monkeypatch.setattr(
        tools, "_comparison_candidates",
        lambda: ([("openai", "openai:model-a"), ("google", "google:model-b")], 2),
    )
    monkeypatch.setattr(tools, "_invoke_gateway_consult", consult)

    result = asyncio.run(_registry().invoke(
        "research.compare",
        {"query": "recent battery advances"},
        ToolContext(
            user_id="research-user",
            permissions={"web:read", "model:consult"},
            principal={"id": "research-user"},
        ),
    ))

    assert result.success
    assert result.metrics["completion"] == "partial"
    assert result.metrics["consultations_succeeded"] == 1
    assert result.metrics["synthesis_status"] == "timed out"
    assert "No consensus is claimed" in result.result
    assert "1 of 2 independent consultations succeeded" in result.result


def test_provider_consult_propagates_cancellation(monkeypatch):
    import research_engine.tool_registry as tools

    async def exercise():
        started = asyncio.Event()

        class HangingGateway:
            async def chat(self, *_args, **_kwargs):
                started.set()
                await asyncio.Event().wait()

        monkeypatch.setattr(
            "jarvis_backend.gateway.ProviderGateway", HangingGateway,
        )
        task = asyncio.create_task(tools._invoke_gateway_consult(
            "openai:model-a",
            "Compare the attributed results.",
        ))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())


def test_compare_capability_denies_missing_web_permission(monkeypatch):
    import research_engine.tool_registry as tools

    async def no_search(self, args, ctx):
        raise AssertionError("authorization must run before network access")

    monkeypatch.setattr(tools.BrowserSearchTool, "invoke", no_search)
    registry = _registry()
    result = asyncio.run(registry.invoke(
        "research.compare",
        {"query": "recent battery advances"},
        ToolContext(
            user_id="research-user",
            permissions=set(),
            principal={"id": "research-user"},
        ),
    ))

    assert not result.success
    assert "PERMISSION_DENIED:web:read" in result.error


def test_compare_does_not_share_request_with_provider_without_consent(monkeypatch):
    import research_engine.tool_registry as tools

    async def no_search(self, args, ctx):
        raise AssertionError("authorization must run before search or provider calls")

    async def no_provider(*_args, **_kwargs):
        raise AssertionError("unauthorized provider must not receive request data")

    monkeypatch.setattr(tools.BrowserSearchTool, "invoke", no_search)
    monkeypatch.setattr(tools, "_invoke_gateway_consult", no_provider)
    result = asyncio.run(_registry().invoke(
        "research.compare",
        {"query": "private project budget for Project Northstar is $2.4m"},
        ToolContext(
            user_id="research-user",
            permissions={"web:read"},
            principal={"id": "research-user"},
        ),
    ))

    assert not result.success
    assert "PERMISSION_DENIED:model:consult" in result.error


def test_authenticated_conversation_executes_and_presents_research_compare(
    client, auth_headers, monkeypatch,
):
    import jarvis_backend.browser_engine as browser_engine
    import research_engine.tool_registry as tools

    class SearchEngine:
        def search(self, query, max_results=10):
            assert query == "recent battery advances"
            return [{
                "title": "Observed public report",
                "url": "https://example.org/report",
                "snippet": "The report describes a measured change.",
                "provider": "fixture-search",
                "rank": 1,
            }]

        def fetch_document(self, *_args, **_kwargs):
            raise AssertionError("this slice uses source snippets, not page fetch")

    monkeypatch.setenv("JARVIS_BROWSER_SEARCH_ENABLED", "1")
    monkeypatch.setattr(browser_engine, "get_engine", lambda _name: SearchEngine())
    monkeypatch.setattr(
        tools, "_comparison_candidates",
        lambda: ([("openai", "openai:model-a"), ("google", "google:model-b")], 2),
    )
    calls: list[str] = []

    async def consult(
        model_reference: str,
        prompt: str,
        system_prompt: str | None = None,
    ):
        calls.append(model_reference)
        provider, model = model_reference.split(":", 1)
        return {
            "provider": provider,
            "model": model,
            "content": (
                f"Synthesis from {provider}."
                if system_prompt and "synthesis model" in system_prompt
                else f"Independent analysis from {provider}."
            ),
        }

    monkeypatch.setattr(tools, "_invoke_gateway_consult", consult)
    request = {
        "session_id": "research-compare-conversation",
        "client_message_id": "research-compare-request",
        "message": (
            "Research recent battery advances, consult the configured AI systems "
            "independently, compare their conclusions, and prepare a sourced report."
        ),
    }

    response = client.post("/api/chat", headers=auth_headers, json=request)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["runtime_command_id"]
    assert "Independent analysis from openai." in payload["message"]
    assert "Independent analysis from google." in payload["message"]
    assert "Synthesis from openai." in payload["message"]
    assert payload["presentation"]["objective"] == "research"
    assert payload["presentation"]["task_state"]["status"] == "completed"
    assert payload["presentation"]["correlation"]["request_id"] == (
        request["client_message_id"]
    )
    assert payload["presentation"]["components"][1]["type"] == (
        "research.source_list"
    )
    assert len(calls) == 3

    command_id = payload["runtime_command_id"]
    command = client.get(
        f"/api/v1/commands/{command_id}",
        headers=auth_headers,
    )
    assert command.status_code == 200
    assert command.json()["selected_capability_id"] == "research.compare"

    revisions = client.get(
        f"/api/v1/presentations/{command_id}/revisions",
        headers=auth_headers,
    )
    assert revisions.status_code == 200
    assert revisions.json()["revisions"][0]["presentation"]["presentation_id"] == (
        payload["presentation"]["presentation_id"]
    )

    events = client.get(
        f"/api/v1/commands/{command_id}/events",
        headers=auth_headers,
    )
    assert events.status_code == 200
    event_names = [
        event.get("type") or event.get("event") or event.get("event_type")
        for event in events.json()["events"]
    ]
    assert event_names.index("world.execution.selected") < event_names.index(
        "world.execution.started"
    )
    assert event_names.index("world.result.observed") < event_names.index(
        "presentation.updated"
    )

    replay = client.post("/api/chat", headers=auth_headers, json=request)
    assert replay.status_code == 200
    assert replay.json()["resumed"] is True
    assert replay.json()["runtime_command_id"] == command_id
    assert len(calls) == 3
