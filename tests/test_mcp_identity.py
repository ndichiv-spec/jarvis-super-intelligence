import asyncio

import pytest
from fastapi import HTTPException
from starlette.responses import JSONResponse

from jarvis_backend import mcp_server


def _http_scope():
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
    }


def _run_asgi(app):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(_http_scope(), receive, send))
    return messages


def test_mcp_http_transport_rejects_unauthenticated_requests(monkeypatch):
    from jarvis_backend import core

    async def downstream(_scope, _receive, _send):
        pytest.fail("unauthenticated MCP request reached the transport")

    def reject_request(**_kwargs):
        raise HTTPException(status_code=401, detail="Not authenticated")

    monkeypatch.setattr(core, "get_current_user", reject_request)

    messages = _run_asgi(mcp_server._AuthenticatedMCPHTTPApp(downstream))

    assert next(message["status"] for message in messages if message["type"] == "http.response.start") == 401


def test_mcp_tool_context_uses_authenticated_identity_and_grants(monkeypatch):
    from jarvis_backend import core

    principal = {"id": "user-123", "roles": ["user"]}
    monkeypatch.setattr(core, "get_current_user", lambda **_kwargs: principal)
    monkeypatch.setattr(
        core,
        "has_permission",
        lambda _user, permission: permission == "tool.github",
    )
    monkeypatch.setattr(core, "is_admin", lambda _user: False)
    contexts = []

    async def downstream(scope, receive, send):
        contexts.append(mcp_server._execution_context())
        await JSONResponse({"ok": True})(scope, receive, send)

    messages = _run_asgi(mcp_server._AuthenticatedMCPHTTPApp(downstream))
    context = contexts[0]

    assert next(message["status"] for message in messages if message["type"] == "http.response.start") == 200
    assert context.user_id == principal["id"]
    assert context.permissions == ["tool.github"]


def test_stdio_context_has_no_authenticated_tool_grants():
    context = mcp_server._execution_context()

    assert context.user_id == "mcp_client"
    assert context.permissions == []
