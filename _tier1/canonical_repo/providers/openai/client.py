"""OpenAI ProviderAdapter for the JARVIS Provider Fabric (spec §6).

Used as a reasoning/tool-capability provider, never as "the JARVIS platform".
The key is read via the fabric SecretManager (never the model context) and the
client is injectable for tests.
"""

from __future__ import annotations

from typing import Optional

from ..base import Capability, ProviderAdapter
from ..health import ProviderHealth
from ..http import OpenAICompatibleClient
from ..openai_compat import OpenAICompatChatMixin
from ..secrets import SecretManager
from ..telemetry import ProviderTelemetry
from .capabilities import OPENAI_ADAPTER_CAPABILITIES
from .config import OpenAIConfig
from .health import openai_health_probe
from .models import OPENAI_MODELS


class OpenAIAdapter(OpenAICompatChatMixin, ProviderAdapter):
    provider_id = "openai"
    display_name = "OpenAI"
    declared_capabilities = OPENAI_ADAPTER_CAPABILITIES

    def __init__(
        self,
        config: Optional[OpenAIConfig] = None,
        secrets: Optional[SecretManager] = None,
        telemetry: Optional[ProviderTelemetry] = None,
        client: Optional[OpenAICompatibleClient] = None,
    ) -> None:
        super().__init__(secrets=secrets, telemetry=telemetry)
        self.config = config or OpenAIConfig.from_environ(secrets=secrets)
        self._http_client = client  # injectable for tests

    # -- config surface -----------------------------------------------------
    @property
    def configured(self) -> bool:
        return self.config.configured

    @property
    def base_url(self) -> str:
        return self.config.base_url

    @property
    def api_key(self) -> Optional[str]:
        return self.config.api_key

    @property
    def default_model(self) -> Optional[str]:
        return self.config.model

    def _dispatch_client(self) -> OpenAICompatibleClient:
        if self._http_client is None:
            self._http_client = OpenAICompatibleClient(
                base_url=self.base_url, api_key=self.api_key
            )
        return self._http_client

    def _client(self) -> OpenAICompatibleClient:
        return self._dispatch_client()

    # -- models ---------------------------------------------------------------
    def _build_models(self):
        return OPENAI_MODELS

    # -- health ---------------------------------------------------------------
    def _probe_health(self) -> ProviderHealth:
        if not self.configured:
            from ..health import HealthStatus

            return ProviderHealth(
                provider=self.provider_id, status=HealthStatus.UNCONFIGURED
            )
        return openai_health_probe(self._client(), provider=self.provider_id)