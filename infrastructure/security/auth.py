"""
JWT-based authentication and authorization middleware.

Provides:
  - Token creation and verification
  - Role-based access control
  - ASGI middleware for request authentication
  - Scope/permission checking
"""

import os
import time
import uuid
import hmac
import json
import hashlib
import base64
from typing import Dict, Optional, List, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class Permission(Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    EXECUTE = "execute"
    MANAGE = "manage"


@dataclass
class TokenPayload:
    sub: str
    exp: float
    iat: float
    jti: str
    roles: List[str] = field(default_factory=lambda: ["user"])
    scopes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sub": self.sub,
            "exp": self.exp,
            "iat": self.iat,
            "jti": self.jti,
            "roles": self.roles,
            "scopes": self.scopes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenPayload":
        return cls(
            sub=data["sub"],
            exp=data["exp"],
            iat=data.get("iat", time.time()),
            jti=data.get("jti", ""),
            roles=data.get("roles", ["user"]),
            scopes=data.get("scopes", []),
        )


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode())


def _hmac_sign(header_b64: str, payload_b64: str, secret: str) -> str:
    msg = f"{header_b64}.{payload_b64}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    return _b64_encode(sig)


class JWTAuthenticator:
    """JWT creation and verification."""

    def __init__(self, secret: str = "", algorithm: str = "HS256", ttl: int = 3600):
        self.secret = secret or os.environ.get("SECRET_KEY", "change-me")
        self.algorithm = algorithm
        self.ttl = ttl

    def create_token(self, subject: str, roles: Optional[List[str]] = None,
                     scopes: Optional[List[str]] = None, ttl: Optional[int] = None) -> str:
        now = time.time()
        payload = TokenPayload(
            sub=subject,
            exp=now + (ttl or self.ttl),
            iat=now,
            jti=uuid.uuid4().hex,
            roles=roles or ["user"],
            scopes=scopes or [],
        )
        header = {"alg": self.algorithm, "typ": "JWT"}
        header_b64 = _b64_encode(json.dumps(header).encode())
        payload_b64 = _b64_encode(json.dumps(payload.to_dict()).encode())
        sig = _hmac_sign(header_b64, payload_b64, self.secret)
        return f"{header_b64}.{payload_b64}.{sig}"

    def verify(self, token: str) -> Optional[TokenPayload]:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            header_b64, payload_b64, sig_b64 = parts

            expected_sig = _hmac_sign(header_b64, payload_b64, self.secret)
            if not hmac.compare_digest(sig_b64, expected_sig):
                return None

            payload_data = json.loads(_b64_decode(payload_b64))
            payload = TokenPayload.from_dict(payload_data)

            if time.time() > payload.exp:
                return None

            return payload
        except Exception:
            return None

    def refresh_token(self, token: str) -> Optional[str]:
        payload = self.verify(token)
        if not payload:
            return None
        return self.create_token(
            subject=payload.sub,
            roles=payload.roles,
            scopes=payload.scopes,
        )

    def has_permission(self, token: str, required_scope: str) -> bool:
        payload = self.verify(token)
        if not payload:
            return False
        if "admin" in payload.roles:
            return True
        return required_scope in payload.scopes


def create_token(subject: str, roles: Optional[List[str]] = None,
                 scopes: Optional[List[str]] = None, ttl: Optional[int] = None) -> str:
    auth = JWTAuthenticator()
    return auth.create_token(subject, roles, scopes, ttl)


def verify_token(token: str) -> Optional[TokenPayload]:
    auth = JWTAuthenticator()
    return auth.verify(token)


class AuthMiddleware:
    """
    ASGI middleware for request authentication.

    Extracts Bearer token from Authorization header and validates it.
    On failure, returns 401 or 403.
    """

    def __init__(self, app: Callable, excluded_paths: tuple = ("/health", "/docs", "/openapi.json", "/metrics")):
        self.app = app
        self.excluded_paths = excluded_paths
        self.authenticator = JWTAuthenticator()

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                await self.app(scope, receive, send)
                return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        if not auth_header.startswith("Bearer "):
            await self._send_401(send, "Missing or invalid Authorization header")
            return

        token = auth_header[7:]
        payload = self.authenticator.verify(token)
        if not payload:
            await self._send_401(send, "Invalid or expired token")
            return

        scope["user"] = {
            "sub": payload.sub,
            "roles": payload.roles,
            "scopes": payload.scopes,
        }
        await self.app(scope, receive, send)

    async def _send_401(self, send: Callable, detail: str):
        body = json.dumps({"error": "unauthorized", "detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
