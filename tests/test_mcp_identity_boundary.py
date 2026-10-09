"""MCP arguments cannot establish a JARVIS user or permission context."""

import asyncio
from types import SimpleNamespace


def test_mcp_tool_call_ignores_client_supplied_identity(monkeypatch):
    from jarvis_backend import mcp_server

    captured = {}

    class FakeToolCapability:
        async def execute(self, request, context):
            captured["request"] = request
            captured["context"] = context
            return SimpleNamespace(
                to_dict=lambda: {"success": False, "error": "Permission denied"}
            )

    class FakeTextContent:
        def __init__(self, **values):
            self.values = values

    class FakeCallToolResult:
        def __init__(self, **values):
            self.values = values

    monkeypatch.setattr(mcp_server, "Tool", object())
    monkeypatch.setattr(mcp_server, "TextContent", FakeTextContent)
    monkeypatch.setattr(mcp_server, "CallToolResult", FakeCallToolResult)
    monkeypatch.setattr(mcp_server, "_get_tool_capability", lambda: FakeToolCapability())

    arguments = {
        "action": "list_issues",
        "owner": "org",
        "repo": "repo",
        "_user_id": "victim-user",
        "_session_id": "victim-session",
    }
    result = asyncio.run(mcp_server._execute_jarvis_tool("github", arguments))

    context = captured["context"]
    assert context.user_id == "mcp_client"
    assert context.session_id != "victim-session"
    assert context.permissions == []
    assert "_user_id" not in captured["request"]["params"]
    assert "_session_id" not in captured["request"]["params"]
    assert arguments["_user_id"] == "victim-user"
    assert result.values["isError"] is True
