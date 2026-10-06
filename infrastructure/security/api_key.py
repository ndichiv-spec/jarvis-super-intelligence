"""
API key management subsystem.

Provides:
  - Generation, validation, and revocation of API keys
  - Role/scope assignment per key
  - Key hashing for secure storage
  - Optional expiry support
"""

import os
import time
import uuid
import json
import hmac
import hashlib
import secrets
import threading
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ApiKey:
    key_id: str
    key_hash: str
    name: str
    roles: List[str] = field(default_factory=lambda: ["user"])
    scopes: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_id": self.key_id,
            "name": self.name,
            "roles": self.roles,
            "scopes": self.scopes,
            "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
            "expires_at": datetime.fromtimestamp(self.expires_at, tz=timezone.utc).isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


class ApiKeyManager:
    """
    API key lifecycle manager.

    In production, back this with Redis or a database for persistence.
    """

    def __init__(self, storage: Optional[Dict[str, ApiKey]] = None):
        self._keys: Dict[str, ApiKey] = storage or {}
        self._lock = threading.Lock()

    def generate(self, name: str, roles: Optional[List[str]] = None,
                 scopes: Optional[List[str]] = None,
                 expires_in_days: Optional[int] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> tuple:
        """
        Generate a new API key.
        Returns (key_id, raw_key) - store the raw_key only once.
        """
        raw_key = f"jv_{secrets.token_urlsafe(32)}"
        key_id = uuid.uuid4().hex[:12]
        key_hash = self._hash_key(raw_key)

        api_key = ApiKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            roles=roles or ["user"],
            scopes=scopes or [],
            expires_at=(time.time() + expires_in_days * 86400) if expires_in_days else None,
            metadata=metadata or {},
        )

        with self._lock:
            self._keys[key_id] = api_key

        return key_id, raw_key

    def validate(self, raw_key: str) -> Optional[ApiKey]:
        """Validate a raw API key string."""
        key_hash = self._hash_key(raw_key)
        with self._lock:
            for api_key in self._keys.values():
                if hmac.compare_digest(api_key.key_hash, key_hash):
                    if not api_key.is_active:
                        return None
                    if api_key.expired:
                        return None
                    return api_key
        return None

    def revoke(self, key_id: str) -> bool:
        with self._lock:
            if key_id in self._keys:
                self._keys[key_id].is_active = False
                return True
            return False

    def get(self, key_id: str) -> Optional[ApiKey]:
        with self._lock:
            return self._keys.get(key_id)

    def list_keys(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [k.to_dict() for k in self._keys.values()]

    def delete(self, key_id: str) -> bool:
        with self._lock:
            return self._keys.pop(key_id, None) is not None

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(f"jarvis:apikey:{raw_key}".encode()).hexdigest()
