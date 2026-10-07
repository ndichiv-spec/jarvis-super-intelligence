"""Cognitive memory, consciousness, emotion, user profile/context."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core import ai_service, get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/cognitive", tags=["memory"])


class MemoryStoreIn(BaseModel):
    content: str
    layer: str = "short_term"
    importance: float = 0.5


class ProcessIn(BaseModel):
    user_input: str
    ai_response: str


def _owner_id(user: Dict[str, Any]) -> str:
    user_id = user.get("id") or user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated identity is missing")
    return str(user_id)


def _owned_memory(user: Dict[str, Any]) -> Dict[str, Any]:
    mem = get_store("memory").load()
    owner_id = _owner_id(user)
    return {
        key: value for key, value in mem.items()
        if value.get("user_id") == owner_id
    }


def _memory_stats(user: Dict[str, Any]) -> Dict[str, Any]:
    mem = _owned_memory(user)
    layers = {}
    for m in mem.values():
        layers[m.get("layer", "short_term")] = layers.get(m.get("layer", "short_term"), 0) + 1
    return {"total": len(mem), "by_layer": layers}


@router.post("/memory/store")
async def memory_store(
    body: MemoryStoreIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    mem = get_store("memory").load()
    mid = str(uuid.uuid4())
    mem[mid] = {
        "id": mid,
        "content": body.content,
        "layer": body.layer,
        "importance": body.importance,
        "user_id": _owner_id(user),
        "created_at": now_iso(),
    }
    get_store("memory").save()
    return mem[mid]


@router.get("/memory/recall")
async def memory_recall(
    query: str = Query(""),
    limit: int = Query(10, ge=1, le=100),
    user: Dict[str, Any] = Depends(get_current_user),
):
    mem = _owned_memory(user)
    ql = query.lower()
    results = [
        m for m in mem.values()
        if not ql or ql in m.get("content", "").lower()
    ]
    results.sort(key=lambda m: m.get("importance", 0), reverse=True)
    return {"results": results[:limit], "count": len(results)}


@router.get("/memory/stats")
async def memory_stats(user: Dict[str, Any] = Depends(get_current_user)):
    return _memory_stats(user)


@router.post("/memory/consolidate")
async def memory_consolidate(user: Dict[str, Any] = Depends(get_current_user)):
    mem = get_store("memory").load()
    for mid, m in mem.items():
        if m.get("user_id") == _owner_id(user) and m.get("layer") == "short_term":
            m["layer"] = "long_term"
    get_store("memory").save()
    return {"status": "COMPLETED", **_memory_stats(user)}


@router.get("/consciousness/report")
async def consciousness_report(user: Dict[str, Any] = Depends(get_current_user)):
    misc = get_store("misc").load()
    focus_by_user = misc.get("attention_focus_by_user", {})
    return {
        "timestamp": now_iso(),
        "state": "NOT_IMPLEMENTED",
        "attention_focus": focus_by_user.get(_owner_id(user), "default"),
        **_memory_stats(user),
    }


@router.post("/process")
async def cognitive_process(
    body: ProcessIn,
    user: Dict[str, Any] = Depends(get_current_user),
):
    mem = get_store("memory").load()
    mid = str(uuid.uuid4())
    mem[mid] = {
        "id": mid,
        "content": f"Q: {body.user_input} A: {body.ai_response}",
        "layer": "short_term",
        "importance": 0.5,
        "user_id": _owner_id(user),
        "created_at": now_iso(),
    }
    get_store("memory").save()
    return {"stored": True, "memory_id": mid}


@router.get("/emotion/analyze")
async def emotion_analyze(text: str = Query("")):
    import re
    joy = bool(re.search(r"\b(great|happy|love|awesome|amazing)\b", text, re.I))
    concern = bool(re.search(r"\b(sad|bad|worry|problem|fear)\b", text, re.I))
    emotion = "positive" if joy else ("concerned" if concern else "neutral")
    return {"emotion": emotion, "confidence": 0.6}


@router.get("/knowledge/search")
async def cognitive_knowledge_search(
    query: str = Query(""),
    category: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    items = get_store("knowledge").load()
    owner_id = _owner_id(user)
    ql = query.lower()
    results = [
        item for item in items.values()
        if isinstance(item, dict)
        and (
            item.get("user_id") == owner_id
            or item.get("user_id") == "system"
            or (
                item.get("user_id") in (None, "")
                and item.get("visibility") == "public"
            )
        )
        and (
            not ql
            or ql in str(item.get("key") or "").lower()
            or ql in str(item.get("value") or "").lower()
        )
        and (not category or item.get("category") == category)
    ]
    return {"results": results, "count": len(results)}


@router.get("/user/{user_id}/profile")
async def user_profile(
    user_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if user_id != _owner_id(user):
        raise HTTPException(status_code=404, detail="User profile not found")
    users = get_store("users").load()
    user = users.get(user_id)
    profile = {
        "id": user_id,
        "preferences": {},
        "traits": {},
        "interaction_count": len(_owned_memory(user)),
        "has_profile": user is not None,
    }
    return profile


@router.get("/context/{user_id}")
async def personalized_context(
    user_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if user_id != _owner_id(user):
        raise HTTPException(status_code=404, detail="User context not found")
    return {
        "user_id": user_id,
        "recent_context": [],
        "preferences": {},
        "personalization_enabled": True,
    }


@router.post("/consciousness/reflect")
async def consciousness_reflect(user: Dict[str, Any] = Depends(get_current_user)):
    mem = _owned_memory(user)
    items = list(mem.values())
    reflection = {
        "timestamp": now_iso(),
        "summary": f"Reflected on {len(items)} memories."
        if items else "No memories to reflect on yet.",
        "insights": [],
    }
    return reflection


@router.post("/consciousness/focus")
async def set_focus(
    focus: str = Query(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    misc = get_store("misc").load()
    focuses = misc.setdefault("attention_focus_by_user", {})
    focuses[_owner_id(user)] = focus
    get_store("misc").save()
    return {"focus": focus}


@router.post("/consciousness/goal")
async def add_goal(
    goal: str = Query(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    misc = get_store("misc").load()
    goals_by_user = misc.setdefault("cognitive_goals_by_user", {})
    goals = goals_by_user.setdefault(_owner_id(user), [])
    goals.append({"id": str(uuid.uuid4()), "goal": goal, "created_at": now_iso()})
    get_store("misc").save()
    return {"success": True, "goal": goal}
