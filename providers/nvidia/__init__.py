"""NVIDIA provider adapter (spec §4, §5).

Supports NVIDIA hosted inference, self-hosted NVIDIA NIM (OpenAI-compatible
``/v1/chat/completions``, ``/v1/responses``, ``/v1/models``, readiness/metrics),
and future NVIDIA cloud deployments. The endpoint is **never assumed local** —
``JARVIS_NVIDIA_ENDPOINT`` controls it (default NVIDIA-hosted API). NeMo
Microservices are kept as an optional remote engineering service (Phase 5), not a
local requirement.
"""

from .capabilities import NVIDIA_ADAPTER_CAPABILITIES
from .client import NvidiaAdapter
from .config import NvidiaConfig
from .health import nvidia_health_probe
from .models import NVIDIA_MODELS

MODELS = NVIDIA_MODELS
CAPABILITIES = NVIDIA_ADAPTER_CAPABILITIES
ADAPTER = NvidiaAdapter

__all__ = [
    "ADAPTER",
    "CAPABILITIES",
    "MODELS",
    "NvidiaAdapter",
    "NvidiaConfig",
    "nvidia_health_probe",
]