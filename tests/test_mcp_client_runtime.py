from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from jarvis_backend.mcp_client import MCPClientManager, MCPServerConfig


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def test_remote_mcp_uses_secret_environment_headers_and_closes_cleanly(monkeypatch):
    monkeypatch.setenv("WORK_TOOLS_AUTH", "Bearer private-token")
    seen = {}
    transport_closed = []

    class FakeHttpClient:
        async def aclose(self):
            seen["http_closed"] = True

    class FakeSession:
        def __init__(self, read_stream, write_stream, read_timeout_seconds):
            seen["session_timeout"] = read_timeout_seconds

        async def initialize(self):
            seen["initialized"] = True

        async def close(self):
            seen["session_closed"] = True

        async def call_tool(self, name, arguments):
            seen["tool_call"] = {"name": name, "arguments": arguments}
            return SimpleNamespace(
                isError=False,
                content=[SimpleNamespace(text="service response")],
            )

    def make_http_client(*, headers, timeout):
        seen["headers"] = headers
        seen["timeout"] = timeout
        return FakeHttpClient()

    @asynccontextmanager
    async def fake_streamable_http_client(url, *, http_client):
        seen["url"] = url
        seen["http_client"] = http_client
        yield object(), object()
        transport_closed.append(True)

    monkeypatch.setattr(
        "mcp.shared._httpx_utils.create_mcp_http_client",
        make_http_client,
    )
    monkeypatch.setattr(
        "mcp.client.streamable_http.streamable_http_client",
        fake_streamable_http_client,
    )
    monkeypatch.setattr("mcp.client.session.ClientSession", FakeSession)

    manager = MCPClientManager()
    manager.register_config(MCPServerConfig(
        name="work-tools",
        transport="http",
        url="https://tools.example.net/mcp?region=west",
        headers_env={"Authorization": "WORK_TOOLS_AUTH"},
        timeout=8,
    ))

    assert _run(manager.connect_all()) == {"work-tools": True}
    assert seen["headers"] == {"Authorization": "Bearer private-token"}
    result = _run(manager.call_tool("work-tools:search", {"query": "backend upgrades"}))
    assert result.success is True
    assert result.content == ["service response"]
    assert seen["tool_call"] == {
        "name": "search",
        "arguments": {"query": "backend upgrades"},
    }
    assert manager.get_server_status("work-tools")["url"] == "https://tools.example.net"
    assert "private-token" not in json.dumps(manager.get_server_status("work-tools"))

    _run(manager.disconnect_all())
    assert seen["session_closed"] is True
    assert seen["http_closed"] is True
    assert transport_closed == [True]


def test_mcp_config_rejects_url_credentials_and_disabled_stdio(monkeypatch):
    manager = MCPClientManager()

    with pytest.raises(ValueError, match="URL userinfo"):
        manager.register_config(MCPServerConfig(
            name="unsafe",
            transport="http",
            url="https://user:password@example.net/mcp",
        ))
    with pytest.raises(ValueError, match="URL query"):
        manager.register_config(MCPServerConfig(
            name="unsafe-query",
            transport="http",
            url="https://example.net/mcp?access_token=hidden",
        ))
    with pytest.raises(ValueError, match="requires HTTPS"):
        manager.register_config(MCPServerConfig(
            name="insecure-remote",
            transport="http",
            url="http://tools.example.net/mcp",
        ))

    monkeypatch.delenv("JARVIS_MCP_ALLOW_STDIO", raising=False)
    with pytest.raises(ValueError, match="stdio is disabled"):
        manager.register_config(MCPServerConfig(
            name="local-tools",
            transport="stdio",
            command=["python", "-m", "some_mcp_server"],
        ))


def test_environment_mcp_config_loads_without_logging_credentials(monkeypatch, caplog):
    monkeypatch.setenv("MCP_SERVERS", json.dumps([{
        "name": "remote-tools",
        "transport": "sse",
        "url": "https://tools.example.net/sse?region=west",
        "headers_env": {"Authorization": "REMOTE_TOOLS_AUTH"},
    }]))
    manager = MCPClientManager()

    assert manager.load_from_environment() == 1
    assert manager.get_server_status("remote-tools")["url"] == "https://tools.example.net"
    assert "region=west" not in caplog.text


def test_stdio_requires_explicit_enablement(monkeypatch):
    monkeypatch.setenv("JARVIS_MCP_ALLOW_STDIO", "true")
    manager = MCPClientManager()

    manager.register_config(MCPServerConfig(
        name="local-tools",
        transport="stdio",
        command=["python", "-m", "some_mcp_server"],
    ))

    assert manager.get_server_status("local-tools")["exists"] is True
