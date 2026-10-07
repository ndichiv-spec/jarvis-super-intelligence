"""Declared adapter-level capabilities for Google Vertex / Gemini (spec §7).

Gemini is multimodal (vision + audio), supports streaming, tool calling,
structured output, reasoning traces and embeddings.
"""

from __future__ import annotations

from ..capabilities import Capability, validate_capabilities

GOOGLE_ADAPTER_CAPABILITIES = validate_capabilities(
    {
        Capability.CHAT,
        Capability.STREAMING,
        Capability.TOOL_CALLING,
        Capability.VISION,
        Capability.AUDIO,
        Capability.EMBEDDINGS,
        Capability.STRUCTURED_OUTPUT,
        Capability.REASONING,
    }
)