"""Brain generation primitives (spec section 13 / §23).

Lightweight, framework-independent request/result types used by the Brain
backends and the FastAPI server.  Modeled on ``silverwing_runtime.generation``
but chat-native (Qwen3 chat template) rather than prompt-native.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrainGenerationConfig:
    """Per-request generation parameters (OpenAI-compatible surface)."""

    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192
    top_p: float = 0.9
    top_k: int | None = None
    repetition_penalty: float = 1.0
    stream: bool = False


@dataclass
class BrainResult:
    """Normalized result returned by a Brain backend."""

    text: str = ""
    model: str = ""
    revision: str = ""
    finish_reason: str = "stop"
    tokens_input: int = 0
    tokens_generated: int = 0
    latency_ms: float = 0.0
    device: str = "cpu"
    backend: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
