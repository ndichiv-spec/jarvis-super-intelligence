"""Authenticated MCP transport for the existing JARVIS capability runtime."""

from __future__ import annotations

import contextvars
import inspect
import json
import keyword
import operator
import os
import time
import uuid
from functools import reduce
from typing import Annotated, Any, Literal, get_args

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import Field, create_model
from starlette.types import ASGIApp, Receive, Scope, Send

from .core import get_current_user

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
_principal: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "jarvis_mcp_principal",
    default=None,
)
_registry: Any | None = None
_server: Any | None = None
_server_app: ASGIApp | None = None
_server_lifespan: Any | None = None
_mounted = False
_started = False
_started_at: float | None = None


def _json_schema_type(schema: dict[str, Any], *, name: str) -> Any:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        types = [
            _json_schema_type({**schema, "type": item}, name=name)
            for item in schema_type
            if item != "null"
        ]
        base = reduce(operator.or_, types) if types else Any
        return base | None if "null" in schema_type else base
    if "enum" in schema:
        values = tuple(schema["enum"])
        if values and all(isinstance(value, str) for value in values):
            return Literal[values]
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        item = _json_schema_type(schema.get("items") or {}, name=f"{name}Item")
        return list[item]
    if schema_type == "object":
        properties = schema.get("properties") or {}
        if not properties:
            return dict[str, Any]
        required = set(schema.get("required") or [])
        fields: dict[str, Any] = {}
        for field_name, field_schema in properties.items():
            python_name = (
                field_name
                if field_name.isidentifier() and not keyword.iskeyword(field_name)
                else f"arg_{field_name}"
            )
            field_type = _json_schema_type(
                field_schema if isinstance(field_schema, dict) else {},
                name=f"{name}_{field_name}",
            )
            field_required = field_name in required
            if not field_required:
                field_type = field_type | None
            metadata: dict[str, Any] = {
                "default": ... if field_required else None,
            }
            if python_name != field_name:
                metadata["alias"] = field_name
            if isinstance(field_schema, dict) and field_schema.get("description"):
                metadata["description"] = field_schema["description"]
            fields[python_name] = (field_type, Field(**metadata))
        model_name = "".join(part.title() for part in name.replace("-", "_").split("_"))
        return create_model(f"Mcp{model_name}", **fields)
    return Any


