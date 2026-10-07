"""OpenAI provider health probe (spec §7/external honesty).

Health is real: an authenticated ``GET /v1/models`` against the configured
endpoint. A rejected key -> error, an unreachable endpoint -> offline, a reachable
endpoint with zero models listed -> degraded.
"""

from __future__ import annotations

from ..errors import ProviderAuthenticationError, ProviderContractError, ProviderUnavailable
from ..health import HealthStatus, ProviderHealth
from ..http import OpenAICompatibleClient


def openai_health_probe(
    client: OpenAICompatibleClient,
    provider: str = "openai",
) -> ProviderHealth:
    import time

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
            detail=f"authentication rejected: {exc}",
        )
    except ProviderUnavailable as exc:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.OFFLINE,
            detail=str(exc),
        )
    except ProviderContractError as exc:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.OFFLINE,
            detail=str(exc),
        )

    if not model_ids:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.DEGRADED,
            latency_ms=latency,
            endpoint_reachable=True,
            detail="endpoint reachable but /v1/models returned no models",
        )
    return ProviderHealth(
        provider=provider,
        status=HealthStatus.HEALTHY,
        latency_ms=latency,
        endpoint_reachable=True,
        detail=f"{len(model_ids)} models advertised",
        models_found=len(model_ids),
    )