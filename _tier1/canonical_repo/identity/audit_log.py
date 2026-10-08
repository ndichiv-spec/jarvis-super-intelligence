"""Owner audit log for identity / provider / privilege action (spec §17).

Records:
  user
  provider
  operation
  resource
  permission
  decision
  timestamp
  result

Never records:
  raw passwords
  raw API keys
  OAuth refresh tokens
  private keys
  secret values
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AuditEvent:
    """A single audit-log entry (never contains raw secrets)."""

    user: str
    provider: str
    operation: str
    resource: str
    permission: str
    decision: str  # "granted" | "denied" | "failed"
    result: str    # "success" | "failure"
    timestamp: float = field(default_factory=time.time)
    resource_id: str = ""
    detail: str = ""
    ip: str = ""
    session_id: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize to a dict with ALL secret-like fields stripped."""
        return {
            "user": self.user,
            "provider": self.provider,
            "operation": self.operation,
            "resource": self.resource,
            "permission": self.permission,
            "decision": self.decision,
            "result": self.result,
            "timestamp": self.timestamp,
            "resource_id": self.resource_id,
            "detail": self.detail,
            "ip": self.ip,
            "session_id": self.session_id[:8] + "..." if self.session_id else "",
        }


class OwnerAuditLog:
    """Append-only audit log for owner / provider / privilege actions.

    All entries are sanitized: raw secret values, tokens, and passwords are
    never recorded.  Only opaque references and booleans are stored.

    The log can be backed by any store with ``load()`` / ``save()`` (returns/saves
    a list).  Defaults to in-memory.
    """

    def __init__(self, store: Any = None, owner_email: str = "ndichiv@gmail.com") -> None:
        self._store = store
        self._owner_email = owner_email.lower().strip()
        self._buffer: list[dict[str, Any]] = []

    def _list(self) -> list[Any]:
        if self._store is None:
            return self._buffer
        data = self._store.load()
        if data is None:
            self._store.put("entries", []) if hasattr(self._store, "put") else None
            return []
        if isinstance(data, dict) and "entries" in data:
            return data["entries"]
        return data if isinstance(data, list) else []

    def _flush(self, entries: list[Any]) -> None:
        if self._store is None:
            self._buffer[:] = entries
            return
        if isinstance(self._store.load(), dict):
            data = dict(self._store.load())
            data["entries"] = entries
            self._store._data = data if hasattr(self._store, "_data") else None
            # Use the store's save mechanism.
            try:
                self._store.load()["entries"] = entries
                self._store.save()
            except Exception:
                pass
        else:
            self._store.load().clear()
            self._store.load().extend(entries)
            self._store.save()

    def record(
        self,
        *,
        user: str,
        provider: str,
        operation: str,
        resource: str,
        permission: str,
        decision: str = "granted",
        result: str = "success",
        resource_id: str = "",
        detail: str = "",
        ip: str = "",
        session_id: str = "",
    ) -> AuditEvent:
        """Append an audit entry.  Secrets are never stored — the caller passes
        only opaque references and booleans."""
        # Defensive scrub: refuse any known secret patterns in detail.
        detail = self._scrub(detail)
        event = AuditEvent(
            user=user,
            provider=provider,
            operation=operation,
            resource=resource,
            permission=permission,
            decision=decision,
            result=result,
            timestamp=time.time(),
            resource_id=resource_id,
            detail=detail,
            ip=ip,
            session_id=session_id,
        )
        entries = self._list()
        entries.append(event.to_safe_dict())
        self._flush(entries)
        return event

    _FORBIDDEN_PATTERNS = (
        "Bearer ",
        "sk-",
        "hf_",
        "nvidia_api_key",
        "password",
        "refresh_token",
        "private_key",
        "client_secret",
    )

    @classmethod
    def _scrub(cls, text: str) -> str:
        """Strip any value that looks like a secret from the detail field."""
        if not text:
            return ""
        for pattern in cls._FORBIDDEN_PATTERNS:
            if pattern.lower() in text.lower():
                return "[REDACTED: potential secret value removed]"
        return text

    def entries(
        self,
        *,
        user: Optional[str] = None,
        provider: Optional[str] = None,
        operation: Optional[str] = None,
        since: float = 0.0,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query the audit log with optional filters (no secret exposure)."""
        all_entries = self._list()
        result = []
        for entry in all_entries:
            if user and entry.get("user") != user:
                continue
            if provider and entry.get("provider") != provider:
                continue
            if operation and entry.get("operation") != operation:
                continue
            if entry.get("timestamp", 0) < since:
                continue
            result.append(entry)
        return result[-limit:]

    def by_owner(
        self, operation: Optional[str] = None, since: float = 0.0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Convenience: all entries for the canonical owner."""
        return self.entries(user=self._owner_email, operation=operation, since=since, limit=limit)

    def summary(self) -> dict[str, Any]:
        """High-level counts for the admin console (no secrets)."""
        entries = self._list()
        total = len(entries)
        denied = sum(1 for e in entries if e.get("decision") == "denied")
        failed = sum(1 for e in entries if e.get("result") == "failure")
        by_provider: dict[str, int] = {}
        by_operation: dict[str, int] = {}
        for e in entries:
            p = e.get("provider", "unknown")
            by_provider[p] = by_provider.get(p, 0) + 1
            o = e.get("operation", "unknown")
            by_operation[o] = by_operation.get(o, 0) + 1
        return {
            "total_events": total,
            "denied_events": denied,
            "failed_events": failed,
            "by_provider": by_provider,
            "by_operation": by_operation,
        }
