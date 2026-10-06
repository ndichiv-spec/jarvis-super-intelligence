"""Built-in automation actions backed by live JARVIS state."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def system_report(_user_id: str, _payload: dict[str, Any]) -> dict[str, Any]:
    """Capture current process capability and request metrics."""
    from jarvis_backend.capability import get_orchestrator
    from jarvis_backend.core import now_iso
    from jarvis_backend.observability import gateway_metrics_snapshot, metrics

    orchestrator = get_orchestrator()
    gateway = gateway_metrics_snapshot()
    gateway.pop("events", None)
    return {
        "generated_at": now_iso(),
        "scope": "current_backend_process",
        "capabilities": orchestrator.registry.get_status(),
        "http_metrics": metrics.snapshot(),
        "model_gateway": gateway,
    }


def knowledge_digest(user_id: str, _payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize visible knowledge metadata without exposing document content."""
    from jarvis_backend.core import get_store, now_iso

    entries = get_store("knowledge").load().values()
    owned = []
    owned_keys = set()
    public = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("user_id") == user_id:
            owned.append(entry)
            owned_keys.add(entry.get("key"))
        elif entry.get("user_id") in (None, "", "system"):
            public.append(entry)

    visible = owned + [
        entry for entry in public if entry.get("key") not in owned_keys
    ]
    categories: dict[str, int] = {}
    for entry in visible:
        category = str(entry.get("category") or "general")
        categories[category] = categories.get(category, 0) + 1

    return {
        "generated_at": now_iso(),
        "scope": "requesting_user_and_public_knowledge",
        "entry_count": len(visible),
        "owned_entry_count": len(owned),
        "public_entry_count": len(visible) - len(owned),
        "categories": categories,
    }


LOCAL_RUNNERS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "report": system_report,
    "digest": knowledge_digest,
}
