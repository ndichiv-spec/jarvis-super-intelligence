"""Knowledge base CRUD, search, and pattern endpoints."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core import ROOT, get_store, now_iso

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
    tags: List[str] = []


def _all() -> Dict[str, Any]:
    return get_store("knowledge").load()


@router.get("/search")
async def search(q: str = Query(""), category: Optional[str] = None):
    ql = q.lower()
    items = _all()
    results = [
        item for item in items.values()
        if (not ql or ql in item.get("key", "").lower()
            or ql in item.get("value", "").lower()
            or ql in " ".join(item.get("tags", [])).lower())
        and (not category or item.get("category") == category)
    ]
    return {"results": results, "count": len(results)}


@router.get("")
async def list_knowledge(limit: int = Query(50), category: Optional[str] = None):
    items = list(_all().values())
    if category:
        items = [i for i in items if i.get("category") == category]
    return {"entries": items[-limit:][::-1], "total": len(items)}


@router.post("")
async def add_knowledge(body: KnowledgeIn):
    items = _all()
    key = body.key.strip().lower().replace(" ", "_")
    items[key] = {
        "id": str(uuid.uuid4()),
        "key": key,
        "value": body.value,
        "category": body.category,
        "tags": body.tags,
        "created_at": now_iso(),
    }
    get_store("knowledge").save()
    return items[key]


@router.delete("")
async def delete_knowledge(key: str = Query(...)):
    items = _all()
    if key in items:
        items.pop(key, None)
        get_store("knowledge").save()
        return {"success": True}
    raise HTTPException(status_code=404, detail="Entry not found")


@router.get("/patterns")
async def knowledge_patterns():
    items = _all()
    categories: Dict[str, int] = {}
    for item in items.values():
        categories[item.get("category", "general")] = categories.get(item.get("category", "general"), 0) + 1
    return {"patterns": categories, "total": len(items)}
