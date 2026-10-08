"""
Authentication Runtime - Platform-wide authentication and authorization.

Provides consistent authentication middleware for all protected routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Callable, Set
from enum import Enum
import time
import threading
import logging
import secrets
import hashlib

logger = logging.getLogger("control_plane.auth_runtime")


class Permission(str, Enum):
    """Platform permissions"""
    READ_SYSTEM = "read:system"
    READ_RESEARCH = "read:research"
    RUN_SANDBOX = "run:sandbox"
    RUN_BROWSER = "run:browser"
    WRITE_KNOWLEDGE = "write:knowledge"
    WRITE_MEMORY = "write:memory"
    CREATE_LESSON = "create:lesson"
    MODIFY_CODE = "modify:code"
    MODIFY_CONFIG = "modify:config"
    RESTART_SERVICE = "restart:service"
    CHANGE_PROVIDER = "change:provider"
    MANAGE_USERS = "manage:users"
    PROMOTE_MODEL = "promote:model"
    APPROVE_CHANGES = "approve:changes"
    VIEW_AUDIT = "view:audit"
    SYSTEM_ADMIN = "admin:system"


class Role:
    """A role with associated permissions"""
    def __init__(
        self,
        name: str,
        description: str = "",
        permissions: set = None,
    ):
        self.name = name
        self.description = description
        self.permissions = permissions or set()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permissions": [p.value for p in self.permissions],
        }


class User:
    """A platform user"""
    def __init__(
        self,
        user_id: str,
        username: str,
        email: Optional[str] = None,
        is_admin: bool = False,
        created_at: float = 0,
        last_active: float = 0,
    ):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.roles: set = set()
        self.permissions: set = set()
        self.is_admin = is_admin
        self.created_at = created_at
        self.last_active = last_active
        self.session_count: int = 0
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission"""
        if permission in self.permissions:
            return True
        for role in self.roles:
            if permission in role.permissions:
                return True
        if permission == Permission.SYSTEM_ADMIN and self.is_admin:
            return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "roles": [r.name for r in self.roles],
            "permissions": [p.value for p in self.permissions],
            "is_admin": self.is_admin,
            "created_at": self.created_at,
            "session_count": self.session_count,
        }


class Session:
    """An authenticated session"""
    def __init__(
        self,
        session_id: str,
        user_id: str,
        created_at: float,
        expires_at: float,
        permissions: set = None,
        roles: set = None,
        workspace_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        is_active: bool = True,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.created_at = created_at
        self.expires_at = expires_at
        self.permissions = permissions or set()
        self.roles = roles or set()
        self.workspace_id = workspace_id
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.is_active = is_active
    
    def is_valid(self) -> bool:
        """Check if session is valid and not expired"""
        return self.is_active and time.time() < self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "permissions": [p.value for p in self.permissions],
            "roles": list(self.roles),
            "workspace_id": self.workspace_id,
        }


@dataclass
class AuthPolicy:
    """Authentication and authorization policy"""
    enabled: bool = True
    session_timeout_sec: int = 3600
    max_sessions_per_user: int = 5
    require_mfa: bool = False
    allowed_ips: Optional[List[str]] = None
    rate_limit_requests: int = 100
    rate_limit_window_sec: int = 60
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "session_timeout_sec": self.session_timeout_sec,
            "max_sessions_per_user": self.max_sessions_per_user,
            "require_mfa": self.require_mfa,
            "allowed_ips": self.allowed_ips,
            "rate_limit_requests": self.rate_limit_requests,
            "rate_limit_window_sec": self.rate_limit_window_sec,
        }


