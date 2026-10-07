"""NeMo Microservices errors (spec §5).

Raised when NeMo is not configured for an operation that requires it.
This is NOT a generic exception — callers can catch it to degrade
gracefully (e.g., skip synthetic data generation when NeMo is unconfigured).
"""

from __future__ import annotations

from typing import Any


class NemError(Exception):
    """Base error for NeMo Microservices client."""


class NeMoUnconfigured(NemError):
    """Raised when NeMo is not configured but an operation requires it.

    This allows callers to detect "NeMo isn't set up" vs "NeMo is set up
    but the request failed" — the latter being a real HTTP/network error.
    """


class NeMoRequestError(NemError):
    """A request to NeMo failed (HTTP error, timeout, bad response)."""

    def __init__(self, message: str, status_code: int = 0, **extra: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.extra = extra
