"""Developer tools: AI access control, API keys, capability management."""

from __future__ import annotations

import secrets
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core import get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/developer", tags=["developer"])


class AIAccessIn(BaseModel):
    extension: str
    enabled: bool


class AIAccessUpdateIn(BaseModel):
    accesses: Dict[str, bool]


class ApiKeyCreateIn(BaseModel):
    name: str
    description: Optional[str] = None
    scopes: Optional[List[str]] = None


@router.get("/access")
async def get_ai_access(user: Dict[str, Any] = Depends(get_current_user)):
    data = get_store("ai_access").load()
    accesses = data.get("accesses", {})
    return {"accesses": accesses, "user": user.get("username")}


@router.put("/access")
async def update_ai_access(body: AIAccessUpdateIn, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    store = get_store("ai_access")
    data = store.load()
    data["accesses"] = body.accesses
    data["updated_at"] = now_iso()
    store.save(data)
    return {"success": True, "accesses": body.accesses}


@router.post("/access/{extension}")
async def toggle_ai_access(extension: str, body: AIAccessIn, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    store = get_store("ai_access")
    data = store.load()
    accesses = data.setdefault("accesses", {})
    accesses[extension] = body.enabled
    data["accesses"] = accesses
    store.save(data)
    return {"success": True, "extension": extension, "enabled": body.enabled}


@router.get("/capabilities")
async def get_ai_capabilities(user: Dict[str, Any] = Depends(get_current_user)):
    data = get_store("ai_access").load()
    accesses = data.get("accesses", {})
    capabilities = _build_capabilities(accesses)
    return {"capabilities": capabilities}


@router.get("/api-keys")
async def list_api_keys(user: Dict[str, Any] = Depends(get_current_user)):
    keys = get_store("api_keys").load()
    mine = [
        {k: v for k, v in item.items() if k != "key"}
        for item in keys.values()
        if item.get("user_id") == user.get("id")
    ]
    return {"api_keys": mine}


@router.post("/api-keys")
async def create_api_key(body: ApiKeyCreateIn, user: Dict[str, Any] = Depends(get_current_user)):
    from ..routers.auth import _audit
    keys = get_store("api_keys").load()
    key_id = str(uuid.uuid4())
    raw_key = "jarvis_" + __import__("secrets").token_hex(24)
    keys[key_id] = {
        "id": key_id,
        "user_id": user["id"],
        "name": body.name,
        "description": body.description,
        "scopes": body.scopes or [],
        "key": raw_key,
        "created_at": now_iso(),
        "expires_at": None,
    }
    get_store("api_keys").save(keys)
    _audit(user["id"], "create_api_key", body.name)
    return {"api_key": keys[key_id], "raw_key": raw_key}


@router.get("/status")
async def developer_status(user: Dict[str, Any] = Depends(get_current_user)):
    data = get_store("ai_access").load()
    accesses = data.get("accesses", {})
    try:
        from jarvis_backend.connectors import dispatch as conn_dispatch
        connectors = conn_dispatch.list_connectors()
    except Exception:
        connectors = []
    return {
        "user": user.get("username"),
        "ai_access": accesses,
        "connectors": connectors,
        "total_extensions": len([a for a in accesses.values() if a]),
        "timestamp": now_iso(),
    }


def _build_capabilities(accesses: Dict[str, bool]) -> List[str]:
    cap_map = {
        "email": ["email.read", "email.send", "email.draft", "email.summarize"],
        "calendar": ["calendar.read", "calendar.write"],
        "filesystem": ["files.read", "files.write"],
        "web": ["web.search", "web.browse"],
        "slack": ["slack.send"],
        "database": ["database.query"],
        "github": ["github.read", "github.write"],
    }
    result = []
    for ext, enabled in accesses.items():
        if enabled:
            result.extend(cap_map.get(ext, []))
    return result


def _require_admin(user: Dict[str, Any]) -> Dict[str, Any]:
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return user
    raise HTTPException(status_code=403, detail="Admin access required")