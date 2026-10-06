"""Shared owner checks for persisted user-scoped resources."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .core import is_admin, is_developer


def principal_owner_id(user: dict[str, Any]) -> str:
    """Return a stable authenticated identity suitable for resource ownership."""
    for key in ("id", "user_id", "email"):
        value = user.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(status_code=401, detail="Authenticated user has no stable identity")


def can_access_owner(owner: str | None, user: dict[str, Any]) -> bool:
    """Admins can access all records; other users can access only their own."""
    if is_admin(user):
        return True
    if not owner or owner == "system":
        return False
    identities = {
        value.strip()
        for key in ("id", "user_id", "email")
        if isinstance((value := user.get(key)), str) and value.strip()
    }
    return owner in identities


def require_owner_access(owner: str | None, user: dict[str, Any]) -> None:
    """Hide both missing and unauthorized resources from non-admin callers."""
    if not can_access_owner(owner, user):
        raise HTTPException(status_code=404, detail="Resource not found")


def require_developer(user: dict[str, Any]) -> None:
    """Restrict costly laboratory execution to developer/admin principals."""
    if not is_developer(user):
        raise HTTPException(status_code=403, detail="Developer access required")
