"""
ASGI middleware for observability instrumentation.

Automatically creates traces, records metrics, and injects context for every request.
"""

import time
from typing import Callable, Dict, Any
from urllib.parse import urlparse

from .metrics import get_metrics_collector
from .tracer import get_tracer


class ObservabilityMiddleware:
    """
    ASGI middleware that instruments every request with:
      - Distributed trace span
      - Request/response metrics (counter + latency histogram)
      - Error rate tracking
      - Trace context injection into request state

    Usage with FastAPI:
        app.add_middleware(ObservabilityMiddleware)
    """

    def __init__(self, app: Callable, excluded_paths: tuple = ("/health", "/metrics", "/favicon.ico")):
        self.app = app
        self.excluded_paths = excluded_paths

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")
        metrics = get_metrics_collector()
        tracer = get_tracer()

        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                await self.app(scope, receive, send)
                return

        start = time.time()
        status_code = 200

        async def _send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        with tracer.span(f"{method} {path}", attributes={"http.method": method, "http.path": path}):
            try:
                await self.app(scope, receive, _send_wrapper)
            except Exception as exc:
                status_code = 500
                metrics.counter("http_errors_total").inc(labels={"method": method, "path": path})
                raise
            finally:
                duration = (time.time() - start) * 1000
                metrics.counter("http_requests_total").inc(labels={
                    "method": method, "path": path, "status": str(status_code),
                })
                metrics.histogram("http_request_duration_ms").observe(duration, labels={
                    "method": method, "path": path,
                })

                # Update gauges
                if status_code >= 500:
                    metrics.counter("http_5xx_total").inc(labels={"method": method, "path": path})
