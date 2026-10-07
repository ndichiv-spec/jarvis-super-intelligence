"""RBAC: users, roles, permissions, audit logs, tenant settings."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..core import (
    _require_admin as require_admin_central,
    _require_owner,
    get_current_user,
    get_store,
    hash_password,
    is_owner,
    make_user_payload,
    now_iso,
    require_permission,
)

router = APIRouter(prefix="/api/v1/rbac", tags=["rbac"])


class UserCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    full_name: Optional[str] = Field(default=None, max_length=120)


class UserUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: Optional[List[str]] = None
    status: Optional[Literal["active", "pending_authorization", "suspended", "disabled"]] = None


class RoleCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=64)
    description: Optional[str] = Field(default=None, max_length=500)
    permissions: List[str] = Field(default_factory=list, max_length=100)


class RoleUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=2, max_length=64)
    description: Optional[str] = Field(default=None, max_length=500)
    permissions: Optional[List[str]] = Field(default=None, max_length=100)


class TenantSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


_require_admin = require_admin_central


def _require_auth(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Any authenticated user may read this resource."""
    return user


@router.get("/users")
async def list_users(page: int = Query(1), per_page: int = Query(20),
                     search: Optional[str] = None,
                     user: Dict[str, Any] = Depends(require_permission("users:read"))):
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
async def create_user(body: UserCreateIn, user: Dict[str, Any] = Depends(_require_owner)):
    users = get_store("users").load()
    if any(u.get("email", "").lower() == body.email.lower() for u in users.values()):
        raise HTTPException(status_code=409, detail="Email exists")
    uid = str(uuid.uuid4())
    users[uid] = {
        "id": uid, "email": body.email, "username": body.username,
        "password_hash": hash_password(body.password),
        "full_name": body.full_name or body.username,
        "email_verified": False,
        "status": "pending_authorization",
        "roles": ["user"],
        "tenant_id": None,
        "created_at": now_iso(),
    }
    get_store("users").save()
    from .auth import (
        _VERIFICATION_TOKEN_TTL_HOURS,
        _generate_verification_token,
        _hash_token,
        _send_account_email,
        now_iso_timestamp,
    )

    raw_token = _generate_verification_token()
    token_hash = _hash_token(raw_token)
    verification_tokens = get_store("email_verification_tokens").load()
    verification_tokens[token_hash] = {
        "user_id": uid,
        "purpose": "email_verification",
        "created_at": now_iso(),
        "expires_at": now_iso_timestamp() + _VERIFICATION_TOKEN_TTL_HOURS * 3600,
        "used": False,
    }
    get_store("email_verification_tokens").save()
    try:
        await _send_account_email(body.email, "verify", raw_token)
    except HTTPException:
        users.pop(uid, None)
        get_store("users").save()
        verification_tokens.pop(token_hash, None)
        get_store("email_verification_tokens").save()
        raise
    _audit_rbac(user, "user_invited", uid)
    return _user_out(users[uid])


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdateIn, user: Dict[str, Any] = Depends(_require_owner)):
    users = get_store("users").load()
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    target = users[user_id]
    if is_owner(target) and body.roles is not None and "owner" not in body.roles:
        raise HTTPException(status_code=403, detail="The canonical owner role cannot be removed")
    if body.roles is not None:
        allowed_roles = {
            role.get("name")
            for role in get_store("roles").load().values()
            if isinstance(role, dict)
        }
        if "owner" in body.roles and not is_owner(target):
            raise HTTPException(status_code=400, detail="OWNER cannot be assigned to another identity")
        if not set(body.roles).issubset(allowed_roles):
            raise HTTPException(status_code=400, detail="Unknown role")
        users[user_id]["roles"] = body.roles
    if body.status is not None:
        users[user_id]["status"] = body.status
        if body.status in {"suspended", "disabled", "pending_authorization"}:
            _revoke_sessions(user_id)
    get_store("users").save()
    _audit_rbac(user, "user_updated", user_id)
    return _user_out(users[user_id])


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: Dict[str, Any] = Depends(_require_owner)):
    users = get_store("users").load()
    target = users.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if is_owner(target):
        raise HTTPException(status_code=403, detail="The canonical owner cannot be deleted")
    users.pop(user_id, None)
    get_store("users").save()
    _revoke_sessions(user_id)
    _audit_rbac(user, "user_deleted", user_id)
    return {"success": True}


@router.get("/roles")
async def list_roles(user: Dict[str, Any] = Depends(require_permission("roles:read"))):
    return {"roles": list(get_store("roles").load().values())}


