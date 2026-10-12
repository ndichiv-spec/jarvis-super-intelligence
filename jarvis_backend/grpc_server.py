"""gRPC server layer for JARVIS.

Implements the Protocol Buffer service definitions from proto/jarvis.proto,
bridging typed gRPC calls to the existing JARVIS capability system.

This is the internal service mesh layer — matching the pattern used by
OpenAI Codex's ``app-server`` / ``app-server-protocol`` for typed
inter-service communication. External clients continue to use REST/JSON;
internal services and the agent runtime use gRPC for type safety and
performance.

Usage:
    python -m jarvis_backend.grpc_server

    # Or embedded (called from main on startup):
    from jarvis_backend.grpc_server import start_grpc_server
    start_grpc_server(host="0.0.0.0", port=50051)
"""
from __future__ import annotations

import asyncio
import json
import time
import os
import sys
import logging
import uuid
from concurrent import futures
from typing import Any, Dict, Optional

import grpc

# Make generated proto modules importable
_PROTO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proto")
if _PROTO_DIR not in sys.path:
    sys.path.insert(0, _PROTO_DIR)

from jarvis_pb2 import (
    ExecuteRequest,
    ExecuteResponse,
    HealthCheckRequest,
    HealthCheckResponse,
    CapabilityInfo,
    ListCapabilitiesResponse,
    ToolCall,
    ToolResult,
    ToolInfo,
    ListToolsResponse,
    Event,
    EmitEventRequest,
    EmitEventResponse,
    GetEventsRequest,
    GetEventsResponse,
    Status,
    CorrelationContext as CorrelationContextProto,
    Timestamp as TimestampProto,
)
from jarvis_pb2_grpc import (
    CapabilityServiceServicer,
    add_CapabilityServiceServicer_to_server,
    ToolServiceServicer,
    add_ToolServiceServicer_to_server,
    EventServiceServicer,
    add_EventServiceServicer_to_server,
)

log = logging.getLogger("jarvis.grpc")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_from_bool(success: bool) -> int:
    """Map a boolean success to a proto Status enum value."""
    return Status.STATUS_OK if success else Status.STATUS_ERROR


def _make_context(proto_ctx: Optional[CorrelationContextProto]) -> Any:
    """Convert a proto CorrelationContext into a JARVIS ExecutionContext."""
    if proto_ctx is None:
        proto_ctx = CorrelationContextProto()

    from jarvis_backend.capability import ExecutionContext

    return ExecutionContext(
        user_id=proto_ctx.user_id or "grpc_client",
        session_id=proto_ctx.session_id or "grpc_session",
        correlation_id=proto_ctx.correlation_id or f"grpc-{uuid.uuid4().hex[:12]}",
        permissions=[],
    )


def _make_proto_context(context: Any) -> CorrelationContextProto:
    """Convert a JARVIS ExecutionContext into a proto CorrelationContext."""
    return CorrelationContextProto(
        correlation_id=context.correlation_id,
        session_id=context.session_id,
        user_id=context.user_id,
    )


def _timestamp_proto() -> TimestampProto:
    """Current timestamp as a proto Timestamp."""
    from google.protobuf.timestamp_pb2 import Timestamp
    ts = Timestamp()
    ts.GetCurrentTime()
    return ts


# ---------------------------------------------------------------------------
# Capability Service
# ---------------------------------------------------------------------------

class CapabilityService(CapabilityServiceServicer):
    """gRPC service that bridges to JARVIS's CapabilityRegistry."""

    def __init__(self):
        self._registry = None

    def _get_registry(self):
        if self._registry is None:
            from jarvis_backend.capabilities import get_registry
            self._registry = get_registry()
        return self._registry

    def Execute(self, request: ExecuteRequest, context: grpc.ServicerContext) -> ExecuteResponse:
        """Execute a capability via gRPC."""
        import uuid
        registry = self._registry or self._get_registry()
        ctx = _make_context(request.ctx)
        cap = registry.get(request.capability_name)

        if cap is None:
            return ExecuteResponse(
                status=Status.STATUS_ERROR,
                capability=request.capability_name,
                success=False,
                error=f"Capability '{request.capability_name}' is not registered",
                error_type="NOT_FOUND",
                correlation_id=ctx.correlation_id,
                timestamp=_timestamp_proto(),
            )

        # Run async capability execute in sync context
        params = json.loads(request.params.decode()) if request.params else {}
        request_dict = {"action": request.action, "params": params}

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(cap.execute(request_dict, ctx))
        finally:
            loop.close()

        data_bytes = json.dumps(result.data, default=str).encode() if result.data else b""

        return ExecuteResponse(
            status=_status_from_bool(result.success),
            capability=result.capability,
            success=result.success,
            data=data_bytes,
            error=result.error or "",
            error_type=result.error_type or "",
            latency_ms=result.latency_ms,
            correlation_id=result.correlation_id,
            timestamp=_timestamp_proto(),
        )

    def Health(self, request: HealthCheckRequest, context: grpc.ServicerContext) -> HealthCheckResponse:
        registry = self._registry or self._get_registry()
        cap = registry.get(request.capability_name)

        if cap is None:
            return HealthCheckResponse(
                status=Status.STATUS_UNAVAILABLE,
                capability=request.capability_name,
                healthy=False,
                error="not registered",
            )

        loop = asyncio.new_event_loop()
        try:
            health = loop.run_until_complete(cap.health())
        finally:
            loop.close()

        return HealthCheckResponse(
            status=_status_from_bool(health.get("healthy", False)),
            capability=health.get("capability", request.capability_name),
            healthy=health.get("healthy", False),
            latency_ms=health.get("latency_ms", 0.0),
            error=health.get("error", "") or "",
        )

    def ListCapabilities(self, request, context: grpc.ServicerContext) -> ListCapabilitiesResponse:
        registry = self._registry or self._get_registry()
        infos = []
        for name in registry.list_all():
            cap = registry.get(name)
            infos.append(CapabilityInfo(
                name=name,
                version=cap.version,
                category=cap.category,
                status=_status_from_bool(cap.status in (
                    __import__("jarvis_backend.capability", fromlist=["CapabilityStatus"]).CapabilityStatus.AVAILABLE,
                )),
            ))
        return ListCapabilitiesResponse(capabilities=infos)


