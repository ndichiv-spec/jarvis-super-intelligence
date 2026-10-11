"""
Error handling architecture.

Provides:
  - Typed exception hierarchy for every subsystem
  - ASGI error handling middleware
  - Error aggregation and reporting
  - Structured error responses
"""

from .handler import ErrorHandler, error_response, exception_to_status
from .tracker import ErrorEvent, ErrorTracker, get_error_tracker
from .types import (
    AIProviderError,
    AuthenticationError,
    AuthorizationError,
    AutomationError,
    CacheError,
    ConfigurationError,
    DatabaseError,
    DependencyError,
    IntegrationError,
    InternalError,
    JarvisError,
    NotFoundError,
    ProviderError,
    RateLimitError,
    ResourceExhaustedError,
    SandboxError,
    SecurityError,
    TimeoutError,
    ValidationError,
)

__all__ = [
    "AIProviderError",
    "AuthenticationError",
    "AuthorizationError",
    "AutomationError",
    "CacheError",
    "ConfigurationError",
    "DatabaseError",
    "DependencyError",
    "ErrorEvent",
    "ErrorHandler",
    "ErrorTracker",
    "IntegrationError",
    "InternalError",
    "JarvisError",
    "NotFoundError",
    "ProviderError",
    "RateLimitError",
    "ResourceExhaustedError",
    "SandboxError",
    "SecurityError",
    "TimeoutError",
    "ValidationError",
    "error_response",
    "exception_to_status",
    "get_error_tracker",
]
