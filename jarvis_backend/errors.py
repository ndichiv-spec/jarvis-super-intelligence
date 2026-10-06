"""JARVIS normalized error taxonomy.

Every failure surfaced to a client must carry a stable, machine-readable
``category`` plus a safe human message, an optional ``request_id``, and an
explicit ``retryable`` flag.  The chat service uses these categories so that
providers being unavailable, streams being interrupted, and quota/rate limits
are all reported honestly instead of being masked as success.
"""

from __future__ import annotations

import asyncio
import uuid
from enum import Enum
from typing import Any, Dict, Optional


class ErrorCategory(str, Enum):
    """Stable, machine-readable failure categories.

    ``*_ERROR`` categories are *not* retried (fatal / user-correctable).
    Network/timeout/availability categories are retried with bounded
    exponential backoff by the chat service.
    """

    # Auth / ownership --------------------------------------------------
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"   # bad/invalid token, expired token
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"     # authenticated but not allowed; or cross-user access denied
    INVALID_REQUEST = "INVALID_REQUEST"             # missing field, unknown id (ownership-safe 404)
    VALIDATION_ERROR = "VALIDATION_ERROR"           # schema/contract violation

    # Provider / model --------------------------------------------------
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"   # no configured backend / falls back to local-rule (never faked)
    STREAM_INTERRUPTED = "STREAM_INTERRUPTED"       # mid-stream disconnect
    RATE_LIMITED = "RATE_LIMITED"                   # 429 from a provider
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"       # out of budget / quota / credits
    CONTEXT_LIMIT = "CONTEXT_LIMIT"                 # input too long (not retryable)
    CONTENT_POLICY = "CONTENT_POLICY"               # provider refused on policy grounds (not retryable)
    MODEL_ERROR = "MODEL_ERROR"                     # provider returned a model-level error
    TIMEOUT = "TIMEOUT"                             # provider did not respond in time
    NETWORK_ERROR = "NETWORK_ERROR"                 # connection / transport failure

    # System ------------------------------------------------------------
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


# Categories where a bounded, exponentially-backed-off retry is safe and
# appropriate.  Ownership/auth/validation/context-limit/policy failures are
# deliberately excluded.
RETRYABLE_CATEGORIES = {
    ErrorCategory.RATE_LIMITED,
    ErrorCategory.PROVIDER_UNAVAILABLE,
    ErrorCategory.STREAM_INTERRUPTED,
    ErrorCategory.RESOURCE_EXHAUSTED,
    ErrorCategory.TIMEOUT,
    ErrorCategory.NETWORK_ERROR,
    ErrorCategory.INTERNAL_ERROR,
    ErrorCategory.UNKNOWN_ERROR,
}


# Categories that map directly to HTTP status codes at the API layer.
_STATUS_BY_CATEGORY = {
    ErrorCategory.AUTHENTICATION_ERROR: 401,
    ErrorCategory.AUTHORIZATION_ERROR: 403,
    ErrorCategory.INVALID_REQUEST: 404,
    ErrorCategory.VALIDATION_ERROR: 400,
    ErrorCategory.RATE_LIMITED: 429,
    ErrorCategory.CONTEXT_LIMIT: 413,
    ErrorCategory.CONTENT_POLICY: 403,
    ErrorCategory.RESOURCE_EXHAUSTED: 429,
    ErrorCategory.PROVIDER_UNAVAILABLE: 503,
    ErrorCategory.STREAM_INTERRUPTED: 502,
    ErrorCategory.MODEL_ERROR: 502,
    ErrorCategory.TIMEOUT: 504,
    ErrorCategory.NETWORK_ERROR: 502,
    ErrorCategory.INTERNAL_ERROR: 500,
    ErrorCategory.UNKNOWN_ERROR: 502,
}


