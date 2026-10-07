"""JARVIS Brain v1 runtime.

A dedicated, first-class model runtime for the JARVIS Brain (Qwen3-4B) with its
own OpenAI-compatible endpoint on ``http://127.0.0.1:8011/v1``, separate from the
Silverwing runtime on :8010 (spec section 1).

The runtime is model-provider agnostic: the same server architecture serves both
the Qwen3-4B Base and the Qwen3-4B SFT candidate; the active model is selected
by ``JARVIS_BRAIN_MODEL`` (spec section 21-22), not by code paths.

Two backends exist:

* ``TransformersBackend`` — the real, production path. Loads Qwen3-4B (Base or
  SFT) from Hugging Face via ``transformers``. Requires a GPU host; on the JARVIS
  PC (8 GB RAM, CPU-only, weights not cached) this cannot load and the server
  refuses to report production health.
* ``StubBackend`` — an explicitly-LABELED development backend (activated only via
  ``JARVIS_BRAIN_BACKEND=stub``). It never presents responses as real Qwen3
  output and never reports ``healthy=true`` / ``available=true``.

Run standalone::

    python -m brain_runtime.server          # real model (transformers)
    JARVIS_BRAIN_BACKEND=stub python -m brain_runtime.server   # dev stub
"""

from __future__ import annotations

__all__ = ["BrainConfig", "BrainCatalog", "create_app"]

from .config import BrainConfig
from .model_registry import BrainCatalog, BrainModel
