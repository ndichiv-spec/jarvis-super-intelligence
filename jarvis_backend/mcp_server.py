"""MCP (Model Context Protocol) server adapter for JARVIS tools.

Exposes JARVIS's existing tool/connectors (browser, github, postgresql) as
MCP tools so that any MCP-compatible client (Claude Code, Codex, custom agents)
can discover and invoke them.

This is the bridge layer that makes JARVIS tools consumable via the emerging
standard protocol used by OpenAI Codex (``ext/mcp``), Anthropic Claude Code,
and other modern AI agent platforms.

Usage:
    # Stdio transport (MCP client <-> this server)
    python -m jarvis_backend.mcp_server

    # Or via the JARVIS API:
    # POST /mcp -- raw MCP protocol over HTTP

Security:
    All tool execution goes through the existing JARVIS ToolCapability security
    boundary: credentials are NEVER passed from the MCP client. Tools access
    their own credentials via the vault/secrets manager. HTTP requests require
    a JARVIS session or bearer credential; per-tool grants come from server-side
    RBAC. The stdio transport has no authenticated principal and no tool grants.
    Authorization is enforced per-tool via _authorize_tool().
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
import os
import sys
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# MCP SDK imports
# ---------------------------------------------------------------------------
try:
    from mcp.server import Server as McpServer
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions
    from mcp import types
    from mcp.types import Tool as McpTool
    from mcp.types import (
        CallToolRequestParams,
        CallToolResult,
        Tool,
        TextContent,
        ErrorData,
    )
except ImportError:
    # MCP not installed — module is still importable (server simply unavailable)
    McpServer = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    McpTool = None
    Tool = None
    CallToolRequestParams = None
    CallToolResult = None
    TextContent = None
    ErrorData = None
    InitializationOptions = None
    NotificationOptions = None

import logging

log = logging.getLogger("jarvis.mcp")

# ---------------------------------------------------------------------------
# Tool metadata: maps JARVIS tool name -> MCP tool definition
# ---------------------------------------------------------------------------

def _github_tool_schema() -> Dict[str, Any]:
    """JSON Schema for GitHub tool operations."""
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "GitHub operation to perform",
                "enum": ["get_repo", "list_repos", "list_issues", "list_commits", "create_issue"],
            },
            "owner": {"type": "string", "description": "Repository owner (user or org)"},
            "repo": {"type": "string", "description": "Repository name"},
            "state": {"type": "string", "default": "open", "description": "Issue state filter"},
            "title": {"type": "string", "description": "Issue title (for create_issue)"},
            "body": {"type": "string", "description": "Issue body (for create_issue)"},
            "per_page": {"type": "integer", "default": 10, "description": "Number of items to return"},
        },
        "required": ["action"],
    }


def _postgresql_tool_schema() -> Dict[str, Any]:
    """JSON Schema for PostgreSQL tool operations."""
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Database operation to perform",
                "enum": ["execute", "query", "list_tables", "describe_table", "health"],
            },
            "query": {"type": "string", "description": "(for execute/query) SQL statement"},
            "table": {"type": "string", "description": "(for describe_table) table name"},
        },
        "required": ["action"],
    }


def _browser_tool_schema() -> Dict[str, Any]:
    """JSON Schema for browser automation tool operations."""
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Browser operation to perform",
                "enum": ["create_session", "navigate", "fetch", "execute_script", "close_session"],
            },
            "url": {"type": "string", "description": "(for navigate/fetch) target URL"},
            "session_id": {"type": "string", "description": "Browser session ID (optional)"},
            "script": {"type": "string", "description": "(for execute_script) JavaScript code"},
            "timeout": {"type": "number", "default": 30, "description": "Request timeout in seconds"},
        },
        "required": ["action"],
    }


def _science_tool_schema() -> Dict[str, Any]:
    """JSON Schema for scientific reasoning tool operations."""
    return {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Science operation to perform",
                "enum": ["solve", "derivative", "integral", "integrate", "limit", "series",
                         "determinant", "inverse", "eigenvalues", "roots", "optimize",
                         "mean", "std", "median", "monte_carlo", "hypothesis", "test_hypothesis"],
            },
            "problem": {"type": "string", "description": "Mathematical expression or equation"},
            "variable": {"type": "string", "default": "x", "description": "Variable to solve for"},
            "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                       "description": "(for determinant/inverse/eigenvalues) 2D matrix data"},
            "vector": {"type": "array", "items": {"type": "number"}, "description": "(for solve) RHS vector"},
            "data": {"type": "array", "items": {"type": "number"}, "description": "(for statistics) data array"},
            "x_min": {"type": "number", "default": -10.0, "description": "(for integrate/roots/optimize) lower bound"},
            "x_max": {"type": "number", "default": 10.0, "description": "(for integrate/roots/optimize) upper bound"},
            "num_points": {"type": "integer", "default": 1000, "description": "Number of sample points"},
            "n_samples": {"type": "integer", "default": 100000, "description": "(for monte_carlo) number of samples"},
            "mc_operation": {"type": "string", "default": "estimate_pi", "description": "(for monte_carlo) MC operation"},
        },
        "required": ["operation"],
    }


def _mcp_tool_schema() -> Dict[str, Any]:
    """JSON Schema for MCP connector tool operations (connects to external MCP servers)."""
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "MCP connector operation. Empty action lists all available external MCP tools.",
            },
            "server": {"type": "string", "description": "External MCP server name (for server:status, server:reconnect)"},
            "query": {"type": "string", "description": "(for server:discover) search query for available tools"},
        },
        "required": ["action"],
    }


def _research_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Research operation to perform",
                "enum": ["initialize", "ingest_feed", "search_arxiv", "ingest_url",
                         "get_knowledge_graph", "discover_new_feeds", "get_status",
                         "ingest_content"],
            },
            "feed_id": {"type": "string", "description": "(for ingest_feed) feed identifier"},
            "query": {"type": "string", "description": "(for search_arxiv) search query"},
            "url": {"type": "string", "description": "(for ingest_url) URL to crawl"},
            "title": {"type": "string", "description": "(for ingest_content) title of content"},
            "content": {"type": "string", "description": "(for ingest_content) content to ingest"},
            "source": {"type": "string", "description": "(for ingest_content) source label"},
            "source_type": {"type": "string", "default": "web_crawl", "description": "Source type"},
            "max_results": {"type": "integer", "default": 10, "description": "(for search_arxiv) max results"},
        },
        "required": ["action"],
    }


# Maps MCP tool name -> (JARVIS tool name, schema, description)
_TOOL_CATALOG: Dict[str, Dict[str, Any]] = {
    "github": {
        "jarvis_tool": "github",
        "schema": _github_tool_schema(),
        "description": "GitHub API integration for repos, issues, PRs, commits",
    },
    "postgresql": {
        "jarvis_tool": "postgresql",
        "schema": _postgresql_tool_schema(),
        "description": "PostgreSQL database connector for queries, schema inspection",
    },
    "browser": {
        "jarvis_tool": "browser",
        "schema": _browser_tool_schema(),
        "description": "Browser automation for web navigation, content extraction, scripting",
    },
    "science": {
        "jarvis_tool": "science",
        "schema": _science_tool_schema(),
        "description": "Scientific reasoning: symbolic math (SymPy), numerical computation (NumPy/SciPy), hypothesis testing, Monte Carlo",
    },
    "research": {
        "jarvis_tool": "research",
        "schema": _research_tool_schema(),
        "description": "Research cortex: RSS/Atom feed ingestion, arXiv search, web crawling, knowledge graph",
    },
    "mcp": {
        "jarvis_tool": "mcp",
        "schema": _mcp_tool_schema(),
        "description": "MCP connector — discovers and invokes tools from external MCP servers (stdio, HTTP, SSE). Lists external tools when action is empty.",
    },
}

_MCP_PRINCIPAL: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "jarvis_mcp_principal",
    default=None,
)
_TOOL_PERMISSIONS = {
    "github": "tool.github",
    "postgresql": "tool.database",
    "browser": "tool.browser",
    "science": "tool.science",
    "research": "tool.research",
    "mcp": "tool.mcp",
}


def _execution_context():
    """Build tool authority only from the authenticated HTTP principal."""
    from jarvis_backend.capability import ExecutionContext

    principal = _MCP_PRINCIPAL.get()
    if principal is None:
        return ExecutionContext(
            user_id="mcp_client",
            session_id=f"mcp-{uuid.uuid4().hex[:8]}",
            correlation_id=f"mcp-{uuid.uuid4().hex[:12]}",
        )

    from jarvis_backend.core import has_permission, is_admin

    user_id = principal.get("id") or principal.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise RuntimeError("Authenticated MCP principal has no user identity")

    permissions = [
        permission
        for permission in _TOOL_PERMISSIONS.values()
        if has_permission(principal, permission)
    ]
    if is_admin(principal):
        permissions.append("admin")

    return ExecutionContext(
        user_id=user_id,
        session_id=f"mcp-{uuid.uuid4().hex[:8]}",
        correlation_id=f"mcp-{uuid.uuid4().hex[:12]}",
        permissions=permissions,
    )


class _AuthenticatedMCPHTTPApp:
    """Authenticate each MCP HTTP request and bind its principal to tool calls."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        try:
            from jarvis_backend.core import get_current_user

            principal = get_current_user(
                authorization=request.headers.get("authorization"),
                request=request,
            )
        except HTTPException as exc:
            response = JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=exc.headers,
            )
            await response(scope, receive, send)
            return

        token = _MCP_PRINCIPAL.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            _MCP_PRINCIPAL.reset(token)


