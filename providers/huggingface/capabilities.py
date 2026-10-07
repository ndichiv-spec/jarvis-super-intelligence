"""Declared adapter-level capabilities for Hugging Face (spec §9).

Registry/dataset/artifact operations need no LLM capability; inference
capabilities only apply to a configured remote inference endpoint. The adapter
itself is honest that these are endpoint-provided, not repo-provided.
"""

from __future__ import annotations

from ..capabilities import Capability, validate_capabilities

HF_ADAPTER_CAPABILITIES = validate_capabilities(
    {
        Capability.CHAT,
        Capability.STREAMING,
        Capability.TOOL_CALLING,
        Capability.EMBEDDINGS,
        Capability.STRUCTURED_OUTPUT,
    }
)