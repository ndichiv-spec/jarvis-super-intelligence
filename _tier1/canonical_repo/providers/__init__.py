"""JARVIS Provider Fabric (Phase 1).

The multi-provider intelligence fabric. Turns external models (OpenAI, NVIDIA NIM,
Google Vertex/Gemini, AWS Bedrock, Hugging Face, local brains) into *replaceable
neural engines* behind one JARVIS-facing abstraction.

Core guarantees (spec §3, §70, §72):

* **Capability honesty** — every :class:`~providers.base.ProviderAdapter` declares
  exactly the capabilities it implements (:class:`providers.capabilities.Capability`).
  An adapter that does not declare a capability raises ``UnsupportedCapability``
  rather than faking it.
* **Secret isolation** — provider credentials are never placed in the model context;
  they are read through :class:`providers.secrets.SecretManager` and guarded by
  ``assert_no_secrets`` (spec §16, §69).
* **No hard-coded winner** — routing order is policy-driven and configurable
  (spec §35); cost is ``None`` when unknown (spec §34), availability is probed,
  never assumed (spec §73).

Layout mirrors the spec §4 contract: each provider lives in ``providers/<name>/``
with ``client | config | health | capabilities | models | telemetry``.
"""

from __future__ import annotations

from .base import (
    Message,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    StreamChunk,
    ToolCall,
    Usage,
)
from .capabilities import ALL_CAPABILITIES, Capability
from .errors import (
    ProviderAuthenticationError,
    ProviderContractError,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderUnconfigured,
    SecretLeakError,
    UnsupportedCapability,
)
from .health import HealthStatus, ProviderHealth
from .models import CostClass, DeploymentKind, ModelRef, PrivacyClass, ProviderModel
from .registry import ProviderRegistry
from .routing import (
    PolicyEngine,
    ProviderRouter,
    RoutingDecision,
    TaskClassifier,
    TaskProfile,
)
from .secrets import SecretManager, get_secret_manager
from .bootstrap import bootstrap_fabric, build_adapters, fabric_status

__version__ = "0.1.0"

__all__ = [
    "ALL_CAPABILITIES",
    "Capability",
    "CostClass",
    "DeploymentKind",
    "HealthStatus",
    "Message",
    "ModelRef",
    "PolicyEngine",
    "PrivacyClass",
    "ProviderAdapter",
    "ProviderAuthenticationError",
    "ProviderContractError",
    "ProviderError",
    "ProviderHealth",
    "ProviderModel",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderRouter",
    "ProviderTimeout",
    "ProviderUnavailable",
    "ProviderUnconfigured",
    "RoutingDecision",
    "SecretLeakError",
    "SecretManager",
    "StreamChunk",
    "TaskClassifier",
    "TaskProfile",
    "ToolCall",
    "UnsupportedCapability",
    "Usage",
    "bootstrap_fabric",
    "build_adapters",
    "fabric_status",
    "get_secret_manager",
]