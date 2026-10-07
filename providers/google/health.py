"""Google health probe (spec §7).

Uses the configured GenAI surface's model list when available; reports
``UNKNOWN`` with a clear detail rather than fabricating availability when the
surface cannot be reached.
"""

from __future__ import annotations

from typing import Optional

from ..errors import ProviderAuthenticationError, ProviderUnavailable
from ..health import HealthStatus, ProviderHealth
from .models_api import GoogleModelsAPI


def google_health_probe(
    models_api: Optional[GoogleModelsAPI],
    provider: str = "google",
) -> ProviderHealth:
    import time

    if models_api is None:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.UNCONFIGURED,
            detail="no google.genai surface configured (api key or vertex project/location)",
        )
    t0 = time.monotonic()
    try:
        names = models_api.list_models()
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
        return ProviderHealth(provider=provider, status=HealthStatus.OFFLINE, detail=str(exc))

    if not names:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.DEGRADED,
            latency_ms=latency,
            endpoint_reachable=True,
            detail="surface reachable but no models listed",
        )
    return ProviderHealth(
        provider=provider,
        status=HealthStatus.HEALTHY,
        latency_ms=latency,
        endpoint_reachable=True,
        detail=f"{len(names)} models advertised",
        models_found=len(names),
    )