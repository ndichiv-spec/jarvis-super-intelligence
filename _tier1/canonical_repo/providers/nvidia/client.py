"""NVIDIA ProviderAdapter (spec §4).

Configurable endpoint (hosted vs self-hosted NIM). Client injectable for tests.
"""

from __future__ import annotations

from typing import Optional

from ..base import ProviderAdapter
from ..capabilities import Capability
from ..health import HealthStatus, ProviderHealth
from ..http import OpenAICompatibleClient
from ..models import PrivacyClass, ProviderModel
from ..openai_compat import OpenAICompatChatMixin
from ..secrets import SecretManager
from ..telemetry import ProviderTelemetry
from .capabilities import NVIDIA_ADAPTER_CAPABILITIES
from .config import NvidiaConfig
from .health import nvidia_health_probe
from .models import NVIDIA_DEFAULT_MODEL, NVIDIA_MODELS


class NvidiaAdapter(OpenAICompatChatMixin, ProviderAdapter):
    provider_id = "nvidia"
    display_name = "NVIDIA NIM"
    declared_capabilities = NVIDIA_ADAPTER_CAPABILITIES

    def __init__(
        self,
        config: Optional[NvidiaConfig] = None,
        secrets: Optional[SecretManager] = None,
        telemetry: Optional[ProviderTelemetry] = None,
        client: Optional[OpenAICompatibleClient] = None,
    ) -> None:
        super().__init__(secrets=secrets, telemetry=telemetry)
        self.config = config or NvidiaConfig.from_environ(secrets=secrets)
        self._http_client = client

    @property
    def configured(self) -> bool:
        return self.config.configured

    @property
    def base_url(self) -> str:
        return self.config.endpoint

    @property
    def api_key(self) -> Optional[str]:
        return self.config.api_key

    @property
    def default_model(self) -> Optional[str]:
        return self.config.model or NVIDIA_DEFAULT_MODEL

    def _client(self) -> OpenAICompatibleClient:
        if self._http_client is None:
            self._http_client = OpenAICompatibleClient(
                base_url=self.base_url, api_key=self.api_key
            )
        return self._http_client

    def _build_models(self):
        """Baseline catalog reconciled against the live ``/v1/models`` list.

        The live catalog is the source of truth: baseline entries that no longer
        exist are dropped, and newly-advertised chat-capable ids are listed so
        the fabric never advertises a model that cannot be served.  When the
        provider is unconfigured or discovery fails, the verified baseline is
        used unchanged.
        """
        if not self.configured:
            return list(NVIDIA_MODELS)
        try:
            live = set(self._client().list_models())
        except Exception:
            return list(NVIDIA_MODELS)
        if not live:
            return list(NVIDIA_MODELS)

        baseline_by_id = {m.model_id: m for m in NVIDIA_MODELS}
        kept = [m for m in NVIDIA_MODELS if m.model_id in live]
        seen = {m.model_id for m in kept}
        for model_id in sorted(live - set(baseline_by_id)):
            caps = _live_capabilities(model_id)
            kept.append(
                ProviderModel(
                    provider=self.provider_id,
                    model_id=model_id,
                    name=model_id,
                    capabilities=caps,
                    privacy_class=PrivacyClass.PUBLIC,
                )
            )
        return kept

    def _probe_health(self) -> ProviderHealth:
        if not self.configured:
            return ProviderHealth(
                provider=self.provider_id, status=HealthStatus.UNCONFIGURED
            )
        return nvidia_health_probe(self._client(), provider=self.provider_id)


def _live_capabilities(model_id: str) -> frozenset[Capability]:
    """Conservative capability inference for live-catalog ids not in baseline.

    Only advertises CHAT when the model id clearly names a generative
    instruction/chat model; nothing is claimed for embed/speech/guard ids.
    """
    if any(tok in model_id for tok in ("embed", "rerank", "asr", "tts")):
        return frozenset()
    chat_tokens = (
        "instruct",
        "chat",
        "flash",
        "lightning",
        "nemotron",
        "llama",
        "deepseek",
        "qwen",
        "mistral",
    )
    if any(tok in model_id for tok in chat_tokens):
        return frozenset({Capability.CHAT})
    return frozenset()