class ChatError(Exception):
    """Raised by the chat service / provider boundary for client-facing errors."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        request_id: Optional[str] = None,
        retryable: Optional[bool] = None,
        detail: Optional[Any] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.safe_message = message
        self.request_id = request_id or str(uuid.uuid4())
        self.retryable = (
            retryable if retryable is not None else category in RETRYABLE_CATEGORIES
        )
        self.detail = detail
        self.status_code = (
            status_code if status_code is not None
            else _STATUS_BY_CATEGORY.get(category, 502)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "category": self.category.value,
                "message": self.safe_message,
                "request_id": self.request_id,
                "retryable": self.retryable,
                "status_code": self.status_code,
            }
        }

    def summary(self) -> str:
        return (
            f"[{self.category.value}] {self.safe_message} "
            f"(request_id={self.request_id}, retryable={self.retryable})"
        )


def normalize_exception(exc: Exception, *, request_id: Optional[str] = None) -> ChatError:
    """Map an arbitrary exception to a safe, retryable ChatError.

    The message of the original exception is never forwarded verbatim to the
    client (it may contain connection strings or provider internals); only a
    safe generic message is used.  The original exception type is retained in
    ``detail`` for server-side logging/metrics.
    """
    if isinstance(exc, ChatError):
        return exc

    # Timeouts (stdlib + asyncio) -> retryable TIMEOUT
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ChatError(
            ErrorCategory.TIMEOUT,
            "The request timed out while waiting for a response. Please try again.",
            request_id=request_id,
            detail=type(exc).__name__,
        )

    # Transport-level network failures -> retryable NETWORK_ERROR
    if isinstance(exc, (ConnectionError, OSError)):
        return ChatError(
            ErrorCategory.NETWORK_ERROR,
            "A network error occurred while contacting the AI provider. "
            "Please try again.",
            request_id=request_id,
            detail=type(exc).__name__,
        )

    # Everything else -> UNKNOWN_ERROR (retryable), never a fabricated success.
    return ChatError(
        ErrorCategory.UNKNOWN_ERROR,
        "An unexpected error occurred while processing the request.",
        request_id=request_id,
        retryable=True,
        detail=type(exc).__name__,
        status_code=502,
    )


def from_provider_exception(exc: Exception, *, request_id: Optional[str] = None) -> ChatError:
    """Map a provider-gate exception to a ChatError.

    Provider SDKs raise a variety of exception types; this inspects the
    exception class/message to classify them without depending on the specific
    SDK.  Retryable conditions bubble up as retryable errors; hard failures
    (auth, policy, context) are not retried.
    """
    if isinstance(exc, ChatError):
        return exc

    # Map by class name first (SDK-agnostic), then by message hints.
    name = type(exc).__name__
    msg = str(exc)

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ChatError(ErrorCategory.TIMEOUT,
                         "The AI provider did not respond within the time limit.",
                         request_id=request_id, detail=name)

    if isinstance(exc, (ConnectionError, OSError)):
        return ChatError(ErrorCategory.NETWORK_ERROR,
                         "A network error occurred while contacting the AI provider.",
                         request_id=request_id, detail=name)

    low = msg.lower()
    if "rate limit" in low or "429" in low or "too many requests" in low:
        return ChatError(ErrorCategory.RATE_LIMITED,
                         "The AI provider is rate-limiting requests. Please wait and try again.",
                         request_id=request_id, detail=name)
    if "context" in low and ("too long" in low or "exceed" in low or "limit" in low
                             or "400" in low or "too_large" in low):
        return ChatError(ErrorCategory.CONTEXT_LIMIT,
                         "The request exceeded the model's context limit.",
                         request_id=request_id, detail=name, retryable=False)
    if "policy" in low or "content_filter" in low or "safety" in low or "prohibited" in low:
        return ChatError(ErrorCategory.CONTENT_POLICY,
                         "The request was rejected due to content policy.",
                         request_id=request_id, detail=name, retryable=False)
    if "authentication" in low or "api key" in low or "unauthorized" in low or "401" in low:
        return ChatError(ErrorCategory.PROVIDER_UNAVAILABLE,
                         "The AI provider is not properly configured.",
                         request_id=request_id, detail=name, retryable=False)

    # Generic provider error: retryable only if it looks network/transient-ish.
    retryable = name in {"ProviderError", "ProviderException"} or True
    return ChatError(ErrorCategory.MODEL_ERROR,
                     "The AI provider returned an error.", request_id=request_id,
                     detail=name, retryable=retryable)
