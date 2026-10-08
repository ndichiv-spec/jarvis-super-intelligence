"""Brain backends package.

Concrete backends:
  * ``transformers_backend.TransformersBackend`` — real Qwen3-4B inference (local).
  * ``remote.RemoteBrainBackend`` — delegates to an OpenAI-compatible remote
    endpoint (e.g. Hugging Face Inference Endpoints).
  * ``nvidia_backend.NvidiaBrainBackend`` — named NVIDIA NIM/NVCF path
    (spec Part D); reuses the OpenAI-compatible HTTP layer.
  * ``huggingface_backend.HuggingFaceBrainBackend`` — named Hugging Face
    inference-endpoint path (spec Part E); reuses the OpenAI-compatible HTTP
    layer.  Token resolved via the canonical ``HUGGINGFACE_API_KEY`` alias.
  * ``stub.StubBackend`` — explicitly-labeled dev stub (``JARVIS_BRAIN_BACKEND=stub``).
"""

from __future__ import annotations

from brain_runtime.backends.base import BrainBackend
from brain_runtime.backends.remote import RemoteBrainBackend
from brain_runtime.backends.stub import StubBackend
from brain_runtime.backends.transformers_backend import TransformersBackend
from brain_runtime.backends.nvidia_backend import NvidiaBrainBackend
from brain_runtime.backends.huggingface_backend import HuggingFaceBrainBackend

__all__ = [
    "BrainBackend",
    "RemoteBrainBackend",
    "NvidiaBrainBackend",
    "HuggingFaceBrainBackend",
    "TransformersBackend",
    "StubBackend",
]