# ---------------------------------------------------------------------------
# Tool execution bridge: MCP tool call -> JARVIS ToolCapability.execute()
# ---------------------------------------------------------------------------

def _get_tool_capability():
    """Get the JARVIS ToolCapability instance."""
    from jarvis_backend.capabilities import get_registry
    registry = get_registry()
    tool_cap = registry.get("tool")
    if tool_cap is None:
        raise RuntimeError("Tool capability not registered in JARVIS registry")
    return tool_cap


def _build_mcp_tools() -> List[Tool]:
    """Build the list of MCP Tool definitions from the JARVIS tool catalog."""
    if Tool is None:
        return []
    tools = []
    for mcp_name, info in _TOOL_CATALOG.items():
        tools.append(Tool(
            name=mcp_name,
            description=info["description"],
            inputSchema=info["schema"],
        ))
    return tools


async def _execute_jarvis_tool(
    tool_name: str,
    arguments: Optional[Dict[str, Any]],
) -> CallToolResult:
    """Execute a JARVIS tool and return the result as MCP CallToolResult."""
    if Tool is None:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({"error": "MCP SDK not installed"}))],
            isError=True,
        )

    args = dict(arguments or {})
    tool_cap = _get_tool_capability()

    # MCP tool arguments are untrusted and cannot establish an authenticated
    # JARVIS principal. The standalone transport receives no user grants.
    args.pop("_user_id", None)
    args.pop("_session_id", None)

    context = _execution_context()

    # Map MCP tool name to JARVIS tool name and extract action + params
    catalog_entry = _TOOL_CATALOG.get(tool_name)
    if catalog_entry is None:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "error_type": "TOOL_NOT_FOUND",
            }))],
            isError=True,
        )

    jarvis_tool_name = catalog_entry["jarvis_tool"]
    action = args.pop("action", "")
    if not action:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Missing required parameter: action",
                "error_type": "INVALID_INPUT",
            }))],
            isError=True,
        )

    # Execute via the ToolCapability (goes through auth + security boundary)
    result = await tool_cap.execute(
        {
            "tool": jarvis_tool_name,
            "action": action,
            "params": args,
        },
        context,
    )

    result_dict = result.to_dict() if hasattr(result, "to_dict") else {
        "success": result.success,
        "data": result.data,
        "error": result.error,
    }

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result_dict, default=str))],
        isError=not result_dict.get("success", False),
    )


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

