"""Authenticated user notification history and read state."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from ..core import get_current_user, get_store

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _user_id(user: Dict[str, Any]) -> str:
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated identity is missing")
    return str(user_id)


@router.get("")
async def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(get_current_user),
):
    notifications = get_store("notifications").load()
    items = notifications.get(_user_id(user), []) if isinstance(notifications, dict) else []
    return {"notifications": items[:limit], "count": min(len(items), limit)}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = _user_id(user)
    notifications = get_store("notifications").load()
    if not isinstance(notifications, dict):
        raise HTTPException(status_code=404, detail="Notification not found")
    items: List[Dict[str, Any]] = notifications.get(user_id, [])
    for item in items:
        if item.get("id") == notification_id:
            item["read"] = True
            get_store("notifications").save()
            return {"success": True}
    raise HTTPException(status_code=404, detail="Notification not found")


@router.post("/read-all")
async def mark_all_notifications_read(user: Dict[str, Any] = Depends(get_current_user)):
    user_id = _user_id(user)
    notifications = get_store("notifications").load()
    if not isinstance(notifications, dict):
        notifications = {}
    items = notifications.get(user_id, [])
    for item in items:
        item["read"] = True
    notifications[user_id] = items
    get_store("notifications").save()
    return {"success": True, "count": len(items)}