class AuthRuntime:
    """
    Platform-wide authentication and authorization runtime.
    
    Provides:
    - User and group management
    - Session management
    - Permission checking
    - Authorization middleware
    """
    
    _instance: Optional["AuthRuntime"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._users: Dict[str, User] = {}
        self._sessions: Dict[str, Session] = {}
        self._roles: Dict[str, Role] = {}
        self._policy = AuthPolicy()
        self._setup_default_roles()
        self._setup_default_users()
    
    @classmethod
    def get_instance(cls) -> "AuthRuntime":
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _setup_default_roles(self) -> None:
        """Set up default platform roles"""
        # Admin role
        admin_role = Role(
            name="admin",
            description="Platform administrator with full access",
            permissions={
                Permission.READ_SYSTEM, Permission.RESTART_SERVICE,
                Permission.MANAGE_USERS, Permission.APPROVE_CHANGES,
                Permission.VIEW_AUDIT, Permission.SYSTEM_ADMIN,
            }
        )
        self._roles["admin"] = admin_role
        
        # Developer role
        dev_role = Role(
            name="developer",
            description="Can develop, test, and modify code",
            permissions={
                Permission.READ_SYSTEM, Permission.MODIFY_CODE,
                Permission.RUN_SANDBOX, Permission.RUN_BROWSER,
                Permission.WRITE_MEMORY,
            }
        )
        self._roles["developer"] = dev_role
        
        # Researcher role
        researcher_role = Role(
            name="researcher",
            description="Can conduct research and create knowledge",
            permissions={
                Permission.READ_SYSTEM, Permission.RUN_BROWSER,
                Permission.WRITE_KNOWLEDGE, Permission.WRITE_MEMORY,
                Permission.READ_RESEARCH,
            }
        )
        self._roles["researcher"] = researcher_role
        
        # Learner role
        learner_role = Role(
            name="learner",
            description="Can participate in learning and challenges",
            permissions={
                Permission.READ_SYSTEM, Permission.READ_RESEARCH,
                Permission.CREATE_LESSON,
            }
        )
        self._roles["learner"] = learner_role
        
        # Viewer role (read-only)
        viewer_role = Role(
            name="viewer",
            description="Read-only access",
            permissions={
                Permission.READ_SYSTEM, Permission.READ_RESEARCH,
            }
        )
        self._roles["viewer"] = viewer_role
    
    def _setup_default_users(self) -> None:
        """Set up default users (for development)"""
        # Default admin user (change password in production!)
        admin_user = User(
            user_id="admin",
            username="admin",
            email="admin@localhost",
            is_admin=True,
            created_at=time.time(),
            last_active=time.time(),
        )
        admin_user.roles.add(self._roles["admin"])
        self._users["admin"] = admin_user
    
    def create_user(
        self,
        username: str,
        email: Optional[str] = None,
        roles: List[str] = None,
        permissions: List[Permission] = None,
        is_admin: bool = False,
    ) -> User:
        """Create a new user"""
        user_id = hashlib.sha256(f"{username}{time.time()}".encode()).hexdigest()[:16]
        
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            permissions=set(permissions or []),
            is_admin=is_admin,
            created_at=time.time(),
            last_active=time.time(),
        )
        # Add roles after creation since User is a dataclass with unhashable fields
        for role_name in (roles or []):
            if role_name in self._roles:
                user.roles.add(self._roles[role_name])
        
        self._users[user_id] = user
        logger.info(f"Created user: {username}")
        return user
    
    def authenticate(
        self,
        username: Optional[str] = None,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        password: Optional[str] = None,
        duration_sec: int = None,
    ) -> Optional[Session]:
        """
        Authenticate a user and create a session.
        
        Supports multiple auth methods:
        - Username/password
        - Email/password
        - API key
        """
        user: Optional[User] = None
        
        if api_key:
            # API key authentication
            user = self._authenticate_api_key(api_key)
        elif email and password:
            user = self._authenticate_email(email, password)
        elif username and password:
            user = self._authenticate_username(username, password)
        
        if not user:
            return None
        
        return self._create_session(user, duration_sec or self._policy.session_timeout_sec)
    
    def _authenticate_api_key(self, api_key: str) -> Optional[User]:
        """Authenticate using API key"""
        # In production, this would verify against a secure store
        # For development, accept any non-empty key
        if api_key and len(api_key) > 10:
            # Return admin for demo purposes in development
            # In production, look up the key in a database
            return self._users.get("admin")
        return None
    
    def _authenticate_email(self, email: str, password: str) -> Optional[User]:
        """Authenticate using email"""
        # In production, verify against user store
        return None
    
    def _authenticate_username(self, username: str, password: str) -> Optional[User]:
        """Authenticate using username"""
        # In production, verify against user store
        return None
    
    def _create_session(self, user: User, duration_sec: int) -> Session:
        """Create a new session for a user"""
        # Clean up expired sessions
        self._cleanup_expired_sessions()
        
        # Check session limits
        user.active_sessions = [
            s for s in self._sessions.values()
            if s.user_id == user.user_id and s.is_valid()
        ]
        
        if len(user.active_sessions) >= self._policy.max_sessions_per_user:
            # Remove oldest session
            oldest = min(user.active_sessions, key=lambda s: s.created_at)
            oldest.is_active = False
            self._sessions[oldest.session_id] = oldest
        
        # Create new session
        session_id = secrets.token_urlsafe(32)
        expires_at = time.time() + duration_sec
        
        session = Session(
            session_id=session_id,
            user_id=user.user_id,
            created_at=time.time(),
            expires_at=expires_at,
            permissions=user.permissions | {p for r in user.roles for p in r.permissions},
            roles={r.name for r in user.roles},
        )
        
        self._sessions[session_id] = session
        user.last_active = time.time()
        user.session_count += 1
        
        logger.info(f"Created session for user: {user.username}")
        return session
    
    def validate_session(self, session_id: str) -> Optional[Session]:
        """Validate a session and return it if valid"""
        session = self._sessions.get(session_id)
        if session and session.is_valid():
            return session
        return None
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID"""
        return self._users.get(user_id)
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID"""
        return self._sessions.get(session_id)
    
    def revoke_session(self, session_id: str) -> bool:
        """Revoke a session"""
        session = self._sessions.get(session_id)
        if session:
            session.is_active = False
            logger.info(f"Revoked session: {session_id}")
            return True
        return False
    
    def check_permission(self, session_id: str, permission: Permission) -> bool:
        """Check if a session has a specific permission"""
        session = self.validate_session(session_id)
        if not session:
            return False
        return permission in session.permissions
    
    def check_permission_by_user(self, user_id: str, permission: Permission) -> bool:
        """Check if a user has a specific permission"""
        user = self._users.get(user_id)
        if not user:
            return False
        return user.has_permission(permission)
    
    def add_role(self, user_id: str, role_name: str) -> bool:
        """Add a role to a user"""
        role = self._roles.get(role_name)
        user = self._users.get(user_id)
        if not role or not user:
            return False
        
        user.roles.add(role)
        logger.info(f"Added role {role_name} to user {user_id}")
        return True
    
    def add_permission(self, user_id: str, permission: Permission) -> bool:
        """Add a permission to a user"""
        user = self._users.get(user_id)
        if not user:
            return False
        
        user.permissions.add(permission)
        logger.info(f"Added permission {permission} to user {user_id}")
        return True
    
    def remove_role(self, user_id: str, role_name: str) -> bool:
        """Remove a role from a user"""
        role = self._roles.get(role_name)
        user = self._users.get(user_id)
        if not role or not user:
            return False
        
        user.roles.discard(role)
        logger.info(f"Removed role {role_name} from user {user_id}")
        return True
    
    def remove_permission(self, user_id: str, permission: Permission) -> bool:
        """Remove a permission from a user"""
        user = self._users.get(user_id)
        if not user:
            return False
        
        user.permissions.discard(permission)
        logger.info(f"Removed permission {permission} from user {user_id}")
        return True
    
    def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions"""
        current_time = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if not s.is_valid()
        ]
        for sid in expired:
            del self._sessions[sid]
        
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired sessions")
    
    def get_active_sessions(self) -> List[Session]:
        """Get all active sessions"""
        return [s for s in self._sessions.values() if s.is_valid()]
    
    def get_all_users(self) -> List[User]:
        """Get all users"""
        return list(self._users.values())
    
    def get_all_roles(self) -> List[Role]:
        """Get all roles"""
        return list(self._roles.values())
    
    def set_policy(self, policy: AuthPolicy) -> None:
        """Set the authentication policy"""
        self._policy = policy
        logger.info(f"Updated auth policy: enabled={policy.enabled}")
    
    def get_policy(self) -> AuthPolicy:
        """Get the current auth policy"""
        return self._policy
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "policy": self._policy.to_dict(),
            "users": [u.to_dict() for u in self._users.values()],
            "roles": [r.to_dict() for r in self._roles.values()],
            "active_sessions": len(self.get_active_sessions()),
        }


# Global auth runtime instance
auth_runtime = AuthRuntime.get_instance()


def check_permission(session_id: str, permission: Permission) -> bool:
    """Check if a session has a permission (convenience function)"""
    return auth_runtime.check_permission(session_id, permission)


def require_permission(permission: Permission):
    """
    Decorator for FastAPI routes that require a specific permission.
    
    Usage:
        @app.get("/protected")
        @require_permission(Permission.READ_SYSTEM)
        async def protected_route(request: Request):
            ...
    """
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # In FastAPI, the session would be extracted from the request
            session_id = kwargs.get("session_id") or (args[0].headers.get("Authorization") if args else None)
            if not session_id or not auth_runtime.validate_session(str(session_id)):
                from fastapi import HTTPException
                raise HTTPException(401, "Authentication required")
            
            if not auth_runtime.check_permission(str(session_id), permission):
                from fastapi import HTTPException
                raise HTTPException(403, "Permission denied")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator