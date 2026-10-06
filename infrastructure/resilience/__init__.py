"""
Resilience patterns for production-grade reliability.

Provides:
  - Circuit breaker for external service calls
  - Retry with exponential backoff and jitter
  - Graceful degradation / fallback chains
  - AI provider resilience (multi-provider failover)
"""

from .circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError
from .retry import RetryStrategy, retry, exponential_backoff
from .fallback import FallbackChain, FallbackProvider, DegradationPolicy
from .ai_provider import AIProviderResilience, ProviderResponse

__all__ = [
    "CircuitBreaker", "CircuitState", "CircuitOpenError",
    "RetryStrategy", "retry", "exponential_backoff",
    "FallbackChain", "FallbackProvider", "DegradationPolicy",
    "AIProviderResilience", "ProviderResponse",
]
