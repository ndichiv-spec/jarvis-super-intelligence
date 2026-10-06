"""Knowledge base CRUD, search, and pattern endpoints."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import ROOT, get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

# Try to reuse the real infrastructure/knowledge package when available.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:  # pragma: no cover
    from infrastructure.knowledge.store import KnowledgeStore as _KS  # type: ignore

    _KNOWLEDGE_PKG = True
except Exception:  # noqa: BLE001
    _KNOWLEDGE_PKG = False


class KnowledgeIn(BaseModel):
    key: str
    value: str
    category: str = "general"
    tags: List[str] = Field(default_factory=list)


def _all() -> Dict[str, Any]:
    return get_store("knowledge").load()


def _normalized_key(key: str) -> str:
    normalized = key.strip().lower().replace(" ", "_")
    if not normalized:
        raise HTTPException(status_code=422, detail="Knowledge key cannot be empty")
    return normalized


def _owned_storage_key(user_id: str, key: str) -> str:
    return f"{user_id}::{key}"


def _visible_items(user_id: str) -> List[Dict[str, Any]]:
    items = _all()
    owned = [
        item for item in items.values()
        if isinstance(item, dict) and item.get("user_id") == user_id
    ]
    owned_keys = {item.get("key") for item in owned}
    public = [
        {**item, "read_only": True}
        for item in items.values()
        if isinstance(item, dict)
        and item.get("user_id") in (None, "", "system")
        and item.get("key") not in owned_keys
    ]
    return owned + public


@router.get("/search")
async def search(
    q: str = Query(""),
    category: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ql = q.lower()
    items = _visible_items(str(user["id"]))
    results = [
        item for item in items
        if (not ql or ql in item.get("key", "").lower()
            or ql in item.get("value", "").lower()
            or ql in " ".join(item.get("tags", [])).lower())
        and (not category or item.get("category") == category)
    ]
    return {"results": results, "count": len(results)}


@router.get("")
async def list_knowledge(
    limit: int = Query(50, ge=1, le=500),
    category: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    items = _visible_items(str(user["id"]))
    if category:
        items = [i for i in items if i.get("category") == category]
    return {"entries": items[-limit:][::-1], "total": len(items)}


@router.post("")
async def add_knowledge(
    body: KnowledgeIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    items = _all()
    key = _normalized_key(body.key)
    user_id = str(user["id"])
    storage_key = _owned_storage_key(user_id, key)
    previous = items.get(storage_key)
    items[storage_key] = {
        "id": previous.get("id", str(uuid.uuid4())) if isinstance(previous, dict) else str(uuid.uuid4()),
        "key": key,
        "value": body.value.strip(),
        "category": body.category.strip() or "general",
        "tags": body.tags,
        "user_id": user_id,
        "created_at": previous.get("created_at", now_iso()) if isinstance(previous, dict) else now_iso(),
    }
    get_store("knowledge").save()
    return items[storage_key]


@router.delete("")
async def delete_knowledge(
    key: str = Query(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    items = _all()
    normalized = _normalized_key(key)
    storage_key = _owned_storage_key(str(user["id"]), normalized)
    if storage_key in items:
        items.pop(storage_key)
        get_store("knowledge").save()
        return {"success": True}
    raise HTTPException(status_code=404, detail="Entry not found")


@router.get("/patterns")
async def knowledge_patterns(user: Dict[str, Any] = Depends(get_current_user)):
    items = _visible_items(str(user["id"]))
    categories: Dict[str, int] = {}
    for item in items:
        categories[item.get("category", "general")] = categories.get(item.get("category", "general"), 0) + 1
    patterns = [
        {
            "pattern": item.get("key", "").removeprefix("pattern:"),
            "response": item.get("value", ""),
            "category": item.get("category", "pattern"),
        }
        for item in items
        if item.get("category") == "pattern" or item.get("key", "").startswith("pattern:")
    ]
    return {"patterns": patterns, "total": len(patterns), "categories": categories}
