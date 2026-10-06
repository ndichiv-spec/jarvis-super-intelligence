"""MCP (Model Context Protocol) client for JARVIS.

Consumes external MCP servers and makes their tools available inside the
JARVIS capability runtime.  Supports three transports:

  * Streamable HTTP  (MCP Streamable HTTP — the modern standard)
  * SSE               (legacy MCP SSE transport)
  * Stdio             (command-based MCP servers, e.g. ``python -m mcp_server``)

Tools discovered from external servers are cached and re-exported through
the JARVIS ToolCapability via ``capabilities/tools/mcp_tool.py``.

Security model:
    External MCP servers are sandboxed through JARVIS's SandboxManager
    (Phase 3).  Credentials are never shared between the MCP server and
    client — each server manages its own auth boundary.  Only explicitly
    registered servers are connected.

Usage:
    from jarvis_backend.mcp_client import MCPClientManager

    mgr = MCPClientManager()
    await mgr.register_server("filesystem", url="http://localhost:9000/mcp")
    tools = await mgr.list_all_tools()   # -> [{"server": ..., "tool": ..., "name": ...}]
    result = await mgr.call_tool("filesystem:search", {"query": "hello"})

Environment:
    Set ``MCP_SERVERS`` as a JSON list of server descriptors to connect at
    startup. Keep credentials in named environment variables; never put tokens
    in a URL or descriptor::

        MCP_SERVERS='[{"name":"work-tools","transport":"http","url":"https://tools.example.net/mcp","headers_env":{"Authorization":"WORK_TOOLS_AUTH"}}]'
        WORK_TOOLS_AUTH='Bearer ...'

    Local command-based servers require explicit opt-in with
    ``JARVIS_MCP_ALLOW_STDIO=true``.
"""
from __future__ import annotations

import asyncio
import inspect
import ipaddress
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlsplit, urlunsplit

log = logging.getLogger("jarvis.mcp_client")

# Transport type alias
TransportType = str  # "http" | "sse" | "stdio"


# ---------------------------------------------------------------------------
# Connection descriptors
# ---------------------------------------------------------------------------

@dataclass
class MCPServerConfig:
    """Configuration for an external MCP server connection."""
    name: str
    transport: TransportType  # "http", "sse", or "stdio"
    url: Optional[str] = None          # for http / sse
    command: Optional[List[str]] = None  # for stdio
    env: Optional[Dict[str, str]] = None  # extra env vars for stdio
    headers_env: Dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    auto_reconnect: bool = True
    reconnect_delay: float = 5.0


def _safe_endpoint(url: Optional[str]) -> Optional[str]:
    """Return a URL suitable for status/logging without credentials or query data."""
    if not url:
        return None
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, "", "", ""))


def _resolve_headers(config: MCPServerConfig) -> Dict[str, str]:
    headers = {}
    for name, variable in config.headers_env.items():
        if not re.fullmatch(r"[A-Za-z0-9-]{1,100}", name):
            raise ValueError("Invalid MCP header name")
        value = os.environ.get(variable, "")
        if not value:
            raise RuntimeError(f"Required MCP header environment variable is missing: {variable}")
        if "\r" in value or "\n" in value:
            raise ValueError("MCP header value contains invalid line breaks")
        headers[name] = value
    return headers


