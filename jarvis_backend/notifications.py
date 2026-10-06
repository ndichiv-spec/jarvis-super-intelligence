"""Persistent, user-scoped JARVIS notification events."""

from __future__ import annotations

import uuid
from typing import Any, Dict

from .core import get_store, now_iso


def record_notification(
    user_id: str,
    title: str,
    detail: str,
    domain: str,
    severity: str = "info",
) -> Dict[str, Any]:
    """Persist an event for its owning user without broadcasting private data."""
    notifications = get_store("notifications").load()
    if not isinstance(notifications, dict):
        notifications = {}
    user_notifications = notifications.get(user_id, [])
    if not isinstance(user_notifications, list):
        user_notifications = []
    entry = {
        "id": f"notification-{uuid.uuid4().hex}",
        "title": title[:160],
        "detail": detail[:1000],
        "domain": domain[:80],
        "severity": severity,
        "created_at": now_iso(),
        "read": False,
    }
    user_notifications.insert(0, entry)
    notifications[user_id] = user_notifications[:200]
    get_store("notifications").save()
    return entry
