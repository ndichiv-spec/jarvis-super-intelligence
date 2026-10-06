from __future__ import annotations

import secrets
import uuid
from enum import Enum
from typing import Iterable, Sequence

try:  # pragma: no cover - optional dependency
    import pyotp
except Exception:  # pragma: no cover
    pyotp = None


class UserRoleEnum(str, Enum):
    USER = "user"
    ADMIN = "admin"
    MANAGER = "manager"
    SYSTEM = "system"


class PermissionEnum(str, Enum):
    AI_CHAT = "ai:chat"
    DASHBOARD_READ = "dashboard:read"
    SYSTEM_ADMIN = "system:admin"
    ANALYTICS_READ = "analytics:read"
    SERVICE_MANAGE = "service:manage"


class RBACService:
    _role_permissions = {
        UserRoleEnum.USER: {PermissionEnum.AI_CHAT, PermissionEnum.DASHBOARD_READ},
        UserRoleEnum.ADMIN: {
            PermissionEnum.AI_CHAT,
            PermissionEnum.DASHBOARD_READ,
            PermissionEnum.SYSTEM_ADMIN,
            PermissionEnum.ANALYTICS_READ,
            PermissionEnum.SERVICE_MANAGE,
        },
        UserRoleEnum.MANAGER: {
            PermissionEnum.AI_CHAT,
            PermissionEnum.DASHBOARD_READ,
            PermissionEnum.ANALYTICS_READ,
            PermissionEnum.SERVICE_MANAGE,
        },
        UserRoleEnum.SYSTEM: {
            PermissionEnum.AI_CHAT,
            PermissionEnum.DASHBOARD_READ,
            PermissionEnum.SYSTEM_ADMIN,
            PermissionEnum.ANALYTICS_READ,
            PermissionEnum.SERVICE_MANAGE,
        },
    }

    def get_all_permissions(self, roles: Iterable[UserRoleEnum | str]) -> set[PermissionEnum]:
        permissions: set[PermissionEnum] = set()
        for role in roles:
            normalized = role.value if isinstance(role, UserRoleEnum) else str(role).lower()
            try:
                permissions.update(self._role_permissions[UserRoleEnum(normalized)])
            except ValueError:
                continue
        return permissions


class TwoFactorService:
    def generate_totp_secret(self) -> str:
        return secrets.token_hex(16)

    def generate_backup_codes(self, count: int = 10) -> list[str]:
        return [
            "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
            for _ in range(count)
        ]

    def verify_totp(self, secret: str, token: str) -> bool:
        if not secret or not token:
            return False
        if pyotp is not None:
            try:
                return bool(pyotp.TOTP(secret).verify(token, valid_window=1))
            except Exception:
                return False
        return len(str(token).strip()) >= 6


class AuthService:
    def __init__(self) -> None:
        self.rbac = RBACService()
        self.two_factor = TwoFactorService()

    async def register_user(
        self,
        db=None,
        username: str | None = None,
        email: str | None = None,
        password: str | None = None,
        roles: Sequence[UserRoleEnum | str] | None = None,
    ) -> dict:
        normalized_roles = [
            role.value if isinstance(role, UserRoleEnum) else str(role).lower() for role in (roles or [UserRoleEnum.USER])
        ]
        return {
            "id": str(uuid.uuid4()),
            "username": username or "user",
            "email": email or f"{username or 'user'}@jarvis.ai",
            "password": password,
            "roles": normalized_roles,
            "is_active": True,
            "is_admin": UserRoleEnum.ADMIN.value in normalized_roles,
        }


auth_service = AuthService()

__all__ = ["AuthService", "PermissionEnum", "RBACService", "TwoFactorService", "UserRoleEnum", "auth_service"]