def _validate_config(config: MCPServerConfig) -> None:
    if not isinstance(config.name, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,64}", config.name
    ):
        raise ValueError("MCP server name must use letters, numbers, '.', '_' or '-'")
    if not isinstance(config.transport, str) or config.transport not in {
        "http", "sse", "stdio"
    }:
        raise ValueError(f"Unsupported MCP transport: {config.transport}")
    if (
        isinstance(config.timeout, bool)
        or not isinstance(config.timeout, (int, float))
        or not 0.1 <= config.timeout <= 300
    ):
        raise ValueError("MCP timeout must be between 0.1 and 300 seconds")
    if config.transport in {"http", "sse"}:
        parsed = urlsplit(config.url or "")
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("MCP HTTP transport requires an absolute HTTP(S) URL")
        _ = parsed.port
        if parsed.username or parsed.password:
            raise ValueError("MCP credentials must be supplied through headers_env, not URL userinfo")
        if any(
            re.search(r"token|secret|api[_-]?key|auth|signature|credential", key, re.I)
            for key, _value in parse_qsl(parsed.query)
        ):
            raise ValueError("MCP credentials must be supplied through headers_env, not the URL query")
        if parsed.scheme == "http":
            try:
                local_host = parsed.hostname == "localhost" or ipaddress.ip_address(
                    parsed.hostname
                ).is_loopback
            except ValueError:
                local_host = False
            if not local_host and os.environ.get(
                "JARVIS_MCP_ALLOW_INSECURE_HTTP", ""
            ).strip().lower() not in {"1", "true", "yes", "on"}:
                raise ValueError(
                    "MCP HTTP requires HTTPS except on loopback; insecure remote HTTP needs explicit opt-in"
                )
    if not isinstance(config.headers_env, dict) or any(
        not isinstance(name, str)
        or not isinstance(variable, str)
        or not re.fullmatch(r"[A-Za-z0-9-]{1,100}", name)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", variable)
        for name, variable in config.headers_env.items()
    ):
        raise ValueError("MCP headers_env must map HTTP headers to environment variable names")
    if config.transport == "stdio":
        if os.environ.get("JARVIS_MCP_ALLOW_STDIO", "").strip().lower() not in {
            "1", "true", "yes", "on"
        }:
            raise ValueError("MCP stdio is disabled; set JARVIS_MCP_ALLOW_STDIO=true to enable it")
        if (
            not config.command
            or not config.command[0]
            or not all(isinstance(arg, str) for arg in config.command)
        ):
            raise ValueError("MCP stdio transport requires a command argument list")
        if config.env is not None and (
            not isinstance(config.env, dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in config.env.items()
            )
        ):
            raise ValueError("MCP stdio environment must contain string keys and values")


@dataclass
class MCPToolInfo:
    """Metadata about a tool discovered from an MCP server."""
    server_name: str
    tool_name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    title: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        """Fully-qualified name: ``server:tool``."""
        return f"{self.server_name}:{self.tool_name}"


@dataclass
class MCPCallResult:
    """Result of calling an MCP tool."""
    success: bool
    content: List[str] = field(default_factory=list)
    structured_content: Optional[Any] = None
    is_error: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Per-server connection
# ---------------------------------------------------------------------------

