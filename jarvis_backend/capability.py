"""
JARVIS CAPABILITY RUNTIME & ORCHESTRATION FABRIC
================================================

This module establishes the common capability contract that all JARVIS
subsystems adhere to. It provides:

- Capability base class with health/execute/shutdown lifecycle
- Capability registry for discovery
- Event bus for capability events
- Orchestrator that connects Brain -> Capabilities
- Correlation ID propagation
- Persistence for capability state
- Security/authorization integration

This is the orchestration layer described in the JARVIS architecture:

    User
     |
    Interaction Layer
     |
    Orchestrator
     |
    Brain
     |
    Capability selection
     |
    Authorization
     |
    Capability execution
     |
    Result
     |
    Brain
     |
    Response
     |
    Interaction Layer
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

# ============================================================================
# STATUS ENUMERATION (truthful, never fake)
# ============================================================================

class CapabilityStatus(str, Enum):
    """Truthful capability status values."""
    AVAILABLE = "available"
    CONFIGURED = "configured"  # Configuration exists but the operation is not verified
    UNAVAILABLE = "unavailable"  # Capability not available
    NOT_CONFIGURED = "not_configured"  # Missing configuration/dependencies
    DEGRADED = "degraded"  # Available but with limited function
    OFFLINE = "offline"  # Service is down
    ERROR = "error"  # Operational error
    ACTIVE = "active"  # Capability is currently processing
    READY = "ready"  # Capability is ready for use
    AUTH_FAILED = "auth_failed"  # Authentication required/rejected
    RATE_LIMITED = "rate_limited"  # Rate limited
    UNSUPPORTED = "unsupported"  # Not supported in this environment


# ============================================================================
# CAPABILITY CONTRACT
# ============================================================================

class Capability(ABC):
    """
    Common runtime contract for ALL JARVIS capabilities.

    Every capability must implement this interface so the orchestrator
    can discover, health-check, execute, and shut down any capability
    uniformly.

    Capabilities are independent subsystems that can:
    - Report their real health status
    - Execute requests with proper context
    - Be cancelled mid-execution
    - Persist their results
    - Emit events for observability
    """

    # Override in subclasses
    name: str = "abstract"
    version: str = "1.0.0"
    category: str = "abstract"
    sensitive: bool = False

    def __init__(self):
        self._status: CapabilityStatus = CapabilityStatus.UNAVAILABLE
        self._error: Optional[str] = None
        self._last_health_check: Optional[float] = None
        self._registry: Optional['CapabilityRegistry'] = None

    @property
    def status(self) -> CapabilityStatus:
        """Current capability status."""
        return self._status

    @property
    def error(self) -> Optional[str]:
        """Current error message, if any."""
        return self._error

    def set_status(self, status: CapabilityStatus, error: Optional[str] = None):
        """Update the capability status."""
        # Handle string status from health checks by converting to enum
        if isinstance(status, str):
            try:
                status = CapabilityStatus(status)
            except ValueError:
                status = CapabilityStatus.ERROR
        self._status = status
        self._error = error
        self._last_health_check = time.time()

        # Emit event
        if self._registry:
            self._registry.event_bus.emit(CapabilityEvent(
                event_type='capability.status.changed',
                source=self.name,
                capability=self.name,
                status=status.value,
                payload={'error': error} if error else {},
            ))

    async def health(self) -> Dict[str, Any]:
        """
        Real health check - must return truthful status.

        Returns:
            Dict with status, latency_ms, error, last_checked, and any
            extra metrics specific to this capability.
        """
        start = time.time()
        try:
            result = await self._check_health()
            latency = (time.time() - start) * 1000
            self.set_status(result.get('status', CapabilityStatus.UNAVAILABLE))
            return {
                'capability': self.name,
                'category': self.category,
                'status': self._status.value,
                'healthy': self._status in (CapabilityStatus.AVAILABLE, CapabilityStatus.READY, CapabilityStatus.ACTIVE),
                'error': self._error,
                'latency_ms': round(latency, 2),
                'last_checked': datetime.now(timezone.utc).isoformat(),
                **result,
            }
        except Exception as e:
            latency = (time.time() - start) * 1000
            self.set_status(CapabilityStatus.ERROR, str(e))
            return {
                'capability': self.name,
                'category': self.category,
                'status': 'error',
                'healthy': False,
                'error': str(e),
                'latency_ms': round(latency, 2),
                'last_checked': datetime.now(timezone.utc).isoformat(),
            }

    async def _check_health(self) -> Dict[str, Any]:
        """
        Subclasses override this for real health checks.

        Must NOT return a hardcoded status. Must actually check the dependency.
        """
        return {'status': CapabilityStatus.NOT_CONFIGURED}

    @abstractmethod
    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional['ExecutionContext'] = None,
    ) -> 'ExecutionResult':
        """
        Execute a capability request with full context and observability.

        Args:
            request: Capability-specific request payload
            context: Execution context (user, session, correlation_id, etc.)

        Returns:
            ExecutionResult with status, data, and telemetry
        """
        ...

    async def cancel(self, correlation_id: str) -> bool:
        """
        Attempt to cancel an in-progress execution.

        Returns True if cancelled, False if not cancellable/already done.
        """
        return False

    async def shutdown(self) -> bool:
        """
        Clean shutdown of the capability.

        Returns True if shutdown was successful.
        """
        self.set_status(CapabilityStatus.OFFLINE)
        return True


# ============================================================================
# EXECUTION CONTEXT
# ============================================================================

@dataclass
class ExecutionContext:
    """Context passed to each capability execution."""
    user_id: str
    session_id: str
    correlation_id: str = ""
    conversation_id: Optional[str] = None
    permissions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    execution_id: str = field(default_factory=lambda: f"exec-{uuid.uuid4()}")

    def __post_init__(self):
        if not self.correlation_id:
            self.correlation_id = f"corr-{uuid.uuid4().hex[:12]}"


@dataclass
class ExecutionResult:
    """Result of a capability execution."""
    capability: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_type: Optional[str] = None
    latency_ms: float = 0.0
    correlation_id: str = ""
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# EVENT BUS
# ============================================================================

@dataclass
class CapabilityEvent:
    """Event emitted by capabilities for observability."""
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str = ""
    session_id: str = ""
    user_id: str = ""
    source: str = ""
    capability: str = ""
    event_type: str = ""
    status: str = "started"
    payload: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    execution_id: str = ""


class EventBus:
    """
    Lightweight event bus for capability events.

    Events represent REAL operations, not display artifacts.
    Every event has a correlation_id linking it to the capability execution.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._async_subscribers: Dict[str, List[Callable]] = {}
        self._events: List[CapabilityEvent] = []
        self._lock = threading.Lock()
        self._max_events = 10000

    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe a sync callback to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def subscribe_async(self, event_type: str, callback: Callable):
        """Subscribe an async callback to an event type."""
        if event_type not in self._async_subscribers:
            self._async_subscribers[event_type] = []
        self._async_subscribers[event_type].append(callback)

    def emit(self, event: CapabilityEvent):
        """Emit an event synchronously."""
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]

        if (
            event.user_id
            and event.session_id
            and event.event_type.endswith((
                ".execution.started",
                ".execution.completed",
                ".execution.failed",
            ))
        ):
            from .event_fabric import Event, get_event_bus

            suffix = event.event_type.rsplit(".", 1)[-1]
            if suffix == "completed" and event.status in {"failed", "error"}:
                suffix = "failed"
            event_type = (
                "tool.execution." + suffix
                if event.capability == "tool"
                else "capability.execution." + suffix
            )
            payload = {"execution_id": event.execution_id} if event.execution_id else {}
            latency = event.metrics.get("latency_ms")
            if isinstance(latency, (int, float)):
                payload["latency_ms"] = latency
            get_event_bus().emit(
                event_type=event_type,
                event=Event.create(
                    event_type=event_type,
                    source="capability_runtime",
                    capability=event.capability,
                    correlation_id=event.correlation_id,
                    session_id=event.session_id,
                    user_id=event.user_id,
                    status=event.status,
                    payload=payload,
                ),
            )

        # Notify sync subscribers
        for cb in self._subscribers.get('*', []):
            try:
                cb(event)
            except Exception:
                pass
        for cb in self._subscribers.get(event.event_type, []):
            try:
                cb(event)
            except Exception:
                pass

    async def emit_async(self, event: CapabilityEvent):
        """Emit an event asynchronously."""
        self.emit(event)
        # Notify async subscribers
        for cb in self._async_subscribers.get('*', []):
            try:
                await cb(event)
            except Exception:
                pass
        for cb in self._async_subscribers.get(event.event_type, []):
            try:
                await cb(event)
            except Exception:
                pass

    def get_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent events."""
        with self._lock:
            events = list(self._events)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [asdict(e) for e in events[-limit:]]


# ============================================================================
# CAPABILITY REGISTRY
# ============================================================================

class CapabilityRegistry:
    """
    Central registry for all JARVIS capabilities.

    Capabilities register themselves here. The orchestrator discovers
    capabilities through this registry.
    """

    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self.event_bus = EventBus()
        self._lock = threading.RLock()

    def register(self, capability: Capability, metadata: Optional[Dict[str, Any]] = None):
        """Register a capability."""
        with self._lock:
            capability._registry = self
            self._capabilities[capability.name] = capability
            self._metadata[capability.name] = metadata or {}

            self.event_bus.emit(CapabilityEvent(
                event_type='capability.registered',
                source=capability.name,
                capability=capability.name,
                status='registered',
                payload=metadata or {},
            ))

    def unregister(self, name: str):
        """Unregister a capability."""
        with self._lock:
            if name in self._capabilities:
                del self._capabilities[name]
                self._metadata.pop(name, None)

    def register_presentation_binding(self, name: str, binding: Any) -> None:
        """Attach validated presentation metadata to an existing capability."""
        with self._lock:
            if name not in self._capabilities:
                raise KeyError(f"Cannot attach presentation metadata to unknown capability: {name}")
            from .presentation.schemas import PresentationCapabilityBinding

            validated = PresentationCapabilityBinding.model_validate(binding)
            self._metadata.setdefault(name, {})["presentation"] = validated.model_dump(
                mode="json",
                by_alias=True,
            )

    def register_output_contract(self, name: str, outputs: list[Any]) -> None:
        """Attach validated output declarations to an existing capability."""
        with self._lock:
            if name not in self._capabilities:
                raise KeyError(f"Cannot attach outputs to unknown capability: {name}")
            from .presentation.schemas import CapabilityOutput

            validated = [CapabilityOutput.model_validate(output) for output in outputs]
            if not validated:
                raise ValueError("Capability output contracts must declare at least one output.")
            output_ids = [output.id for output in validated]
            if len(output_ids) != len(set(output_ids)):
                raise ValueError("Capability output contract identifiers must be unique.")
            self._metadata.setdefault(name, {})["outputs"] = [
                output.model_dump(mode="json", by_alias=True)
                for output in validated
            ]

    def get_metadata(self, name: str) -> Dict[str, Any]:
        """Return a copy of metadata owned by the registered capability."""
        with self._lock:
            return deepcopy(self._metadata.get(name, {}))

    def get(self, name: str) -> Optional[Capability]:
        """Get a capability by name."""
        with self._lock:
            return self._capabilities.get(name)

    def list_all(self) -> List[str]:
        """List all registered capability names."""
        with self._lock:
            return sorted(self._capabilities.keys())

    def list_by_category(self, category: str) -> List[str]:
        """List capabilities in a category."""
        with self._lock:
            return sorted([
                name for name, cap in self._capabilities.items()
                if cap.category == category
            ])

    async def health_all(self) -> Dict[str, Dict[str, Any]]:
        """Run health checks on all registered capabilities."""
        results = {}
        for name, cap in self._capabilities.items():
            results[name] = await cap.health()
        return results

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current status of all capabilities."""
        statuses = {}
        for name, cap in self._capabilities.items():
            statuses[name] = {
                'capability': name,
                'category': cap.category,
                'status': cap.status.value,
                'error': cap.error,
                'last_health_check': cap._last_health_check,
                'version': cap.version,
            }
        return statuses


