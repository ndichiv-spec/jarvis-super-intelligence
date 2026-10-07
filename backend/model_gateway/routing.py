"""Model routing in the AI platform.

Extends the platform's existing router: a request is routable to Silverwing,
OpenAI, Anthropic, Google, DeepSeek, Ollama, local models, or any other
approved provider.  Silverwing is a first-class provider.

        TASK
          |--> capability map
          |--> available providers (health)
          |--> policy (privacy / cost / availability)
          v
    Silverwing or another approved model

Fallbacks (spec section 28) are ALWAYS recorded: a fallback decision is logged
and the response metadata carries ``fallback_from`` so the UI never presents a
non-Silverwing answer as a Silverwing answer.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .client import SilverwingClient
from .models import GatewayError, GatewayResponse

log = logging.getLogger("model_gateway.routing")

# Task -> required capabilities (spec sections 16, 32).
TASK_CAPABILITIES: dict[str, list[str]] = {
    "conversation": ["text-generation"],
    "chat": ["text-generation"],
    "coding": ["coding"],
    "reasoning": ["reasoning"],
    "math": ["math"],
    "research": ["text-generation", "reasoning"],
    "summarization": ["text-generation"],
    "embeddings": ["embeddings"],
    "vision": ["vision"],
    "image-generation": ["image-generation"],
    "tool-use": ["tool-use"],
}

# Provider preference per policy (approved fallback order).
POLICY_PROVIDERS: dict[str, list[str]] = {
    "silverwing_first": [
        "silverwing",
        "openai",
        "anthropic",
        "google",
        "deepseek",
        "ollama",
        "local",
    ],
    "local_first": ["silverwing", "ollama", "local", "openai"],
    "best_quality": ["anthropic", "openai", "google", "silverwing"],
    "low_cost": ["silverwing", "ollama", "deepseek", "openai"],
    "private_only": ["silverwing", "local"],
}


@dataclass
class RoutingDecision:
    """Provenance of a routing decision (spec section 28)."""

    requested_model: str
    selected_provider: str
    selected_model: str
    capability: str = "text-generation"
    policy: str = "silverwing_first"
    fallback_from: str | None = None
    reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_model": self.requested_model,
            "selected_provider": self.selected_provider,
            "selected_model": self.selected_model,
            "capability": self.capability,
            "policy": self.policy,
            "fallback_from": self.fallback_from,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class ModelGateway:
    """Platform routing boundary: chooses a provider then dispatches.

    Components (rooms/agents/tools) call :meth:`chat` / :meth:`generate`; they
    never talk to providers directly.
    """

    def __init__(
        self, silverwing: SilverwingClient | None = None, policy: str = "silverwing_first"
    ):
        self.silverwing = silverwing or SilverwingClient()
        self.policy = policy

    # ------------------------------------------------------------------ #
    # Routing
    # ------------------------------------------------------------------ #
    async def _select(
        self,
        capability: str,
        requested_model: str | None,
        prefer_silverwing: bool = True,
    ) -> tuple[str, str, str | None]:
        """Return ``(provider, model_id, fallback_from)``.

        Silverwing is selected when the runtime reports the requested (or
        default) model as registered and its capabilities cover ``capability``.
        The selection source is the RUNTIME's ``/v1/models`` (the platform
        never reads weight manifests locally); the local registry is only a
        secondary fallback when the runtime is unreachable.
        """
        requested = (requested_model or self.silverwing.model).strip()
        model = await self._lookup_runtime_model(requested)
        if model is None:
            model = self._lookup_local_registry(requested)

        if model is not None and model.status not in ("archived",):
            caps = list(model.capabilities)
            if capability in caps or capability == "text-generation" or not caps:
                return "silverwing", model.id, None
            # Silverwing exists but lacks the capability -> record fallback.
            return "provider", requested, f"silverwing:{model.id}"

        # Silverwing is registered but model unknown -> fallback from default.
        if prefer_silverwing:
            return "provider", requested, "silverwing"

        return "silverwing", requested, None

    async def _lookup_runtime_model(self, ref: str) -> Any:
        """Ask the runtime registry (/v1/models) for a model by id or full id."""
        try:
            models = await self.silverwing.models()
        except Exception:
            return None
        for m in models:
            if m.id == ref:
                return m
            # Accept a short base ref like "120m-base-v1" -> full id
            # (matches "silverwing-120m-base-v1" from ref "120m-base-v1"),
            # without false-matching unrelated models that share only a
            # version suffix (e.g. "jarvis-brain-qwen3-4b-v1" for ref
            # "silverwing-120m-base-v1").
            if m.id.endswith(f"-{ref}") and ref != m.id:
                return m
        return None

    def _lookup_local_registry(self, ref: str) -> Any:
        """Local-registry fallback (dev setups that DO have the repo)."""
        try:
            from silverwing_runtime.config import RuntimeConfig
            from silverwing_runtime.model_registry import SilverwingRegistry

            reg = SilverwingRegistry(RuntimeConfig())
            entry = reg.lookup(ref)
            if entry is None:
                return None
            try:
                from backend.model_gateway.models import GatewayModel

                return GatewayModel(
                    id=entry.full_id,
                    context_length=entry.context_length,
                    parameters=entry.parameter_count,
                    capabilities=list(entry.capabilities),
                    status=entry.status,
                )
            except Exception:
                return entry
        except Exception:
            return None

    async def chat(
        self,
        messages: list[dict[str, str]],
        task: str = "chat",
        model: str | None = None,
        policy: str | None = None,
        system: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> tuple[GatewayResponse, RoutingDecision]:
        """Route and dispatch a chat request.  Returns ``(response, decision)``."""
        policy = policy or self.policy
        capability = TASK_CAPABILITIES.get(task, ["text-generation"])[0]
        provider, model_id, fallback_from = await self._select(
            capability,
            model,
            prefer_silverwing=True,
        )

        # Silverwing path. Health is refreshed (no stale cache) so a single
        # slow probe under CPU load cannot misroute a request to fallback.
        silverwing_health = await self.silverwing.health(refresh=True)
        if provider == "silverwing" and silverwing_health.is_healthy:
            decision = RoutingDecision(
                requested_model=model or self.silverwing.model,
                selected_provider="silverwing",
                selected_model=model_id,
                capability=capability,
                policy=policy,
                fallback_from=fallback_from,
                reason="silverwing selected (healthy + capability match)",
            )
            chat_kwargs: dict[str, Any] = {"model": model_id}
            if system is not None:
                chat_kwargs["system"] = system
            if timeout is not None:
                chat_kwargs["timeout"] = timeout
            chat_kwargs.update(kwargs)
            try:
                resp = await self.silverwing.chat(messages, **chat_kwargs)
            except GatewayError:
                raise
            except Exception as exc:
                # Transient transport failure mid-chat: re-probe once. If the
                # runtime is still healthy the failure was transient -> raise a
                # retryable error, NOT an "offline" verdict. Only a confirmed
                # unhealthy runtime proceeds to the fallback path below.
                silverwing_health = await self.silverwing.health(refresh=True)
                if silverwing_health.is_healthy:
                    raise GatewayError(
                        f"Silverwing chat transiently failed ({exc}); retry the request.",
                        code="gw_chat_transient",
                    )
                log.warning("silverwing chat failed and runtime unhealthy: %r", exc)
            else:
                self._record(decision, resp)
                return resp, decision

        # Silverwing offline -> approved fallback (recorded ONLY after success;
        # a failed fallback always raises so nothing unreachable is claimed).
        fallback_resp = await self._fallback_chat(messages, capability, system=system, **kwargs)
        decision = RoutingDecision(
            requested_model=model or self.silverwing.model,
            selected_provider=fallback_resp.metadata.get("provider", "openai"),
            selected_model=fallback_resp.model,
            capability=capability,
            policy=policy,
            fallback_from=f"silverwing:{model_id}",
            reason=f"silverwing {silverwing_health.status.value}; using approved fallback",
        )
        self._record(decision, fallback_resp)
        return fallback_resp, decision

    async def generate(self, prompt: str, **kwargs: Any) -> tuple[GatewayResponse, RoutingDecision]:
        return await self.chat([{"role": "user", "content": prompt}], task="chat", **kwargs)

    # ------------------------------------------------------------------ #
    # Fallbacks
    # ------------------------------------------------------------------ #
    async def _fallback_chat(
        self, messages: list[dict[str, str]], _capability: str, *,
        system: str | None = None, **_kwargs: Any,
    ) -> GatewayResponse:
        """Dispatch to an approved platform provider (OpenAI first).

        This uses the existing platform provider layer (silverwing-backend's
        ModelRouter) when reachable; otherwise raises a GatewayError which the
        caller can surface honestly.
        """
        # 1) Try the platform's existing provider manager.
        try:
            from jarvis_backend.gateway import provider_gateway  # type: ignore[import-not-found]

            # _bypass_gateway=True prevents recursion: we're already inside
            # ModelGateway (called via ProviderGateway), so the fallback must
            # go straight to the model_provider path, not re-enter ModelGateway.
            result = await provider_gateway.chat(messages, model=None, system=system, _bypass_gateway=True)
            return GatewayResponse(
                content=result["content"],
                model=result["model"],
                latency_ms=float(result.get("latency_ms") or 0.0),
                metadata={"provider": "openai"},
            )
        except Exception as exc:
            log.warning("platform provider fallback unavailable: %s", exc)
        # 2) Honest failure - never fabricate.
        raise GatewayError(
            "Silverwing is offline and no approved fallback provider is "
            "configured. The request was NOT answered by a model.",
            code="gw_fallback_unavailable",
        )

    def _record(self, decision: RoutingDecision, resp: GatewayResponse) -> None:
        """Telemetry for the Observatory (spec section 26)."""
        event = {
            "event": "gateway.routing",
            "request_id": resp.metadata.get("request_id"),
            "timestamp0": time.time(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "decision": decision.to_dict(),
            "response_model": resp.model,
            "revision": resp.revision,
            "latency_ms": resp.latency_ms,
            "total_tokens": resp.usage.total_tokens,
            "tool_calls": [tc.tool for tc in resp.tool_calls],
            "device": resp.metadata.get("device", ""),
            "fallback": bool(decision.fallback_from),
            "success": True,
            "error": None,
        }
        log.info("model_gateway routing: %s", event)
        try:
            from jarvis_backend.observability import (
                record_gateway_event,  # type: ignore[import-not-found]
            )

            record_gateway_event(event)
        except Exception as exc:
            log.debug("observability bridge unavailable: %s", exc)


# Module-level default gateway used by the platform.
default_gateway = ModelGateway()
