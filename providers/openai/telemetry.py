"""OpenAI provider telemetry.

Thin per-provider recorder over the fabric's shared telemetry so the Provider
Center / Observatory can ask for "openai metrics" without reaching into internals.
"""

from __future__ import annotations

from typing import Optional

from ..telemetry import ProviderEvent, ProviderTelemetry, get_telemetry


def openai_telemetry() -> ProviderTelemetry:
    return get_telemetry()


def record_openai(
    kind: str = "request",
    model: str = "",
    request_id: str = "",
    latency_ms: Optional[float] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    error: str = "",
    status: str = "",
    **kwargs,
) -> ProviderEvent:
    return get_telemetry().event(
        provider="openai",
        model=model,
        request_id=request_id,
        kind=kind,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        error=error,
        status=status,
        **kwargs,
    )