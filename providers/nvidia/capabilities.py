"""Declared adapter-level capabilities for NVIDIA NIM (spec §4).

Surface is OpenAI-compatible inference: chat, streaming, tool calling, structured
output (``json_object``), embeddings and reasoning-capable models. Per-model
truth in :mod:`providers.nvidia.models`.
"""

from __future__ import annotations

from ..capabilities import Capability, validate_capabilities

NVIDIA_ADAPTER_CAPABILITIES = validate_capabilities(
    {
        Capability.CHAT,
        Capability.STREAMING,
        Capability.TOOL_CALLING,
        Capability.EMBEDDINGS,
        Capability.STRUCTURED_OUTPUT,
        Capability.REASONING,
    }
)