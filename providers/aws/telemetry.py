"""AWS provider telemetry."""

from __future__ import annotations

from ..telemetry import ProviderEvent, ProviderTelemetry, get_telemetry


def aws_telemetry() -> ProviderTelemetry:
    return get_telemetry()


def record_aws(**kwargs) -> ProviderEvent:
    return get_telemetry().event(provider="aws", **kwargs)