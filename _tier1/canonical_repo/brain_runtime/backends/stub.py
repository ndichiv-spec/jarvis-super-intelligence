"""Explicitly-LABELED development stub for the JARVIS Brain runtime.

Activated ONLY via ``JARVIS_BRAIN_BACKEND=stub``.  It is NOT a silent fallback:
if the real ``TransformersBackend`` cannot load the Qwen3-4B weights (e.g. on
the JARVIS PC, which has no GPU and insufficient RAM for a 4 B-parameter
model), the server must be explicitly started in ``stub`` mode.  The stub:

* still enforces bearer-token authentication (real key check), so "invalid key"
  / "missing key" / "malformed authorization" are tested exactly as in
  production;
* NEVER presents its output as real Qwen3 inference — every reply is visibly
  prefixed ``[brain-stub]``;
* NEVER reports production health — ``/health`` returns ``stub=true`` and
  ``production_health=false`` / ``available=false``, so the platform gateway
  treats the Brain as unavailable and honest-falls-back to Silverwing.

This mirrors ``silverwing_runtime.backends.echo.EchoBackend`` (which is similarly
marked ``sw-echo`` and never masquerades as the torch backend).
"""

from __future__ import annotations

from brain_runtime.backends.base import BrainBackend
from brain_runtime.generation import BrainGenerationConfig, BrainResult


class StubBackend(BrainBackend):
    """Deterministic development backend; explicitly labeled, never production."""

    def __init__(self, model_id: str = "", revision: str = "") -> None:
        self.backend = "brain-stub"
        self.device = "cpu"
        self.model_id = model_id or "jarvis-brain-qwen3-4b-v1"
        self.revision = revision or "stub"
        self.parameters = 0
        self.loaded = True  # the stub itself is "loaded"
        self._warmup_done = False

    def load(self) -> None:
        # Nothing to load; the stub is in-memory.  No real weights are used.
        return None

    def warmup(self, prompt: str) -> str:
        self._warmup_done = True
        return "warmup-ok"

    def generate(self, messages: list[dict], configuration: BrainGenerationConfig) -> BrainResult:
        # Reconstruct a compact view of the conversation for the stub reply.
        last = ""
        if messages:
            last = str(messages[-1].get("content", ""))
        text = f"[brain-stub] {last}" if last else "[brain-stub] (no input)"
        return BrainResult(
            text=text,
            model=self.model_id,
            revision=self.revision,
            finish_reason="stop",
            tokens_input=sum(len(str(m.get("content", ""))) for m in messages),
            tokens_generated=0,
            latency_ms=0.5,
            device=self.device,
            backend=self.backend,
            metadata={
                "backend": self.backend,
                "device": self.device,
                "stub": True,
                "note": "JARVIS_BRAIN_BACKEND=stub development stub; not real Qwen3 inference",
            },
        )

    def close(self) -> None:
        return None
