"""Google provider adapter (spec §7).

Two distinct layers:
* *Identity* — Google OIDC (Phase 2; lives in the unified identity layer, not here).
* *AI* — Vertex AI / Gemini via ``google.genai`` (installed), configured with an
  API key (``JARVIS_GOOGLE_API_KEY``) or Vertex project+location
  (``JARVIS_VERTEX_PROJECT_ID``/``JARVIS_VERTEX_LOCATION``). Workload identity for
  external clouds is Phase 2 (§54/55).

The adapter is testable via an injected ``models_api`` object.
"""

from .capabilities import GOOGLE_ADAPTER_CAPABILITIES
from .client import GoogleAdapter
from .config import GoogleConfig
from .health import google_health_probe
from .models import GOOGLE_MODELS

MODELS = GOOGLE_MODELS
CAPABILITIES = GOOGLE_ADAPTER_CAPABILITIES
ADAPTER = GoogleAdapter

__all__ = [
    "ADAPTER",
    "CAPABILITIES",
    "MODELS",
    "GoogleAdapter",
    "GoogleConfig",
    "google_health_probe",
]