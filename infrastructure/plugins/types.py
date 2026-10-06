"""
Core plugin types: manifest, state, metadata, and versioning.
"""

from __future__ import annotations
import time
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class PluginState(Enum):
    DISCOVERED = "discovered"
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNINSTALLED = "uninstalled"
    ERROR = "error"


class PluginHook(Enum):
    """Standardized extension hooks across all subsystems."""
    # Chat
    CHAT_BEFORE_RESPONSE = "chat:before_response"
    CHAT_AFTER_RESPONSE = "chat:after_response"
    CHAT_MESSAGE_FILTER = "chat:message_filter"

    # Agent
    AGENT_BEFORE_EXECUTE = "agent:before_execute"
    AGENT_AFTER_EXECUTE = "agent:after_execute"
    AGENT_TOOL_INVOKE = "agent:tool_invoke"

    # Memory
    MEMORY_BEFORE_STORE = "memory:before_store"
    MEMORY_AFTER_RETRIEVE = "memory:after_retrieve"
    MEMORY_BEFORE_SEARCH = "memory:before_search"

    # Voice
    VOICE_BEFORE_SYNTHESIS = "voice:before_synthesis"
    VOICE_AFTER_RECOGNITION = "voice:after_recognition"

    # Automation
    AUTOMATION_BEFORE_EXECUTE = "automation:before_execute"
    AUTOMATION_AFTER_EXECUTE = "automation:after_execute"

    # API
    API_BEFORE_REQUEST = "api:before_request"
    API_AFTER_RESPONSE = "api:after_response"

    # System
    SYSTEM_STARTUP = "system:startup"
    SYSTEM_SHUTDOWN = "system:shutdown"
    SYSTEM_HEALTH_CHECK = "system:health_check"

    # Webhook
    WEBHOOK_RECEIVED = "webhook:received"

    # Observability
    OBSERVABILITY_METRIC = "observability:metric"
    OBSERVABILITY_LOG = "observability:log"


class PluginPermission(Enum):
    """Granular permissions a plugin can request."""
    NETWORK_HTTP = "network:http"
    NETWORK_WEBSOCKET = "network:websocket"
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    DATABASE_READ = "database:read"
    DATABASE_WRITE = "database:write"
    AI_INFERENCE = "ai:inference"
    EXECUTE_CODE = "execute:code"
    EXECUTE_SHELL = "execute:shell"
    API_CALL = "api:call"
    WEBHOOK_RECEIVE = "webhook:receive"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    OBSERVABILITY_EMIT = "observability:emit"
    SYSTEM_CONFIG = "system:config"


@dataclass
class PluginVersion:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, version_str: str) -> PluginVersion:
        parts = version_str.split(".")
        return cls(
            major=int(parts[0]) if len(parts) > 0 else 0,
            minor=int(parts[1]) if len(parts) > 1 else 0,
            patch=int(parts[2]) if len(parts) > 2 else 0,
        )

    def __lt__(self, other: PluginVersion) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: PluginVersion) -> bool:
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)

    def __gt__(self, other: PluginVersion) -> bool:
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PluginVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)


@dataclass
class PluginDependency:
    plugin_id: str
    version: Optional[str] = None
    optional: bool = False

    def satisfied_by(self, version: PluginVersion) -> bool:
        if not self.version:
            return True
        return _check_version_constraint(version, self.version)


def _check_version_constraint(installed: PluginVersion, constraint: str) -> bool:
    """Check if installed version satisfies a constraint string like >=1.0.0, ==2.0.0, etc."""
    constraint = constraint.strip()
    if constraint.startswith(">="):
        spec = PluginVersion.parse(constraint[2:])
        return installed >= spec
    elif constraint.startswith("<="):
        spec = PluginVersion.parse(constraint[2:])
        return installed <= spec
    elif constraint.startswith(">"):
        spec = PluginVersion.parse(constraint[1:])
        return installed > spec
    elif constraint.startswith("<"):
        spec = PluginVersion.parse(constraint[1:])
        return installed < spec
    elif constraint.startswith("=="):
        spec = PluginVersion.parse(constraint[2:])
        return installed == spec
    elif constraint.startswith("!="):
        spec = PluginVersion.parse(constraint[2:])
        return installed != spec
    else:
        spec = PluginVersion.parse(constraint)
        return installed >= spec


@dataclass
class PluginManifest:
    id: str
    version: PluginVersion
    name: str = ""
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""
    min_host_version: str = "3.0.0"
    permissions: List[PluginPermission] = field(default_factory=list)
    hooks: List[PluginHook] = field(default_factory=list)
    dependencies: List[PluginDependency] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    config_schema: Optional[Dict[str, Any]] = None
    entrypoint: str = "main:Plugin"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PluginManifest:
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=PluginVersion.parse(data.get("version", "0.0.0")),
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", ""),
            homepage=data.get("homepage", ""),
            min_host_version=data.get("min_host_version", "3.0.0"),
            permissions=[PluginPermission(p) for p in data.get("permissions", [])],
            hooks=[PluginHook(h) for h in data.get("hooks", [])],
            dependencies=[PluginDependency(**d) for d in data.get("dependencies", [])],
            interfaces=data.get("interfaces", []),
            tags=data.get("tags", []),
            config_schema=data.get("config_schema"),
            entrypoint=data.get("entrypoint", "main:Plugin"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": str(self.version),
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
            "min_host_version": self.min_host_version,
            "permissions": [p.value for p in self.permissions],
            "hooks": [h.value for h in self.hooks],
            "dependencies": [
                {"plugin_id": d.plugin_id, "version": d.version, "optional": d.optional}
                for d in self.dependencies
            ],
            "interfaces": self.interfaces,
            "tags": self.tags,
            "config_schema": self.config_schema,
            "entrypoint": self.entrypoint,
        }


@dataclass
class PluginMetadata:
    manifest: PluginManifest
    state: PluginState = PluginState.DISCOVERED
    installed_at: Optional[float] = None
    enabled_at: Optional[float] = None
    last_error: Optional[str] = None
    error_count: int = 0
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_enabled(self) -> bool:
        return self.state == PluginState.ENABLED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "state": self.state.value,
            "installed_at": datetime.fromtimestamp(self.installed_at, tz=timezone.utc).isoformat()
                if self.installed_at else None,
            "enabled_at": datetime.fromtimestamp(self.enabled_at, tz=timezone.utc).isoformat()
                if self.enabled_at else None,
            "last_error": self.last_error,
            "error_count": self.error_count,
            "config": self.config,
        }


class PluginBase:
    """Base class all plugins must extend."""

    metadata: PluginMetadata

    async def initialize(self, context: PluginContext) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy"}
