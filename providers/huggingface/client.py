"""Hugging Face ProviderAdapter (spec §9).

Role split, never conflated:

* **registry role** — model, dataset and adapter metadata lookups against
  ``huggingface.co/api``.  This role is available whenever ``JARVIS_HF_TOKEN``
  is set.

* **inference role** — chat, streaming and embeddings through an OpenAI-compatible
  inference endpoint.  This role is **only** available when
  ``JARVIS_HF_INFERENCE_ENDPOINT`` is set.  A Hugging Face *repo* is never
  assumed to be an inference endpoint (spec §9).

The adapter uses the shared :class:`~providers.http.OpenAICompatibleClient` for
inference (same as OpenAI/NVIDIA).  The client is injectable for tests.
"""

from __future__ import annotations

from typing import List, Optional

from ..base import (
    Message,
    ProviderAdapter,
    ProviderRequest,
)
from ..health import HealthStatus, ProviderHealth
from ..http import OpenAICompatibleClient
from ..openai_compat import OpenAICompatChatMixin
from ..secrets import SecretManager
from ..telemetry import ProviderTelemetry
from .capabilities import HF_ADAPTER_CAPABILITIES
from .config import HuggingFaceConfig
from .health import hf_health_probe
from .models import HF_MODELS


class HuggingFaceAdapter(OpenAICompatChatMixin, ProviderAdapter):
    """Hugging Face provider adapter.

    ``configured`` reflects the *registry* role (``JARVIS_HF_TOKEN`` set).
    Inference capabilities (chat/stream/embeddings) additionally require
    ``JARVIS_HF_INFERENCE_ENDPOINT``; the adapter is honest about this:
    when the token is present but no endpoint is configured, chat/stream
    raise :class:`ProviderUnconfigured`.
    """

    provider_id = "hf"
    display_name = "Hugging Face"
    declared_capabilities = HF_ADAPTER_CAPABILITIES

    def __init__(
        self,
        config: Optional[HuggingFaceConfig] = None,
        secrets: Optional[SecretManager] = None,
        telemetry: Optional[ProviderTelemetry] = None,
        client: Optional[OpenAICompatibleClient] = None,
    ) -> None:
        super().__init__(secrets=secrets, telemetry=telemetry)
        self.config = config or HuggingFaceConfig.from_environ(secrets=secrets)
        self._http_client = client  # injectable for tests

    # -- config surface -----------------------------------------------------
    @property
    def configured(self) -> bool:
        return self.config.configured

    @property
    def base_url(self) -> str:
        return self.config.inference_endpoint or ""

    @property
    def api_key(self) -> Optional[str]:
        return self.config.token

    @property
    def default_model(self) -> Optional[str]:
        return self.config.model

    @property
    def inference_ready(self) -> bool:
        """True iff both a token and an inference endpoint are configured."""
        return bool(self.config.token) and bool(self.config.inference_endpoint)

    def _dispatch_client(self) -> OpenAICompatibleClient:
        if self._http_client is None:
            if not self.config.inference_endpoint:
                from ..errors import ProviderUnconfigured

                raise ProviderUnconfigured(
                    "hf: no inference endpoint configured "
                    "(set JARVIS_HF_INFERENCE_ENDPOINT)"
                )
            self._http_client = OpenAICompatibleClient(
                base_url=self.config.inference_endpoint,
                api_key=self.config.token,
            )
        return self._http_client

    def _client(self) -> OpenAICompatibleClient:
        return self._dispatch_client()

    # -- models ---------------------------------------------------------------
    def _build_models(self):
        return HF_MODELS

    # -- health ---------------------------------------------------------------
    def _probe_health(self) -> ProviderHealth:
        if not self.configured:
            return ProviderHealth(
                provider=self.provider_id, status=HealthStatus.UNCONFIGURED
            )
        if not self.inference_ready:
            return ProviderHealth(
                provider=self.provider_id,
                status=HealthStatus.UNKNOWN,
                detail="registry token present; no inference endpoint configured",
            )
        return hf_health_probe(
            self._client(), provider=self.provider_id,
            detail="hf inference endpoint",
        )

    # -- registry helpers -----------------------------------------------------
    def hub_health(self, *, force: bool = True) -> ProviderHealth:
        """Real-registry health: an authenticated whoami probe (spec §4/§21).

        Uses the canonical status vocabulary — the reported state is whatever
        the live Hub actually answered (healthy / authentication_failed /
        forbidden / rate_limited / timeout / unavailable / unconfigured).
        """
        if not self.config.token:
            return ProviderHealth(
                provider=self.provider_id, status=HealthStatus.UNCONFIGURED
            )
        from .hub import hf_auth_probe

        return hf_auth_probe(
            self.config.token,
            api_base=self.config.api_base,
            timeout=max(10.0, float(self.config.timeout or 15)),
        )

    def discover_models(
        self,
        *,
        search: Optional[str] = None,
        author: Optional[str] = None,
        limit: int = 20,
        pipeline_tag: Optional[str] = None,
    ) -> List[dict]:
        """Discover real models from the live Hub (spec §2).

        Returns list of :class:`~providers.huggingface.hub.HfModelInfo` as
        dicts; does not require (but benefits from) the configured token.
        """
        from .hub import discover_models

        infos = discover_models(
            self.config.token,
            search=search,
            author=author,
            limit=limit,
            pipeline_tag=pipeline_tag,
            api_base=self.config.api_base,
            timeout=max(10.0, float(self.config.timeout or 15)),
        )
        return [dict(info.__dict__.items()) for info in infos]

    def hub_identity(self) -> dict:
        """Resolve the authenticated Hub identity (whoami), if a token exists."""
        if not self.config.token:
            return {}
        from .hub import whoami_token

        try:
            _, payload = whoami_token(
                self.config.token,
                api_base=self.config.api_base,
                timeout=max(10.0, float(self.config.timeout or 15)),
            )
            return payload or {}
        except Exception:
            return {}

    def list_models_remote(self) -> List[str]:
        """Query the HuggingFace API for the configured user/org models.

        Author is resolved from the authenticated whoami identity so we list
        *our* models — not a popularity list (spec §2).
        """
        if not self.config.token:
            from ..errors import ProviderUnconfigured

            raise ProviderUnconfigured("hf: no token (set JARVIS_HF_TOKEN)")
        identity = self.hub_identity()
        author = ""
        for candidate in (
            identity.get("name"),
            (identity.get("user") or {}).get("name"),
            (identity.get("org") or {}).get("name"),
        ):
            if candidate:
                author = str(candidate)
                break
        try:
            discovered = self.discover_models(author=author or None, limit=100)
        except Exception:
            discovered = []
        return [row["model_id"] for row in discovered]

    # -- chat (delegates to OpenAICompatChatMixin) ---------------------------
    def _resolve_model(self, request: ProviderRequest) -> str:
        model = request.model or self.default_model
        if not model:
            raise self._unconfigured_model()
        return model
