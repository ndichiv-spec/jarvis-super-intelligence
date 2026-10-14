"""Opt-in public-service check for the canonical JARVIS chat/runtime path.

Set ``JARVIS_WORLD_WORKSPACE_LIVE=1`` and use a disposable test database to
run this test. It contacts DuckDuckGo's public search endpoint and needs no
provider credentials; model synthesis is optional and failure is reported as
partial completion with the real search result URLs retained.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from jarvis_backend.chat_service import ChatService
from jarvis_backend.runtime_events import runtime_event_service


pytestmark = pytest.mark.skipif(
    os.environ.get("JARVIS_WORLD_WORKSPACE_LIVE") != "1",
    reason="set JARVIS_WORLD_WORKSPACE_LIVE=1 to contact the public search service",
)


def test_natural_language_request_executes_and_persists_real_web_search(monkeypatch):
    owner_id = f"world-live-{uuid.uuid4()}"
    owner_email = "world-workspace-live@example.invalid"
    session_id = f"world-workspace-live-{uuid.uuid4()}"
    request_id = f"world-request-{uuid.uuid4()}"
    monkeypatch.setenv("JARVIS_ADMIN_EMAIL", owner_email)

    # Mirror the canonical application startup hook before exercising the
    # same ChatService entrypoint used by both HTTP chat routes.
    from jarvis_backend.capabilities import register_all_capabilities

    register_all_capabilities()
    service = ChatService()
    service.create_session(owner_id, session_id, "World Workspace live acceptance")
    result = asyncio.run(service.send_message(
        owner_id,
        session_id,
        "Research official Python documentation downloads",
        request_id=request_id,
        principal={"id": owner_id, "email": owner_email, "roles": ["owner"]},
    ))

    assert result["status"] == "COMPLETED", (
        result.get("error"), result.get("tool_calls"), result.get("runtime_events")
    )
    assert result["tool_calls"]
    call = result["tool_calls"][0]
    assert call["name"] == "browser.search"
    assert call["status"] == "completed"
    assert call["result"]["provenance"]["capability"] == "HttpBrowserEngine.search"
    assert call["result"]["result_count"] > 0
    assert result["sources"]

    persisted = service.get_session(owner_id, session_id)
    assistant = next(message for message in persisted["messages"] if message["role"] == "assistant")
    assert assistant["request_id"] == request_id
    assert assistant["tool_calls"][0]["result"]["result_count"] > 0
    runtime = runtime_event_service.resume(owner_id, session_id)
    event_types = {event["type"] for event in runtime["events"]}
    assert "request_created" in event_types
    assert "request_completed" in event_types
