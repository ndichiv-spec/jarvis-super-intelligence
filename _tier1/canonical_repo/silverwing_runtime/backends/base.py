"""Backend interface (framework-independent)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from silverwing_runtime.generation import GenerationRequest, GenerationResult


class InferenceBackend(ABC):
    """Abstract generation backend."""

    @abstractmethod
    def warmup(self, prompt: str) -> str:
        """Run a warmup generation; returns generated text."""

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate a completion for ``request.prompt``."""

    def close(self) -> None:
        """Optional teardown hook; subclasses may override it."""
        return None