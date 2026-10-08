"""Stark unified AI gateway endpoints."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..core import ai_service, get_store, now_iso

router = APIRouter(prefix="/api/v1/stark", tags=["stark"])


class StarkChatIn(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    priority: Optional[str] = None
    stream: bool = False


class StarkToolIn(BaseModel):
    tool_name: str
    params: Dict[str, Any] = {}


@router.post("/chat")
async def stark_chat(body: StarkChatIn):
    response = await ai_service.chat(body.message)
    return {
        "message": response,
        "session_id": str(uuid.uuid4()),
        "priority": body.priority or "normal",
        "timestamp": now_iso(),
    }


@router.post("/tool")
async def stark_tool(body: StarkToolIn):
    result = {
        "tool": body.tool_name,
        "status": "success",
        "result": body.params,
        "timestamp": now_iso(),
    }
    return result


@router.get("/status")
async def stark_status():
    return {
        "status": "online",
        "gateway": "stark",
        "ai": ai_service.settings(),
        "tools_available": ["web_search", "code_exec", "memory", "knowledge"],
    }


@router.get("/health")
async def stark_health():
    return {"status": "healthy", "gateway": "stark", "timestamp": now_iso()}
