"""Hugging Face baseline model entries.

These are *deployable* model ids for a configured remote OpenAI-compatible
inference endpoint (spec §9: repo != endpoint). Live discovery comes from the
endpoint's ``/v1/models``.
"""

from __future__ import annotations

from ..models import DeploymentKind, models_from_declared

HF_MODELS = models_from_declared(
    "hf",
    [
        {
            "model": "meta-llama/Llama-3.3-70B-Instruct",
            "name": "Llama 3.3 70B Instruct (HF inference)",
            "deployment": "remote_endpoint",
            "context_length": 131072,
            "capabilities": "chat streaming tool_calling structured_output",
            "cost_class": "medium",
            "latency_class": "medium",
        },
        {
            "model": "deepseek-ai/DeepSeek-R1",
            "name": "DeepSeek R1 (HF inference)",
            "deployment": "remote_endpoint",
            "context_length": 131072,
            "capabilities": "chat streaming reasoning structured_output",
            "cost_class": "medium",
            "latency_class": "high",
        },
        {
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "name": "MiniLM-L6 embeddings (HF inference)",
            "deployment": "remote_endpoint",
            "context_length": 256,
            "capabilities": "embeddings",
            "cost_class": "free",
            "latency_class": "low",
        },
    ],
)