"""AWS Bedrock health probe.

Calls ``list_foundation_models`` when credentials/region allow; reports honest
status otherwise (missing boto3 -> unconfigured, access denied -> error).
"""

from __future__ import annotations

from typing import Optional

from .clients import BedrockClients
from ..health import HealthStatus, ProviderHealth


def aws_health_probe(
    clients: Optional[BedrockClients],
    provider: str = "aws",
) -> ProviderHealth:
    import time

    if clients is None:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.UNCONFIGURED,
            detail="boto3 not importable or no region configured",
        )
    t0 = time.monotonic()
    try:
        summary = clients.list_models()
        latency = (time.monotonic() - t0) * 1000.0
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "credential" in lowered or "access" in lowered or "unauthorized" in lowered:
            return ProviderHealth(
                provider=provider, status=HealthStatus.ERROR,
                detail=f"credentials rejected: {message[:200]}",
            )
        return ProviderHealth(
            provider=provider, status=HealthStatus.OFFLINE, detail=message[:200]
        )
    if not summary:
        return ProviderHealth(
            provider=provider,
            status=HealthStatus.DEGRADED,
            latency_ms=latency,
            detail="reachable but no foundation models listed",
        )
    return ProviderHealth(
        provider=provider,
        status=HealthStatus.HEALTHY,
        latency_ms=latency,
        detail=f"{len(summary)} foundation models",
        models_found=len(summary),
    )