"""Google provider telemetry."""

from __future__ import annotations

from ..telemetry import ProviderEvent, ProviderTelemetry, get_telemetry


def google_telemetry() -> ProviderTelemetry:
    return get_telemetry()


def record_google(**kwargs) -> ProviderEvent:
    return get_telemetry().event(provider="google", **kwargs)