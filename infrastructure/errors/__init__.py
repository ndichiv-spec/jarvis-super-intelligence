"""
Error handling architecture.

Provides:
  - Typed exception hierarchy for every subsystem
  - ASGI error handling middleware
  - Error aggregation and reporting
  - Structured error responses
"""

from .types import (
    JarvisError, ConfigurationError, SecurityError, AuthenticationError,
    AuthorizationError, RateLimitError, ProviderError, AIProviderError,
    DatabaseError, CacheError, ValidationError, NotFoundError,
    TimeoutError, DependencyError, ResourceExhaustedError,
    SandboxError, AutomationError, InternalError,
)
from .handler import ErrorHandler, error_response, exception_to_status
from .tracker import ErrorTracker, ErrorEvent, get_error_tracker

__all__ = [
    "JarvisError", "ConfigurationError", "SecurityError",
    "AuthenticationError", "AuthorizationError", "RateLimitError",
    "ProviderError", "AIProviderError",
    "DatabaseError", "CacheError", "ValidationError", "NotFoundError",
    "TimeoutError", "DependencyError", "ResourceExhaustedError",
    "SandboxError", "AutomationError", "InternalError",
    "ErrorHandler", "error_response", "exception_to_status",
    "ErrorTracker", "ErrorEvent", "get_error_tracker",
]
