"""General-purpose, multi-model provider abstraction for Silverwing.

Extends the provider pattern established by the Training Advisor
(``training_advisor.providers.TrainingAdvisorProvider`` -> ``GeminiProvider`` +
``LocalProvider``) into a *general* LLM routing layer that the agent
orchestrator, the Training Advisor, and the HTTP ``/api/models/*`` surface can
all share.

A model is addressed by a single string of the form::

    <provider>:<model-id>

e.g. ``openai:gpt-5.6-sol``  ``anthropic:claude-fable-5``  ``google:gemini-2.5``
     ``groq:deepseek-v4-pro``  ``ollama:deepseek-v4-pro``  ``local-rule``
     ``bedrock:anthropic.claude-opus-5``  ``vertex:gemini-2.5-pro``
     ``deepseek:deepseek-v4-pro``  ``llamacpp:Qwen3-32B-Q4_K_M.gguf``

``provider`` is matched against the registered provider names; unknown /
unauthorized / no-SDK models fall through to :class:`LocalProvider` (a
deterministic echo + rule fallback) so Silverwing keeps running with no
credentials and no SDKs installed.

Providers currently registered
------------------------------
``openai``    â€“ OpenAI API (GPT-5.x, GPT-OSS)            (``OPENAI_API_KEY``)
``anthropic`` â€“ Anthropic Claude API                      (``ANTHROPIC_API_KEY``)
``google``    â€“ Google Gemini via ``google.genai``        (``GEMINI_API_KEY``)
``groq``      â€“ GroqCloud hosted inference                (``GROQ_API_KEY``)
``deepseek``  â€“ DeepSeek API (OpenAI-compatible endpoint)  (``DEEPSEEK_API_KEY``)
``ollama``    â€“ Local Ollama server                        (``OLLAMA_HOST``)
``llamacpp``  â€“ Local llama.cpp server (OpenAI-compatible) (``LLAMACPP_API_BASE``)
``bedrock``   â€“ AWS Bedrock Converse API                   (``AWS_PROFILE`` / env)
``vertex``    â€“ Google Cloud Vertex AI                     (``GOOGLE_APPLICATION_CREDENTIALS``)
``local``     â€“ Deterministic local echo (no credentials)

All third-party SDKs (``openai``, ``anthropic``, ``google.genai``, ``groq``,
``ollama``, ``boto3``, ``google-cloud-aiplatform``) are imported *lazily*
inside each provider, so this module imports cleanly in a bare Python
environment (verified by the test suite: providers report unavailable,
:class:`LocalProvider` works).

Security model
--------------
* API keys are read **only** from the environment and are never hard-coded or
  logged.  ``GEMINI_API_KEY`` is reused from the Training Advisor config; the
  other providers read ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` /
  ``GROQ_API_KEY`` / ``OLLAMA_HOST`` / ``DEEPSEEK_API_KEY`` /
  ``LLAMACPP_API_BASE`` / ``AWS_PROFILE`` / ``GOOGLE_APPLICATION_CREDENTIALS``.
* Providers never mutate optimizer / scheduler / checkpoints - chat is
  advisory + structured data extraction only.
* Structured output uses a registered Pydantic schema; responses are
  re-validated by the caller and a malformed JSON object is discarded (the
  caller falls back to ``LocalProvider``), mirroring the Training Advisor's
  prompt-injection / malformed-output guard.

Model catalog
-------------
A comprehensive, static catalogue of available foundation models (providers,
model IDs, context windows, capabilities, pricing, open-weights flags) lives
in :mod:`model_catalog`.  ``MODEL_CATALOG`` is re-exported from this module
and surfaced through the ``/api/models/catalog`` HTTP endpoint.

Mapping this string-swap model layer onto the recommended orchestration
framework: a Pydantic-AI :class:`~pydantic_ai.Agent` is constructed from
exactly these strings, e.g. ``Agent('openai:gpt-5.6-sol')``.  The same strings
are accepted by LangChain (``ChatOpenAI(model="gpt-5.6-sol")`` etc.), LangGraph,
LlamaIndex, CrewAI, and AutoGen â€” see ``ORCHESTRATION.md`` for the mapping.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum as PyEnum
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

log = logging.getLogger("silverwing.model_provider")

# Re-export the static model catalogue so callers can do
# ``from model_provider import MODEL_CATALOG``.
try:  # keep the module import-safe even if model_catalog has issues
    from model_catalog import (  # type: ignore[import-not-found]
        MODEL_CATALOG,
        MODEL_CATALOG_BY_KEY,
        PROVIDER_PROFILES,
        get_model_info,
        list_by_provider,
        list_all_models,
        list_families,
        list_open_weights,
    )
except Exception:  # pragma: no cover - fallback when model_catalog is unavailable
    MODEL_CATALOG = {}  # type: ignore[assignment]
    MODEL_CATALOG_BY_KEY = {}  # type: ignore[assignment]
    PROVIDER_PROFILES = {}  # type: ignore[assignment]

    def get_model_info(*a, **kw):
        return None

    def list_by_provider(*a, **kw):
        return []

    def list_all_models(*a, **kw):
        return []

    def list_families(*a, **kw):
        return {}

    def list_open_weights(*a, **kw):
        return []


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ModelRequest(BaseModel):
    """A single chat request routed through a model provider."""

    messages: List[Dict[str, Any]] = Field(default_factory=list)
    model: Optional[str] = None  # provider:model-id or bare provider name
    system: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    # Name of a Pydantic schema registered on the ModelManager via
    # ``register_schema``. When set, providers attempt structured JSON output
    # and the response is re-validated against the schema.
    response_model: Optional[str] = None


class ModelResponse(BaseModel):
    """Normalized response returned by every provider."""

    content: str
    parsed: Any = None
    usage: Dict[str, Any] = Field(default_factory=dict)
    provider: str
    model: str
    finish_reason: Optional[str] = None
    # Rich telemetry fields (populated by providers that support them)
    latency_ms: Optional[float] = None
    estimated_cost: Optional[float] = None  # USD
    reasoning_content: Optional[str] = None  # extended thinking / reasoning
    citations: Optional[List[Dict[str, Any]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    streaming: bool = False


class HealthStatus(str, PyEnum):
    """Provider health states (section 9 of the architecture spec)."""

    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    OFFLINE = "OFFLINE"
    AUTH_ERROR = "AUTH_ERROR"
    DEPRECATED = "DEPRECATED"
    UNKNOWN = "UNKNOWN"


class PrivacyLevel(str, PyEnum):
    """Request privacy classification (section 16)."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    SENSITIVE = "sensitive"


class CostPolicy(str, PyEnum):
    """Cost-control policies (section 15)."""

    FREE_ONLY = "free_only"
    LOCAL_ONLY = "local_only"
    LOW_COST = "low_cost"
    BEST_QUALITY = "best_quality"
    LOW_LATENCY = "low_latency"
    PRIVATE_ONLY = "private_only"


class ModelClass(str, PyEnum):
    """Model classification tags (section 2)."""

    LOCAL_OPEN_WEIGHT = "LOCAL_OPEN_WEIGHT"
    LOCAL_PROPRIETARY = "LOCAL_PROPRIETARY"
    CLOUD_API = "CLOUD_API"
    FREE_TIER = "FREE_TIER"
    PAID_API = "PAID_API"
    SPECIALIZED = "SPECIALIZED"
    EMBEDDING = "EMBEDDING"
    VISION = "VISION"
    AUDIO = "AUDIO"
    CODE = "CODE"
    REASONING = "REASONING"
    RESEARCH = "RESEARCH"
    SMALL_EDGE = "SMALL_EDGE"
    LARGE_FRONTIER = "LARGE_FRONTIER"


class ModelSpec(BaseModel):
    """A registered model specification (section 13 â€” Capability Registry entry)."""

    id: str                               # e.g. "openai:gpt-5.6-sol"
    provider: str
    deployment: str = ""                  # e.g. "openai", "ollama", "bedrock"
    model_id: str                         # provider-native ID
    name: str = ""
    description: str = ""
    context_length: int = 0
    max_output_tokens: int = 0
    modality: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    model_classes: List[str] = Field(default_factory=list)
    pricing_input: Optional[float] = None   # $ per 1M input tokens
    pricing_output: Optional[float] = None  # $ per 1M output tokens
    free_tier: bool = False
    open_weights: bool = False
    license: str = ""
    commercial_use: str = ""
    local_availability: str = ""
    api_availability: str = ""
    supported_engines: List[str] = Field(default_factory=list)
    hardware_requirements: str = ""
    latency_ms: Optional[float] = None
    benchmark_score: Optional[float] = None
    status: HealthStatus = HealthStatus.UNKNOWN
    privacy: str = "public"
    # Dynamic health / cost tracking
    last_check: float = 0.0              # epoch seconds
    health_history: List[Dict[str, Any]] = Field(default_factory=list)


class RoutingDecision(BaseModel):
    """A single model-routing decision with full provenance (section 8)."""

    task: str
    requested_capability: Optional[str] = None
    requested_privacy: str = "public"
    requested_latency: str = "normal"
    requested_cost: str = "best_quality"
    selected_model: str
    provider: str
    reason: str
    fallback: Optional[str] = None
    fallback_chain: List[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    cost_estimate: float = 0.0
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=lambda: time.time())
    success: bool = True
    error: Optional[str] = None


