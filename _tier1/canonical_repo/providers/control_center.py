"""Phase 6 — Provider Control Center (spec §2).

Provides a single entry point that reports the *real* operational state of
every provider the JARVIS platform can use:

    IMPLEMENTED   – the adapter exists in code
    CONFIGURED   – the required env vars are present
    AUTHENTICATED – the API key / token is accepted by the provider
    HEALTHY      – a real probe against the live endpoint succeeded
    READY        – healthy AND has at least one usable model

The center never infers readiness merely because an adapter exists.  Every
state is derived from a real probe or a real credential check.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from providers.health import (
    HealthCache,
    HealthStatus,
    ProviderHealth,
    get_inference_result,
)
from providers.secrets import SecretManager


# --------------------------------------------------------------------------- #
# Provider metadata — one entry per IMPLEMENTED adapter
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProviderMeta:
    provider: str
    display_name: str
    module: str
    secret_names: tuple[str, ...]
    probe: Any  # callable(secrets: SecretManager) -> ProviderHealth
    capabilities: tuple[str, ...]


_PROVIDER_META: dict[str, ProviderMeta] = {}
_registry_built = False


def register_provider(meta: ProviderMeta) -> None:
    _PROVIDER_META[meta.provider] = meta


def _build_registry(secrets: Optional[SecretManager] = None) -> None:
    """Build the provider registry with real probe callables."""
    global _registry_built
    if _registry_built:
        return
    sm = secrets or SecretManager()

    # ---- OpenAI ----
    from providers.openai.config import OpenAIConfig
    from providers.openai.health import openai_health_probe, OpenAICompatibleClient
    from providers.openai.capabilities import OPENAI_ADAPTER_CAPABILITIES

    def _probe_openai(sm: SecretManager) -> ProviderHealth:
        config = OpenAIConfig.from_environ(secrets=sm)
        if not config.configured or not config.api_key:
            return ProviderHealth(provider="openai", status=HealthStatus.UNCONFIGURED,
                                  detail="not configured")
        client = OpenAICompatibleClient(base_url=config.base_url, api_key=config.api_key)
        return openai_health_probe(client, provider="openai")

    register_provider(ProviderMeta(
        provider="openai", display_name="OpenAI", module="providers.openai",
        secret_names=("OPENAI_API_KEY", "JARVIS_OPENAI_API_KEY"),
        probe=_probe_openai,
        capabilities=tuple(sorted(c.value for c in OPENAI_ADAPTER_CAPABILITIES)),
    ))

    # ---- NVIDIA ----
    from providers.nvidia.config import NvidiaConfig
    from providers.nvidia.health import nvidia_health_probe, OpenAICompatibleClient as NvClient
    from providers.nvidia.capabilities import NVIDIA_ADAPTER_CAPABILITIES

    def _probe_nvidia(sm: SecretManager) -> ProviderHealth:
        config = NvidiaConfig.from_environ(secrets=sm)
        if not config.configured or not config.api_key:
            return ProviderHealth(provider="nvidia", status=HealthStatus.UNCONFIGURED,
                                  detail="not configured")
        client = NvClient(base_url=config.endpoint, api_key=config.api_key)
        return nvidia_health_probe(client, provider="nvidia")

    register_provider(ProviderMeta(
        provider="nvidia", display_name="NVIDIA NIM", module="providers.nvidia",
        secret_names=("NVIDIA_API_KEY", "JARVIS_NVIDIA_API_KEY"),
        probe=_probe_nvidia,
        capabilities=tuple(sorted(c.value for c in NVIDIA_ADAPTER_CAPABILITIES)),
    ))

    # ---- Google ----
    from providers.google.config import GoogleConfig
    from providers.google.health import google_health_probe, GoogleModelsAPI
    from providers.google.capabilities import GOOGLE_ADAPTER_CAPABILITIES

    def _probe_google(sm: SecretManager) -> ProviderHealth:
        config = GoogleConfig.from_environ(secrets=sm)
        if not config.configured or not config.api_key:
            return ProviderHealth(provider="google", status=HealthStatus.UNCONFIGURED,
                                  detail="not configured")
        api = GoogleModelsAPI(api_key=config.api_key, project=config.project, location=config.location)
        return google_health_probe(api, provider="google")

    register_provider(ProviderMeta(
        provider="google", display_name="Google Vertex AI / Gemini", module="providers.google",
        secret_names=("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
                      "JARVIS_GOOGLE_API_KEY"),
        probe=_probe_google,
        capabilities=tuple(sorted(c.value for c in GOOGLE_ADAPTER_CAPABILITIES)),
    ))

    # ---- AWS ----
    from providers.aws.config import AwsConfig
    from providers.aws.health import aws_health_probe, BedrockClients
    from providers.aws.capabilities import AWS_ADAPTER_CAPABILITIES

    def _probe_aws(sm: SecretManager) -> ProviderHealth:
        config = AwsConfig.from_environ(secrets=sm)
        if not config.configured:
            return ProviderHealth(provider="aws", status=HealthStatus.UNCONFIGURED,
                                  detail="not configured")
        clients = BedrockClients(region=config.region)
        return aws_health_probe(clients, provider="aws")

    register_provider(ProviderMeta(
        provider="aws", display_name="AWS Bedrock", module="providers.aws",
        secret_names=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"),
        probe=_probe_aws,
        capabilities=tuple(sorted(c.value for c in AWS_ADAPTER_CAPABILITIES)),
    ))

    # ---- Hugging Face ----
    from providers.huggingface.config import HuggingFaceConfig
    from providers.huggingface.health import hf_health_probe, OpenAICompatibleClient as HfClient
    from providers.huggingface.capabilities import HF_ADAPTER_CAPABILITIES

    def _probe_hf(sm: SecretManager) -> ProviderHealth:
        config = HuggingFaceConfig.from_environ(secrets=sm)
        if not config.configured or not config.token:
            return ProviderHealth(provider="hf", status=HealthStatus.UNCONFIGURED,
                                  detail="not configured")
        # HF is primarily a registry; if an inference endpoint is configured,
        # probe it.  Otherwise verify token auth via whoami.
        if config.inference_endpoint:
            client = HfClient(base_url=config.inference_endpoint, api_key=config.token)
            return hf_health_probe(client, provider="hf", detail="inference endpoint")
        # Registry-only path: verify token via whoami (no network call needed for listing)
        try:
            from huggingface_hub import HfApi
            api = HfApi()
            whoami = api.whoami(token=config.token)
            return ProviderHealth(
                provider="hf", status=HealthStatus.HEALTHY,
                latency_ms=0,
                detail=f"authenticated as {whoami.get('name', whoami.get('sub', '?'))} (registry-only, no inference endpoint)",
                models_found=0,
            )
        except Exception as exc:
            return ProviderHealth(provider="hf", status=HealthStatus.AUTHENTICATION_FAILED,
                                  detail=str(exc)[:200])

    register_provider(ProviderMeta(
        provider="hf", display_name="Hugging Face", module="providers.huggingface",
        secret_names=("HF_TOKEN", "JARVIS_HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
        probe=_probe_hf,
        capabilities=tuple(sorted(c.value for c in HF_ADAPTER_CAPABILITIES)),
    ))

    _registry_built = True


@dataclass
class ProviderStatus:
    """Full operational status of a provider (spec §1, §2)."""
    provider: str
    display_name: str
    implemented: bool
    configured: bool
    authenticated: bool
    healthy: bool
    ready: bool
    health_status: str
    model_list_available: bool = False
    inference_verified: bool = False
    inference_healthy: bool = False
    inference_authorized: bool = False
    capabilities: list[str] = field(default_factory=list)
    verified_capabilities: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    latency_ms: Optional[float] = None
    errors: str = ""
    last_checked: float = field(default_factory=time.time)
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "display_name": self.display_name,
            "implemented": self.implemented,
            "configured": self.configured,
            "authenticated": self.authenticated,
            "healthy": self.healthy,
            "ready": self.ready,
            "status": self.health_status,
            "model_list_available": self.model_list_available,
            "inference_verified": self.inference_verified,
            "inference_healthy": self.inference_healthy,
            "inference_authorized": self.inference_authorized,
            "capabilities": self.capabilities,
            "verified_capabilities": self.verified_capabilities,
            "models": self.models,
            "latency_ms": self.latency_ms,
            "errors": self.errors,
            "last_checked": self.last_checked,
            "actions": self.actions,
        }


class ProviderControlCenter:
    """Central provider status + health registry (spec §2, §11, §13).

    Usage::

        center = ProviderControlCenter()
        center.refresh()          # run all real probes
        report = center.report()  # full status dict
        center.check_provider("openai")  # single provider
    """

    def __init__(self, secrets: Optional[SecretManager] = None) -> None:
        self._sm = secrets or SecretManager()
        _build_registry(self._sm)
        self._cache: dict[str, HealthCache] = {}
        self._last_health: dict[str, ProviderHealth] = {}
        self._last_status: dict[str, ProviderStatus] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def list_providers(self) -> list[str]:
        """Return all *implemented* provider IDs."""
        return list(_PROVIDER_META.keys())

    def is_configured(self, provider: str) -> bool:
        """True iff the required secret/env vars are present (spec §1)."""
        meta = _PROVIDER_META.get(provider)
        if meta is None:
            return False
        return any(self._sm.get(k) for k in meta.secret_names)

    def check_provider(self, provider: str, *, force: bool = False) -> ProviderStatus:
        """Run (or reuse cached) probe for one provider and build status."""
        meta = _PROVIDER_META.get(provider)
        if meta is None:
            return ProviderStatus(
                provider=provider,
                display_name=provider.title(),
                implemented=False,
                configured=False,
                authenticated=False,
                healthy=False,
                ready=False,
                health_status=HealthStatus.UNCONFIGURED.value,
                errors="provider adapter not implemented",
                actions=[],
            )

        if provider not in self._cache:
            self._cache[provider] = HealthCache(
                provider=provider,
                probe=lambda p=provider: self._run_probe(p),
                ttl=30.0,
            )

        health = self._cache[provider].get(force=force)
        configured = self.is_configured(provider)
        recorded = get_inference_result(provider)
        if recorded is not None and configured and health.status in (
            HealthStatus.HEALTHY,
            HealthStatus.DEGRADED,
        ):
            health = replace(
                health,
                status=recorded.status,
                endpoint_reachable=True,
                credential_authorized=recorded.credential_authorized,
                inference_verified=recorded.inference_verified,
                models_found=max(health.models_found, recorded.models_found),
                detail=recorded.detail or health.detail,
            )
        self._last_health[provider] = health

        caps = list(meta.capabilities)
        verified = list(caps) if health.is_authenticated else []
        models: list[str] = []

        # Map health status to authenticated flag
        authenticated = health.status in (
            HealthStatus.HEALTHY, HealthStatus.DEGRADED,
        )
        if not authenticated and configured and health.status is HealthStatus.AUTHENTICATION_FAILED:
            authenticated = False  # auth explicitly failed

        actions = self._available_actions(provider, health, configured)

        status = ProviderStatus(
            provider=provider,
            display_name=meta.display_name,
            implemented=True,
            configured=configured,
            authenticated=authenticated,
            healthy=health.is_healthy,
            ready=health.is_inference_ready,
            health_status=health.status.value,
            model_list_available=health.endpoint_reachable and health.models_found > 0,
            inference_verified=health.inference_verified,
            inference_healthy=health.inference_verified and health.is_healthy,
            inference_authorized=health.credential_authorized is True or health.inference_verified,
            capabilities=caps,
            verified_capabilities=verified,
            models=models,
            latency_ms=health.latency_ms,
            errors=health.detail,
            last_checked=health.checked_at,
            actions=actions,
        )
        self._last_status[provider] = status
        return status

    def _run_probe(self, provider: str) -> ProviderHealth:
        """Execute the real probe for a provider."""
        meta = _PROVIDER_META.get(provider)
        if meta is None:
            return ProviderHealth(
                provider=provider, status=HealthStatus.UNKNOWN,
                detail="not implemented",
            )
        return meta.probe(self._sm)

    def _available_actions(
        self, provider: str, health: ProviderHealth, configured: bool
    ) -> list[str]:
        actions = ["test", "refresh"]
        if not configured:
            actions = ["connect"]
        elif health.status is HealthStatus.AUTHENTICATION_FAILED:
            actions = ["connect", "rotate_credentials"]
        elif health.is_authenticated:
            actions.extend(["inspect_capabilities", "disconnect"])
        return actions

    def refresh(
        self, providers: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """Run real probes for all (or specified) providers."""
        targets = providers or self.list_providers()
        for p in targets:
            self.check_provider(p, force=True)
        return {
            "checked_at": time.time(),
            "providers": {p: s.to_dict() for p, s in self._last_status.items()},
        }

    def report(self) -> dict[str, Any]:
        """Return the full status report from the last probe cycle."""
        if not self._last_status:
            for p in self.list_providers():
                self.check_provider(p, force=True)
        return {
            "checked_at": time.time(),
            "providers": {p: s.to_dict() for p, s in self._last_status.items()},
        }

    # ------------------------------------------------------------------ #
    # Routing (spec §11 — connects fabric to the Model Gateway)
    # ------------------------------------------------------------------ #

    def route_task(
        self, task_text: str, *, policy: str = "best_quality",
        include_brain: bool = True,
    ) -> dict[str, Any]:
        """Route a task to the best *ready* provider based on real health.

        Only providers that are authenticated + healthy (i.e. have passed a
        real probe) are considered.  The JARVIS Brain remote endpoint is
        checked first when configured (spec §9); if it is unreachable the
        router falls through to cloud providers, then to local/Silverwing.
        """
        # Ensure all providers have been probed
        for p in self.list_providers():
            if p not in self._last_health:
                self.check_provider(p, force=True)

        # 1. Check JARVIS Brain remote (spec §9 — preferred general-purpose path)
        routing_chain: list[dict[str, Any]] = []

        brain_endpoint = self._sm.get("JARVIS_BRAIN_ENDPOINT") or ""
        if include_brain and brain_endpoint:
            brain_healthy = self._probe_brain_endpoint(brain_endpoint)
            if brain_healthy:
                routing_chain.append({
                    "provider": "jarvis-brain",
                    "endpoint": brain_endpoint,
                    "model": self._sm.get("JARVIS_BRAIN_MODEL") or "jarvis-brain-qwen3-4b-v1",
                    "reason": "preferred remote brain (Qwen3-4B)",
                })

        # 2. Fall through to configured + authenticated cloud providers
        from providers.routing import ProviderRouter, TaskClassifier
        from providers.bootstrap import bootstrap_fabric

        reg = bootstrap_fabric()
        router = ProviderRouter(registry=reg, policy=policy)
        decision = router.route_text(task_text)

        if decision.selected_provider:
            # Find the real health status of the selected provider
            adapter = reg.get(decision.selected_provider)
            if adapter:
                h = adapter.health(force=False)
                if h.is_ready:
                    routing_chain.append({
                        "provider": decision.selected_provider,
                        "model": decision.selected_model,
                        "reason": decision.reason,
                        "health_status": h.status.value,
                        "latency_ms": h.latency_ms,
                    })
                else:
                    # Provider is configured but not ready — skip in routing chain
                    pass

        # 3. Add fallback chain — only ready providers
        for fb in decision.fallback_chain:
            fb_provider = fb.get("provider", "")
            adapter = reg.get(fb_provider) if fb_provider else None
            if adapter:
                h = adapter.health(force=False)
                if h.is_ready:
                    routing_chain.append({
                        "provider": fb["provider"],
                        "model": fb["model"],
                        "reason": f"fallback ({h.status.value})",
                        "health_status": h.status.value,
                    })

        selected = routing_chain[0] if routing_chain else None
        selected_provider = selected["provider"] if selected else None

        # If no ready provider, check Silverwing fallback
        silverwing_available = bool(self._sm.get("SILVERWING_ENDPOINT"))
        if not selected:
            silverwing_ep = self._sm.get("SILVERWING_ENDPOINT") or os.environ.get(
                "SILVERWING_ENDPOINT", ""
            )
            if silverwing_ep:
                routing_chain.append({
                    "provider": "silverwing",
                    "endpoint": silverwing_ep,
                    "model": self._sm.get("SILVERWING_MODEL", "silverwing-120m-base-v1"),
                    "reason": "offline local fallback",
                    "health_status": "offline",
                    "latency_ms": None,
                })
                selected = routing_chain[-1]
                selected_provider = "silverwing"

        result = {
            "task": task_text,
            "policy": policy,
            "selected_provider": selected_provider,
            "selected_model": selected["model"] if selected else None,
            "routing_chain": routing_chain,
            "no_ready_providers": selected is None,
            "brain_configured": bool(brain_endpoint),
            "brain_healthy": bool(routing_chain) and routing_chain[0].get("provider") == "jarvis-brain",
            "silverwing_available": silverwing_available,
        }
        return result

    def _probe_brain_endpoint(self, endpoint: str, timeout: float = 10.0) -> bool:
        """Quick reachability check for the JARVIS Brain (spec §9)."""
        import httpx
        try:
            root = endpoint.rstrip("/").replace("/v1", "")
            # Try /v1/chat/completions with a minimal payload
            url = endpoint.rstrip("/") + "/chat/completions"
            resp = httpx.post(
                url,
                headers={"Authorization": "Bearer " + (self._sm.get("JARVIS_BRAIN_API_KEY") or "")},
                json={"model": "jarvis-brain-qwen3-4b-sft-v1",
                      "messages": [{"role": "user", "content": "ok"}],
                      "max_tokens": 1},
                timeout=timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Admin control actions (spec §2) — never display raw secrets
    # ------------------------------------------------------------------ #

    def connect(self, provider: str, credentials: dict[str, str]) -> dict[str, Any]:
        """Inject credentials at runtime (not persisted)."""
        meta = _PROVIDER_META.get(provider)
        if meta is None:
            return {"provider": provider, "success": False, "error": "not implemented"}
        for key in meta.secret_names:
            for ck, cv in credentials.items():
                if ck.upper() in key.upper() or key.upper() in ck.upper():
                    self._sm.put(key, cv)
        self._cache.pop(provider, None)
        status = self.check_provider(provider, force=True)
        return {"provider": provider, "success": status.configured,
                "status": status.health_status}

    def disconnect(self, provider: str) -> dict[str, Any]:
        """Clear provider from cache (runtime disconnect)."""
        self._cache.pop(provider, None)
        self._last_status.pop(provider, None)
        self._last_health.pop(provider, None)
        return {"provider": provider, "success": True, "status": "disconnected"}

    def test(self, provider: str) -> dict[str, Any]:
        """Run a real probe for a single provider (spec §3, §4)."""
        return self.check_provider(provider, force=True).to_dict()

    def inspect_capabilities(self, provider: str) -> dict[str, Any]:
        """Return declared vs verified capabilities (spec §3, §11)."""
        meta = _PROVIDER_META.get(provider)
        if meta is None:
            return {"provider": provider, "declared": [], "verified": [],
                    "note": "not implemented"}
        health = self._last_health.get(provider)
        if health is None:
            self.check_provider(provider, force=True)
            health = self._last_health.get(provider)
        verified = list(meta.capabilities) if (health and health.is_authenticated) else []
        return {
            "provider": provider,
            "display_name": meta.display_name,
            "declared": list(meta.capabilities),
            "verified": verified,
            "health_status": health.status.value if health else "unknown",
        }

    def rotate_credentials(
        self, provider: str, new_credentials: dict[str, str]
    ) -> dict[str, Any]:
        """Replace credentials at runtime."""
        return self.connect(provider, new_credentials)
