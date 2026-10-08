"""NVIDIA-brain backend for the JARVIS Brain runtime (spec Part D).

A thin, named specialization of the OpenAI-compatible :class:`RemoteBrainBackend`
that targets NVIDIA-hosted inference (NIM on the API Catalog, the
``nvcf.nvidia.com`` cloud endpoints, or a self-hosted NIM).  It reuses the
*exact* same streaming + chat HTTP path as the generic remote backend — no
HTTP duplicated — and only fixes the provider identity, model default, and
credential source so the runtime is never tied to Silverwing.

Live path (no local weights):
    JARVIS_BRAIN_BACKEND=nvidia
    JARVIS_NVIDIA_API_KEY / NVIDIA_API_KEY  -> outbound Bearer to NVIDIA
    JARVIS_NVIDIA_ENDPOINT                   -> https://integrate.api.nvidia.com/v1
    JARVIS_NVIDIA_MODEL                      -> nvidia/nemotron-3-ultra-550b-a55b

Honesty (spec §13): if the NVIDIA key/endpoint is absent the backend reports
``available=false``/``OFFLINE`` — it never fabricates health.  The outbound
NVIDIA credential is never returned by any Brain API route.
"""

from __future__ import annotations

from brain_runtime.backends.remote import RemoteBrainBackend
from brain_runtime.generation import BrainGenerationConfig

__all__ = ["NvidiaBrainBackend", "NVIDIA_NIM_ENDPOINT", "NVIDIA_DEFAULT_MODEL"]

NVIDIA_NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


class NvidiaBrainBackend(RemoteBrainBackend):
    """Live NVIDIA NIM/NVCF inference path for the Brain runtime."""

    # Set in __init__ (after super) so provider is authoritative for host.
    backend = "nvidia"
    provider = "nvidia"

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
        endpoint = endpoint or (cfg.nvidia_endpoint if cfg else NVIDIA_NIM_ENDPOINT)
        model = model or (cfg.nvidia_model if cfg else NVIDIA_DEFAULT_MODEL)
        api_key = api_key or (cfg.nvidia_api_key if cfg else "")
        super().__init__(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            timeout=timeout,
            retries=retries,
            stream=stream,
        )
        # Authoritative provider label regardless of host shape.
        self.backend = "nvidia"
        self.provider = "nvidia"
