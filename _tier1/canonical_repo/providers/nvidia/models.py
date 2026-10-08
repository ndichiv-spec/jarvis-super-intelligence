"""NVIDIA NIM model catalog (baseline; live truth via ``/v1/models``).

Ids reference real NVIDIA NIM models confirmed against the hosted catalog
(``GET https://integrate.api.nvidia.com/v1/models``).  Every id in this baseline
exists on the public endpoint today; routing uses this baseline when live
discovery is unavailable, and ``NvidiaAdapter._build_models`` reconciles it
against a live ``/v1/models`` call at runtime so the catalog never advertises a
model that is not actually servable.
"""

from __future__ import annotations

from ..models import models_from_declared

# The documented JARVIS default NVIDIA NIM chat model.  Verified invocable on
# the hosted catalog with a standard NVIDIA key (the popular llama-3.1 /
# nemotron-4 ids are advertised but return 404 "Function not found" on this
# account class).  Never overridden by code — ``JARVIS_NVIDIA_MODEL`` /
# ``JARVIS_BRAIN_MODEL`` may still select a different discovered model.
NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

NVIDIA_MODELS = models_from_declared(
    "nvidia",
    [
        {
            "model": NVIDIA_DEFAULT_MODEL,
            "name": "Nemotron 3 Ultra 550B A55B",
            "context_length": 131072,
            "capabilities": "chat streaming tool_calling structured_output reasoning",
            "deployment": "hosted",
            "cost_class": "high",
            "latency_class": "medium",
            "aliases": ("nvidia:nim:nvidia/nemotron-3-ultra-550b-a55b",),
        },
        {
            "model": "nvidia/llama-3.1-nemotron-70b-instruct",
            "name": "Llama 3.1 Nemotron 70B Instruct",
            "context_length": 131072,
            "capabilities": "chat streaming tool_calling structured_output reasoning",
            "deployment": "hosted",
            "cost_class": "medium",
            "latency_class": "low",
        },
        {
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "name": "Nemotron 3 Super 120B A12B",
            "context_length": 131072,
            "capabilities": "chat streaming tool_calling structured_output reasoning",
            "cost_class": "medium",
            "latency_class": "low",
        },
        {
            "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "name": "Nemotron 3 Nano Omni 30B A3B Reasoning",
            "context_length": 131072,
            "capabilities": "chat streaming reasoning",
            "cost_class": "low",
            "latency_class": "low",
        },
        {
            "model": "mistralai/mistral-nemotron",
            "name": "Mistral Nemotron",
            "context_length": 131072,
            "capabilities": "chat streaming",
            "cost_class": "medium",
            "latency_class": "low",
        },
        {
            "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "name": "Nemotron 3.5 Lightning 30B A3B",
            "context_length": 131072,
            "capabilities": "chat streaming tool_calling structured_output reasoning",
            "cost_class": "low",
            "latency_class": "low",
        },
        {
            "model": "deepseek-ai/deepseek-v4.1-flash",
            "name": "DeepSeek V4.1 Flash",
            "context_length": 131072,
            "capabilities": "chat streaming tool_calling structured_output reasoning",
            "cost_class": "low",
            "latency_class": "low",
        },
        {
            "model": "nvidia/nemotron-3-embed-1b",
            "name": "Nemotron 3 Embed 1B (embeddings)",
            "context_length": 4096,
            "capabilities": "embeddings",
            "cost_class": "low",
            "latency_class": "medium",
        },
    ],
)