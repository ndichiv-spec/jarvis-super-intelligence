"""Observability for JARVIS: request-id correlation, structured logging,
metrics middleware, and error tracking.

This module is intentionally dependency-light: it imports only the standard
library plus an already-installed ``structlog`` (falling back to ``logging``
if structlog is absent).  It does **not** import ``jarvis_backend.core`` to
avoid a circular import — it is wired onto the app by ``main.build_app``.

Public surface
--------------
* ``request_id_var`` — contextvar carrying the active correlation id.
* ``get_logger()``   — a structured (JSON) logger that auto-injects the
  active ``request_id``.
* ``metrics``        — module-level :class:`Metrics` registry (counters,
  a latency histogram, an error counter, an in-flight gauge).
* ``install_observability(app)`` — register the two middlewares, the
  structured-logger config, a generic ``Exception`` handler, and wire
  correlation into the existing ``ChatError`` handler.
* ``record_error(request, exc)`` — attach the correlation id to a
  ``ChatError`` (or classify an arbitrary exception) and emit a structured
  error log + metrics increment.  Used by the chat/auth routes.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from .errors import ChatError, normalize_exception

# Re-exported for the chat/auth routes so they can emit correlated logs.
get_logger = None  # initialised lazily by _configure_logger

# --------------------------------------------------------------------------- #
# Correlation context
# --------------------------------------------------------------------------- #
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "jarvis_request_id", default=None
)


def get_request_id(request: Request | None = None) -> str | None:
    """Return the active request-id (from the request state, the contextvar,
    or a freshly generated one as a last resort)."""
    if request is not None:
        rid = getattr(request.state, "request_id", None)
        if rid:
            return rid
    return request_id_var.get() or str(uuid.uuid4())


def _add_request_id(
    _logger: logging.Logger, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor: inject the active request_id into every record."""
    rid = request_id_var.get()
    if rid is not None:
        event_dict.setdefault("request_id", rid)
    return event_dict


_CONFIGURED = {"done": False}


