"""Short-lived in-memory references for sensitive geospatial presentation data."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _LocationEntry:
    user_id: str
    session_id: str
    request_id: str
    execution_id: str
    expires_at: float
    value: dict[str, Any]
    presentation_id: str | None = None
    rendered: bool = False


class EphemeralLocationData:
    """Keep coordinates out of durable chat, event, and presentation stores."""

    def __init__(self, *, ttl_seconds: int = 900) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._entries: dict[str, _LocationEntry] = {}

    def create(
        self,
        user_id: str,
        session_id: str,
        request_id: str,
        execution_id: str,
        value: dict[str, Any],
    ) -> str:
        reference = secrets.token_urlsafe(24)
        with self._lock:
            self._expire()
            self._entries[reference] = _LocationEntry(
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                execution_id=execution_id,
                expires_at=time.monotonic() + self._ttl_seconds,
                value=dict(value),
            )
        return reference

    def attach_presentation(self, reference: str, presentation_id: str) -> None:
        with self._lock:
            entry = self._entries.get(reference)
            if entry is None or entry.expires_at <= time.monotonic():
                raise KeyError("The temporary location reference has expired.")
            entry.presentation_id = presentation_id

    def get(
        self,
        reference: str,
        *,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            self._expire()
            entry = self._entries.get(reference)
            if entry is None or entry.user_id != user_id or entry.session_id != session_id:
                return None
            return dict(entry.value)

    def presentation(
        self,
        presentation_id: str,
        *,
        user_id: str,
        session_id: str,
    ) -> dict[str, str] | None:
        with self._lock:
            self._expire()
            for entry in self._entries.values():
                if (
                    entry.presentation_id == presentation_id
                    and entry.user_id == user_id
                    and entry.session_id == session_id
                ):
                    return {
                        "request_id": entry.request_id,
                        "execution_id": entry.execution_id,
                    }
            return None

    def get_for_presentation(
        self,
        presentation_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            self._expire()
            for reference, entry in self._entries.items():
                if entry.presentation_id == presentation_id and entry.user_id == user_id:
                    return {
                        "reference": reference,
                        "session_id": entry.session_id,
                        "request_id": entry.request_id,
                        "execution_id": entry.execution_id,
                        "value": dict(entry.value),
                        "rendered": entry.rendered,
                    }
            return None

    def mark_rendered(
        self,
        presentation_id: str,
        *,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            self._expire()
            for entry in self._entries.values():
                if (
                    entry.presentation_id == presentation_id
                    and entry.user_id == user_id
                    and entry.session_id == session_id
                ):
                    already_rendered = entry.rendered
                    entry.rendered = True
                    return {
                        "request_id": entry.request_id,
                        "execution_id": entry.execution_id,
                        "already_rendered": already_rendered,
                    }
            return None

    def _expire(self) -> None:
        now = time.monotonic()
        for reference, entry in list(self._entries.items()):
            if entry.expires_at <= now:
                del self._entries[reference]


ephemeral_location_data = EphemeralLocationData()