def _tool_signature(schema: dict[str, Any], *, name: str) -> inspect.Signature:
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    parameters = []
    for argument, definition in properties.items():
        definition = definition if isinstance(definition, dict) else {}
        python_name = (
            argument
            if argument.isidentifier() and not keyword.iskeyword(argument)
            else f"arg_{argument}"
        )
        annotation = _json_schema_type(definition, name=f"{name}_{argument}")
        if argument not in required and type(None) not in get_args(annotation):
            annotation = annotation | None
        field_metadata: dict[str, Any] = {}
        if definition.get("description"):
            field_metadata["description"] = definition["description"]
        constraints = {
            key: definition[key]
            for key in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems")
            if key in definition
        }
        if constraints:
            field_metadata["json_schema_extra"] = constraints
        if field_metadata:
            annotation = Annotated[annotation, Field(**field_metadata)]
        if python_name != argument:
            annotation = Annotated[
                annotation,
                Field(alias=argument, validation_alias=argument),
            ]
        default = inspect.Parameter.empty if argument in required else definition.get("default")
        if argument not in required and default is inspect.Parameter.empty:
            default = None
        parameters.append(
            inspect.Parameter(
                python_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )
    return inspect.Signature(parameters)


def _capability_registry():
    global _registry
    if _registry is not None:
        return _registry
    from research_engine.capability_tools import build_capability_registry

    _registry = build_capability_registry()
    return _registry


def _plain_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    from pydantic import BaseModel

    return {
        key: (value.model_dump(by_alias=True) if isinstance(value, BaseModel) else value)
        for key, value in arguments.items()
    }


def _make_capability_handler(tool_name: str, signature: inspect.Signature):
    async def invoke_capability(**arguments: Any) -> str:
        principal = _principal.get()
        if principal is None:
            from mcp.server.mcpserver.exceptions import ToolError

            raise ToolError("Authentication required")
        from research_engine.tool_registry import ToolContext

        user_id = str(principal.get("id") or principal.get("email") or "")
        result = await _capability_registry().invoke(
            tool_name,
            _plain_arguments(arguments),
            ToolContext(
                request_id=uuid.uuid4().hex,
                user_id=user_id,
                principal=principal,
            ),
        )
        if not result.success:
            from mcp.server.mcpserver.exceptions import ToolError

            raise ToolError(result.error or "Capability execution failed")
        return json.dumps(
            {
                "tool": result.name,
                "success": True,
                "result": result.result,
                "duration_ms": round(result.duration_ms, 2),
            },
            ensure_ascii=False,
            default=str,
        )

    invoke_capability.__name__ = tool_name.replace(".", "_").replace("-", "_")
    invoke_capability.__signature__ = signature
    invoke_capability.__annotations__ = {
        parameter.name: parameter.annotation for parameter in signature.parameters.values()
    } | {"return": str}
    return invoke_capability


def get_mcp_server():
    global _server
    if _server is None:
        from mcp.server.mcpserver import MCPServer
        from mcp.types import ToolAnnotations
        from research_engine.models import RiskLevel

        registry = _capability_registry()
        server = MCPServer(
            name="jarvis",
            title="JARVIS Runtime",
            description="Authenticated tools backed by the JARVIS runtime capability registry.",
            instructions=(
                "Use only listed capabilities. Tool execution uses JARVIS authorization "
                "and returns real results or explicit errors."
            ),
            version="4.0.0",
        )
        for description in registry.describe():
            tool_name = description["name"]
            handler = _make_capability_handler(
                tool_name,
                _tool_signature(
                    description.get("parameters") or {},
                    name=tool_name,
                ),
            )
            risk = RiskLevel(description.get("risk", RiskLevel.READ.value))
            server.add_tool(
                handler,
                name=tool_name,
                description=description.get("description", ""),
                annotations=ToolAnnotations(
                    readOnlyHint=risk == RiskLevel.READ,
                    destructiveHint=risk in {RiskLevel.WRITE, RiskLevel.ADMIN},
                    openWorldHint=risk == RiskLevel.NETWORK,
                ),
            )

        @server.tool(
            name="jarvis_command_events",
            description=(
                "Read persisted events for a JARVIS command owned by the authenticated "
                "user. Use after_sequence to resume replay."
            ),
        )
        async def jarvis_command_events(
            command_id: str,
            after_sequence: int = 0,
            limit: int = 100,
        ) -> str:
            principal = _principal.get()
            if principal is None:
                from mcp.server.mcpserver.exceptions import ToolError

                raise ToolError("Authentication required")
            from .routers.commands import _owned_command
            from .runtime import runtime

            try:
                _owned_command(command_id, principal)
            except HTTPException as exc:
                from mcp.server.mcpserver.exceptions import ToolError

                raise ToolError("Command not found") from exc
            if after_sequence < 0:
                from mcp.server.mcpserver.exceptions import ToolError

                raise ToolError("after_sequence must be non-negative")
            if not 1 <= limit <= 500:
                from mcp.server.mcpserver.exceptions import ToolError

                raise ToolError("limit must be between 1 and 500")
            return json.dumps(
                runtime.replay_events(
                    command_id,
                    after_sequence=after_sequence,
                    limit=limit,
                ),
                ensure_ascii=False,
                default=str,
            )

        @server.resource(
            "jarvis://runtime/status",
            name="JARVIS Runtime Status",
            description="Live backend and persisted execution-store status.",
            mime_type="application/json",
        )
        async def jarvis_runtime_status() -> str:
            from sqlalchemy import text

            from .db import get_engine
            from .runtime import runtime

            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
            tools = await server.list_tools()
            return json.dumps(
                {
                    "runtime": "ALIVE",
                    "database": "AVAILABLE",
                    "mcp": {
                        "protocol": "streamable-http",
                        "tools_registered": len(tools),
                        "events_replay": True,
                        "execution_registry": runtime.__class__.__name__,
                    },
                }
            )

        _server = server
    return _server


def _allowed_hosts() -> list[str]:
    configured = os.environ.get("JARVIS_MCP_ALLOWED_HOSTS", "")
    if configured.strip():
        return [value.strip() for value in configured.split(",") if value.strip()]
    return [
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
        "[::1]",
        "[::1]:*",
        "testserver",
        "testserver:*",
        "testclient",
        "testclient:*",
    ]


def _allowed_origins() -> list[str]:
    configured = os.environ.get("JARVIS_MCP_ALLOWED_ORIGINS", "")
    if configured.strip():
        return [value.strip() for value in configured.split(",") if value.strip()]
    return [
        "http://localhost:*",
        "https://localhost:*",
        "http://127.0.0.1:*",
        "https://127.0.0.1:*",
        "http://testserver",
        "http://testclient",
    ]


async def _authenticated_mcp_app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        assert _server_app is not None
        await _server_app(scope, receive, send)
        return
    authorization = next(
        (
            value.decode("latin-1")
            for key, value in scope.get("headers", [])
            if key.lower() == b"authorization"
        ),
        None,
    )
    try:
        principal = get_current_user(authorization)
    except HTTPException:
        response = JSONResponse(
            {"error": "Authentication required"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)
        return

    context_token = _principal.set(principal)
    try:
        assert _server_app is not None
        if scope["path"] in {"", "/"}:
            scope = {**scope, "path": "/"}
        await _server_app(scope, receive, send)
    finally:
        _principal.reset(context_token)


def _new_mcp_transport() -> ASGIApp:
    global _server_app
    from mcp.server.transport_security import TransportSecuritySettings

    server = get_mcp_server()
    sdk_app = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        host="0.0.0.0",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_allowed_hosts(),
            allowed_origins=_allowed_origins(),
        ),
    )
    _server_app = sdk_app
    return sdk_app