class _MCPServerConnection:
    """Manages a single MCP server connection (transport + session)."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: Optional[Any] = None
        self._read_stream = None
        self._write_stream = None
        self._transport_ctx = None
        self._http_client = None
        self._connected = False
        self._last_connect: float = 0.0
        self._tool_cache: Dict[str, MCPToolInfo] = {}
        self._tool_cache_ts: float = 0.0
        self._tools_ttl: float = 60.0  # cache for 60 seconds

    # -- lifecycle ----------------------------------------------------------

    async def connect(self) -> bool:
        """Establish the MCP session. Returns True on success."""
        if self.config.transport == "http":
            return await self._connect_streamable_http()
        elif self.config.transport == "sse":
            return await self._connect_sse()
        elif self.config.transport == "stdio":
            return await self._connect_stdio()
        else:
            log.error("Unknown transport type: %s", self.config.transport)
            return False

    async def _connect_streamable_http(self) -> bool:
        try:
            from mcp.client.streamable_http import streamable_http_client
            from mcp.client.session import ClientSession

            headers = _resolve_headers(self.config)
            parameters = inspect.signature(streamable_http_client).parameters
            if "http_client" in parameters:
                from mcp.shared._httpx_utils import create_mcp_http_client
                import httpx2

                self._http_client = create_mcp_http_client(
                    headers=headers,
                    timeout=httpx2.Timeout(
                        self.config.timeout,
                        read=self.config.timeout,
                    ),
                )
                self._transport_ctx = streamable_http_client(
                    self.config.url,
                    http_client=self._http_client,
                )
            else:
                self._transport_ctx = streamable_http_client(
                    self.config.url,
                    headers=headers,
                )
            self._read_stream, self._write_stream = await self._transport_ctx.__aenter__()

            self._session = ClientSession(
                read_stream=self._read_stream,
                write_stream=self._write_stream,
                read_timeout_seconds=self.config.timeout,
            )
            await self._session.initialize()
            self._connected = True
            self._last_connect = time.time()
            log.info("Connected to MCP server '%s' via Streamable HTTP at %s",
                     self.config.name, _safe_endpoint(self.config.url))
            return True
        except Exception as e:
            log.error("Streamable HTTP connection to '%s' failed: %s",
                      self.config.name, type(e).__name__)
            await self._cleanup_streams()
            return False

    async def _connect_sse(self) -> bool:
        try:
            from mcp.client.sse import sse_client
            from mcp.client.session import ClientSession

            self._transport_ctx = sse_client(
                self.config.url,
                headers=_resolve_headers(self.config),
            )
            self._read_stream, self._write_stream = await self._transport_ctx.__aenter__()

            self._session = ClientSession(
                read_stream=self._read_stream,
                write_stream=self._write_stream,
                read_timeout_seconds=self.config.timeout,
            )
            await self._session.initialize()
            self._connected = True
            self._last_connect = time.time()
            log.info("Connected to MCP server '%s' via SSE at %s",
                     self.config.name, _safe_endpoint(self.config.url))
            return True
        except Exception as e:
            log.error("SSE connection to '%s' failed: %s",
                      self.config.name, type(e).__name__)
            await self._cleanup_streams()
            return False

    async def _connect_stdio(self) -> bool:
        try:
            from mcp.client.stdio import stdio_client, StdioServerParameters
            from mcp.client.session import ClientSession

            params = StdioServerParameters(
                command=self.config.command[0],
                args=self.config.command[1:],
                env={**(os.environ), **(self.config.env or {})},
            )
            self._transport_ctx = stdio_client(params)
            self._read_stream, self._write_stream = await self._transport_ctx.__aenter__()

            self._session = ClientSession(
                read_stream=self._read_stream,
                write_stream=self._write_stream,
                read_timeout_seconds=self.config.timeout,
            )
            await self._session.initialize()
            self._connected = True
            self._last_connect = time.time()
            log.info("Connected to MCP server '%s' via stdio", self.config.name)
            return True
        except Exception as e:
            log.error("Stdio connection to '%s' failed: %s",
                      self.config.name, type(e).__name__)
            await self._cleanup_streams()
            return False

    async def _cleanup_streams(self):
        """Clean up transport streams."""
        try:
            if self._session is not None:
                await self._session.close()
        except Exception as exc:
            log.warning("MCP session close failed for '%s': %s",
                        self.config.name, type(exc).__name__)
        try:
            if self._transport_ctx is not None:
                await self._transport_ctx.__aexit__(None, None, None)
        except Exception as exc:
            log.warning("MCP transport close failed for '%s': %s",
                        self.config.name, type(exc).__name__)
        try:
            if self._http_client is not None:
                await self._http_client.aclose()
        except Exception as exc:
            log.warning("MCP HTTP client close failed for '%s': %s",
                        self.config.name, type(exc).__name__)
        self._session = None
        self._transport_ctx = None
        self._http_client = None
        self._read_stream = None
        self._write_stream = None
        self._connected = False

    async def disconnect(self):
        await self._cleanup_streams()
        self._tool_cache.clear()
        self._tool_cache_ts = 0.0
        log.info("Disconnected from MCP server '%s'", self.config.name)

    async def reconnect(self) -> bool:
        """Reconnect to the server, clearing stale state first."""
        await self.disconnect()
        return await self.connect()

    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    # -- tool discovery -----------------------------------------------------

    async def list_tools(self) -> List[MCPToolInfo]:
        """List all tools available from this server (cached)."""
        now = time.time()
        if self._tool_cache and (now - self._tool_cache_ts) < self._tools_ttl:
            return list(self._tool_cache.values())

        if not self.is_connected:
            return []

        try:
            result = await self._session.list_tools()
            self._tool_cache = {}
            for tool in result.tools:
                info = MCPToolInfo(
                    server_name=self.config.name,
                    tool_name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    output_schema=getattr(tool, "outputSchema", None),
                    title=getattr(tool, "title", None),
                )
                self._tool_cache[info.qualified_name] = info
            self._tool_cache_ts = time.time()
            return list(self._tool_cache.values())
        except Exception as e:
            log.error("list_tools failed for '%s': %s", self.config.name, e)
            return []

    # -- tool execution -----------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPCallResult:
        """Call a tool on this server by raw tool name."""
        if not self.is_connected:
            return MCPCallResult(
                success=False, is_error=True,
                error=f"Server '{self.config.name}' is not connected",
            )

        start = time.time()
        try:
            result = await self._session.call_tool(tool_name, arguments or {})

            content_texts: List[str] = []
            structured: Optional[Any] = None
            for content_block in result.content or []:
                if hasattr(content_block, "text"):
                    content_texts.append(content_block.text)
                elif hasattr(content_block, "structured_content"):
                    structured = content_block.structured_content

            return MCPCallResult(
                success=not result.isError,
                content=content_texts,
                structured_content=structured,
                is_error=result.isError,
                error=None if not result.isError else "Tool returned error",
                duration_ms=(time.time() - start) * 1000.0,
            )
        except Exception as e:
            return MCPCallResult(
                success=False, is_error=True,
                error=f"{type(e).__name__}: {str(e)[:300]}",
                duration_ms=(time.time() - start) * 1000.0,
            )


# ---------------------------------------------------------------------------
# Manager: multiple server connections
# ---------------------------------------------------------------------------

class MCPClientManager:
    """Manages connections to multiple external MCP servers."""

    def __init__(self):
        self._servers: Dict[str, _MCPServerConnection] = {}
        self._connected_at_startup: List[str] = []

    # -- server lifecycle ---------------------------------------------------

    def register_config(self, config: MCPServerConfig) -> None:
        """Register a server config (not yet connected)."""
        _validate_config(config)
        current = self._servers.get(config.name)
        if current is not None and current.config == config:
            return
        if current is not None and current.is_connected:
            raise ValueError("Disconnect the existing MCP server before changing its config")
        self._servers[config.name] = _MCPServerConnection(config)

    def register_config_from_dict(self, data: Dict[str, Any]) -> MCPServerConfig:
        """Register a server from a dict (transport, url/command, etc.)."""
        config = MCPServerConfig(**{
            k: data[k] for k in ("name", "transport") if k in data
        } | {
            k: v for k, v in data.items()
            if k not in ("name", "transport")
        })
        self.register_config(config)
        return config

    async def connect_server(self, name: str) -> bool:
        conn = self._servers.get(name)
        if conn is None:
            return False
        try:
            ok = await asyncio.wait_for(conn.connect(), timeout=conn.config.timeout)
        except asyncio.TimeoutError:
            log.warning("MCP server '%s' connection timed out", name)
            await conn.disconnect()
            return False
        if ok and name not in self._connected_at_startup:
            self._connected_at_startup.append(name)
        return ok

    async def disconnect_server(self, name: str) -> None:
        conn = self._servers.get(name)
        if conn:
            await conn.disconnect()

    async def connect_all(self) -> Dict[str, bool]:
        """Connect to all registered servers. Returns {name: success}."""
        names = list(self._servers)
        outcomes = await asyncio.gather(
            *(
                self.connect_server(name)
                if not self._servers[name].is_connected
                else asyncio.sleep(0, result=True)
                for name in names
            )
        )
        return dict(zip(names, outcomes, strict=True))

    async def disconnect_all(self) -> None:
        for name in list(self._servers.keys()):
            await self.disconnect_server(name)

    async def reload_config(self) -> Dict[str, bool]:
        """Disconnect and reconnect all servers (hot reload)."""
        await self.disconnect_all()
        return await self.connect_all()

    # -- tool discovery -----------------------------------------------------

    def list_registered_servers(self) -> List[str]:
        return list(self._servers.keys())

    def get_server_status(self, name: str) -> Dict[str, Any]:
        conn = self._servers.get(name)
        if conn is None:
            return {"exists": False}
        return {
            "exists": True,
            "connected": conn.is_connected,
            "transport": conn.config.transport,
            "url": _safe_endpoint(conn.config.url),
            "last_connect": conn._last_connect,
            "cached_tool_count": len(conn._tool_cache),
        }

    async def list_all_tools(self) -> List[MCPToolInfo]:
        """List tools from ALL connected servers."""
        all_tools: List[MCPToolInfo] = []
        for conn in self._servers.values():
            if conn.is_connected:
                all_tools.extend(await conn.list_tools())
        return all_tools

    async def list_tools_by_server(self, server_name: str) -> List[MCPToolInfo]:
        conn = self._servers.get(server_name)
        if conn is None or not conn.is_connected:
            return []
        return await conn.list_tools()

    # -- tool execution -----------------------------------------------------

    async def call_tool(self, qualified_name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPCallResult:
        """Call a tool by ``server:tool_name`` qualified name."""
        if ":" not in qualified_name:
            return MCPCallResult(
                success=False, is_error=True,
                error="qualified_name must be 'server:tool'",
            )

        server_name, tool_name = qualified_name.split(":", 1)
        conn = self._servers.get(server_name)
        if conn is None:
            return MCPCallResult(success=False, is_error=True,
                               error=f"No MCP server named '{server_name}'")
        if not conn.is_connected:
            if conn.config.auto_reconnect:
                if not await conn.reconnect():
                    return MCPCallResult(success=False, is_error=True,
                                       error=f"Server '{server_name}' reconnection failed")
            else:
                return MCPCallResult(success=False, is_error=True,
                                   error=f"Server '{server_name}' is not connected")

        return await conn.call_tool(tool_name, arguments)

    # -- auto-configuration -------------------------------------------------

    def load_from_environment(self) -> int:
        """Load server configs from the ``MCP_SERVERS`` env var."""
        raw = os.environ.get("MCP_SERVERS", "")
        if not raw:
            return 0

        try:
            servers = json.loads(raw) if raw.strip().startswith("[") else [json.loads(raw)]
        except json.JSONDecodeError as e:
            log.warning("MCP_SERVERS is not valid JSON: %s", e)
            return 0
        if not isinstance(servers, list):
            log.warning("MCP_SERVERS must contain a JSON array or object")
            return 0

        count = 0
        for entry in servers:
            try:
                if not isinstance(entry, dict):
                    raise ValueError("MCP server descriptor must be an object")
                self.register_config_from_dict(entry)
                count += 1
            except Exception as e:
                name = entry.get("name", "unnamed") if isinstance(entry, dict) else "unnamed"
                log.warning("Skipping MCP server config '%s': %s", name, type(e).__name__)

        if count:
            log.info("Loaded %d MCP server(s) from environment", count)
        return count


# ---------------------------------------------------------------------------
# Singleton convenience
# ---------------------------------------------------------------------------

_default_manager: Optional[MCPClientManager] = None


def get_mcp_client_manager() -> MCPClientManager:
    """Get or create the singleton MCPClientManager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = MCPClientManager()
        _default_manager.load_from_environment()
    return _default_manager


async def start_mcp_clients() -> Dict[str, bool]:
    """Connect to explicitly configured MCP servers during application startup."""
    manager = get_mcp_client_manager()
    return await manager.connect_all()


async def stop_mcp_clients() -> None:
    """Close MCP sessions and transport resources during application shutdown."""
    if _default_manager is not None:
        await _default_manager.disconnect_all()


__all__ = [
    "MCPServerConfig",
    "MCPToolInfo",
    "MCPCallResult",
    "MCPClientManager",
    "get_mcp_client_manager",
    "start_mcp_clients",
    "stop_mcp_clients",
]
