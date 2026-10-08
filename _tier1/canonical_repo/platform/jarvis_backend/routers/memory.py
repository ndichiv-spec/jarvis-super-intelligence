"""Cognitive memory, consciousness, emotion, user profile/context."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..core import ai_service, get_store, now_iso

router = APIRouter(prefix="/api/v1/cognitive", tags=["memory"])


class MemoryStoreIn(BaseModel):
    content: str
    layer: str = "short_term"
    importance: float = 0.5


class ProcessIn(BaseModel):
    user_input: str
    ai_response: str
    user_id: Optional[str] = None


def _memory_stats() -> Dict[str, Any]:
    mem = get_store("memory").load()
    layers = {}
    for m in mem.values():
        layers[m.get("layer", "short_term")] = layers.get(m.get("layer", "short_term"), 0) + 1
    return {"total": len(mem), "by_layer": layers}


@router.post("/memory/store")
async def memory_store(body: MemoryStoreIn):
    mem = get_store("memory").load()
    mid = str(uuid.uuid4())
    mem[mid] = {
        "id": mid,
        "content": body.content,
        "layer": body.layer,
        "importance": body.importance,
        "created_at": now_iso(),
    }
    get_store("memory").save()
    return mem[mid]


@router.get("/memory/recall")
async def memory_recall(query: str = Query(""), limit: int = Query(10)):
    mem = get_store("memory").load()
    ql = query.lower()
    results = [
        m for m in mem.values()
        if not ql or ql in m.get("content", "").lower()
    ]
    results.sort(key=lambda m: m.get("importance", 0), reverse=True)
    return {"results": results[:limit], "count": len(results)}


@router.get("/memory/stats")
async def memory_stats():
    return _memory_stats()


@router.post("/memory/consolidate")
async def memory_consolidate():
    mem = get_store("memory").load()
    for mid, m in mem.items():
        if m.get("layer") == "short_term":
            m["layer"] = "long_term"
    get_store("memory").save()
    return {"success": True, **_memory_stats()}


@router.get("/consciousness/report")
async def consciousness_report():
    return {
        "timestamp": now_iso(),
        "state": "aware",
        "attention_focus": get_store("misc").load().get("attention_focus", "default"),
        **_memory_stats(),
    }


@router.post("/process")
async def cognitive_process(body: ProcessIn):
    mem = get_store("memory").load()
    mid = str(uuid.uuid4())
    mem[mid] = {
        "id": mid,
        "content": f"Q: {body.user_input} A: {body.ai_response}",
        "layer": "short_term",
        "importance": 0.5,
        "user_id": body.user_id,
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
async def cognitive_knowledge_search(query: str = Query(""), category: Optional[str] = None):
    items = get_store("knowledge").load()
    ql = query.lower()
    results = [
        item for item in items.values()
        if not ql or ql in item.get("key", "").lower()
        or ql in item.get("value", "").lower()
    ]
    return {"results": results, "count": len(results)}


@router.get("/user/{user_id}/profile")
async def user_profile(user_id: str):
    users = get_store("users").load()
    user = users.get(user_id)
    profile = {
        "id": user_id,
        "preferences": {},
        "traits": {},
        "interaction_count": len(get_store("memory").load()),
        "has_profile": user is not None,
    }
    return profile


@router.get("/context/{user_id}")
async def personalized_context(user_id: str):
    return {
        "user_id": user_id,
        "recent_context": [],
        "preferences": {},
        "personalization_enabled": True,
    }


@router.post("/consciousness/reflect")
async def consciousness_reflect():
    mem = get_store("memory").load()
    items = list(mem.values())
    reflection = {
        "timestamp": now_iso(),
        "summary": f"Reflected on {len(items)} memories."
        if items else "No memories to reflect on yet.",
        "insights": [],
    }
    return reflection


@router.post("/consciousness/focus")
async def set_focus(focus: str = Query("")):
    misc = get_store("misc").load()
    misc["attention_focus"] = focus
    get_store("misc").save()
    return {"focus": focus}


@router.post("/consciousness/goal")
async def add_goal(goal: str = Query("")):
    misc = get_store("misc").load()
    goals = misc.setdefault("cognitive_goals", [])
    goals.append({"id": str(uuid.uuid4()), "goal": goal, "created_at": now_iso()})
    get_store("misc").save()
    return {"success": True, "goal": goal}