# ---------------------------------------------------------------------------
# Tool Service
# ---------------------------------------------------------------------------

class ToolService(ToolServiceServicer):
    """gRPC service for tool execution (MCP bridge)."""

    def __init__(self):
        self._registry = None

    def _get_registry(self):
        if self._registry is None:
            from jarvis_backend.capabilities import get_registry
            self._registry = get_registry()
        return self._registry

    def CallTool(self, request: ToolCall, context: grpc.ServicerContext) -> ToolResult:
        registry = self._registry or self._get_registry()
        tool_cap = registry.get("tool")

        if tool_cap is None:
            return ToolResult(
                status=Status.STATUS_ERROR,
                success=False,
                error="Tool capability not registered",
            )

        ctx = _make_context(request.ctx)
        args = json.loads(request.arguments.decode()) if request.arguments else {}
        args["action"] = request.action

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(tool_cap.execute(
                {"tool": request.tool_name, "action": request.action, "params": args},
                ctx,
            ))
        finally:
            loop.close()

        content_bytes = json.dumps(result.data, default=str).encode() if result.data else b""

        return ToolResult(
            status=_status_from_bool(result.success),
            success=result.success,
            content=content_bytes,
            error=result.error or "",
            latency_ms=result.latency_ms,
            correlation_id=result.correlation_id,
        )

    def ListTools(self, request, context: grpc.ServicerContext) -> ListToolsResponse:
        registry = self._registry or self._get_registry()
        tool_cap = registry.get("tool")

        if tool_cap is None:
            return ListToolsResponse()

        tools = []
        for info in tool_cap.list_tools():
            tools.append(ToolInfo(
                name=info["name"],
                version=info.get("version", ""),
                category=info.get("category", "tool"),
                description="",
                input_schema=b"{}",
            ))
        return ListToolsResponse(tools=tools)


# ---------------------------------------------------------------------------
# Event Service
# ---------------------------------------------------------------------------

class EventService(EventServiceServicer):
    """gRPC service for event emission and retrieval (streaming supported)."""

    def __init__(self):
        self._event_bus = None

    def _get_bus(self):
        if self._event_bus is None:
            from jarvis_backend.event_fabric import get_event_bus
            self._event_bus = get_event_bus()
        return self._event_bus

    def EmitEvent(self, request: EmitEventRequest, context: grpc.ServicerContext) -> EmitEventResponse:
        bus = self._event_bus or self._get_bus()
        event_dict = json.loads(request.event.payload.decode()) if request.event.payload else {}
        bus.emit(type("E", (), {
            "event_type": request.event.event_type,
            "source": request.event.source,
            "capability": request.event.capability,
            "correlation_id": request.event.correlation_id,
            "session_id": request.event.session_id,
            "user_id": request.event.user_id,
            "status": request.event.status,
            "payload": event_dict,
            "metrics": dict(request.event.metrics),
            "timestamp": "",
        })())
        return EmitEventResponse(status=Status.STATUS_OK, event_id=request.event.event_id)

    def GetEvents(self, request: GetEventsRequest, context: grpc.ServicerContext) -> GetEventsResponse:
        bus = self._event_bus or self._get_bus()
        events = bus.get_events(request.event_type if request.event_type else None, request.limit or 100)
        proto_events = []
        for ev in events:
            payload_str = json.dumps(ev.get("payload", {})) if ev.get("payload") else ""
            proto_events.append(Event(
                event_id=ev.get("event_id", ""),
                event_type=ev.get("event_type", ""),
                source=ev.get("source", ""),
                capability=ev.get("capability", ""),
                status=ev.get("status", ""),
                correlation_id=ev.get("correlation_id", ""),
                session_id=ev.get("session_id", ""),
                user_id=ev.get("user_id", ""),
                payload=payload_str.encode(),
            ))
        return GetEventsResponse(events=proto_events)

    def SubscribeEvents(self, request, context: grpc.ServicerContext):
        """Server-streaming: yield events as they arrive."""
        bus = self._event_bus or self._get_bus()
        # Simple polling subscriber — in production, use a proper queue
        seen_ids = set()
        while True:
            events = bus.get_events(limit=10)
            for ev in events:
                if ev.get("event_id") in seen_ids:
                    continue
                seen_ids.add(ev.get("event_id", ""))
                payload_str = json.dumps(ev.get("payload", {})) if ev.get("payload") else ""
                yield Event(
                    event_id=ev.get("event_id", ""),
                    event_type=ev.get("event_type", ""),
                    source=ev.get("source", ""),
                    capability=ev.get("capability", ""),
                    status=ev.get("status", ""),
                    correlation_id=ev.get("correlation_id", ""),
                    session_id=ev.get("session_id", ""),
                    user_id=ev.get("user_id", ""),
                    payload=payload_str.encode(),
                )
            time.sleep(0.5)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

