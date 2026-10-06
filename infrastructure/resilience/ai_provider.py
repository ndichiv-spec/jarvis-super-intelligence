"""
AI provider resilience.

Provides multi-provider failover, request retry, and circuit breaking
specifically for AI/LLM provider calls (OpenAI, Gemini, Ollama, etc.).
"""

import time
import asyncio
import logging
from typing import Callable, Any, Optional, List, Dict, Type
from dataclasses import dataclass, field
from enum import Enum

from .circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from .retry import RetryStrategy, retry
from .fallback import FallbackChain, FallbackProvider, FallbackResult

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ProviderResponse:
    success: bool
    data: Any = None
    provider: str = ""
    model: str = ""
    error: Optional[str] = None
    latency_ms: float = 0.0
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "provider": self.provider,
            "model": self.model,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 2),
            "cached": self.cached,
        }


class AIProviderResilience:
    """
    Multi-provider AI resilience with:
      - Per-provider circuit breakers
      - Provider failover (try provider A, then B, then C)
      - Request retry with exponential backoff
      - Health tracking per provider
      - Optional response caching

    Usage:
        resilience = AIProviderResilience()

        @resilience.provider("openai")
        async def call_openai(prompt):
            ...

        @resilience.provider("gemini")
        async def call_gemini(prompt):
            ...

        response = await resilience.execute(
            prompt="Hello",
            preferred_providers=["openai", "gemini", "ollama"],
        )
    """

    def __init__(self, default_timeout: float = 60.0, cache_ttl: float = 0):
        self.default_timeout = default_timeout
        self.cache_ttl = cache_ttl
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._providers: Dict[str, Callable] = {}
        self._health: Dict[str, ProviderStatus] = {}
        self._cache: Dict[str, ProviderResponse] = {}
        self._cache_times: Dict[str, float] = {}

    def provider(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        """Decorator to register a provider function."""
        self._circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self._health[name] = ProviderStatus.HEALTHY

        def decorator(fn: Callable):
            self._providers[name] = fn
            return fn
        return decorator

    def register(self, name: str, fn: Callable, **breaker_kwargs):
        """Register a provider programmatically."""
        self._circuit_breakers[name] = CircuitBreaker(
            name=name,
            **breaker_kwargs,
        )
        self._providers[name] = fn
        self._health[name] = ProviderStatus.HEALTHY

    async def execute(self, *args, preferred_providers: Optional[List[str]] = None,
                      fallback_provider: Optional[str] = None, **kwargs) -> ProviderResponse:
        """
        Execute an AI request with multi-provider failover.

        Tries providers in order, falling back if circuit is open or call fails.
        """
        providers = preferred_providers or list(self._providers.keys())
        if not providers:
            return ProviderResponse(success=False, error="No AI providers configured")

        last_error: Optional[str] = None

        for provider_name in providers:
            breaker = self._circuit_breakers.get(provider_name)
            fn = self._providers.get(provider_name)

            if not fn:
                continue
            if breaker and breaker.state == CircuitState.OPEN:
                self._health[provider_name] = ProviderStatus.UNHEALTHY
                logger.warning(f"Circuit open for AI provider '{provider_name}', skipping")
                last_error = f"Circuit breaker open for '{provider_name}'"
                continue

            try:
                start = time.time()

                async def call():
                    if asyncio.iscoroutinefunction(fn):
                        return await fn(*args, **kwargs)
                    return fn(*args, **kwargs)

                result = await asyncio.wait_for(call(), timeout=self.default_timeout)
                latency = (time.time() - start) * 1000

                if breaker:
                    await breaker._on_success()

                self._health[provider_name] = ProviderStatus.HEALTHY

                response = ProviderResponse(
                    success=True,
                    data=result,
                    provider=provider_name,
                    latency_ms=latency,
                )

                # Cache if enabled
                if self.cache_ttl > 0:
                    cache_key = f"{provider_name}:{hash(str(args) + str(kwargs))}"
                    self._cache[cache_key] = response
                    self._cache_times[cache_key] = time.time()

                return response

            except asyncio.TimeoutError:
                self._health[provider_name] = ProviderStatus.DEGRADED
                last_error = f"Provider '{provider_name}' timed out"
                logger.warning(last_error)
                if breaker:
                    await breaker._on_failure()

            except CircuitOpenError as e:
                last_error = str(e)
                self._health[provider_name] = ProviderStatus.UNHEALTHY

            except Exception as e:
                self._health[provider_name] = ProviderStatus.DEGRADED
                last_error = f"Provider '{provider_name}' failed: {e}"
                logger.warning(last_error)
                if breaker:
                    await breaker._on_failure()

        # Try fallback provider
        if fallback_provider and fallback_provider in self._providers:
            try:
                fn = self._providers[fallback_provider]
                result = await fn(*args, **kwargs)
                return ProviderResponse(
                    success=True,
                    data=result,
                    provider=fallback_provider,
                )
            except Exception as e:
                last_error = f"Fallback provider '{fallback_provider}' also failed: {e}"

        return ProviderResponse(
            success=False,
            error=last_error or "All providers exhausted",
        )

    def get_health(self) -> Dict[str, str]:
        return {name: status.value for name, status in self._health.items()}

    def get_circuit_breakers(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: cb.to_dict() for name, cb in self._circuit_breakers.items()
        }

    def reset_provider(self, name: str):
        if name in self._circuit_breakers:
            self._circuit_breakers[name].reset()
            self._health[name] = ProviderStatus.HEALTHY
