"""Hugging Face provider adapter (spec §9).

Role split, never conflated:
* *registry/dataset/artifact* role — model, dataset and adapter metadata lookups
  against ``huggingface.co/api``;
* *inference* — only when a remote OpenAI-compatible inference endpoint is
  configured (``JARVIS_HF_INFERENCE_ENDPOINT``). A HF repo is **not** an inference
  endpoint; the adapter accepts any valid remote endpoint (spec §9).
"""

from .capabilities import HF_ADAPTER_CAPABILITIES
from .client import HuggingFaceAdapter
from .config import HuggingFaceConfig
from .health import hf_health_probe
from .hub import (
    HfModelInfo,
    HubError,
    capabilities_for_pipeline,
    discover_models,
    hf_auth_probe,
    whoami_token,
)
from .models import HF_MODELS
from .telemetry import hf_telemetry, record_hf

MODELS = HF_MODELS
CAPABILITIES = HF_ADAPTER_CAPABILITIES
ADAPTER = HuggingFaceAdapter

__all__ = [
    "ADAPTER",
    "CAPABILITIES",
    "MODELS",
    "HF_MODELS",
    "HuggingFaceAdapter",
    "HuggingFaceConfig",
    "HfModelInfo",
    "HubError",
    "capabilities_for_pipeline",
    "discover_models",
    "hf_auth_probe",
    "hf_health_probe",
    "hf_telemetry",
    "record_hf",
    "whoami_token",
]