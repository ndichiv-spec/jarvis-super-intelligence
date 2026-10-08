"""EchoBackend — explicit development/test backend only.

Activated ONLY via ``SILVERWING_BACKEND=echo``.  It never presents itself as
real model output (every response is visibly marked ``[sw-echo]``) and is
never used as a silent fallback when the torch backend fails.
"""

from __future__ import annotations

from silverwing_runtime.backends.base import InferenceBackend
from silverwing_runtime.generation import GenerationRequest, GenerationResult


class EchoBackend(InferenceBackend):
    """Deterministic backend used only in tests / development modes."""

    def __init__(self, marker: str = "sw-echo"):
        self.marker = marker
        self.device = "n/a"
        self.backend = "echo"

    def warmup(self, _prompt: str) -> str:
        return "warmup-ok"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        text = f"[{self.marker}] {request.prompt}"
        return GenerationResult(
            text=text,
            finish_reason="stop",
            tokens_generated=0,
            latency_ms=0.5,
            metadata={"backend": "echo", "device": "n/a"},
        )