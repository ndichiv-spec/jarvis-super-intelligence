"""Provider health model for the JARVIS Provider Fabric (spec §7, §31).

A provider is *healthy* only when a real probe against its real endpoint succeeds.
Everything else is reported honestly (``unconfigured``, ``offline``, ``error``,
``unknown``). The fabric never assumes availability; ``HealthCache`` attaches a TTL
so probes are bounded.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import Enum
from threading import Lock
from typing import Callable, Optional


class HealthStatus(str, Enum):
    # Spec §13 health states:
    UNCONFIGURED = "unconfigured"  # no credentials/endpoint configured
    UNKNOWN = "unknown"  # not probed yet
    AUTHENTICATION_FAILED = "authentication_failed"  # key present but rejected by provider
    OFFLINE = "offline"  # unreachable / no response
    UNAVAILABLE = "unavailable"  # reachable but explicitly reports unavailable
    DEGRADED = "degraded"  # reachable but partial (e.g. no usable models)
    HEALTHY = "healthy"  # real probe succeeded
    ERROR = "error"  # probe failed with an exception (unexpected)
    FORBIDDEN = "forbidden"  # HTTP 403, token valid but access denied to a resource
    RATE_LIMITED = "rate_limited"  # HTTP 429, API rate limit exceeded
    TIMEOUT = "timeout"  # request timed out, network or server latency issue

    @property
    def ok(self) -> bool:
        """True for states that can still serve requests (healthy or degraded)."""
        return self is HealthStatus.HEALTHY or self is HealthStatus.DEGRADED


@dataclass
class ProviderHealth:
    provider: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    checked_at: float = field(default_factory=time.time)
    detail: str = ""
    models_found: int = 0
    endpoint_reachable: bool = False
    credential_authorized: Optional[bool] = None
    inference_verified: bool = False

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "ok": self.status.ok,
            "latency_ms": self.latency_ms,
            "checked_at": self.checked_at,
            "detail": self.detail,
            "models_found": self.models_found,
            "endpoint_reachable": self.endpoint_reachable,
            "credential_authorized": self.credential_authorized,
            "inference_verified": self.inference_verified,
        }

    @property
    def is_configured(self) -> bool:
        return self.status is not HealthStatus.UNCONFIGURED

    @property
    def is_authenticated(self) -> bool:
        """True iff the provider is reachable and credentials were accepted."""
        if self.credential_authorized is not None:
            return self.credential_authorized
        return self.status in (
            HealthStatus.HEALTHY, HealthStatus.DEGRADED,
        )

    @property
    def is_healthy(self) -> bool:
        """True iff the provider is healthy enough to serve requests."""
        return self.status.ok

    @property
    def is_ready(self) -> bool:
        """True iff the provider is fully ready (healthy + has models)."""
        return self.is_healthy and self.models_found > 0

    @property
    def is_inference_ready(self) -> bool:
        """True iff a real inference succeeded and models are available."""
        return self.inference_verified and self.models_found > 0


_INFERENCE_RESULTS: dict[str, ProviderHealth] = {}
_INFERENCE_RESULTS_LOCK = Lock()


def record_inference_result(
    provider: str,
    status: HealthStatus,
    *,
    models_found: int = 0,
    detail: str = "",
) -> None:
    with _INFERENCE_RESULTS_LOCK:
        current = _INFERENCE_RESULTS.get(provider)
        if current is None:
            current = ProviderHealth(provider=provider, status=HealthStatus.UNKNOWN)
        _INFERENCE_RESULTS[provider] = replace(
            current,
            provider=provider,
            status=status,
            checked_at=time.time(),
            detail=detail or current.detail,
            models_found=max(current.models_found, models_found),
            endpoint_reachable=True,
            credential_authorized=(
                True if status is HealthStatus.HEALTHY
                else False if status is HealthStatus.AUTHENTICATION_FAILED
                else None
            ),
            inference_verified=status is HealthStatus.HEALTHY,
        )


def get_inference_result(provider: str) -> Optional[ProviderHealth]:
    with _INFERENCE_RESULTS_LOCK:
        current = _INFERENCE_RESULTS.get(provider)
        return replace(current) if current is not None else None


class HealthCache:
    """TTL cache around a provider probe callable."""

    def __init__(self, provider: str, probe: Callable[[], ProviderHealth], ttl: float = 30.0):
        self.provider = provider
        self._probe = probe
        self.ttl = ttl
        self._value: Optional[ProviderHealth] = None
        self._lock = Lock()

    def get(self, force: bool = False) -> ProviderHealth:
        now = time.time()
        with self._lock:
            if self._value is None or force or (now - self._value.checked_at) > self.ttl:
                try:
                    self._value = self._probe()
                except Exception as exc:  # never let a probe crash routing
                    self._value = ProviderHealth(
                        provider=self.provider,
                        status=HealthStatus.ERROR,
                        detail=f"{exc.__class__.__name__}: {exc}",
                    )
            return self._value

    def set(self, value: ProviderHealth) -> None:
        with self._lock:
            self._value = value

    def invalidate(self) -> None:
        with self._lock:
            self._value = None
