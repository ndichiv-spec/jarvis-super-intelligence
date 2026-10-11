"""
Structured error taxonomy.

Every error type carries:
  - A machine-readable error code
  - A human-readable message
  - The subsystem of origin
  - Optional details dict for structured context
  - Optional original exception for traceback preservation
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class JarvisError(Exception):
    """Base error for all Jarvis subsystems."""
    message: str = "An unexpected error occurred"
    code: str = "internal_error"
    subsystem: str = "core"
    details: dict[str, Any] | None = None
    original: Exception | None = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "subsystem": self.subsystem,
            "details": self.details or {},
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ── Configuration ──────────────────────────────────────────

class ConfigurationError(JarvisError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message=message, code="configuration_error",
                         subsystem="config", details=details)


# ── Security ───────────────────────────────────────────────

class SecurityError(JarvisError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message=message, code="security_error",
                         subsystem="security", details=details)


class AuthenticationError(SecurityError):
    def __init__(self, message: str = "Authentication required",
                 details: dict[str, Any] | None = None):
        JarvisError.__init__(
            self,
            message=message,
            code="authentication_error",
            subsystem="security",
            details=details,
        )


class AuthorizationError(SecurityError):
    def __init__(self, message: str = "Permission denied",
                 details: dict[str, Any] | None = None):
        JarvisError.__init__(
            self,
            message=message,
            code="authorization_error",
            subsystem="security",
            details=details,
        )


class RateLimitError(SecurityError):
    def __init__(self, message: str = "Rate limit exceeded",
                 retry_after: float = 0, details: dict[str, Any] | None = None):
        JarvisError.__init__(
            self,
            message=message,
            code="rate_limit_error",
            subsystem="security",
            details={**(details or {}), "retry_after": retry_after},
        )


# ── Providers (DB, Cache, AI) ──────────────────────────────

class ProviderError(JarvisError):
    def __init__(self, message: str, provider: str = "",
                 details: dict[str, Any] | None = None):
        super().__init__(message=message, code="provider_error",
                         subsystem=f"provider.{provider}" if provider else "provider",
                         details=details)


class AIProviderError(ProviderError):
    def __init__(self, message: str, provider: str = "ai",
                 model: str = "", details: dict[str, Any] | None = None):
        JarvisError.__init__(
            self,
            message=message,
            code="ai_provider_error",
            subsystem=f"provider.{provider}" if provider else "provider",
            details={**(details or {}), "provider": provider, "model": model},
        )
        self.model = model


class DatabaseError(ProviderError):
    def __init__(self, message: str = "Database error",
                 details: dict[str, Any] | None = None):
        JarvisError.__init__(
            self,
            message=message,
            code="database_error",
            subsystem="provider.database",
            details=details,
        )


class CacheError(ProviderError):
    def __init__(self, message: str = "Cache error",
                 details: dict[str, Any] | None = None):
        super().__init__(message=message, provider="cache", details=details)


# ── Validation ─────────────────────────────────────────────

class ValidationError(JarvisError):
    def __init__(self, message: str = "Validation failed",
                 field: str = "", details: dict[str, Any] | None = None):
        super().__init__(message=message, code="validation_error",
                         subsystem="validation",
                         details={**(details or {}), "field": field})


class NotFoundError(JarvisError):
    def __init__(self, message: str = "Resource not found",
                 resource_type: str = "", resource_id: str = "",
                 details: dict[str, Any] | None = None):
        super().__init__(message=message, code="not_found",
                         subsystem="api",
                         details={**(details or {}), "resource_type": resource_type, "resource_id": resource_id})


# ── Timeouts / Resources ───────────────────────────────────

class TimeoutError(JarvisError):
    def __init__(self, message: str = "Operation timed out",
                 timeout_seconds: float = 0, details: dict[str, Any] | None = None):
        super().__init__(message=message, code="timeout",
                         subsystem="core",
                         details={**(details or {}), "timeout_seconds": timeout_seconds})


class DependencyError(JarvisError):
    def __init__(self, message: str = "Dependency unavailable",
                 dependency: str = "", details: dict[str, Any] | None = None):
        super().__init__(message=message, code="dependency_error",
                         subsystem=f"dependency.{dependency}" if dependency else "dependency",
                         details=details)


class ResourceExhaustedError(JarvisError):
    def __init__(self, message: str = "Resource exhausted",
                 resource: str = "", limit: Any = None,
                 details: dict[str, Any] | None = None):
        super().__init__(message=message, code="resource_exhausted",
                         subsystem="core",
                         details={**(details or {}), "resource": resource, "limit": str(limit) if limit else None})


# ── Execution ──────────────────────────────────────────────

class SandboxError(JarvisError):
    def __init__(self, message: str = "Sandbox execution failed",
                 action: str = "", details: dict[str, Any] | None = None):
        super().__init__(message=message, code="sandbox_error",
                         subsystem="sandbox",
                         details={**(details or {}), "action": action})


class AutomationError(JarvisError):
    def __init__(self, message: str = "Automation execution failed",
                 details: dict[str, Any] | None = None):
        super().__init__(message=message, code="automation_error",
                         subsystem="automation", details=details)


class InternalError(JarvisError):
    def __init__(self, message: str = "Internal error",
                 details: dict[str, Any] | None = None):
        super().__init__(message=message, code="internal_error",
                         subsystem="core", details=details)


class IntegrationError(ProviderError):
    def __init__(self, message: str, service: str = "",
                 details: dict[str, Any] | None = None):
        JarvisError.__init__(
            self,
            message=message,
            code="integration_error",
            subsystem=f"integration.{service}" if service else "integration",
            details={**(details or {}), "service": service},
        )
