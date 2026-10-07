"""Health probe for NeMo Microservices (spec §5).

Returns an honest status — ``UNHEALTHY`` if the API key is missing,
``HEALTHY`` if the endpoint responds, ``UNHEALTHY`` if the request fails.
Never fabricates a healthy status.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..health import HealthStatus, ProviderHealth


def nemo_health_probe(
    http_client: Any = None,
    provider: str = "nemo",
    config: Optional[Any] = None,
) -> ProviderHealth:
    """Probe the NeMo endpoint readiness.

    Parameters
    ----------
    http_client
        Injectable async/sync HTTP client for tests.  Must have an
        ``async def get(url, **kwargs)`` method and a ``sync_get`` fallback.
    provider
        Provider identifier (default "nemo").
    config
        NeMoConfig instance.  If ``None``, the probe reports UNCONFIGURED.
    """
    if config is None:
        return ProviderHealth(
            provider=provider, status=HealthStatus.UNCONFIGURED,
        )
    if not getattr(config, "configured", False):
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.UNCONFIGURED,
            detail="JARVIS_NEMO_API_KEY not set",
        )
    if http_client is None:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.OFFLINE,
            detail="no http client available to probe endpoint",
        )
    # Build health URL: /v1/health or /v1/models
    base = getattr(config, "endpoint", "https://api.nvidia.com/nemo/v1")
    health_url = f"{base.rstrip('/')}/v1/health"

    start = time.time()
    try:
        # Try synchronous first, fall back to async.
        if hasattr(http_client, "sync_get"):
            resp = http_client.sync_get(health_url, timeout=getattr(config, "timeout", 10.0))
        elif hasattr(http_client, "get") and not hasattr(http_client.get, "__call__"):
            resp = http_client.get(health_url, timeout=getattr(config, "timeout", 10.0))
        else:
            # Assume async client
            import asyncio
            resp = asyncio.run(http_client.get(health_url, timeout=getattr(config, "timeout", 10.0)))
        latency_ms = round((time.time() - start) * 1000, 1)
        if hasattr(resp, "status_code") and resp.status_code == 200:
            return ProviderHealth(
                provider=provider,
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                models_found=1,  # health endpoint responded
                detail="NeMo endpoint ready",
            )
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.OFFLINE,
            latency_ms=latency_ms,
            detail=f"HTTP {resp.status_code if hasattr(resp, 'status_code') else 'unknown'}",
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((time.time() - start) * 1000, 1)
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.OFFLINE,
            latency_ms=latency_ms,
            detail=f"probe error: {exc!r}",
        )