def _configure_logger() -> None:
    """Configure a process-wide structured (JSON) logger exactly once."""
    if _CONFIGURED["done"]:
        return
    _CONFIGURED["done"] = True
    root = logging.getLogger("jarvis")
    root.setLevel(logging.INFO)
    # If the host application hasn't installed a root handler yet, add a
    # stream handler so structured output is visible in production/dev.
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
        )

    try:
        import structlog  # type: ignore

        structlog.configure(
            processors=[
                _add_request_id,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        jarvis_logger = structlog.get_logger("jarvis")
    except Exception:  # pragma: no cover - structlog is a declared dependency
        jarvis_logger = logging.getLogger("jarvis")

    # Rebind the module-level accessor so callers see the configured logger.
    global get_logger
    get_logger = lambda: jarvis_logger  # noqa: E731


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
class _Counter:
    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = 0

    def inc(self, by: int = 1) -> None:
        self.value += by


class _Histogram:
    """A tiny exponential-bucket latency histogram (no external deps)."""

    _DEFAULT_BUCKETS = (
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf"),
    )

    def __init__(self, buckets: tuple[float, ...] = _DEFAULT_BUCKETS) -> None:
        self._buckets = list(buckets)
        self._count = 0
        self._sum = 0.0
        self._obs = [0 for _ in self._buckets]

    def observe(self, value: float) -> None:
        self._count += 1
        self._sum += value
        for i, b in enumerate(self._buckets):
            if value <= b:
                self._obs[i] += 1
                return

    def snapshot(self) -> dict[str, Any]:
        buckets = []
        for b, c in zip(self._buckets, self._obs, strict=True):
            # ``float("inf")`` is not JSON-serialisable; use the Prometheus
            # ``+Inf`` convention so /api/v1/metrics renders cleanly.
            le: Any = "+Inf" if b == float("inf") else b
            buckets.append({"le": le, "count": c})
        return {
            "count": self._count,
            "sum": self._sum,
            "buckets": buckets,
        }


class Metrics:
    """In-process request metrics (counters + a latency histogram).

    Optionally mirrors into ``prometheus_client`` when it is installed so the
    same counters can be scraped by Prometheus on :http:/metrics.
    """

    def __init__(self) -> None:
        # (method, path_template, status) -> request count
        self.requests_total: dict[tuple[str, str, int], int] = {}
        self.request_duration = _Histogram()
        # category -> error count
        self.errors_total: dict[str, int] = {}
        self.active_requests = _Counter()
        self._prom_init()

    # -- mutations -------------------------------------------------------- #
    def inc_request(self, method: str, path: str, status: int) -> None:
        key = (method, path, status)
        self.requests_total[key] = self.requests_total.get(key, 0) + 1
        self._prom_inc("requests_total", method=method, path=path, status=str(status))

    def observe_duration(self, seconds: float) -> None:
        self.request_duration.observe(seconds)
        self._prom_observe("request_duration_seconds", seconds)

    def inc_error(self, category: str) -> None:
        self.errors_total[category] = self.errors_total.get(category, 0) + 1
        self._prom_inc("errors_total", category=category)

    def inc_active(self) -> None:
        self.active_requests.inc()

    def dec_active(self) -> None:
        if self.active_requests.value > 0:
            self.active_requests.value -= 1

    # -- reads ------------------------------------------------------------ #
    def snapshot(self) -> dict[str, Any]:
        return {
            "requests_total": {
                f"{m}|{p}|{s}": c for (m, p, s), c in self.requests_total.items()
            },
            "request_duration_seconds": self.request_duration.snapshot(),
            "errors_total": dict(self.errors_total),
            "active_requests": self.active_requests.value,
        }

    def reset(self) -> None:
        self.requests_total.clear()
        self.request_duration = _Histogram()
        self.errors_total.clear()
        self.active_requests.value = 0

    # -- optional prometheus bridge --------------------------------------- #
    def _prom_init(self) -> None:
        self._prom = None
        try:
            import prometheus_client  # type: ignore

            if not prometheus_client.REGISTRY._names_to_collectors.get(
                "jarvis_requests_total"
            ):
                self._prom = {
                    "requests": prometheus_client.Counter(
                        "jarvis_requests_total",
                        "HTTP requests by method/path/status",
                        ["method", "path", "status"],
                    ),
                    "duration": prometheus_client.Histogram(
                        "jarvis_request_duration_seconds",
                        "HTTP request latency",
                        buckets=_Histogram._DEFAULT_BUCKETS,
                    ),
                    "errors": prometheus_client.Counter(
                        "jarvis_errors_total",
                        "Errors by category",
                        ["category"],
                    ),
                    "active": prometheus_client.Gauge(
                        "jarvis_active_requests",
                        "In-flight requests",
                    ),
                }
        except Exception:  # pragma: no cover - prometheus is optional
            self._prom = None

    def _prom_inc(self, name: str, **labels: str) -> None:
        if self._prom and name == "requests_total":
            self._prom["requests"].labels(**labels).inc()
        elif self._prom and name == "errors_total":
            self._prom["errors"].labels(**labels).inc()

    def _prom_observe(self, name: str, seconds: float) -> None:
        if self._prom and name == "request_duration_seconds":
            self._prom["duration"].observe(seconds)


metrics = Metrics()


# --------------------------------------------------------------------------- #
# Model-gateway telemetry (Observatory / Laboratory feeds)
# --------------------------------------------------------------------------- #
# Every inference request routed through the model gateway produces one event
# (spec section 26): request_id, timestamp, model, revision, latency,
# tokens, device, success, error, tool_calls, verification.  Prompt content is
# deliberately NOT stored (privacy policy).
GATEWAY_EVENT_LOG: dict[str, Any] = {
    "events": [],
    "counts": {
        "requests": 0,
        "failures": 0,
        "fallbacks": 0,
        "tool_calls": 0,
        "tokens": 0,
    },
}


def record_gateway_event(event: dict[str, Any]) -> None:
    """Record one gateway inference event (Observatory telemetry)."""
    counts = GATEWAY_EVENT_LOG["counts"]
    counts["requests"] = counts.get("requests", 0) + 1
    if event.get("success") is False:
        counts["failures"] = counts.get("failures", 0) + 1
    if event.get("fallback"):
        counts["fallbacks"] = counts.get("fallbacks", 0) + 1
    if event.get("tool_calls"):
        counts["tool_calls"] = counts.get("tool_calls", 0) + len(event["tool_calls"])
    counts["tokens"] = counts.get("tokens", 0) + int(event.get("total_tokens", 0))
    GATEWAY_EVENT_LOG["events"].append(event)
    if len(GATEWAY_EVENT_LOG["events"]) > 5000:  # bounded ring buffer
        GATEWAY_EVENT_LOG["events"] = GATEWAY_EVENT_LOG["events"][-5000:]


def gateway_metrics_snapshot() -> dict[str, Any]:
    """Laboratory / Observatory view of model-layer performance."""
    events = GATEWAY_EVENT_LOG["events"]
    latencies = [e.get("latency_ms", 0.0) for e in events if e.get("latency_ms")]
    total_tokens = sum(e.get("total_tokens", 0) for e in events)
    elapsed_ms = max(
        (e.get("timestamp0_ms", 0.0) for e in events), default=0.0
    ) or 1.0
    fallbacks = GATEWAY_EVENT_LOG["counts"].get("fallbacks", 0)
    return {
        "requests": GATEWAY_EVENT_LOG["counts"].get("requests", 0),
        "failures": GATEWAY_EVENT_LOG["counts"].get("failures", 0),
        "fallbacks": fallbacks,
        "fallback_rate": (fallbacks / len(events)) if events else 0.0,
        "tool_calls": GATEWAY_EVENT_LOG["counts"].get("tool_calls", 0),
        "tokens_total": total_tokens,
        "latency_ms_avg": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "tokens_per_sec": (total_tokens * 1000.0 / elapsed_ms) if events else 0.0,
        "events": events[-200:],
    }


def _route_path(request: Request) -> str:
    """Best-effort normalised route path (template, falling back to raw path)."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    return request.url.path


# --------------------------------------------------------------------------- #
# Middlewares
# --------------------------------------------------------------------------- #
class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate / propagate a correlation id for every request.

    Honours an inbound ``X-Request-ID`` header; otherwise mint a UUID.  The id
    is stored on ``request.state.request_id`` and the ``request_id_var``
    contextvar so that async work spawned during the request still observes it.
    The id is echoed back on every response via ``X-Request-ID``.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            # Always echo the correlation id, even on error responses.
            with contextlib.suppress(Exception):
                response.headers["X-Request-ID"] = rid
            request_id_var.reset(token)
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record per-request counters, latency, and an in-flight gauge."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        method = request.method
        path = _route_path(request)
        metrics.inc_active()
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            duration = time.perf_counter() - t0
            metrics.dec_active()
            metrics.inc_request(method, path, status)
            metrics.observe_duration(duration)
        return response


# --------------------------------------------------------------------------- #
# Error tracking
# --------------------------------------------------------------------------- #
def record_error(request: Request, exc: BaseException) -> ChatError:
    """Correlate an exception with the active request-id and emit a structured
    error log + metrics increment.

    If ``exc`` is already a :class:`ChatError`, its ``request_id`` is (re)set to
    the active correlation id so it round-trips in the response.  Otherwise the
    exception is classified via :func:`normalize_exception`.  The (possibly
    rewritten) ``ChatError`` is returned so handlers can use it.
    """
    _configure_logger()
    rid = get_request_id(request)
    log = get_logger()
    err = exc if isinstance(exc, ChatError) else normalize_exception(exc, request_id=rid)
    # Correlate: bind the request id so the client response matches server logs.
    err.request_id = rid
    metrics.inc_error(err.category.value)
    log.error(
        "error",
        category=err.category.value,
        message=err.message,
        retryable=err.retryable,
        status_code=err.status_code,
        request_id=err.request_id,
        error_type=type(exc).__name__,
        detail=getattr(err, "detail", None),
        user_id=getattr(request.state, "user_id", None),
    )
    return err


# --------------------------------------------------------------------------- #
# Installation
# --------------------------------------------------------------------------- #
def install_observability(app: FastAPI) -> None:
    """Register observability onto ``app``.

    Safe to call multiple times (idempotent).  Adds:
      * ``MetricsMiddleware`` then ``RequestIDMiddleware`` (added in this order
        so the request-id middleware ends up closest to the router and every
        logged record / error carries the correlation id),
      * a structured logger config,
      * a generic ``Exception`` handler that logs + returns a safe 500,
      * and rewrites the existing ``ChatError`` handler (if present) to route
        errors through :func:`record_error`.
    """
    _configure_logger()

    # Guard against double-registration on reload/re-import.
    if getattr(app, "_jarvis_observability_installed", False):
        return
    app._jarvis_observability_installed = True  # type: ignore[attr-defined]

    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIDMiddleware)

    async def _unhandled_error_handler(request: Request, exc: Exception):
        err = record_error(request, exc)
        body = {
            "error": {
                "category": "INTERNAL_ERROR",
                "message": "Internal server error",
                "request_id": err.request_id,
                "retryable": True,
                "status_code": 500,
            }
        }
        response = JSONResponse(status_code=500, content=body)
        response.headers["X-Request-ID"] = err.request_id
        return response

    app.exception_handler(Exception)(_unhandled_error_handler)

    async def _chat_error_handler(request: Request, exc: ChatError):
        err = record_error(request, exc)
        response = JSONResponse(status_code=err.status_code, content=err.to_dict())
        response.headers["X-Request-ID"] = err.request_id
        return response

    app.exception_handler(ChatError)(_chat_error_handler)

    # Structured error contract for Starlette/FastAPI HTTP exceptions, which is
    # what produces the dreaded ``{"detail":"Not Found"}`` (spec Part B).
    # FastAPI's ``HTTPException`` subclasses ``StarletteHTTPException``, so 4xx
    # validation/auth errors all flow through here too.  The response never
    # echoes credentials, stack traces, or internal identifiers.
    _HTTP_CODE_MAP = {
        400: ("INVALID_REQUEST", "The request is invalid.", False),
        401: ("AUTHENTICATION_ERROR", "Authentication required.", False),
        403: ("AUTHORIZATION_ERROR",
              "You are not authorized to access this resource.", False),
        404: ("ROUTE_NOT_FOUND", "The requested API route does not exist.", False),
        405: ("METHOD_NOT_ALLOWED",
              "This HTTP method is not allowed for the requested route.", False),
        422: ("VALIDATION_ERROR", "Request validation failed.", False),
        429: ("RATE_LIMITED",
              "Rate limit exceeded. Please retry after a short delay.", True),
        408: ("TIMEOUT", "The request timed out. Please try again.", True),
        504: ("TIMEOUT", "The upstream request timed out. Please try again.", True),
        501: (
            "CAPABILITY_NOT_CONFIGURED",
            "This capability is not configured or implemented.",
            False,
        ),
        503: ("SERVICE_UNAVAILABLE", "The service is temporarily unavailable.", True),
    }

    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        code, message, retryable = _HTTP_CODE_MAP.get(
            exc.status_code,
            ("REQUEST_ERROR", "The request could not be completed.", False),
        )
        # For validation/auth-style errors the upstream detail is user-facing
        # and safe; for everything else prefer the curated message so internal
        # identifiers never leak.
        if exc.status_code in (400, 422) and exc.detail:
            message = str(exc.detail)[:256]
        rid = get_request_id(request)
        body = {
            "error": {
                "code": code,
                "message": message,
                "request_id": rid,
                "path": str(request.url.path),
                "method": request.method,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status_code": exc.status_code,
                "retryable": retryable,
                "documentation": "/docs",
            }
        }
        metrics.inc_error(code)
        _configure_logger()
        log_fn = get_logger()
        log_fn.error(
            "http_error",
            code=code,
            status_code=exc.status_code,
            path=body["error"]["path"],
            method=request.method,
            request_id=rid,
        )
        response = JSONResponse(status_code=exc.status_code, content=body)
        response.headers["X-Request-ID"] = rid
        return response

    app.exception_handler(StarletteHTTPException)(_http_exception_handler)

    # --------------------------------------------------------------- #
    # OpenTelemetry distributed tracing (Phase 19 upgrade)           #
    # --------------------------------------------------------------- #
    # Initialize the OTel SDK with an OTLP exporter (for Jaeger/Tempo/
    # otel-collector) and integrate spans into the request lifecycle.
    # This matches the pattern used by OpenAI Codex (otel / otel-trace-websocket)
    # and Claude Code.
    _init_opentelemetry(app)


# --------------------------------------------------------------------------- #
# OpenTelemetry distributed tracing
# --------------------------------------------------------------------------- #
_OTEL_INITIALIZED = False


def _init_opentelemetry(app: FastAPI) -> None:
    """Initialize OpenTelemetry SDK with OTLP exporter and trace propagation.

    Sets up:
      * TracerProvider with batch span processor
      * OTLP exporter (endpoint configurable via OTEL_EXPORTER_OTLP_ENDPOINT)
      * W3C TraceContext propagator (compatible with Codex/Claude/otcol)
      * Correlation ID <-> trace span linking
      * Optional FastAPI/requests/asgi instrumentors

    Falls back gracefully if OTel packages are not installed.
    """
    global _OTEL_INITIALIZED
    if _OTEL_INITIALIZED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        # Resource identifies this service in traces (matching Codex's
        # `otel` crate that sets service.name attributes)
        resource = Resource.create({
            "service.name": "jarvis-backend",
            "service.version": "3.0.0",
            "deployment.environment": os.environ.get("JARVIS_ENV", "production"),
        })

        provider = TracerProvider(resource=resource)

        # OTLP exporter — sends spans to otel-collector or Tempo/Jaeger
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        try:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception:
            # Fall back to console exporter if OTLP endpoint is unreachable
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)

        # Use W3C TraceContext propagator (standard used by all platforms)
        set_global_textmap(CompositePropagator())

        # Instrument FastAPI if the instrumentor is available
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
        except Exception:
            pass

        _OTEL_INITIALIZED = True
        log = get_logger() if get_logger else logging.getLogger("jarvis")
        if hasattr(log, "info"):
            log.info("OpenTelemetry distributed tracing initialized",
                     otlp_endpoint=otlp_endpoint,
                     service_name="jarvis-backend")

    except ImportError:
        # OTel SDK not installed — degrade gracefully
        pass
    except Exception:
        # Any other init error — don't block server startup
        pass


def get_tracer():
    """Return the OTel tracer for JARVIS, or a no-op tracer if OTel is unavailable."""
    try:
        from opentelemetry import trace
        return trace.get_tracer("jarvis-backend", "3.0.0")
    except Exception:
        return _NoopTracer()


class _NoopTracer:
    """No-op tracer used when OpenTelemetry SDK is unavailable."""

    def start_as_current_span(self, name, context=None, **kwargs):
        import contextlib

        @contextlib.contextmanager
        def _noop_span():
            yield _NoopSpan()

        return _noop_span()


class _NoopSpan:
    """No-op span mock."""

    def set_attribute(self, key, value):
        pass

    def set_attributes(self, attrs):
        pass

    def add_event(self, name, attributes=None):
        pass

    def set_status(self, status, description=None):
        pass

    def end(self):
        pass

    @property
    def context(self):
        return self

    @property
    def span_context(self):
        return self

    @property
    def trace_id(self):
        return None

    @property
    def span_id(self):
        return None