@router.post("/roles")
async def create_role(body: RoleCreateIn, user: Dict[str, Any] = Depends(_require_owner)):
    roles = get_store("roles").load()
    if body.name.lower() in {"owner", "admin", "operator", "user", "service"}:
        raise HTTPException(status_code=400, detail="Built-in roles cannot be replaced")
    if "*" in body.permissions:
        raise HTTPException(status_code=400, detail="Wildcard permissions are reserved for OWNER")
    rid = str(uuid.uuid4())
    roles[rid] = {
        "id": rid, "name": body.name, "description": body.description,
        "permissions": body.permissions, "created_at": now_iso(),
    }
    get_store("roles").save()
    _audit_rbac(user, "role_created", rid)
    return roles[rid]


@router.put("/roles/{role_id}")
async def update_role(role_id: str, body: RoleUpdateIn, user: Dict[str, Any] = Depends(_require_owner)):
    roles = get_store("roles").load()
    if role_id not in roles:
        raise HTTPException(status_code=404, detail="Role not found")
    if roles[role_id].get("name") in {"owner", "admin", "operator", "user", "service"}:
        raise HTTPException(status_code=403, detail="Built-in role permissions are managed by JARVIS")
    if body.permissions is not None and "*" in body.permissions:
        raise HTTPException(status_code=400, detail="Wildcard permissions are reserved for OWNER")
    if body.name is not None:
        roles[role_id]["name"] = body.name
    if body.description is not None:
        roles[role_id]["description"] = body.description
    if body.permissions is not None:
        roles[role_id]["permissions"] = body.permissions
    get_store("roles").save()
    _audit_rbac(user, "role_updated", role_id)
    return roles[role_id]


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, user: Dict[str, Any] = Depends(_require_owner)):
    roles = get_store("roles").load()
    if role_id not in roles:
        raise HTTPException(status_code=404, detail="Role not found")
    if roles[role_id].get("name") in {"owner", "admin", "operator", "user", "service"}:
        raise HTTPException(status_code=403, detail="Built-in role cannot be deleted")
    roles.pop(role_id, None)
    get_store("roles").save()
    _audit_rbac(user, "role_deleted", role_id)
    return {"success": True}


@router.get("/permissions")
async def list_permissions(resource: Optional[str] = None,
                           user: Dict[str, Any] = Depends(require_permission("permissions:read"))):
    perms = get_store("permissions").load()
    if resource:
        perms = {k: v for k, v in perms.items() if v.get("resource") == resource}
    return {"permissions": list(perms.values())}


@router.get("/audit-logs")
async def audit_logs(action: Optional[str] = None,
                     resource_type: Optional[str] = None,
                     user_id: Optional[str] = None,
                     page: int = Query(1), per_page: int = Query(20),
                     user: Dict[str, Any] = Depends(require_permission("audit:read"))):
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
async def export_audit_logs(user: Dict[str, Any] = Depends(require_permission("audit:read"))):
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
async def tenant_settings(user: Dict[str, Any] = Depends(require_permission("system:read"))):
    tenant = get_store("tenant").load()
    return tenant or {
        "max_users": 100, "max_storage_mb": 10240,
        "max_api_calls_per_day": 10000, "settings": {},
    }


@router.put("/tenant/settings")
async def update_tenant_settings(body: TenantSettingsIn,
                                 user: Dict[str, Any] = Depends(_require_owner)):
    tenant = get_store("tenant").load()
    for field, value in body.model_dump(exclude_none=True).items():
        tenant[field] = value
    get_store("tenant").save()
    _audit_rbac(user, "tenant_settings_updated", "tenant")
    return tenant


def _audit_rbac(actor: Dict[str, Any], action: str, target_id: str) -> None:
    logs = get_store("audit_logs").load()
    logs.append({
        "id": str(uuid.uuid4()),
        "actor_id": actor.get("id"),
        "action": action,
        "resource_type": "rbac",
        "resource_id": target_id,
        "timestamp": now_iso(),
    })
    get_store("audit_logs").save()


def _revoke_sessions(user_id: str) -> None:
    sessions = get_store("sessions").load()
    for session_id in [
        key for key, session in sessions.items()
        if session.get("user_id") == user_id
    ]:
        sessions.pop(session_id, None)
    get_store("sessions").save()

    refresh_tokens = get_store("refresh_tokens").load()
    for token_id in [
        key for key, entry in refresh_tokens.items()
        if entry.get("user_id") == user_id
    ]:
        refresh_tokens.pop(token_id, None)
    get_store("refresh_tokens").save()

    api_keys = get_store("api_keys").load()
    for record in api_keys.values():
        if record.get("owner") == user_id or record.get("user_id") == user_id:
            record["status"] = "revoked"
    get_store("api_keys").save()
