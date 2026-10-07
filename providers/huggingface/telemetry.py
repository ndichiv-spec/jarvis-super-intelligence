"""Hugging Face provider telemetry."""

from __future__ import annotations

from ..telemetry import ProviderEvent, ProviderTelemetry, get_telemetry


def hf_telemetry() -> ProviderTelemetry:
    return get_telemetry()


def record_hf(**kwargs) -> ProviderEvent:
    return get_telemetry().event(provider="hf", **kwargs)
