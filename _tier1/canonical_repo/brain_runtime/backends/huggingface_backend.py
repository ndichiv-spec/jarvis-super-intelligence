"""Hugging Face brain backend for the JARVIS Brain runtime (spec Part E).

A first-class, named backend targeting a Hugging Face Inference Endpoint
(an OpenAI-compatible inference server).  It reuses the same streaming + chat
HTTP path as the generic :class:`RemoteBrainBackend` — no HTTP duplicated —
and only fixes the provider identity, model default, and credential source
(``HUGGINGFACE_API_KEY`` == ``HF_TOKEN`` == ``JARVIS_HF_TOKEN`` via the
canonical env loader).

Live path:
    JARVIS_BRAIN_BACKEND=huggingface
    HUGGINGFACE_API_KEY (alias of HF_TOKEN / JARVIS_HF_TOKEN) -> Bearer to HF
    JARVIS_HF_INFERENCE_ENDPOINT                                 -> HF inference /v1
    JARVIS_HF_MODEL                                              -> model id on the endpoint

Honesty (spec §13): absent a token or endpoint this backend reports
``available=false``/``OFFLINE`` — it never fabricates availability, and the
HF token is never returned by any Brain API route.
"""

from __future__ import annotations

from brain_runtime.backends.remote import RemoteBrainBackend

__all__ = ["HuggingFaceBrainBackend"]

_HF_DEFAULT_MODEL = "jarvis-brain-qwen3-4b-v1"


class HuggingFaceBrainBackend(RemoteBrainBackend):
    """First-class Hugging Face Inference Endpoint backend for the Brain."""

    backend = "huggingface"
    provider = "hf-inference"

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        retries: int = 2,
        *,
        stream: bool = True,
    ) -> None:
        from brain_runtime.config import BrainConfig

        cfg = BrainConfig() if endpoint is None or api_key is None or model is None else None
        endpoint = endpoint or (cfg.huggingface_endpoint if cfg else "")
        model = model or (cfg.huggingface_model if cfg else _HF_DEFAULT_MODEL)
        api_key = api_key or (cfg.huggingface_api_key if cfg else "")
        super().__init__(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            timeout=timeout,
            retries=retries,
            stream=stream,
        )
        self.backend = "huggingface"
        # Preserve the hf-inference label for provider reports.
        self.provider = "hf-inference"
