"""Brain backend interface (framework-independent).

Mirrors ``silverwing_runtime.backends.base.InferenceBackend`` but chat-native:
the Brain serves an OpenAI-compatible ``/v1/chat/completions`` surface, so
backends operate on message lists rather than a bare prompt.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from brain_runtime.generation import BrainGenerationConfig, BrainResult


class BrainBackend(ABC):
    """Abstract generation backend for the JARVIS Brain runtime.

    A ``BrainBackend`` is a *runtime boundary*: the Brain service and FastAPI
    server are written against this protocol, never against a concrete
    implementation (spec Part C).  The next JARVIS training cycle is therefore
    never a platform block — swap the backend in config and the runtime adapts.

    Concrete backends declare:
    * ``backend``         — stable backend name (e.g. ``remote``, ``nvidia``,
      ``huggingface``, ``transformers``, ``brain-stub``).
    * ``provider``        — upstream provider label (e.g. ``nvidia``,
      ``hf-inference``, ``local``, ``stub``); empty when not applicable.
    * ``model_id``        — the model id *actually serving* inference.
    * ``stream_support``  — whether ``stream()`` yields real tokens.
    """

    # Overridden by concrete backends.
    backend: str = ""
    device: str = ""
    model_id: str = ""
    revision: str = ""
    parameters: int = 0
    loaded: bool = False
    provider: str = ""
    # Whether ``stream()`` yields genuine token-by-token SSE chunks.  Backends
    # that only generate a whole answer (stub, local torch) leave this False and
    # the server falls back to a single-content chunk (never simulated per-token
    # chunking of a non-streaming model).
    stream_support: bool = False

    @abstractmethod
    def load(self) -> None:
        """Acquire the model (tokenizers + weights) for ``self.model_id``."""

    @abstractmethod
    def warmup(self, prompt: str) -> str:
        """Run a warmup generation; returns generated text."""

    @abstractmethod
    def generate(self, messages: list[dict], configuration: BrainGenerationConfig) -> BrainResult:
        """Generate a chat completion for ``messages``."""

    def stream(
        self, messages: list[dict], configuration: BrainGenerationConfig
    ):
        """Yield OpenAI-style chunk dicts token-by-token (spec Part O).

        Default implementation: backends that do not advertise
        ``stream_support`` are not streamable.  Remote/NVIDIA/HF backends
        override this to stream genuine SSE tokens from the upstream provider.
        The server checks ``stream_support`` and never calls this for
        non-streaming backends.
        """
        raise NotImplementedError("backend does not support streaming")

    def list_models(self) -> list[dict]:
        """Models discoverable from this backend's upstream (may be empty)."""
        return []

    def close(self) -> None:
        """Optional teardown hook; subclasses may override it."""
        return None
