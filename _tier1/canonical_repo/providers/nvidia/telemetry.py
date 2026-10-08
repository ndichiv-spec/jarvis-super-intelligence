"""NVIDIA provider telemetry."""

from __future__ import annotations

from typing import Optional

from ..telemetry import ProviderEvent, ProviderTelemetry, get_telemetry


def nvidia_telemetry() -> ProviderTelemetry:
    return get_telemetry()


def record_nvidia(**kwargs) -> ProviderEvent:
    return get_telemetry().event(provider="nvidia", **kwargs)