class ModelConfig(BaseModel):
    """Environment-backed configuration for all model providers.

    Every field defaults to an environment lookup, so no secret is ever
    hard-coded. Providers are simply *unavailable* when their key/env is
    absent; the system degrades gracefully to :class:`LocalProvider`.
    """

    default_model: str = Field(default_factory=lambda: os.environ.get("SILVERWING_MODEL", "local-rule"))
    openai_model: str = Field(default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-5.6-sol"))
    anthropic_model: str = Field(default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"))
    gemini_model: str = Field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.5-pro") or os.environ.get("GOOGLE_MODEL", "gemini-2.5-pro"))
    groq_model: str = Field(default_factory=lambda: os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"))
    ollama_model: str = Field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "llama3.3:70b"))
    ollama_host: str = Field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    deepseek_model: str = Field(default_factory=lambda: os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    deepseek_base: str = Field(default_factory=lambda: os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"))
    llamacpp_model: str = Field(default_factory=lambda: os.environ.get("LLAMACPP_MODEL", "Qwen3-32B-Q4_K_M.gguf"))
    llamacpp_base: str = Field(default_factory=lambda: os.environ.get("LLAMACPP_API_BASE", "http://127.0.0.1:8081/v1"))
    bedrock_model: str = Field(default_factory=lambda: os.environ.get("BEDROCK_MODEL", "anthropic.claude-opus-5"))
    bedrock_region: str = Field(default_factory=lambda: os.environ.get("AWS_REGION", "us-east-1"))
    vertex_model: str = Field(default_factory=lambda: os.environ.get("VERTEX_MODEL", "publishers/google/models/gemini-2.5-pro"))
    vertex_location: str = Field(default_factory=lambda: os.environ.get("VERTEX_AI_LOCATION", "us-central1"))
    vertex_project: str = Field(default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    timeout_seconds: float = Field(default_factory=lambda: float(os.environ.get("MODEL_TIMEOUT_SECONDS", "30")))
    max_retries: int = Field(default_factory=lambda: int(os.environ.get("MODEL_MAX_RETRIES", "3")))

    # Secret accessors - read on demand, never stored beyond this call.
    @property
    def openai_key(self) -> Optional[str]:
        return os.environ.get("OPENAI_API_KEY")

    @property
    def anthropic_key(self) -> Optional[str]:
        return os.environ.get("ANTHROPIC_API_KEY")

    @property
    def gemini_key(self) -> Optional[str]:
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    @property
    def groq_key(self) -> Optional[str]:
        return os.environ.get("GROQ_API_KEY")

    @property
    def deepseek_key(self) -> Optional[str]:
        return os.environ.get("DEEPSEEK_API_KEY")

    @property
    def bedrock_credentials(self) -> Optional[str]:
        """Return a credential sentinel if *any* AWS auth env var is set."""
        if os.environ.get("AWS_PROFILE"):
            return os.environ["AWS_PROFILE"]
        if os.environ.get("AWS_ACCESS_KEY_ID"):
            return "env"
        return None

    @property
    def vertex_credentials(self) -> Optional[str]:
        return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    # Convenience: does at least one cloud provider have a key?
    def any_cloud_key(self) -> bool:
        return bool(
            self.openai_key or self.anthropic_key or self.gemini_key
            or self.groq_key or self.deepseek_key
            or self.bedrock_credentials or self.vertex_credentials
        )


# Registered provider name -> default model id (used when a bare provider name
# is given without an explicit model-id, e.g. "openai").
_PROVIDER_DEFAULTS: Dict[str, str] = {
    "openai": "gpt-5.6-sol",
    "anthropic": "claude-opus-5",
    "google": "gemini-2.5-pro",
    "groq": "llama-3.3-70b-versatile",
    "deepseek": "deepseek-v4-pro",
    "ollama": "llama3.3:70b",
    "llamacpp": "Qwen3-32B-Q4_K_M.gguf",
    "bedrock": "anthropic.claude-opus-5",
    "vertex": "publishers/google/models/gemini-2.5-pro",
    "silverwing": "silverwing-120m-base-v1",
    "vllm": "default",
}

_PROVIDER_ALIASES: Dict[str, str] = {
    "gemini": "google",
    "google": "google",
    "geminai": "google",
    "openai": "openai",
    "openai-compatible": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "groq": "groq",
    "groqcloud": "groq",
    "deepseek": "deepseek",
    "deepseekai": "deepseek",
    "ollama": "ollama",
    "ollama_local": "ollama",
    "llamacpp": "llamacpp",
    "llama_cpp": "llamacpp",
    "llamacpp_server": "llamacpp",
    "bedrock": "bedrock",
    "aws_bedrock": "bedrock",
    "vertex": "vertex",
    "vertexai": "vertex",
    "vertex_ai": "vertex",
    "local": "local",
    "silverwing": "silverwing",
    "vllm": "vllm",
}

_LOCAL = "local-rule"


def parse_model(ref: Optional[str], config: Optional[ModelConfig] = None) -> Tuple[str, str]:
    """Resolve a model reference string into ``(provider_name, model_id)``.

    * ``"openai:gpt-5.6-sol"``  -> ``("openai", "gpt-5.6-sol")``
    * ``"google:gemini-2.5"``   -> ``("google", "gemini-2.5")``
    * ``"openai"`` (bare)       -> ``("openai", <default>)``
    * ``"local-rule"`` / empty  -> ``("local", "local-rule")``
    * ``"bedrock:anthropic.claude-opus-5"`` -> ``("bedrock", "anthropic.claude-opus-5")``
    * ``"vertex:gemini-2.5-pro"`` -> ``("vertex", "gemini-2.5-pro")``
    * ``"deepseek:deepseek-v4-pro"`` -> ``("deepseek", "deepseek-v4-pro")``
    * ``"llamacpp:Qwen3-32B-Q4"`` -> ``("llamacpp", "Qwen3-32B-Q4")``
    * unknown string            -> ``("local", ref)`` (safe fallback)
    """
    ref = (ref or "").strip()
    if not ref or ref == _LOCAL:
        return ("local", _LOCAL)
    cfg = config or ModelConfig()
    if ":" in ref:
        prov, model = ref.split(":", 1)
        prov, model = prov.strip().lower(), model.strip()
        prov = _PROVIDER_ALIASES.get(prov, prov)
        if not model:
            model = _PROVIDER_DEFAULTS.get(prov, cfg.openai_model)
        return (prov, model)
    # bare name
    prov = _PROVIDER_ALIASES.get(ref.lower(), ref.lower())
    if prov in _PROVIDER_DEFAULTS:
        return (prov, _PROVIDER_DEFAULTS[prov])
    # treat as an opaque model id routed through the default provider
    default_prov, _ = parse_model(cfg.default_model, cfg)
    return (default_prov, ref)


def _sdk_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _extract_json(text: str) -> Optional[Any]:
    """Best-effort extraction of the outermost JSON object in ``text``."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # tolerate markdown-fenced JSON
    first = text.find("{")
    last = text.rfind("}")
    if 0 <= first < last:
        try:
            return json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            return None
    return None


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------


class ModelProvider(ABC):
    """Abstract base for a model provider.

    Subclasses implement :meth:`_achat` (the SDK call) and override
    :meth:`is_available`. SDK clients are imported lazily so this module is
    import-safe with no third-party packages installed.

    The full Protocol (``generate``, ``stream``, ``embed``, ``health``,
    ``list_models``) is honoured by every concrete provider. Default
    implementations are provided for ``stream`` (delegates to ``chat``),
    ``embed`` (raises ``NotImplementedError``), and
    ``list_models`` (returns a single-entry list).
    """

    name: str = "abstract"

    def __init__(self, config: Optional[ModelConfig] = None, client: Any = None):
        self.config = config or ModelConfig()
        self._client = client  # injectable for tests
        self._health: HealthStatus = HealthStatus.UNKNOWN

    @abstractmethod
    def is_available(self) -> bool:
        """True when the SDK is importable *and* credentials are present."""

    @property
    def authorized(self) -> bool:
        return self.is_available()

    def resolve_model(self, model_id: Optional[str]) -> str:
        return model_id or _PROVIDER_DEFAULTS.get(self.name, "default")

    def auth_status(self) -> Dict[str, Any]:
        return {"provider": self.name, "available": self.is_available(),
                "authorized": self.authorized, "model": self.resolve_model(None)}

    # -- retry wrapper ------------------------------------------------------
    async def chat(self, request: ModelRequest) -> ModelResponse:
        last: BaseException | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._achat(request),
                    timeout=self.config.timeout_seconds + 2.0,
                )
            except asyncio.TimeoutError:
                last = TimeoutError(f"{self.name} chat timed out (attempt {attempt + 1})")
            except Exception as e:  # noqa: BLE001
                last = e
                log.warning("%s chat failed (attempt %d): %r", self.name, attempt + 1, e)
            if attempt < self.config.max_retries:
                backoff = min(8.0, 0.5 * (2 ** attempt))
                await asyncio.sleep(backoff)
        log.error("%s chat exhausted retries: %r", self.name, last)
        raise last  # type: ignore[misc]

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Primary generation entry-point (alias for ``chat``)."""
        return await self.chat(request)

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelResponse]:
        """Stream token-by-token responses. Default: yield a single non-streaming response."""
        yield await self.chat(request)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts. Default: raises NotImplementedError."""
        raise NotImplementedError(f"{self.name} does not support embeddings")

    async def health(self) -> HealthStatus:
        """Return the current health status of this provider."""
        if self.is_available():
            return self._health if self._health != HealthStatus.UNKNOWN else HealthStatus.AVAILABLE
        return HealthStatus.OFFLINE

    def list_models(self) -> List[str]:
        """List model IDs available from this provider."""
        return [self.resolve_model(None)]

    # -- to be implemented by subclasses -----------------------------------
    @abstractmethod
    async def _achat(self, request: ModelRequest) -> ModelResponse:
        ...


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------


class LocalProvider(ModelProvider):
    """Deterministic, dependency-free fallback. Always available.

    Echoes the last user message so every provider slot is testable without a
    network or SDK. It never calls out to any external service.
    """

    name = "local"

    def is_available(self) -> bool:
        return True

    def resolve_model(self, model_id: Optional[str]) -> str:
        return model_id or _LOCAL

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        # Find the last user message; echo it back with a marker so callers can
        # distinguish a local echo from a real model response.
        text = ""
        for msg in reversed(request.messages):
            if msg.get("role") == "user":
                parts = msg.get("content")
                if isinstance(parts, str):
                    text = parts
                    break
                if isinstance(parts, list):
                    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
                    break
        content = f"[local] {text}" if text else "[local] (no user message)"
        parsed = None
        if request.response_model and text:
            parsed = _extract_json(text)
        return ModelResponse(
            content=content,
            parsed=parsed,
            usage={"provider": "local"},
            provider=self.name,
            model=_LOCAL,
            finish_reason="stop",
        )


class SilverwingProvider(LocalProvider):
    """First-class provider for Silverwing's own model (Silverwing Decoder V2).

    This wraps the existing Silverwing inference server / local model and
    exposes it through the same ``ModelProvider`` interface used by all
    external providers.  Silverwing is **never** replaced or hidden â€” it is
    the always-available native model and acts as the ultimate fallback.

    Unlike :class:`LocalProvider` (a pure deterministic echo for testing /
    fail-safe), ``SilverwingProvider`` is the designated *production* local
    model slot.  When the actual Silverwing inference server is reachable
    (via ``SILVERWING_SERVER_URL``), it delegates there; when it is not, it
    falls back to the deterministic echo behaviour so the system stays
    operational.

    Environment variables (read lazily so process env set after import applies):
        ``SILVERWING_SERVER_URL``  - explicit HTTP endpoint for the native
        Silverwing inference server. Falls back to ``SILVERWING_ENDPOINT``
        (the canonical integration env, default ``http://127.0.0.1:8010``).
        If unset or unreachable, the provider operates in *rule-based echo* mode.
        ``SILVERWING_MODEL_ID``    - model name reported in responses
        (default ``silverwing-120m-base-v1``; ``SILVERWING_MODEL`` also honored).
    """

    name = "silverwing"

    _DEFAULT_MODEL = "silverwing-120m-base-v1"
    _DEFAULT_ENDPOINT = "http://127.0.0.1:8010"

    @classmethod
    def _server_url(cls) -> str:
        return (os.environ.get("SILVERWING_SERVER_URL")
                or os.environ.get("SILVERWING_ENDPOINT")
                or cls._DEFAULT_ENDPOINT).rstrip("/")

    @classmethod
    def _model_id(cls) -> str:
        return (os.environ.get("SILVERWING_MODEL_ID")
                or os.environ.get("SILVERWING_MODEL")
                or cls._DEFAULT_MODEL)

    # Back-compat class attributes (import-time snapshot; live code uses the
    # lazy helpers above so late-arriving env is honored).
    SILVERWING_MODEL_ID = os.environ.get("SILVERWING_MODEL_ID", _DEFAULT_MODEL)
    SILVERWING_SERVER_URL = os.environ.get("SILVERWING_SERVER_URL", "")

    def _base_url(self) -> str:
        # Instance-level override wins, then env, then default.
        url = (getattr(self, "server_url", "")
               or self._server_url())
        return url.rstrip("/")

    def is_available(self) -> bool:
        # The Silverwing model is always available (at minimum, in echo mode).
        return True

    def resolve_model(self, model_id: Optional[str]) -> str:
        # Legacy alias has no trained weights; route it to the real 120M base.
        if not model_id or model_id == "silverwing-decoder-v2":
            return self._model_id()
        return model_id

    @property
    def model_id(self) -> str:
        return self._model_id()

    async def health(self) -> HealthStatus:
        base = self._base_url()
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                # Runtime serves /v1/health; probe it first, then bare /health.
                for path in ("/v1/health", "/health"):
                    try:
                        resp = await client.get(f"{base}{path}")
                    except Exception:
                        continue
                    if resp.status_code == 200:
                        return HealthStatus.AVAILABLE
                    if resp.status_code in (429,):
                        return HealthStatus.RATE_LIMITED
                    if resp.status_code in (401, 403):
                        return HealthStatus.AUTH_ERROR
                    return HealthStatus.DEGRADED
        except Exception:
            pass
        # Server unreachable â€” echo mode keeps the surface alive, but echo
        # answers are tagged below so they can never pass as model output.
        return HealthStatus.AVAILABLE

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Deterministic embedding proxy (hash-based).  The real Silverwing
        server provides embeddings when reachable; otherwise we return
        deterministic pseudo-embeddings so downstream code never crashes."""
        import hashlib
        result = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [float(b) / 255.0 for b in h[:256]]
            result.append(vec)
        return result

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        """Delegate to the Silverwing server if configured; otherwise echo."""
        model_id = self.resolve_model(
            request.model.split(":", 1)[-1] if request.model else None)
        start = time.monotonic()

        # Delegate to the trained Silverwing runtime (TorchBackend weights).
        # Runtime routes live under /v1/*; legacy bare paths tried as fallback.
        base = self._base_url()
        try:
            import httpx
            async with httpx.AsyncClient(
                    timeout=self.config.timeout_seconds) as client:
                payload = {
                    "model": model_id,
                    "messages": _normalize_messages(request.messages, request.system),
                    "temperature": request.temperature if request.temperature is not None else 0.7,
                    "max_tokens": request.max_tokens or int(os.environ.get("SILVERWING_MAX_TOKENS", "64")),
                    "stream": False,
                }
                for path in ("/v1/chat/completions", "/chat/completions"):
                    try:
                        resp = await client.post(f"{base}{path}", json=payload)
                    except Exception as e:
                        log.warning("Silverwing server unreachable, falling back to echo: %r", e)
                        break
                    if resp.status_code == 200:
                        data = resp.json()
                        choice = data["choices"][0]
                        content = choice.get("message", {}).get("content", "")
                        return ModelResponse(
                            content=content,
                            parsed=_extract_json(content) if request.response_model else None,
                            usage=data.get("usage", {}),
                            provider=self.name,
                            model=data.get("model", model_id),
                            finish_reason=choice.get("finish_reason"),
                            latency_ms=round((time.monotonic() - start) * 1000, 2),
                        )
        except Exception as e:
            log.warning("Silverwing server unreachable, falling back to echo: %r", e)

        # Echo fallback â€” deterministic and always available.
        text = ""
        for msg in reversed(request.messages):
            if msg.get("role") == "user":
                parts = msg.get("content")
                if isinstance(parts, str):
                    text = parts
                    break
                if isinstance(parts, list):
                    text = "".join(p.get("text", "")
                                   for p in parts if p.get("type") == "text")
                    break
        # Echo fallback â€” deterministic and always available. Tagged as an
        # echo fallback so it can never be mistaken for trained-model output.
        content = (f"[silverwing] (echo-fallback: trained model unreachable) {text}"
                   if text else "[silverwing] (echo-fallback: no user message)")
        parsed = _extract_json(text) if request.response_model and text else None
        return ModelResponse(
            content=content,
            parsed=parsed,
            usage={"provider": "silverwing"},
            provider=self.name,
            model=model_id,
            finish_reason="stop",
            latency_ms=round((time.monotonic() - start) * 1000, 2),
        )


def _normalize_messages(messages: List[Dict[str, Any]], system: Optional[str]) -> List[Dict[str, Any]]:
    msgs = []
    if system:
        # Anthropic/Anthropic-style require system as a separate param or an
        # explicit message; OpenAI accepts a system role message.
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    return msgs


class OpenAIProvider(ModelProvider):
    name = "openai"

    def is_available(self) -> bool:
        return self.config.openai_key is not None and _sdk_available("openai")

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        # Lazy import + injectable client for tests.
        from openai import AsyncOpenAI
        client: Any = self._client or AsyncOpenAI(
            api_key=self.config.openai_key, timeout=self.config.timeout_seconds)
        model = self.resolve_model(request.model.split(":", 1)[-1] if request.model else None)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _normalize_messages(request.messages, request.system),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.response_model:
            # Best-effort structured output (json_object). The caller is
            # expected to validate the parsed result against its schema.
            kwargs["response_format"] = {"type": "json_object"}
            kwargs["messages"] = kwargs["messages"]  # type: ignore[assignment]
        resp = await client.chat.completions.create(**{k: v for k, v in kwargs.items() if v is not None})
        choice = resp.choices[0]
        content = choice.message.content or ""
        parsed = _extract_json(content) if request.response_model else None
        usage = getattr(resp, "usage", None)
        usage_dict = usage.model_dump() if usage else {}
        return ModelResponse(
            content=content, parsed=parsed, usage=usage_dict,
            provider=self.name, model=getattr(resp, "model", model),
            finish_reason=getattr(choice, "finish_reason", None),
        )


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def is_available(self) -> bool:
        return self.config.anthropic_key is not None and _sdk_available("anthropic")

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        import anthropic
        client: Any = self._client or anthropic.AsyncAnthropic(
            api_key=self.config.anthropic_key, timeout=self.config.timeout_seconds)
        model = self.resolve_model(request.model.split(":", 1)[-1] if request.model else None)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": request.messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
        }
        if request.system:
            kwargs["system"] = request.system
        resp = await client.messages.create(**{k: v for k, v in kwargs.items() if v is not None})
        content = "".join(part.get("text", "") for part in resp.get("content", [])) if isinstance(resp, dict) else \
            "".join(part.text for part in getattr(resp, "content", []) if getattr(part, "text", None))
        parsed = _extract_json(content) if request.response_model else None
        return ModelResponse(
            content=content, parsed=parsed,
            usage={"output_tokens": getattr(resp, "usage", {}).get("output_tokens", None) if hasattr(resp, "usage") else None},
            provider=self.name, model=getattr(resp, "model", model),
            finish_reason=getattr(resp, "stop_reason", None),
        )


class GeminiProvider(ModelProvider):
    """Google Gemini via the current ``google.genai`` SDK (NOT legacy)."""

    name = "google"

    def is_available(self) -> bool:
        return self.config.gemini_key is not None and _sdk_available("google.genai")

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        # gemini SDK generate_content is synchronous; run it off the event loop.
        def _sync() -> ModelResponse:
            from google import genai
            from google.genai import types
            client: Any = self._client or genai.Client(
                api_key=self.config.gemini_key,
                http_options={"timeout": self.config.timeout_seconds})
            model = self.resolve_model(request.model.split(":", 1)[-1] if request.model else None)
            contents: List[Any] = []
            if request.system:
                contents.append({"role": "system", "parts": [{"text": request.system}]})
            contents.extend(request.messages)
            cfg = types.GenerateContentConfig(
                temperature=request.temperature,
                max_output_tokens=request.max_tokens,
            )
            if request.response_model:
                cfg.response_mime_type = "application/json"
            resp = client.models.generate_content(model=model, contents=contents, config=cfg)
            text = resp.text or ""
            parsed = _extract_json(text) if request.response_model else None
            usage = resp.get("usage_metadata", {}) if isinstance(resp, dict) else getattr(resp, "usage_metadata", {}) or {}
            return ModelResponse(
                content=text, parsed=parsed, usage=dict(usage) if usage else {},
                provider=self.name, model=model,
                finish_reason=getattr(resp, "finish_reason", None),
            )
        return await asyncio.to_thread(_sync)


class GroqProvider(ModelProvider):
    name = "groq"

    def is_available(self) -> bool:
        return self.config.groq_key is not None and _sdk_available("groq")

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        from groq import AsyncGroq
        client: Any = self._client or AsyncGroq(
            api_key=self.config.groq_key, timeout=self.config.timeout_seconds)
        model = self.resolve_model(request.model.split(":", 1)[-1] if request.model else None)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _normalize_messages(request.messages, request.system),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        resp = await client.chat.completions.create(
            **{k: v for k, v in kwargs.items() if v is not None})
        choice = resp.choices[0]
        return ModelResponse(
            content=choice.message.content or "",
            parsed=_extract_json(choice.message.content or "") if request.response_model else None,
            usage=getattr(resp, "usage", None).model_dump() if getattr(resp, "usage", None) else {},
            provider=self.name, model=getattr(resp, "model", model),
            finish_reason=getattr(choice, "finish_reason", None),
        )


class OllamaProvider(ModelProvider):
    """Local Ollama server (also reusable for a llama.cpp server in the same
    OpenAI-compatible shape by pointing ``OLLAMA_HOST`` at it)."""

    name = "ollama"

    def is_available(self) -> bool:
        # Ollama needs the SDK *and* a reachable host.  We don't probe the
        # socket (that would be slow); instead we treat the SDK + any
        # OLLAMA_HOST env var as sufficient.  When the SDK is absent the
        # provider is unavailable (hermetic test env).
        return _sdk_available("ollama") and bool(os.environ.get("OLLAMA_HOST"))

    def resolve_model(self, model_id: Optional[str]) -> str:
        return model_id or self.config.ollama_model

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        import ollama
        client: Any = self._client or ollama.AsyncClient(host=self.config.ollama_host, timeout=self.config.timeout_seconds)
        model = self.resolve_model(request.model.split(":", 1)[-1] if request.model else None)
        messages = _normalize_messages(request.messages, request.system)
        resp = await client.chat(model=model, messages=messages,
                                 options={"temperature": request.temperature, "num_predict": request.max_tokens or 4096})
        msg = resp.get("message", {}) if isinstance(resp, dict) else getattr(resp, "message", {})
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        parsed = _extract_json(content) if request.response_model else None
        return ModelResponse(
            content=content, parsed=parsed, usage={"provider": "ollama"},
            provider=self.name, model=model, finish_reason="stop",
        )


class DeepSeekProvider(ModelProvider):
    """DeepSeek API provider.

    DeepSeek exposes an OpenAI-compatible chat completion endpoint at
    ``https://api.deepseek.com/v1``.  We reuse the ``openai`` SDK (already a
    dependency) with a custom ``base_url`` and ``DEEPSEEK_API_KEY``.
    """

    name = "deepseek"

    def is_available(self) -> bool:
        return self.config.deepseek_key is not None and _sdk_available("openai")

    def resolve_model(self, model_id: Optional[str]) -> str:
        return model_id or self.config.deepseek_model

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        from openai import AsyncOpenAI
        client: Any = self._client or AsyncOpenAI(
            api_key=self.config.deepseek_key,
            base_url=self.config.deepseek_base,
            timeout=self.config.timeout_seconds,
        )
        model = self.resolve_model(request.model.split(":", 1)[-1] if request.model else None)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _normalize_messages(request.messages, request.system),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.response_model:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await client.chat.completions.create(
            **{k: v for k, v in kwargs.items() if v is not None})
        choice = resp.choices[0]
        content = choice.message.content or ""
        return ModelResponse(
            content=content,
            parsed=_extract_json(content) if request.response_model else None,
            usage=getattr(resp, "usage", None).model_dump() if getattr(resp, "usage", None) else {},
            provider=self.name, model=model,
            finish_reason=getattr(choice, "finish_reason", None),
        )


class LlamaCppProvider(ModelProvider):
    """Local llama.cpp server (OpenAI-compatible HTTP API).

    The llama.cpp ``llama-server`` binary exposes a REST endpoint that is
    wire-compatible with the OpenAI Chat Completions API.  We therefore reuse
    the ``openai`` SDK, pointing ``base_url`` at ``LLAMACPP_API_BASE``.
    """

    name = "llamacpp"

    def is_available(self) -> bool:
        # Requires both the OpenAI SDK (for API compat) and an explicit
        # LLAMACPP_API_BASE env var (the user must point us at a running
        # llama-server).  Using the SDK alone is not sufficient because the
        # server may not be running.
        return bool(os.environ.get("LLAMACPP_API_BASE")) and _sdk_available("openai")

    def resolve_model(self, model_id: Optional[str]) -> str:
        return model_id or self.config.llamacpp_model

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        from openai import AsyncOpenAI
        client: Any = self._client or AsyncOpenAI(
            base_url=self.config.llamacpp_base,
            timeout=self.config.timeout_seconds,
        )
        model = self.resolve_model(request.model.split(":", 1)[-1] if request.model else None)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _normalize_messages(request.messages, request.system),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        resp = await client.chat.completions.create(
            **{k: v for k, v in kwargs.items() if v is not None})
        choice = resp.choices[0]
        content = choice.message.content or ""
        return ModelResponse(
            content=content,
            parsed=_extract_json(content) if request.response_model else None,
            usage=getattr(resp, "usage", None).model_dump() if getattr(resp, "usage", None) else {},
            provider=self.name, model=model,
            finish_reason=getattr(choice, "finish_reason", None),
        )


class BedrockProvider(ModelProvider):
    """AWS Bedrock provider via the Converse API (``boto3``).

    Bedrock is a managed model-serving layer that fronts dozens of FMs
    (Anthropic Claude, Meta Llama, Cohere, Amazon Nova, Mistral, etc.).
    Authentication uses standard AWS credential resolution (env vars, shared
    config profile, or IAM role).  The synchronous ``boto3`` client is wrapped
    in :func:`asyncio.to_thread` so it plays nice with the async ``chat``.
    """

    name = "bedrock"

    # Map friendly model names to Bedrock model IDs / inference-profile ARNs.
    # In practice the caller can pass any valid Bedrock model ID directly.
    _MODEL_MAP: Dict[str, str] = {
        "claude-fable-5-1": "anthropic.claude-fable-5-1-v1:0",
        "claude-opus-5": "anthropic.claude-opus-5-v1:0",
        "claude-sonnet-5": "anthropic.claude-sonnet-5-v1:0",
        "claude-haiku-4-5": "anthropic.claude-haiku-4-5-v1:0",
        "gpt-5.6-sol": "openai.gpt-5.6-sol-v1:0",
        "gpt-5.5": "openai.gpt-5.5-v1:0",
        "llama4-scout": "meta.llama-4-scout-17b-instruct-v1:0",
        "llama4-maverick": "meta.llama-4-maverick-402b-instruct-v1:0",
        "deepseek-v3": "deepseek.v3-1-128k-20250520",
        "deepseek-r1": "deepseek.r1-128k-20250520",
        "qwen3-235b": "qwen3-235b-a22b-2507-v1:0",
        "nova-pro": "amazon.nova-pro-v1:0",
        "nova-micro": "amazon.nova-micro-v1:0",
    }

    def is_available(self) -> bool:
        return self.config.bedrock_credentials is not None and _sdk_available("boto3")

    def resolve_model(self, model_id: Optional[str]) -> str:
        if model_id is None:
            return self.config.bedrock_model
        return self._MODEL_MAP.get(model_id, model_id)

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        # boto3 is synchronous; offload to a thread.
        def _sync() -> ModelResponse:
            import boto3  # type: ignore[import-not-found]
            client: Any = self._client or boto3.client("bedrock-runtime", region_name=self.config.bedrock_region)
            raw_model = request.model.split(":", 1)[-1] if request.model else None
            model_id = self.resolve_model(raw_model)
            system_prompts: List[Any] = []
            if request.system:
                system_prompts.append({"text": request.system})
            converse_kwargs: Dict[str, Any] = {
                "modelId": model_id,
                "messages": request.messages,
                "system": system_prompts,
            }
            if request.temperature is not None:
                converse_kwargs["inferenceConfig"] = {
                    "temperature": request.temperature,
                    "maxOutputTokens": request.max_tokens or 4096,
                }
            elif request.max_tokens:
                converse_kwargs["inferenceConfig"] = {"maxOutputTokens": request.max_tokens}
            resp = client.converse(**converse_kwargs)
            output = resp.get("output", {}) if isinstance(resp, dict) else getattr(resp, "output", {})
            content_parts = output.get("message", {}).get("content", []) if isinstance(output, dict) else []
            text = "".join(p.get("text", "") if isinstance(p, dict) else "" for p in content_parts)
            usage = resp.get("usage", {}) if isinstance(resp, dict) else getattr(resp, "usage", {}) or {}
            return ModelResponse(
                content=text,
                parsed=_extract_json(text) if request.response_model else None,
                usage=dict(usage) if usage else {},
                provider=self.name, model=model_id,
                finish_reason="stop",
            )
        return await asyncio.to_thread(_sync)


class VertexProvider(ModelProvider):
    """Google Cloud Vertex AI provider.

    Uses the ``google-cloud-aiplatform`` SDK.  Authentication relies on
    Application Default Credentials (``GOOGLE_APPLICATION_CREDENTIALS`` or
    ``gcloud auth application-default login``).  Model IDs use the Vertex format
    ``publishers/<publisher>/models/<model>`` (e.g.
    ``publishers/google/models/gemini-2.5-pro``).
    """

    name = "vertex"

    # Friendly-name -> full Vertex model resource name.
    _MODEL_MAP: Dict[str, str] = {
        "gemini-2.5-pro": "publishers/google/models/gemini-2.5-pro",
        "gemini-2.5-flash": "publishers/google/models/gemini-2.5-flash",
        "gemini-3.8-flash": "publishers/google/models/gemini-3.8-flash",
        "llama4-scout": "publishers/meta/models/llama-4-scout-17b",
        "llama4-maverick": "publishers/meta/models/llama-4-maverick-402b",
        "qwen3-235b": "publishers/qwen/models/qwen3-235b-a22b-2507",
    }

    def is_available(self) -> bool:
        return self.config.vertex_credentials is not None and _sdk_available("google.cloud.aiplatform")

    def resolve_model(self, model_id: Optional[str]) -> str:
        if model_id is None:
            return self.config.vertex_model
        # If it's already a full resource name, return as-is.
        if model_id.startswith("publishers/"):
            return model_id
        return self._MODEL_MAP.get(model_id, model_id)

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        # aiplatform SDK calls are synchronous; offload to a thread.
        def _sync() -> ModelResponse:
            from vertexai.generative_models import GenerativeModel, GenerationConfig  # type: ignore[import-not-found]
            import vertexai  # type: ignore[import-not-found]
            raw_model = request.model.split(":", 1)[-1] if request.model else None
            model_id = self.resolve_model(raw_model)
            vertexai.init(
                project=self.config.vertex_project,
                location=self.config.vertex_location,
            )
            gen_cfg: Dict[str, Any] = {}
            if request.temperature is not None:
                gen_cfg["temperature"] = request.temperature
            if request.max_tokens:
                gen_cfg["max_output_tokens"] = request.max_tokens
            model = GenerativeModel(model_id)
            # Build contents
            contents = model._to_contents(request.messages) if hasattr(model, "_to_contents") else request.messages
            resp = model.generate_content(
                contents=contents,
                generation_config=GenerationConfig(**gen_cfg) if gen_cfg else None,
                system_instruction=request.system,
            )
            text = resp.text or ""
            return ModelResponse(
                content=text,
                parsed=_extract_json(text) if request.response_model else None,
                usage={"provider": "vertex"},
                provider=self.name, model=model_id,
                finish_reason="stop",
            )
        return await asyncio.to_thread(_sync)


# ---------------------------------------------------------------------------
# Registry / manager
# ---------------------------------------------------------------------------


class ProviderInfo(BaseModel):
    name: str
    available: bool
    authorized: bool
    model: str


class ModelManager:
    """Resolves model references to providers and dispatches chat requests.

    A singleton is created in ``main.py`` (mirrors the
    ``_TRAINING_ADVISOR_INST`` pattern) and exposed via the ``model_provider``
    tool + ``/api/models/*`` HTTP routes.
    """

    def __init__(self, config: Optional[ModelConfig] = None, providers: Optional[Dict[str, ModelProvider]] = None):
        self.config = config or ModelConfig()
        # Instantiate every provider (lazy SDK imports mean construction is
        # cheap; availability is determined at call time by ``is_available``).
        self._providers: Dict[str, ModelProvider] = providers or {
            p.name: p for p in (
                OpenAIProvider(self.config),
                AnthropicProvider(self.config),
                GeminiProvider(self.config),
                GroqProvider(self.config),
                DeepSeekProvider(self.config),
                OllamaProvider(self.config),
                LlamaCppProvider(self.config),
                BedrockProvider(self.config),
                VertexProvider(self.config),
                LocalProvider(self.config),
                SilverwingProvider(self.config),
                VLLMProvider(self.config),
            )
        }
        self._schemas: Dict[str, type] = {}

    # -- provider registration ---------------------------------------------
    def register(self, provider: ModelProvider) -> None:
        self._providers[provider.name] = provider

    def register_schema(self, name: str, model_cls: type) -> None:
        self._schemas[name] = model_cls

    # -- resolution ---------------------------------------------------------
    def parse(self, ref: Optional[str]) -> Tuple[str, str]:
        return parse_model(ref, self.config)

    def provider_for(self, ref: Optional[str] = None) -> Tuple[ModelProvider, str]:
        """Return ``(provider, model_id)``.

        Falls back to :class:`LocalProvider` when the requested provider is
        unavailable or the ref is unknown.
        """
        prov_name, model_id = self.parse(ref)
        provider = self._providers.get(prov_name) or self._providers.get("local")
        if provider is None:
            provider = LocalProvider(self.config)
            self._providers["local"] = provider
        if not provider.is_available():
            log.warning("Provider %r not available; falling back to LocalProvider for %r", prov_name, ref)
            provider = self._providers.get("local") or LocalProvider(self.config)
        return provider, model_id

    def default_model(self) -> str:
        return self.config.default_model

    def set_default(self, ref: Optional[str]) -> str:
        prov, model = self.parse(ref)
        self.config.default_model = f"{prov}:{model}" if prov != "local" else "local-rule"
        return self.config.default_model

    def auth_status(self) -> Dict[str, Any]:
        return {
            "default": self.config.default_model,
            "any_cloud_key": self.config.any_cloud_key(),
            "providers": {name: p.auth_status() for name, p in self._providers.items()},
            "schemas": sorted(self._schemas.keys()),
            "catalog_size": len(MODEL_CATALOG),
        }

    def list_providers(self) -> List[ProviderInfo]:
        return [
            ProviderInfo(
                name=name,
                available=p.is_available(),
                authorized=p.authorized,
                model=p.resolve_model(None),
            )
            for name, p in self._providers.items()
        ]

    def get_schema(self, name: str) -> Optional[type]:
        return self._schemas.get(name)

    # -- dispatch ----------------------------------------------------------
    async def achat(self, request: ModelRequest) -> ModelResponse:
        provider, model_id = self.provider_for(request.model or self.config.default_model)
        # If a response_model schema is registered, attach the class so the
        # provider can be tested for structured output; otherwise pass through.
        if request.response_model:
            schema = self.get_schema(request.response_model)
            if schema is None:
                log.warning("response_model %r not registered; proceeding without schema", request.response_model)
        req = ModelRequest(
            messages=request.messages, model=f"{provider.name}:{model_id}",
            system=request.system, temperature=request.temperature,
            max_tokens=request.max_tokens, response_model=request.response_model,
        )
        return await provider.chat(req)

    async def aclose(self) -> None:
        for p in self._providers.values():
            closer = getattr(p, "aclose", None)
            if closer is not None:
                try:
                    res = closer()
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:  # noqa: BLE001
                    pass


# ---------------------------------------------------------------------------
# vLLM provider (section 4.4 â€” high-throughput serving backend)
# ---------------------------------------------------------------------------


class VLLMProvider(ModelProvider):
    """High-throughput serving backend via vLLM's OpenAI-compatible API."""

    name = "vllm"

    def is_available(self) -> bool:
        return _sdk_available("openai") and bool(os.environ.get("VLLM_API_BASE"))

    def resolve_model(self, model_id: Optional[str]) -> str:
        return model_id or os.environ.get("VLLM_MODEL", "default")

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        from openai import AsyncOpenAI
        base_url = os.environ.get("VLLM_API_BASE")
        client: Any = self._client or AsyncOpenAI(
            base_url=base_url,
            api_key=os.environ.get("VLLM_API_KEY", "unused"),
            timeout=self.config.timeout_seconds)
        model = self.resolve_model(
            request.model.split(":", 1)[-1] if request.model else None)
        resp = await client.chat.completions.create(
            model=model,
            messages=_normalize_messages(request.messages, request.system),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        choice = resp.choices[0]
        content = choice.message.content or ""
        return ModelResponse(
            content=content,
            parsed=_extract_json(content) if request.response_model else None,
            usage=getattr(resp, "usage", None).model_dump() if getattr(resp, "usage", None) else {},
            provider=self.name,
            model=getattr(resp, "model", model),
            finish_reason=getattr(choice, "finish_reason", None),
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (section 4.5 â€” generic adapter)
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(ModelProvider):
    """Generic adapter for any OpenAI-compatible server.

    Register a named instance via environment:

        SILVERWING_CUSTOM_<NAME>_URL=...
        SILVERWING_CUSTOM_<NAME>_KEY=...
        SILVERWING_CUSTOM_<NAME>_MODEL=...

    Or instantiate directly::

        OpenAICompatibleProvider(config, client, name="my-llama",
                                 base_url="http://localhost:8080/v1")
    """

    name = "openai-compatible"

    def __init__(self, config: Optional[ModelConfig] = None,
                 client: Any = None, *, name: str = "openai-compatible",
                 base_url: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(config, client)
        self._name = name
        self._base_url = base_url
        self._api_key = api_key

    def is_available(self) -> bool:
        return _sdk_available("openai") and self._resolve_base_url() is not None

    @property
    def name(self) -> str:
        return self._name

    def _resolve_base_url(self) -> Optional[str]:
        if self._base_url:
            return self._base_url
        env_key = f"SILVERWING_CUSTOM_{self._name.upper()}_URL"
        return os.environ.get(env_key)

    def resolve_model(self, model_id: Optional[str]) -> str:
        if model_id:
            return model_id
        env_key = f"SILVERWING_CUSTOM_{self._name.upper()}_MODEL"
        return os.environ.get(env_key, "default")

    async def _achat(self, request: ModelRequest) -> ModelResponse:
        from openai import AsyncOpenAI
        client: Any = self._client or AsyncOpenAI(
            base_url=self._resolve_base_url(),
            api_key=self._api_key or os.environ.get(
                f"SILVERWING_CUSTOM_{self._name.upper()}_KEY", "unused"),
            timeout=self.config.timeout_seconds)
        model = self.resolve_model(
            request.model.split(":", 1)[-1] if request.model else None)
        resp = await client.chat.completions.create(
            model=model,
            messages=_normalize_messages(request.messages, request.system),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        choice = resp.choices[0]
        content = choice.message.content or ""
        return ModelResponse(
            content=content,
            parsed=_extract_json(content) if request.response_model else None,
            usage=getattr(resp, "usage", None).model_dump() if getattr(resp, "usage", None) else {},
            provider=self.name,
            model=getattr(resp, "model", model),
            finish_reason=getattr(choice, "finish_reason", None),
        )


# ---------------------------------------------------------------------------
# Cost tracking (section 15)
# ---------------------------------------------------------------------------


class CostTracker:
    """Tracks token usage, latency, and estimated costs for every invocation.

    Costs are computed from the model catalogue pricing data. When pricing is
    unknown, ``estimated_cost`` stays ``None`` rather than being fabricated.
    """

    def __init__(self, registry: Optional["ModelRegistry"] = None):
        self._registry = registry
        self._log: List[Dict[str, Any]] = []

    def estimate_cost(self, provider: str, model: str,
                      input_tokens: int, output_tokens: int) -> Optional[float]:
        """Calculate USD cost from catalog pricing. Returns ``None`` if unknown."""
        key = f"{provider}:{model}"
        info = get_model_info(key)
        if info is None:
            # Try matching on model_id alone (catalog may use native IDs)
            for k, v in MODEL_CATALOG.items():
                if k.endswith(f":{model}") or v.model_id == model:
                    info = v
                    break
        if info is None:
            return None
        price_in = getattr(info, "pricing_input", None)
        price_out = getattr(info, "pricing_output", None)
        if price_in is None or price_out is None:
            return None
        total = (input_tokens * price_in / 1_000_000.0
                 + output_tokens * price_out / 1_000_000.0)
        return round(total, 6)

    def record(self, provider: str, model: str, input_tokens: int,
               output_tokens: int, latency_ms: float,
               task: str = "", cost_policy: str = "best_quality",
               success: bool = True, error: Optional[str] = None) -> float:
        """Record a usage event and return the estimated cost (or 0.0 if unknown)."""
        cost = self.estimate_cost(provider, model, input_tokens, output_tokens)
        entry = {
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "estimated_cost": cost,
            "task": task,
            "cost_policy": cost_policy,
            "success": success,
            "error": error,
            "timestamp": time.time(),
        }
        self._log.append(entry)
        return cost or 0.0

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._log)

    def total_cost(self) -> float:
        return sum(e.get("estimated_cost") or 0.0 for e in self._log)


# ---------------------------------------------------------------------------
# Privacy policy (section 16)
# ---------------------------------------------------------------------------


class PrivacyPolicy:
    """Classifies requests and enforces data-flow policy.

    Private / sensitive requests prefer local providers. Cloud providers are
    only used when explicitly permitted by policy.
    """

    # Provider privacy classification
    PROVIDER_PRIVACY: Dict[str, str] = {
        "local": "private",
        "silverwing": "private",
        "ollama": "private",
        "llamacpp": "private",
        "openai": "public",
        "anthropic": "public",
        "google": "public",
        "groq": "public",
        "deepseek": "public",
        "bedrock": "internal",
        "vertex": "internal",
        "vllm": "private",
        "openai-compatible": "private",
    }

    @classmethod
    def classify(cls, provider: str) -> str:
        """Return the privacy level of a provider (public/internal/private)."""
        return cls.PROVIDER_PRIVACY.get(provider, "public")

    @classmethod
    def is_allowed(cls, provider: str, privacy_level: str) -> bool:
        """Check if a provider is allowed for the given privacy level."""
        prov_priv = cls.classify(provider)
        levels = {
            PrivacyLevel.PUBLIC: {"public", "internal", "private", "sensitive"},
            PrivacyLevel.INTERNAL: {"internal", "private", "sensitive"},
            PrivacyLevel.PRIVATE: {"private", "sensitive"},
            PrivacyLevel.SENSITIVE: {"sensitive"},
        }
        return prov_priv in levels.get(privacy_level, {"public", "internal", "private", "sensitive"})


# ---------------------------------------------------------------------------
# Observability (section 18)
# ---------------------------------------------------------------------------


class ObservabilityEvent(BaseModel):
    """A single observability event emitted by the model gateway."""

    event_type: str  # model.request, model.routing, model.started, etc.
    request_id: str
    mission_id: Optional[str] = None
    agent_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    status: str = "ok"  # ok, error, fallback
    fallback: Optional[str] = None
    error: Optional[str] = None
    provenance: Optional[str] = None  # privacy level / policy
    timestamp: float = Field(default_factory=lambda: time.time())


class EventLog:
    """In-memory event log (section 18 observably). Can be swapped for a
    persistent sink (file, Kafka, etc.) in production."""

    def __init__(self):
        self._events: List[ObservabilityEvent] = []
        self._max_events: int = 10_000

    def record(self, event: ObservabilityEvent) -> None:
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

    def get(self, event_types: Optional[List[str]] = None,
            request_id: Optional[str] = None) -> List[Dict[str, Any]]:
        results = self._events
        if event_types:
            results = [e for e in results if e.event_type in event_types]
        if request_id:
            results = [e for e in results if e.request_id == request_id]
        return [e.model_dump() for e in results]

    def recent(self, n: int = 100) -> List[Dict[str, Any]]:
        return [e.model_dump() for e in self._events[-n:]]


# ---------------------------------------------------------------------------
# Model Registry (persistent capability registry â€” section 13)
# ---------------------------------------------------------------------------


def _infer_model_classes(info) -> List[str]:
    """Infer ModelClass tags from a :class:`ModelInfo`'s capabilities and metadata.

    This bridges the static catalog (which uses capability tags like
    ``reasoning``, ``coding``, ``multimodal``, ``open_weights``) into the
    broader ModelClass taxonomy defined in section 2.
    """
    caps = info.capabilities
    classes: List[str] = []
    if info.open_weights:
        # Open weights + local serving â†’ LOCAL_OPEN_WEIGHT
        local_serving = any(s in ("ollama", "llamacpp", "vllm")
                            for s in info.serving.keys()) or not any(
            s in ("openai", "anthropic", "google", "groq", "bedrock", "vertex")
            for s in info.serving.keys())
        classes.append(ModelClass.LOCAL_OPEN_WEIGHT.value if local_serving
                       else ModelClass.CLOUD_API.value)
    else:
        classes.append(ModelClass.CLOUD_API.value)

    if "reasoning" in caps:
        classes.append(ModelClass.REASONING.value)
    if "coding" in caps:
        classes.append(ModelClass.CODE.value)
    if "vision" in caps or "multimodal" in caps:
        classes.append(ModelClass.VISION.value)
    if "audio" in caps:
        classes.append(ModelClass.AUDIO.value)
    if "embeddings" in caps:
        classes.append(ModelClass.EMBEDDING.value)
    if info.free_tier:
        classes.append(ModelClass.FREE_TIER.value)

    # Size heuristics
    ctx = info.context_length or 0
    if ctx >= 1_000_000:
        classes.append(ModelClass.LARGE_FRONTIER.value)
    elif ctx < 32_000:
        classes.append(ModelClass.SMALL_EDGE.value)

    # Specialized tags
    family = (info.family or "").lower()
    if "coder" in family or "code" in family:
        classes.append(ModelClass.SPECIALIZED.value)

    return classes


class ModelRegistry:
    """Persistent registry of model capabilities (section 13).

    Builds on the static :data:`MODEL_CATALOG` by adding mutable runtime
    state (health, latency, benchmark scores) that can be updated and
    persisted to a JSON file.
    """

    def __init__(self, config: Optional[ModelConfig] = None,
                 path: Optional[str] = None):
        self._config = config or ModelConfig()
        self._path = path or os.environ.get("SILVERWING_REGISTRY_PATH",
                                            "model_registry.json")
        self._specs: Dict[str, ModelSpec] = {}
        self._load_or_build()

    def _load_or_build(self) -> None:
        """Load from disk if available; otherwise build from MODEL_CATALOG."""
        loaded = False
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                for entry in data.get("models", []):
                    spec = ModelSpec(**entry)
                    self._specs[spec.id] = spec
                loaded = True
            except Exception:
                pass
        if not loaded:
            self._build_from_catalog()

    def _build_from_catalog(self) -> None:
        """Populate the registry from the static MODEL_CATALOG."""
        for key, info in MODEL_CATALOG.items():
            pricing = getattr(info, "pricing", None)
            price_in = pricing.input_per_1m if pricing else None
            price_out = pricing.output_per_1m if pricing else None
            spec = ModelSpec(
                id=key,
                provider=info.provider,
                model_id=info.model_id,
                name=info.name,
                description=info.description,
                context_length=info.context_length or 0,
                model_classes=[mc for mc in _infer_model_classes(info)
                               if mc in [m.value for m in ModelClass]],
                capabilities=list(info.capabilities),
                pricing_input=price_in,
                pricing_output=price_out,
                free_tier=info.free_tier,
                open_weights=info.open_weights,
                status=HealthStatus.AVAILABLE if info.provider == "local" else HealthStatus.UNKNOWN,
            )
            self._specs[key] = spec

    def save(self) -> None:
        """Persist the registry to disk."""
        data = {
            "models": [s.model_dump() for s in self._specs.values()],
            "updated_at": time.time(),
        }
        try:
            with open(self._path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception:
            log.warning("Failed to persist model registry to %s", self._path)

    def get(self, model_id: str) -> Optional[ModelSpec]:
        return self._specs.get(model_id)

    def list(self) -> List[ModelSpec]:
        return list(self._specs.values())

    def by_provider(self, provider: str) -> List[ModelSpec]:
        return [s for s in self._specs.values() if s.provider == provider]

    def by_capability(self, capability: str) -> List[ModelSpec]:
        return [s for s in self._specs.values() if capability in s.capabilities]

    def update_health(self, model_id: str, status: HealthStatus) -> None:
        spec = self._specs.get(model_id)
        if spec:
            old = spec.status
            spec.status = status
            spec.last_check = time.time()
            spec.health_history.append({
                "timestamp": time.time(),
                "from": old.value, "to": status.value,
            })
            if len(spec.health_history) > 50:
                spec.health_history = spec.health_history[-50:]

    def all_available(self) -> List[ModelSpec]:
        """Return only models whose provider is available."""
        available_providers = set()
        mgr = ModelManager(self._config)
        for name, provider in mgr._providers.items():
            if provider.is_available():
                available_providers.add(name)
        return [s for s in self._specs.values()
                if s.provider in available_providers or s.open_weights]


# ---------------------------------------------------------------------------
# Model Router (section 7)
# ---------------------------------------------------------------------------


class ModelRouter:
    """Selects models based on capability, privacy, latency, cost, etc.

    The router consults the :class:`ModelRegistry` for capability metadata and
    the :class:`ModelManager` for provider availability, then returns a
    :class:`RoutingDecision` with full provenance.
    """

    # Capability â†’ model class mapping (section 7 routing rules)
    TASK_TO_CLASSES: Dict[str, List[str]] = {
        "coding": [ModelClass.CODE.value, ModelClass.LOCAL_OPEN_WEIGHT.value,
                    ModelClass.LARGE_FRONTIER.value],
        "deep_reasoning": [ModelClass.REASONING.value,
                           ModelClass.LARGE_FRONTIER.value],
        "fast_response": [ModelClass.SMALL_EDGE.value,
                          ModelClass.FREE_TIER.value],
        "multimodal": [ModelClass.VISION.value,
                       ModelClass.LOCAL_OPEN_WEIGHT.value,
                       ModelClass.LARGE_FRONTIER.value],
        "research": [ModelClass.RESEARCH.value,
                     ModelClass.LARGE_FRONTIER.value,
                     ModelClass.REASONING.value],
        "embedding": [ModelClass.EMBEDDING.value,
                      ModelClass.LOCAL_OPEN_WEIGHT.value],
        "small_edge": [ModelClass.SMALL_EDGE.value,
                       ModelClass.LOCAL_OPEN_WEIGHT.value],
    }

    # Cost policy â†’ provider preference order
    COST_POLICY_PROVIDERS: Dict[str, List[str]] = {
        "free_only": ["local", "silverwing", "ollama", "llamacpp"],
        "local_only": ["local", "silverwing", "ollama", "llamacpp"],
        "low_cost": ["groq", "deepseek", "ollama", "llamacpp", "silverwing", "local"],
        "best_quality": ["openai", "anthropic", "vertex", "bedrock", "google",
                         "groq", "deepseek", "silverwing", "ollama", "llamacpp", "local"],
        "low_latency": ["groq", "openai", "silverwing", "ollama", "local"],
        "private_only": ["local", "silverwing", "ollama", "llamacpp"],
    }

    def __init__(self, manager: Optional[ModelManager] = None,
                 registry: Optional[ModelRegistry] = None):
        self._manager = manager or ModelManager()
        self._registry = registry or ModelRegistry(self._manager.config)
        self._cost_tracker = CostTracker(self._registry)
        self._event_log = EventLog()

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @property
    def cost_tracker(self) -> CostTracker:
        return self._cost_tracker

    @property
    def events(self) -> EventLog:
        return self._event_log

    def _available_providers(self) -> List[str]:
        return [name for name, p in self._manager._providers.items()
                if p.is_available()]

    def _filter_by_privacy(self, specs: List[ModelSpec],
                           privacy_level: str) -> List[ModelSpec]:
        if privacy_level in (PrivacyLevel.PUBLIC.value, ""):
            return specs
        return [s for s in specs
                if PrivacyPolicy.is_allowed(s.provider, privacy_level)]

    def _filter_by_policy(self, specs: List[ModelSpec],
                          cost_policy: str) -> List[ModelSpec]:
        pref = self.COST_POLICY_PROVIDERS.get(cost_policy,
                                              self.COST_POLICY_PROVIDERS["best_quality"])
        # Partition: preferred providers first, then the rest
        preferred = [s for s in specs if s.provider in pref]
        others = [s for s in specs if s.provider not in pref]
        return preferred + others

    def select(self, capability: str = "",
               privacy: str = PrivacyLevel.PUBLIC.value,
               latency: str = "normal",
               cost: str = CostPolicy.BEST_QUALITY.value,
               model_classes: Optional[List[str]] = None,
               task: str = "",
               request_id: Optional[str] = None) -> RoutingDecision:
        """Select the best model for the given criteria.

        Returns a :class:`RoutingDecision` with full provenance, including
        the fallback chain.
        """
        req_id = request_id or str(uuid.uuid4())
        available = self._available_providers()
        specs = self._registry.list()

        # Filter: available providers only (open-weights can be self-hosted)
        specs = [s for s in specs if s.provider in available or s.open_weights]

        # Filter by capability/task
        if capability and not model_classes:
            model_classes = self.TASK_TO_CLASSES.get(capability, [])
        if model_classes:
            specs = [s for s in specs if any(
                mc in s.model_classes for mc in model_classes)]

        # If capability didn't filter, try capability list on specs
        if capability and not specs:
            specs = self._registry.by_capability(capability)

        # Filter by task-specific capability
        if task:
            task_specs = self._registry.by_capability(task)
            if task_specs:
                specs = task_specs

        # Filter by privacy
        specs = self._filter_by_privacy(specs, privacy)

        # Filter by cost policy (prefer low-cost / local providers)
        specs = self._filter_by_policy(specs, cost)

        # Sort by benchmark score (descending) then by cost (ascending if free_tier)
        def sort_key(s: ModelSpec) -> Tuple[float, float, float]:
            score = -(s.benchmark_score or 0.0)
            price = s.pricing_input or float("inf") if cost in ("low_cost", "free_only") else 0.0
            lat = -(s.latency_ms or 0.0)
            return (score, price, lat)

        specs.sort(key=sort_key)

        # Build fallback chain: walk sorted specs, pick first available
        selected: Optional[ModelSpec] = None
        fallback_chain: List[str] = []

        for s in specs:
            candidate_ref = f"{s.provider}:{s.model_id}"
            if not selected:
                provider_obj = self._manager._providers.get(s.provider)
                if provider_obj and provider_obj.is_available():
                    selected = s
                else:
                    fallback_chain.append(candidate_ref)
            else:
                fallback_chain.append(candidate_ref)

        # Ultimate fallback: Silverwing or Local
        ultimate_fallback = "silverwing:silverwing-120m-base-v1"
        if "silverwing" not in available and "local" not in available:
            ultimate_fallback = "local:local-rule"

        if not selected:
            selected_model = ultimate_fallback
            provider_name = selected_model.split(":")[0]
            reason = f"No available model for capability='{capability}', task='{task}'; using ultimate fallback"
        else:
            selected_model = f"{selected.provider}:{selected.model_id}"
            provider_name = selected.provider
            reason = (f"{capability or 'default'} + privacy={privacy} + "
                      f"cost={cost} -> {selected_model}")

        decision = RoutingDecision(
            task=task or capability or "chat",
            requested_capability=capability,
            requested_privacy=privacy,
            requested_latency=latency,
            requested_cost=cost,
            selected_model=selected_model,
            provider=provider_name,
            reason=reason,
            fallback=ultimate_fallback if selected_model != ultimate_fallback else None,
            fallback_chain=fallback_chain[:5],
            request_id=req_id,
        )

        # Log routing event
        self._event_log.record(ObservabilityEvent(
            event_type="model.routing",
            request_id=req_id,
            provider=provider_name,
            model=selected_model,
            status="ok",
            fallback=ultimate_fallback if selected_model != ultimate_fallback else None,
            provenance=privacy,
        ))

        return decision

    async def route_and_chat(self, request: ModelRequest,
                             task: str = "",
                             privacy: str = PrivacyLevel.PUBLIC.value,
                             cost: str = CostPolicy.BEST_QUALITY.value,
                             capability: str = "") -> Tuple[ModelResponse, RoutingDecision]:
        """Route a request through the router, then execute via ModelManager.

        Returns ``(response, routing_decision)`` with full telemetry.
        """
        decision = self.select(
            capability=capability, privacy=privacy, cost=cost, task=task)

        # Log request event
        self._event_log.record(ObservabilityEvent(
            event_type="model.request",
            request_id=decision.request_id,
            provider=decision.provider,
            model=decision.selected_model,
            provenance=privacy,
        ))

        start = time.monotonic()
        try:
            resp = await self._manager.achat(request)
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            resp.latency_ms = elapsed_ms

            # Estimate cost from token usage
            input_tokens = resp.usage.get("input_tokens",
                                          resp.usage.get("prompt_tokens", 0))
            output_tokens = resp.usage.get("output_tokens",
                                           resp.usage.get("completion_tokens", 0))
            cost_val = self._cost_tracker.record(
                resp.provider, resp.model, input_tokens, output_tokens,
                elapsed_ms, task=task, cost_policy=cost, success=True)
            resp.estimated_cost = cost_val

            # Log lifecycle events
            self._event_log.record(ObservabilityEvent(
                event_type="model.started", request_id=decision.request_id,
                provider=resp.provider, model=resp.model, latency_ms=elapsed_ms))
            self._event_log.record(ObservabilityEvent(
                event_type="model.completed", request_id=decision.request_id,
                provider=resp.provider, model=resp.model,
                latency_ms=elapsed_ms, status="ok",
                input_tokens=input_tokens, output_tokens=output_tokens))

            decision.latency_ms = elapsed_ms
            decision.cost_estimate = cost_val
            return resp, decision

        except Exception as e:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            log.error("Router failed for %s: %r", decision.selected_model, e)
            self._event_log.record(ObservabilityEvent(
                event_type="model.error", request_id=decision.request_id,
                provider=decision.provider, model=decision.selected_model,
                latency_ms=elapsed_ms, status="error", error=str(e)))

            decision.error = str(e)
            decision.success = False

            # Execute genuine providers from the routing fallback chain.
            # local-rule is deterministic scaffolding, not an AI provider,
            # and must never be returned as a successful model response.
            attempted = {decision.selected_model}

            for fallback_ref in decision.fallback_chain:
                if not fallback_ref or fallback_ref in attempted:
                    continue

                if fallback_ref == "local:local-rule":
                    continue

                attempted.add(fallback_ref)

                try:
                    fallback_provider, fallback_model = self._manager.provider_for(
                        fallback_ref
                    )

                    if fallback_provider is None:
                        continue

                    if not fallback_provider.is_available():
                        continue

                    self._event_log.record(ObservabilityEvent(
                        event_type="model.fallback",
                        request_id=decision.request_id,
                        provider=fallback_ref.split(":", 1)[0],
                        model=fallback_model,
                        fallback=decision.selected_model,
                        provenance=privacy,
                    ))

                    fallback_request = ModelRequest(
                        messages=request.messages,
                        model=fallback_model,
                        system=request.system,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        response_model=request.response_model,
                    )

                    fallback_start = time.monotonic()
                    fallback_resp = await fallback_provider.chat(fallback_request)
                    fallback_elapsed = round(
                        (time.monotonic() - fallback_start) * 1000,
                        2,
                    )

                    content = getattr(fallback_resp, "content", None)

                    if not isinstance(content, str) or not content.strip():
                        continue

                    fallback_resp.latency_ms = fallback_elapsed
                    decision.fallback = fallback_ref
                    decision.latency_ms = fallback_elapsed
                    decision.success = True
                    decision.error = None

                    self._event_log.record(ObservabilityEvent(
                        event_type="model.completed",
                        request_id=decision.request_id,
                        provider=fallback_ref.split(":", 1)[0],
                        model=fallback_model,
                        latency_ms=fallback_elapsed,
                        status="fallback",
                    ))

                    return fallback_resp, decision

                except Exception as fallback_error:
                    log.warning(
                        "Provider fallback failed for %s: %r",
                        fallback_ref,
                        fallback_error,
                    )

                    self._event_log.record(ObservabilityEvent(
                        event_type="model.error",
                        request_id=decision.request_id,
                        provider=fallback_ref.split(":", 1)[0],
                        model=fallback_ref,
                        status="error",
                        error=str(fallback_error),
                    ))

            # Never convert a real provider failure into local-rule output.
            raise RuntimeError(
                "No verified AI provider could complete the request. "
                f"primary={decision.selected_model}; "
                f"error={decision.error}; "
                f"fallbacks={decision.fallback_chain[:5]}"
            ) from e


__all__ = [
    "ProviderInfo", "ModelManager", "LocalProvider", "SilverwingProvider",
    "OpenAIProvider", "AnthropicProvider", "GeminiProvider", "GroqProvider",
    "OllamaProvider", "DeepSeekProvider", "LlamaCppProvider", "BedrockProvider",
    "VertexProvider", "VLLMProvider", "OpenAICompatibleProvider", "ModelRouter", "ModelRegistry", "RoutingDecision",
    "ModelSpec", "HealthStatus", "PrivacyLevel", "CostPolicy", "ModelClass",
    "CostTracker", "ObservabilityEvent", "PrivacyPolicy",
    "parse_model", "ProviderInfo", "MODEL_CATALOG",
]

