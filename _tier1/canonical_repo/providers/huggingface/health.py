"""Hugging Face health probe (spec §9).

Inference health only when a remote endpoint is configured (probed like any
OpenAI-compatible surface). Otherwise reported as registry-configured with no
inference — never assumed healthy.
"""

from __future__ import annotations

from typing import Optional

from ..errors import ProviderAuthenticationError, ProviderContractError, ProviderUnavailable
from ..health import HealthStatus, ProviderHealth
from ..http import OpenAICompatibleClient


def hf_health_probe(
    client: Optional[OpenAICompatibleClient],
    provider: str = "hf",
    detail: str = "",
) -> ProviderHealth:
    import time

    if client is None:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.UNKNOWN,
            detail=detail or "registry role configured; no inference endpoint",
        )

    t0 = time.monotonic()
    try:
        model_ids = client.list_models()
        latency = (time.monotonic() - t0) * 1000.0
    except ProviderAuthenticationError as exc:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.AUTHENTICATION_FAILED,
            endpoint_reachable=True,
            credential_authorized=False,
            detail=f"inference endpoint auth rejected: {exc}",
        )
    except ProviderUnavailable as exc:
        return ProviderHealth(
            provider=provider, status=HealthStatus.OFFLINE,
            detail=f"inference endpoint unreachable: {exc}",
        )
    except ProviderContractError as exc:
        return ProviderHealth(
            provider=provider, status=HealthStatus.OFFLINE,
            detail=f"inference endpoint malformed: {exc}",
        )

    if not model_ids:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.DEGRADED,
            latency_ms=latency,
            endpoint_reachable=True,
            detail="inference endpoint reachable but no models listed",
        )
    return ProviderHealth(
        provider=provider,
        status=HealthStatus.HEALTHY,
        latency_ms=latency,
        detail=f"inference endpoint: {len(model_ids)} models advertised",
        models_found=len(model_ids),
    )