# ============================================================================
# ORCHESTRATOR
# ============================================================================

class Orchestrator:
    """
    The JARVIS Orchestration Layer.

    Connects the Brain to capabilities through a common execution path:

    User -> Interaction Layer -> Orchestrator -> Brain ->
    Capability Selection -> Authorization ->
    Capability Execution -> Result -> Brain -> Response -> Interaction Layer
    """

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry
        self._active_executions: Dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()

    async def execute_capability(
        self,
        capability_name: str,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute a capability with full observability.

        This is the single entry point for the Brain to invoke any capability.
        """
        if context is None:
            context = ExecutionContext(
                user_id="anonymous",
                session_id="default",
            )

        cap = self.registry.get(capability_name)
        if not cap:
            return ExecutionResult(
                capability=capability_name,
                success=False,
                error=f"Capability '{capability_name}' is not registered",
                error_type="NOT_FOUND",
                correlation_id=context.correlation_id,
            )
        sensitive = bool(cap.sensitive)

        # Capabilities that can probe an individual action should avoid
        # blocking execution on unrelated tools' health checks.
        action_health = getattr(cap, "health_for_request", None)
        health = (
            await action_health(request)
            if callable(action_health)
            else await cap.health()
        )
        if health.get('status') == 'unavailable' or not health.get('healthy', False):
            # Capability not available - return truthful state
            return ExecutionResult(
                capability=capability_name,
                success=False,
                error=health.get('error') or f"Capability '{capability_name}' is unavailable",
                error_type="UNAVAILABLE",
                latency_ms=0.0,
                correlation_id=context.correlation_id,
                metrics=health,
            )

        # Emit start event
        await self.registry.event_bus.emit_async(CapabilityEvent(
            event_type=f'{capability_name}.execution.started',
            capability=capability_name,
            source='orchestrator',
            correlation_id=context.correlation_id,
            execution_id=context.execution_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload=(
                {'sensitive': True, 'request_redacted': True}
                if sensitive
                else {'request': request}
            ),
        ))

        start_time = time.time()
        result = None

        # OpenTelemetry distributed tracing — creates a span for each
        # capability execution, linking it to the correlation_id so traces
        # can be followed end-to-end across services (matching Codex's
        # otel-trace pattern).
        from .observability import get_tracer
        tracer = get_tracer()

        with tracer.start_as_current_span(f"capability.{capability_name}.execute") as span:
            span.set_attribute("capability.name", capability_name)
            span.set_attribute("capability.category", cap.category)
            span.set_attribute("correlation.id", context.correlation_id)
            span.set_attribute("user.id", context.user_id)
            span.set_attribute("session.id", context.session_id)

            try:
                # Execute with timeout
                task = asyncio.create_task(self._execute_with_timeout(cap, request, context))
                self._active_executions[context.correlation_id] = task

                result = await asyncio.wait_for(
                    task,
                    timeout=context.timeout_seconds,
                )
            except asyncio.TimeoutError:
                result = ExecutionResult(
                    capability=capability_name,
                    success=False,
                    error=f"Capability '{capability_name}' timed out after {context.timeout_seconds}s",
                    error_type="TIMEOUT",
                    correlation_id=context.correlation_id,
                )
                span.set_attribute("error", True)
                await cap.cancel(context.correlation_id)
            except Exception as e:
                result = ExecutionResult(
                    capability=capability_name,
                    success=False,
                    error=str(e),
                    error_type=type(e).__name__,
                    correlation_id=context.correlation_id,
                )
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e)[:200])
            finally:
                if context.correlation_id in self._active_executions:
                    del self._active_executions[context.correlation_id]

            # Record latency
            result.latency_ms = (time.time() - start_time) * 1000.0
            result.correlation_id = context.correlation_id

            # Set span attributes based on result
            span.set_attribute("capability.success", result.success)
            span.set_attribute("capability.latency_ms", result.latency_ms)
            if result.error:
                span.set_attribute("capability.error", result.error[:200])

            # LangSmith trace (extends OTel with prompt tracing + cost attribution)
            if not sensitive:
                try:
                    from .langsmith_integration import get_langsmith_tracer
                    ls_tracer = get_langsmith_tracer()
                    ls_tracer.record_capability_execution(
                        capability=capability_name,
                        action=request.get('action', 'execute'),
                        request=request,
                        result=result.to_dict(),
                        latency_ms=result.latency_ms,
                        correlation_id=context.correlation_id,
                        user_id=context.user_id,
                    )
                except Exception:
                    pass  # LangSmith is non-blocking — never break capability execution

        # Emit completion event
        await self.registry.event_bus.emit_async(CapabilityEvent(
            event_type=f'{capability_name}.execution.completed',
            capability=capability_name,
            source='orchestrator',
            correlation_id=context.correlation_id,
            execution_id=context.execution_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed' if result.success else 'failed',
            payload=(
                {
                    'success': result.success,
                    'error_type': result.error_type,
                    'latency_ms': result.latency_ms,
                    'correlation_id': result.correlation_id,
                    'sensitive': True,
                    'result_redacted': True,
                }
                if sensitive
                else result.to_dict()
            ),
        ))

        return result

    async def _execute_with_timeout(
        self,
        capability: Capability,
        request: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        """Execute capability with its context."""
        return await capability.execute(request, context)

    async def cancel_capability(self, correlation_id: str) -> bool:
        """Cancel a running capability execution."""
        task = self._active_executions.get(correlation_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def get_active_executions(self) -> List[Dict[str, Any]]:
        """Get list of active executions."""
        return [
            {'correlation_id': cid, 'capability': 'running'}
            for cid in self._active_executions
        ]

    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all capabilities through the orchestrator."""
        return {
            'capabilities': self.registry.get_status(),
            'active_executions': self.get_active_executions(),
        }


# ============================================================================
# GLOBAL SINGLETONS
# ============================================================================

_registry: Optional[CapabilityRegistry] = None
_orchestrator: Optional[Orchestrator] = None


def get_registry() -> CapabilityRegistry:
    """Get the global capability registry."""
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry


def get_orchestrator() -> Orchestrator:
    """Get the global orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator(get_registry())
    return _orchestrator


# ============================================================================
# CONVENIENCE: Quick capability creation helpers
# ============================================================================

def capability(
    name: str,
    category: str,
    version: str = "1.0.0",
    health_check: Optional[Callable] = None,
    execute_fn: Optional[Callable] = None,
):
    """
    Decorator/factory to create a capability from functions.

    Usage:
        my_cap = capability(
            name="my_tool",
            category="tools",
            health_check=lambda: {"status": "ok"},
            execute_fn=my_tool_execute,
        )
        get_registry().register(my_cap)
    """

    class FunctionCapability(Capability):
        pass

    FunctionCapability.name = name
    FunctionCapability.category = category
    FunctionCapability.version = version

    async def _check_health(self):
        if health_check:
            return health_check()
        return {"status": CapabilityStatus.READY}

    async def _execute(self, request, context=None):
        if execute_fn:
            start = time.time()
            try:
                result_data = execute_fn(request, context)
                if isinstance(result_data, tuple):
                    success, data = result_data
                else:
                    success = True
                    data = result_data or {}
                return ExecutionResult(
                    capability=name,
                    success=success,
                    data=data,
                    latency_ms=(time.time() - start) * 1000,
                    correlation_id=context.correlation_id if context else "",
                )
            except Exception as e:
                return ExecutionResult(
                    capability=name,
                    success=False,
                    error=str(e),
                    error_type=type(e).__name__,
                    latency_ms=(time.time() - start) * 1000,
                    correlation_id=context.correlation_id if context else "",
                )
        return ExecutionResult(
            capability=name,
            success=False,
            error="No execute function provided",
            error_type="NOT_IMPLEMENTED",
        )

    FunctionCapability._check_health = _check_health
    FunctionCapability.execute = _execute

    return FunctionCapability()


__all__ = [
    'Capability',
    'CapabilityStatus',
    'ExecutionContext',
    'ExecutionResult',
    'CapabilityEvent',
    'EventBus',
    'CapabilityRegistry',
    'Orchestrator',
    'get_registry',
    'get_orchestrator',
    'capability',
]
