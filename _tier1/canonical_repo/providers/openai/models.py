"""OpenAI model catalog (baseline declarative entries).

The live source of truth at runtime is ``GET /v1/models`` on the configured
endpoint; this static catalog only provides the fabric with honest *baseline*
metadata (capability, cost class, privacy, latency) for routing when discovery is
unavailable. Model ids here are real OpenAI platform families; do not invent new
ones without evidence (spec §73).
"""

from __future__ import annotations

from ..models import DeploymentKind, models_from_declared

OPENAI_MODELS = models_from_declared(
    "openai",
    [
        {
            "model": "gpt-5",
            "name": "OpenAI GPT-5 (reasoning flagship)",
            "context_length": 400000,
            "capabilities": "chat responses streaming tool_calling structured_output reasoning web_search file_search computer_use",
            "cost_class": "high",
            "latency_class": "medium",
        },
        {
            "model": "gpt-5-mini",
            "name": "OpenAI GPT-5 mini (fast, lower cost)",
            "context_length": 400000,
            "capabilities": "chat responses streaming tool_calling structured_output reasoning web_search file_search",
            "cost_class": "low",
            "latency_class": "low",
        },
        {
            "model": "gpt-4o",
            "name": "OpenAI GPT-4o (multimodal)",
            "context_length": 128000,
            "capabilities": "chat responses streaming tool_calling vision structured_output web_search file_search",
            "cost_class": "medium",
            "latency_class": "low",
        },
        {
            "model": "gpt-4o-mini",
            "name": "OpenAI GPT-4o mini (cheap multimodal)",
            "context_length": 128000,
            "capabilities": "chat responses streaming tool_calling vision structured_output web_search",
            "cost_class": "low",
            "latency_class": "low",
            "aliases": ("gpt-4o-mini",),
        },
        {
            "model": "o3",
            "name": "OpenAI o3 (deep reasoning)",
            "context_length": 200000,
            "capabilities": "chat streaming tool_calling structured_output reasoning",
            "cost_class": "high",
            "latency_class": "high",
        },
        {
            "model": "o3-mini",
            "name": "OpenAI o3 mini (reasoning, faster)",
            "context_length": 200000,
            "capabilities": "chat streaming tool_calling structured_output reasoning",
            "cost_class": "low",
            "latency_class": "medium",
        },
        {
            "model": "text-embedding-3-small",
            "name": "OpenAI text-embedding-3-small",
            "context_length": 8191,
            "capabilities": "embeddings",
            "cost_class": "low",
            "latency_class": "low",
        },
        {
            "model": "text-embedding-3-large",
            "name": "OpenAI text-embedding-3-large",
            "context_length": 8191,
            "capabilities": "embeddings",
            "cost_class": "low",
            "latency_class": "low",
        },
    ],
)