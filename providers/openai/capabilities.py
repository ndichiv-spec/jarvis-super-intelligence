"""Declared adapter-level capabilities for the OpenAI provider.

This is a *surface* declaration (what the OpenAI platform exposes). Per-model
capability truth is in :mod:`providers.openai.models`. ``validate_capabilities``
guarantees these names exist before registration.
"""

from __future__ import annotations

from ..capabilities import Capability, validate_capabilities

OPENAI_ADAPTER_CAPABILITIES = validate_capabilities(
    {
        Capability.CHAT,
        Capability.RESPONSES,
        Capability.STREAMING,
        Capability.TOOL_CALLING,
        Capability.VISION,
        Capability.AUDIO,
        Capability.EMBEDDINGS,
        Capability.STRUCTURED_OUTPUT,
        Capability.REASONING,
        Capability.BATCH,
        Capability.FINE_TUNING,
        Capability.EVALUATION,
        Capability.WEB_SEARCH,
        Capability.FILE_SEARCH,
        Capability.COMPUTER_USE,
    }
)