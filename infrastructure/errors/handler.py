"""
Error handler and middleware for ASGI/FastAPI applications.

Provides:
  - Centralized exception handling with structured JSON responses
  - HTTP status code mapping for all error types
  - ASGI middleware for automatic error capture
"""

import time
import json
import logging
import traceback
from typing import Callable, Dict, Any, Optional, Type
from enum import Enum

from .types import (
    JarvisError, AuthenticationError, AuthorizationError, RateLimitError,
    NotFoundError, ValidationError, TimeoutError, ResourceExhaustedError,
    AIProviderError, ProviderError, SandboxError,
)

logger = logging.getLogger(__name__)


def exception_to_status(exc: Exception) -> int:
    """Map error types to HTTP status codes."""
    mapping: Dict[Type[Exception], int] = {
        AuthenticationError: 401,
        AuthorizationError: 403,
        NotFoundError: 404,
        RateLimitError: 429,
        ValidationError: 422,
        TimeoutError: 504,
        ResourceExhaustedError: 503,
        AIProviderError: 502,
        ProviderError: 502,
        SandboxError: 500,
        JarvisError: 500,
    }
    for exc_type, status in mapping.items():
        if isinstance(exc, exc_type):
            return status
    return 500


def error_response(exc: Exception, include_traceback: bool = False) -> Dict[str, Any]:
    """Build a structured error response dict."""
    if isinstance(exc, JarvisError):
        body = exc.to_dict()
    else:
        body = {
            "error": True,
            "code": "internal_error",
            "message": str(exc) or "An unexpected error occurred",
            "subsystem": "core",
            "details": {},
        }

    body["status_code"] = exception_to_status(exc)

    if include_traceback:
        body["traceback"] = traceback.format_exc()

    return body


class ErrorHandler:
    """
    Centralized error handler.

    Can be used as ASGI middleware or called directly.
    """

    def __init__(self, app: Callable, include_traceback: bool = False,
                 log_errors: bool = True):
        self.app = app
        self.include_traceback = include_traceback
        self.log_errors = log_errors

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            if self.log_errors:
                logger.exception(f"Unhandled exception: {exc}")

            body = error_response(exc, include_traceback=self.include_traceback)
            status = body["status_code"]
            encoded = json.dumps(body).encode()

            await send({
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"x-error-code", body["code"].encode()),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": encoded,
            })
