"""OpenAI provider adapter (spec §6).

Configuration
-------------
``JARVIS_OPENAI_API_KEY`` (or ``OPENAI_API_KEY``) and ``JARVIS_OPENAI_MODEL``.
No default model is assumed — the adapter reads the live ``/v1/models`` list for
discovery and refuses to chat until a model is configured (spec §73: don't
fabricate model availability).

Capabilities are declared, never assumed. The adapter declares the *surface* it
implements (chat, responses, streaming, tool calling, structured output,
embeddings, web/file search, vision, audio, reasoning, batch, fine-tuning,
evaluation) of OpenAI's platform; per-model capability truth lives in
:mod:`providers.openai.models`.
"""

from .capabilities import OPENAI_ADAPTER_CAPABILITIES
from .client import OpenAIAdapter
from .config import OpenAIConfig
from .health import openai_health_probe
from .models import OPENAI_MODELS

MODELS = OPENAI_MODELS
CAPABILITIES = OPENAI_ADAPTER_CAPABILITIES
ADAPTER = OpenAIAdapter

__all__ = [
    "ADAPTER",
    "CAPABILITIES",
    "MODELS",
    "OpenAIAdapter",
    "OpenAIConfig",
    "openai_health_probe",
]