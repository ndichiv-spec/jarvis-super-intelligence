"""Declared adapter-level capabilities for AWS Bedrock (spec §8)."""

from __future__ import annotations

from ..capabilities import Capability, validate_capabilities

AWS_ADAPTER_CAPABILITIES = validate_capabilities(
    {
        Capability.CHAT,
        Capability.STREAMING,
        Capability.TOOL_CALLING,
        Capability.VISION,
        Capability.EMBEDDINGS,
        Capability.REASONING,
    }
)