def create_mcp_application() -> ASGIApp:
    _new_mcp_transport()
    return _authenticated_mcp_app


def mount_mcp(app: Any) -> None:
    global _mounted
    if _mounted:
        return
    mcp_app = create_mcp_application()
    app.mount("/mcp", mcp_app, name="mcp")
    _mounted = True

    @app.on_event("startup")
    async def start_mcp_transport() -> None:
        global _server_lifespan, _started, _started_at
        sdk_app = _new_mcp_transport()
        lifespan = sdk_app.router.lifespan_context(sdk_app)
        await lifespan.__aenter__()
        _server_lifespan = lifespan
        _started = True
        _started_at = time.time()

    @app.on_event("shutdown")
    async def stop_mcp_transport() -> None:
        global _server_app, _server_lifespan, _started, _started_at
        if _server_lifespan is not None:
            await _server_lifespan.__aexit__(None, None, None)
            _server_lifespan = None
        _server_app = None
        _started = False
        _started_at = None


async def mcp_status() -> dict[str, Any]:
    try:
        server = get_mcp_server()
        tools = await server.list_tools()
        resource_list = await server.list_resources()
        healthy = bool(_mounted and _started and _server_app is not None and tools)
        return {
            "status": "AVAILABLE" if healthy else "DEGRADED",
            "protocol": "MCP Streamable HTTP",
            "endpoint": "/mcp/",
            "configured": _server is not None,
            "mounted": _mounted,
            "reachable": _mounted and _started,
            "healthy": healthy,
            "executable": healthy,
            "authenticated": True,
            "running": _started,
            "tools_registered": len(tools),
            "resources_registered": len(resource_list),
            "events_replay": any(tool.name == "jarvis_command_events" for tool in tools),
            "last_checked": time.time(),
            "uptime_seconds": (round(time.time() - _started_at, 2) if _started_at else None),
        }
    except Exception as exc:
        return {
            "status": "UNAVAILABLE",
            "protocol": "MCP Streamable HTTP",
            "endpoint": "/mcp/",
            "configured": _server is not None,
            "mounted": _mounted,
            "reachable": False,
            "healthy": False,
            "executable": False,
            "authenticated": True,
            "error": type(exc).__name__,
            "last_checked": time.time(),
        }


@router.get("/status")
async def mcp_status_endpoint(
    user: CurrentUser,
) -> dict[str, Any]:
    del user
    return await mcp_status()