_SERVER: Optional[grpc.aio.Server] = None


async def start_grpc_server(host: str = "0.0.0.0", port: int = 50051) -> int:
    """Start the gRPC server asynchronously (for use with FastAPI lifespan).

    Returns the actual bound port.
    """
    global _SERVER
    if _SERVER is not None:
        return port

    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    server = grpc.aio.server()

    add_CapabilityServiceServicer_to_server(CapabilityService(), server)
    add_ToolServiceServicer_to_server(ToolService(), server)
    add_EventServiceServicer_to_server(EventService(), server)

    actual_port = server.add_insecure_port(f"{host}:{port}")
    await server.start()
    _SERVER = server
    log.info("JARVIS gRPC server started on port %d", actual_port)
    return actual_port


async def stop_grpc_server(grace: float = 5.0) -> None:
    """Stop the embedded gRPC server during FastAPI shutdown."""
    global _SERVER
    server, _SERVER = _SERVER, None
    if server is not None:
        await server.stop(grace)
        await server.wait_for_termination()


def start_grpc_server_blocking(host: str = "0.0.0.0", port: int = 50051) -> None:
    """Start gRPC server (blocking, for standalone use).

    Usage: python -m jarvis_backend.grpc_server
    """
    import uuid  # needed for _make_context

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_CapabilityServiceServicer_to_server(CapabilityService(), server)
    add_ToolServiceServicer_to_server(ToolService(), server)
    add_EventServiceServicer_to_server(EventService(), server)

    server.add_insecure_port(f"{host}:{port}")
    server.start()
    log.info("JARVIS gRPC server (blocking) started on %s:%d", host, port)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


# ---------------------------------------------------------------------------
# Client helpers (for other JARVIS services to call gRPC)
# ---------------------------------------------------------------------------

class GrpcClient:
    """Thin client wrapper for calling JARVIS gRPC services.

    Usage:
        client = GrpcClient("localhost:50051")
        response = client.execute_capability("brain", "process", {"query": "hello"})
    """

    def __init__(self, host: str = "localhost", port: int = 50051):
        self._channel = grpc.insecure_channel(f"{host}:{port}")
        self._capability_stub = None
        self._tool_stub = None
        self._event_stub = None

    def _ensure_stubs(self):
        if self._capability_stub is None:
            from jarvis_pb2_grpc import CapabilityServiceStub
            from jarvis_pb2_grpc import ToolServiceStub
            from jarvis_pb2_grpc import EventServiceStub
            self._capability_stub = CapabilityServiceStub(self._channel)
            self._tool_stub = ToolServiceStub(self._channel)
            self._event_stub = EventServiceStub(self._channel)

    def execute_capability(self, capability_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call Execute on the Capability gRPC service."""
        self._ensure_stubs()
        request = ExecuteRequest(
            capability_name=capability_name,
            action=action,
            params=json.dumps(params).encode() if params else b"{}",
            ctx=CorrelationContextProto(correlation_id=f"client-{uuid.uuid4().hex[:12]}"),
            timeout_seconds=30.0,
        )
        response = self._capability_stub.Execute(request)
        if response.data:
            data = json.loads(response.data.decode())
        else:
            data = {}
        return {
            "success": response.success,
            "status": response.status,
            "data": data,
            "error": response.error,
            "latency_ms": response.latency_ms,
            "correlation_id": response.correlation_id,
        }

    def call_tool(self, tool_name: str, action: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call CallTool on the Tool gRPC service."""
        self._ensure_stubs()
        request = ToolCall(
            tool_name=tool_name,
            action=action,
            arguments=json.dumps(arguments).encode() if arguments else b"{}",
        )
        response = self._tool_stub.CallTool(request)
        content = json.loads(response.content.decode()) if response.content else {}
        return {
            "success": response.success,
            "status": response.status,
            "data": content,
            "error": response.error,
            "latency_ms": response.latency_ms,
        }

    def close(self):
        self._channel.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS gRPC server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50051)
    args = parser.parse_args()
    start_grpc_server_blocking(args.host, args.port)
