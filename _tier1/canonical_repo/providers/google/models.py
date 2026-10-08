"""Google Gemini/Vertex model catalog (baseline declarative entries).

Live model discovery comes from the configured Vertex/GenAI surface; this is the
honest baseline for routing. Model ids are real Gemini families.
"""

from __future__ import annotations

from ..models import models_from_declared

GOOGLE_MODELS = models_from_declared(
    "google",
    [
        {
            "model": "gemini-2.5-flash",
            "name": "Gemini 2.5 Flash",
            "context_length": 1000000,
            "capabilities": "chat streaming tool_calling vision audio structured_output reasoning embeddings",
            "cost_class": "low",
            "latency_class": "low",
        },
        {
            "model": "gemini-2.0-flash",
            "name": "Gemini 2.0 Flash (fast multimodal)",
            "context_length": 1000000,
            "capabilities": "chat streaming tool_calling vision audio structured_output embeddings",
            "cost_class": "low",
            "latency_class": "low",
        },
        {
            "model": "gemini-2.5-pro",
            "name": "Gemini 2.5 Pro (deprecated - listed for routing fallbacks)",
            "context_length": 1000000,
            "capabilities": "chat streaming tool_calling vision audio structured_output reasoning embeddings",
            "cost_class": "medium",
            "latency_class": "medium",
        },
        {
            "model": "text-embedding-004",
            "name": "Gemini text embeddings",
            "context_length": 2048,
            "capabilities": "embeddings",
            "cost_class": "low",
            "latency_class": "low",
        },
    ],
)