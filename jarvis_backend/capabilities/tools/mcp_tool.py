"""MCP tool wrapper for JARVIS ToolCapability.

This bridges external MCP (Model Context Protocol) servers into JARVIS's
capability registry.  Each external MCP server is treated as a connector
source, and every tool it exposes becomes available through the JARVIS
ToolCapability with a qualified name of ``mcp:<server>:<tool>``.

The MCP tool wrapper follows the same connector pattern as GitHubTool,
PostgreSQLTool, BrowserTool, etc.:

    Brain
     |- Tool request ("tool": "mcp", "action": "<server>:<tool>", "params": ...)
     |- Authorization
     |- MCP connector
     |- External MCP server
     |- Sanitized result
     |- Brain

Configuration:
    External MCP servers are configured via the ``MCP_SERVERS`` environment
    variable (JSON array of server descriptors) or programmatically via
    ``MCPClientManager.register_config()``.

    Example MCP_SERVERS:
    '''
    [{
        "name": "filesystem",
        "transport": "stdio",
        "command": ["python", "-m", "mcp_server_fs"],
        "timeout": 30
    }, {
        "name": "brave-search",
        "transport": "http",
        "url": "http://localhost:9000/mcp",
        "timeout": 30
    }]
    '''

Security boundary:
    - Credentials are NEVER passed from the Brain to the MCP connector.
    - Each MCP server manages its own auth via its own config/env.
    - Authorization is enforced via _authorize_tool() (requires 'tool.mcp').
    - Sandboxed execution is layered on top via SandboxManager (Phase 3).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

# Ensure jarvis_backend is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

log = None  # type: ignore


def _get_logger():
    global log
    if log is None:
        import logging
        log = logging.getLogger("jarvis.mcp_tool")
    return log


def _ensure_manager():
    """Get the global MCPClientManager singleton, creating if needed."""
    from jarvis_backend.mcp_client import get_mcp_client_manager
    return get_mcp_client_manager()


class MCPTool:
    """Connector tool that bridges external MCP servers into JARVIS.

    Implements the same interface as other JARVIS tools (GitHubTool,
    PostgreSQLTool, BrowserTool): ``health()``, ``execute(action, params, context)``,
    ``shutdown()``.

    The ``action`` field is the qualified tool name ``<server>:<tool>``.
    Params are forwarded as the MCP tool's ``arguments``.
    """

    name = "mcp"
    version = "1.0.0"
    category = "connector"
    description = (
        "MCP (Model Context Protocol) connector — bridges external MCP servers "
        "into JARVIS. Supports stdio, HTTP/SSE, and Streamable HTTP transports. "
        "Each external tool is addressed as '<server>:<tool>'."
    )

    def __init__(self):
        self._manager: Optional[Any] = None
        self._initialized = False
        self._connected_servers: List[str] = []

    async def _ensure_initialized(self) -> bool:
        """Lazily initialize the MCP client manager and connect to servers."""
        if self._initialized:
            return True

        try:
            self._manager = _ensure_manager()
        except Exception as e:
            _get_logger().warning("MCP client manager unavailable: %s", e)
            self._initialized = True  # set so we don't retry every call
            self._manager = None
            return False

        # Load servers from environment and connect
        count = self._manager.load_from_environment()
        if count > 0:
            _get_logger().info("MCP tool: loaded %d server(s) from MCP_SERVERS", count)

        # Connect to all registered servers
        results = await self._manager.connect_all()
        for server_name, ok in results.items():
            if ok:
                self._connected_servers.append(server_name)
                _get_logger().info("MCP tool: connected to server '%s'", server_name)
            else:
                _get_logger().warning("MCP tool: failed to connect to server '%s'", server_name)

        self._initialized = True
        return len(self._connected_servers) > 0

    async def health(self) -> Dict[str, Any]:
        """Check health of MCP server connections and list available tools."""
        await self._ensure_initialized()

        if self._manager is None:
            return {
                "status": "not_configured",
                "healthy": False,
                "error": "MCP client library not available. Install: pip install mcp",
            }

        server_statuses = {}
        total_tools = 0
        for name in self._manager.list_registered_servers():
            status = self._manager.get_server_status(name)
            if status.get("connected"):
                tools = await self._manager.list_tools_by_server(name)
                status["tools"] = [t.tool_name for t in tools]
                status["tool_count"] = len(tools)
                total_tools += len(tools)
            server_statuses[name] = status

        connected = sum(1 for s in server_statuses.values() if s.get("connected"))

        return {
            "status": "ok" if connected > 0 else "not_configured",
            "healthy": connected > 0,
            "connected_servers": connected,
            "registered_servers": len(server_statuses),
            "total_tools": total_tools,
            "servers": server_statuses,
        }

    async def execute(self, action: str, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Execute a tool on an external MCP server.

        Args:
            action: Qualified tool name in ``server:tool`` format
            params: Arguments to pass to the MCP tool (forwarded as-is)
            context: JARVIS ExecutionContext

        Returns:
            Result dict with 'success', 'data', 'error', 'error_type', etc.
        """
        await self._ensure_initialized()

        if self._manager is None:
            return {
                "success": False,
                "error": "MCP client not initialized",
                "error_type": "NOT_INITIALIZED",
            }

        if not action:
            # No action = list available tools
            return await self._handle_list_tools()

        start_time = time.time()
        correlation_id = getattr(context, "correlation_id", f"mcp-{uuid.uuid4().hex[:12]}")

        try:
            result = await self._manager.call_tool(action, params)

            elapsed_ms = (time.time() - start_time) * 1000.0

            if not result.success:
                return {
                    "success": False,
                    "error": result.error or f"Tool '{action}' returned error",
                    "error_type": "MCP_TOOL_ERROR",
                    "correlation_id": correlation_id,
                    "metrics": {"duration_ms": round(elapsed_ms, 2), "is_error": True},
                }

            # Merge text content and structured content into data
            data: Dict[str, Any] = {
                "tool": action,
                "content": result.content,
            }
            if result.structured_content is not None:
                data["structured_content"] = result.structured_content
            if result.metadata:
                data["metadata"] = result.metadata

            return {
                "success": True,
                "data": data,
                "error": None,
                "error_type": None,
                "correlation_id": correlation_id,
                "artifacts": [],
                "metrics": {
                    "duration_ms": round(elapsed_ms, 2),
                    "is_error": False,
                    "content_blocks": len(result.content),
                },
            }

        except Exception as e:
            _get_logger().error("MCP tool execution error: %s", e, exc_info=True)
            return {
                "success": False,
                "error": f"MCP execution error: {str(e)[:300]}",
                "error_type": type(e).__name__,
                "correlation_id": correlation_id,
                "metrics": {"duration_ms": round((time.time() - start_time) * 1000, 2)},
            }

    async def _handle_list_tools(self) -> Dict[str, Any]:
        """When action is empty, list all available MCP tools."""
        tools: List[Dict[str, Any]] = []
        for name in self._manager.list_registered_servers():
            server_tools = await self._manager.list_tools_by_server(name)
            for t in server_tools:
                tools.append({
                    "qualified_name": t.qualified_name,
                    "server": t.server_name,
                    "name": t.tool_name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                })

        return {
            "success": True,
            "data": {
                "available_mcp_servers": self._manager.list_registered_servers(),
                "connected_servers": self._connected_servers,
                "tools": tools,
                "tool_count": len(tools),
            },
            "error": None,
            "error_type": None,
        }

    async def discover_actions(self) -> List[Dict[str, Any]]:
        """Return the connected servers' real MCP tool schemas."""
        await self._ensure_initialized()
        if self._manager is None:
            return []
        result = await self._handle_list_tools()
        return result["data"]["tools"] if result.get("success") else []

    async def shutdown(self) -> bool:
        """Disconnect from all MCP servers."""
        if self._manager is not None:
            try:
                await self._manager.disconnect_all()
            except Exception:
                pass
        self._initialized = False
        self._connected_servers.clear()
        return True


__all__ = ["MCPTool"]