def _handle_list_tools(ctx, params):
    """MCP handler: list available JARVIS tools."""
    tools = []
    for mcp_name, info in _TOOL_CATALOG.items():
        tools.append(McpTool(
            name=mcp_name,
            description=info["description"],
            inputSchema=info["schema"],
        ))
    return types.ListToolsResult(tools=tools)


async def _handle_call_tool(name: str, arguments: Optional[Dict[str, Any]]) -> CallToolResult:
    """MCP handler: execute a JARVIS tool by name."""
    return await _execute_jarvis_tool(name, arguments)


def create_mcp_server() -> Optional[McpServer]:
    """Create and configure the MCP server that wraps JARVIS tools.

    Uses the constructor-based registration API of mcp 2.x where tool
    handlers (``on_list_tools`` / ``on_call_tool``) are passed as keyword
    arguments to the ``Server`` constructor.
    """
    if McpServer is None:
        log.warning("MCP SDK not installed; MCP server unavailable")
        return None

    async def handle_list_tools(ctx, params):
        return _handle_list_tools(ctx, params)

    async def handle_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:
        return await _handle_call_tool(params.name, params.arguments)

    server = McpServer(
        "jarvis-tools",
        version="3.0.0",
        on_list_tools=handle_list_tools,
        on_call_tool=handle_call_tool,
    )

    return server


# ---------------------------------------------------------------------------
# HTTP transport: Serve MCP over HTTP (SSE) for JARVIS API integration
# ---------------------------------------------------------------------------

def get_mcp_http_app():
    """Return a Starlette/FastAPI ASGI app for MCP over HTTP/SSE transport.

    Mount this at /mcp on the JARVIS FastAPI app to serve MCP protocol
    over HTTP using the standard MCP Streamable HTTP transport.
    """
    if McpServer is None:
        return None

    server = create_mcp_server()
    if server is None:
        return None

    # The streamable_http_app() method returns a fully configured ASGI app
    # that handles session management, SSE streaming, and JSON-RPC framing.
    return _AuthenticatedMCPHTTPApp(server.streamable_http_app())


# ---------------------------------------------------------------------------
# Stdio transport: For direct MCP client connection (like Claude Code, Codex)
# ---------------------------------------------------------------------------

def run_stdio_server():
    """Run the MCP server over stdio transport.

    This is the standard MCP transport used by Claude Code and Codex CLI.
    Clients communicate via JSON-RPC over stdin/stdout:

        python -m jarvis_backend.mcp_server
    """
    if McpServer is None:
        log.error("MCP SDK not installed. Install: pip install mcp")
        sys.exit(1)

    from mcp.server.stdio import stdio_server

    server = create_mcp_server()
    if server is None:
        sys.exit(1)

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server={
                        "name": "jarvis-tools",
                        "version": "3.0.0",
                    },
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                    ),
                ),
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_stdio_server()
