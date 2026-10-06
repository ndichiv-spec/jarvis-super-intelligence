"""RBAC: users, roles, permissions, audit logs, tenant settings."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core import get_current_user, get_store, hash_password, make_user_payload, now_iso

router = APIRouter(prefix="/api/v1/rbac", tags=["rbac"])


class UserCreateIn(BaseModel):
    email: str
    username: str
    password: str
    full_name: Optional[str] = None
    roles: List[str] = []


class UserUpdateIn(BaseModel):
    roles: Optional[List[str]] = None
    status: Optional[str] = None


class RoleCreateIn(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[str] = []


class RoleUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class TenantSettingsIn(BaseModel):
    max_users: Optional[int] = None
    max_storage_mb: Optional[int] = None
    max_api_calls_per_day: Optional[int] = None
    settings: Optional[Dict[str, Any]] = None


def _user_out(u: Dict[str, Any]) -> Dict[str, Any]:
    out = make_user_payload(u)
    out["roles"] = u.get("roles", [])
    return out


def _require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Gate a route to users holding the admin role (or an explicit ``is_admin``).

    Role names are resolved against the roles store so a role object carrying
    ``*`` permissions also grants access, matching the canonical OWNER/ADMIN
    role set seeded by ``core._seed_canonical_roles``.
    """
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return user
    # Resolve named roles against the store for ``*`` (owner) permission.
    role_names = set(names)
    roles = get_store("roles").load()
    for role in roles.values():
        if role.get("name") in role_names or role.get("id") in role_names:
            perms = role.get("permissions") or []
            if "*" in perms:
                return user
    raise HTTPException(status_code=403, detail="Admin access required")


def _require_auth(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Any authenticated user may read this resource."""
    return user


@router.get("/users")
async def list_users(page: int = Query(1), per_page: int = Query(20),
                     search: Optional[str] = None, user: Dict[str, Any] = Depends(_require_admin)):
    users = list(get_store("users").load().values())
    if search:
        sl = search.lower()
        users = [u for u in users if sl in u.get("email", "").lower()
                 or sl in u.get("username", "").lower()
                 or sl in (u.get("full_name") or "").lower()]
    total = len(users)
    start = (page - 1) * per_page
    return {
        "users": [_user_out(u) for u in users[start:start + per_page]],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/users")
async def create_user(body: UserCreateIn, user: Dict[str, Any] = Depends(_require_admin)):
    users = get_store("users").load()
    if any(u.get("email", "").lower() == body.email.lower() for u in users.values()):
        raise HTTPException(status_code=409, detail="Email exists")
    uid = str(uuid.uuid4())
    users[uid] = {
        "id": uid, "email": body.email, "username": body.username,
        "password_hash": hash_password(body.password),
        "full_name": body.full_name or body.username, "status": "active",
        "roles": body.roles or ["user"], "created_at": now_iso(),
    }
    get_store("users").save()
    return _user_out(users[uid])


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdateIn, user: Dict[str, Any] = Depends(_require_admin)):
    users = get_store("users").load()
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    if body.roles is not None:
        users[user_id]["roles"] = body.roles
    if body.status is not None:
        users[user_id]["status"] = body.status
    get_store("users").save()
    return _user_out(users[user_id])


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: Dict[str, Any] = Depends(_require_admin)):
    users = get_store("users").load()
    users.pop(user_id, None)
    get_store("users").save()
    return {"success": True}


@router.get("/roles")
async def list_roles(user: Dict[str, Any] = Depends(_require_auth)):
    return {"roles": list(get_store("roles").load().values())}


@router.post("/roles")
async def create_role(body: RoleCreateIn, user: Dict[str, Any] = Depends(_require_admin)):
    roles = get_store("roles").load()
    rid = str(uuid.uuid4())
    roles[rid] = {
        "id": rid, "name": body.name, "description": body.description,
        "permissions": body.permissions, "created_at": now_iso(),
    }
    get_store("roles").save()
    return roles[rid]


@router.put("/roles/{role_id}")
async def update_role(role_id: str, body: RoleUpdateIn, user: Dict[str, Any] = Depends(_require_admin)):
    roles = get_store("roles").load()
    if role_id not in roles:
        raise HTTPException(status_code=404, detail="Role not found")
    if body.name is not None:
        roles[role_id]["name"] = body.name
    if body.description is not None:
        roles[role_id]["description"] = body.description
    if body.permissions is not None:
        roles[role_id]["permissions"] = body.permissions
    get_store("roles").save()
    return roles[role_id]


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, user: Dict[str, Any] = Depends(_require_admin)):
    roles = get_store("roles").load()
    roles.pop(role_id, None)
    get_store("roles").save()
    return {"success": True}


@router.get("/permissions")
async def list_permissions(resource: Optional[str] = None,
                           user: Dict[str, Any] = Depends(_require_auth)):
    perms = get_store("permissions").load()
    if resource:
        perms = {k: v for k, v in perms.items() if v.get("resource") == resource}
    return {"permissions": list(perms.values())}


@router.get("/audit-logs")
async def audit_logs(action: Optional[str] = None,
                     resource_type: Optional[str] = None,
                     user_id: Optional[str] = None,
                     page: int = Query(1), per_page: int = Query(20),
                     user: Dict[str, Any] = Depends(_require_admin)):
    logs = get_store("audit_logs").load()
    if action:
        logs = [l for l in logs if l.get("action") == action]
    if resource_type:
        logs = [l for l in logs if l.get("resource_type") == resource_type]
    if user_id:
        logs = [l for l in logs if l.get("actor_id") == user_id]
    total = len(logs)
    start = (page - 1) * per_page
    return {"logs": logs[start:start + per_page][::-1], "total": total}


@router.get("/audit-logs/export")
async def export_audit_logs(user: Dict[str, Any] = Depends(_require_admin)):
    logs = get_store("audit_logs").load()
    buf = io.StringIO()
    writer = csv.writer(buf)
    if logs:
        writer.writerow(logs[0].keys())
        for l in logs:
            writer.writerow(l.values())
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


@router.get("/tenant/settings")
async def tenant_settings(user: Dict[str, Any] = Depends(_require_auth)):
    tenant = get_store("tenant").load()
    return tenant or {
        "max_users": 100, "max_storage_mb": 10240,
        "max_api_calls_per_day": 10000, "settings": {},
    }


@router.put("/tenant/settings")
async def update_tenant_settings(body: TenantSettingsIn,
                                 user: Dict[str, Any] = Depends(_require_admin)):
    tenant = get_store("tenant").load()
    for field, value in body.model_dump(exclude_none=True).items():
        tenant[field] = value
    get_store("tenant").save()
    return tenant
