"""Remote Silverwing client (platform side).

The AI platform calls the Silverwing runtime strictly over HTTP.  It never
downloads weights (spec section 36) and never imports the Transformer.

Configuration is entirely via environment variables:

    SILVERWING_ENDPOINT    runtime base URL (e.g. http://localhost:8010)
    SILVERWING_API_KEY     optional bearer token (never hard-coded)
    SILVERWING_MODEL       default model ref (silverwing-120m-base-v1)
    SILVERWING_MODE        local | remote | kaggle | cloud
    SILVERWING_MODEL_PATH  local weight path for SILVERWING_MODE=local
    SILVERWING_TIMEOUT     request timeout seconds

Modes:
    remote  -> HTTP calls to SILVERWING_ENDPOINT (production)
    local   -> synthesizes an in-process EchoBackend from registry metadata
               using the same interface (development / tests)
    kaggle  -> reserved; expects SILVERWING_ENDPOINT
    cloud   -> reserved; expects SILVERWING_ENDPOINT
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from .health import GatewayHealth, HealthLevel
from .models import (
    GatewayError,
    GatewayMessage,
    GatewayModel,
    GatewayResponse,
    GatewayToolCall,
    GatewayUsage,
)

log = logging.getLogger("model_gateway.client")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# 120M-parameter Silverwing runs on CPU (~246 ms/token at 256 ctx).  The previous
# 256-token ceiling made generations take ~63-180 s, which exceeded the runtime's
# per-request window under sustained/multi-turn load -> 504 -> backend degraded
# (503) -> the platform fell back to cloud providers (and, with no cloud key,
# FAILED).  Cap generation to a CPU-safe ceiling so the runtime stays healthy
# across back-to-back requests.  Overridable via SILVERWING_MAX_TOKENS for
# larger/GPU-served models.
_DEFAULT_MAX_TOKENS = int(_env("SILVERWING_MAX_TOKENS", "64") or "64")


class SilverwingClient:
    """HTTP client to the Silverwing runtime API (OpenAI-compatible)."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        *_,
        _httpx_client: Any = None,  # injected test double
    ):
        self.endpoint = (endpoint or _env("SILVERWING_ENDPOINT", "")).rstrip("/")
        self.api_key = api_key or _env("SILVERWING_API_KEY", "")
        self.model = (model or _env("SILVERWING_MODEL", "silverwing-120m-base-v1")).strip()
        self.timeout = float(timeout or _env("SILVERWING_TIMEOUT", "30") or 30)
        self.mode = _env("SILVERWING_MODE", "remote").lower()
        self.model_path = _env("SILVERWING_MODEL_PATH", "")
        self._client = _httpx_client  # injected (async httpx-like) client
        self._health_cache: GatewayHealth | None = None
        self._health_at = 0.0

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #
    @property
    def is_remote(self) -> bool:
        return bool(self.endpoint and self.mode in ("remote", "kaggle", "cloud"))

    async def _http(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> Any:
        if not self.is_remote:
            raise GatewayError(
                "Silverwing endpoint is not configured (SILVERWING_ENDPOINT)",
                code="gw_not_configured",
            )
        if self._client is not None:
            resp = await self._client.request(
                method, f"{self.endpoint}{path}", json=json_body, timeout=self.timeout
            )
            return resp
        import httpx

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as c:
            if method == "GET":
                resp = await c.get(f"{self.endpoint}{path}")
            else:
                resp = await c.post(f"{self.endpoint}{path}", json=json_body or {})
        return resp

    @staticmethod
    def _parse_json(resp: Any) -> dict[str, Any]:
        try:
            return resp.json()
        except Exception as exc:
            raise GatewayError(
                f"invalid JSON from Silverwing runtime ({resp.status_code})",
                code="gw_bad_response",
                status=getattr(resp, "status_code", None),
            ) from exc

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def health(self, *, refresh: bool = False) -> GatewayHealth:
        now = time.monotonic()
        if not refresh and self._health_cache and now - self._health_at < 5.0:
            return self._health_cache
        if not self.is_remote:
            h = self._local_health()
            self._cache_health(h)
            return h
        try:
            resp = await self._http("GET", "/v1/health")
        except Exception as exc:
            h = GatewayHealth(status=HealthLevel.OFFLINE, detail=str(exc), checked_at=time.time())
            self._cache_health(h)
            return h
        if resp.status_code == 200:
            data = self._parse_json(resp)
            h = GatewayHealth(
                status=HealthLevel.HEALTHY,
                model=data.get("model", ""),
                revision=data.get("revision", ""),
                loaded=data.get("loaded", False),
                device=data.get("device", ""),
                backend=data.get("backend", ""),
                parameters=data.get("parameters", 0) or 0,
                warmup_ok=data.get("warmup_ok", False),
                checked_at=time.time(),
                detail=data.get("detail"),
            )
        else:
            data = self._parse_json(resp)
            h = GatewayHealth(
                status=HealthLevel.DEGRADED,
                model=data.get("model", ""),
                revision=data.get("revision", ""),
                device=data.get("device", ""),
                backend=data.get("backend", ""),
                parameters=data.get("parameters", 0) or 0,
                warmup_ok=data.get("warmup_ok", False),
                detail=data.get("detail") or f"HTTP {resp.status_code}",
                loaded=data.get("loaded", False),
                checked_at=time.time(),
            )
        self._cache_health(h)
        return h

    def _cache_health(self, h: GatewayHealth) -> None:
        self._health_cache = h
        self._health_at = time.monotonic()

    def _local_health(self) -> GatewayHealth:
        from silverwing_runtime.config import RuntimeConfig
        from silverwing_runtime.inference import InferenceService
        from silverwing_runtime.model_loader import ModelLoader
        from silverwing_runtime.model_registry import SilverwingRegistry

        cfg = RuntimeConfig()
        reg = SilverwingRegistry(cfg)
        loader = ModelLoader(reg, config=cfg)
        entry = reg.lookup(self.model.split("/")[-1])
        try:
            svc = InferenceService(loader, cfg)
            svc.warmup(entry.full_id if entry else self.model)
            return GatewayHealth(
                status=HealthLevel.HEALTHY,
                model=(entry.full_id if entry else self.model),
                revision=(entry.revision if entry else ""),
                loaded=True,
                device="cpu",
                backend=cfg.backend,
                parameters=(entry.parameter_count if entry else 0),
                warmup_ok=True,
                checked_at=time.time(),
            )
        except Exception as exc:
            return GatewayHealth(
                status=HealthLevel.OFFLINE,
                detail=str(exc),
                checked_at=time.time(),
            )

    async def models(self) -> list[GatewayModel]:
        """List models known to the Silverwing registry."""
        if not self.is_remote:
            from silverwing_runtime.config import RuntimeConfig
            from silverwing_runtime.model_registry import SilverwingRegistry

            reg = SilverwingRegistry(RuntimeConfig())
            return [
                GatewayModel(
                    id=e.full_id,
                    context_length=e.context_length,
                    parameters=e.parameter_count,
                    capabilities=list(e.capabilities),
                    status=e.status,
                )
                for e in reg.list_models()
            ]
        resp = await self._http("GET", "/v1/models")
        if resp.status_code != 200:
            raise GatewayError(
                f"model list failed: HTTP {resp.status_code}",
                code="gw_models_failed",
                status=resp.status_code,
            )
        data = self._parse_json(resp)
        return [GatewayModel(**m) for m in data.get("data", [])]

    async def generate(self, prompt: str, **kwargs: Any) -> GatewayResponse:
        """Call POST /v1/generate and return a normalized response."""
        if not self.is_remote:
            return self._local_generate(prompt, **kwargs)
        body = {
            "prompt": prompt,
            "model": kwargs.get("model") or self.model,
            "max_new_tokens": kwargs.get("max_new_tokens", 256),
            "temperature": kwargs.get("temperature", 0.7),
            "top_k": kwargs.get("top_k"),
            "top_p": kwargs.get("top_p", 0.9),
            "repetition_penalty": kwargs.get("repetition_penalty", 1.0),
        }
        resp = await self._http("POST", "/v1/generate", json_body=body)
        if resp.status_code != 200:
            raise GatewayError(
                f"generate failed: HTTP {resp.status_code}",
                code="gw_generate_failed",
                status=resp.status_code,
            )
        data = self._parse_json(resp)
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return GatewayResponse(
            content=choice.get("text", ""),
            model=data.get("model", self.model),
            revision=data.get("revision", ""),
            latency_ms=float(data.get("latency_ms", 0.0)) or 0.0,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=GatewayUsage(
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> GatewayResponse:
        """Call POST /v1/chat/completions and return a normalized response."""
        if not self.is_remote:
            return self._local_chat(messages, **kwargs)
        # The runtime's messages_to_prompt formats every role (including
        # "system") via <|role|> blocks, so we prepend a system message when
        # one is supplied.  This keeps the Silverwing weights honest: they are
        # base-model weights, and the system prompt is part of the prompt, not
        # a claim about fine-tuning.
        all_messages: list[dict[str, Any]] = []
        system = kwargs.get("system")
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(
            GatewayMessage(**m).model_dump() if isinstance(m, dict) else m for m in messages
        )
        body = {
            "model": kwargs.get("model") or self.model,
            "messages": all_messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_new_tokens", kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS)),
            "top_p": kwargs.get("top_p", 0.9),
            "top_k": kwargs.get("top_k"),
            "repetition_penalty": kwargs.get("repetition_penalty", 1.0),
            "stream": kwargs.get("stream", False),
        }
        resp = await self._http("POST", "/v1/chat/completions", json_body=body)
        if resp.status_code != 200:
            raise GatewayError(
                f"chat failed: HTTP {resp.status_code}",
                code="gw_chat_failed",
                status=resp.status_code,
            )
        data = self._parse_json(resp)
        if data.get("object") == "chat.completion.chunk":
            return self._collect_stream(data)
        choice = data["choices"][0]
        message = choice.get("message", {})
        usage = data.get("usage", {})
        tool_calls = message.get("tool_calls", [])
        return GatewayResponse(
            content=message.get("content", ""),
            model=data.get("model", self.model),
            revision=data.get("revision", ""),
            latency_ms=float(data.get("latency_ms", 0.0)) or 0.0,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=GatewayUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            tool_calls=[GatewayToolCall(**t) for t in tool_calls] if tool_calls else [],
            metadata={
                "device": data.get("device", ""),
                "backend": data.get("backend", ""),
                "provider": "silverwing",
            },
        )

    # -- local dev mode (same interface, no remote server) ---------------
    def _local_model(self) -> dict[str, Any]:
        from silverwing_runtime.config import RuntimeConfig
        from silverwing_runtime.model_registry import SilverwingRegistry

        reg = SilverwingRegistry(RuntimeConfig())
        ref = self.model
        entry = reg.lookup(ref)
        if entry is None:
            raise GatewayError(
                f"model {ref!r} not found in local registry", code="gw_model_unknown"
            )
        if entry.status == "archived":
            raise GatewayError(f"model {ref!r} is archived", code="gw_archived")
        return {"entry": entry, "registry": reg}

    def _local_generate(self, prompt: str, **kwargs: Any) -> GatewayResponse:
        cfg = self._local_model()
        result = _echo_generate(prompt, **kwargs)
        return GatewayResponse(
            content=result.text,
            model=cfg["entry"].full_id,
            revision=cfg["entry"].revision,
            latency_ms=result.latency_ms,
            finish_reason=result.finish_reason,
            usage=GatewayUsage(
                completion_tokens=result.tokens_generated, total_tokens=result.tokens_generated
            ),
        )

    def _local_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> GatewayResponse:
        from silverwing_runtime.generation import messages_to_prompt

        cfg = self._local_model()
        prompt = messages_to_prompt([dict(m) for m in messages])
        result = _echo_generate(prompt, **kwargs)
        return GatewayResponse(
            content=result.text,
            model=cfg["entry"].full_id,
            revision=cfg["entry"].revision,
            latency_ms=result.latency_ms,
            finish_reason=result.finish_reason,
            usage=GatewayUsage(
                completion_tokens=result.tokens_generated, total_tokens=result.tokens_generated
            ),
        )

    @staticmethod
    def _collect_stream(data: dict[str, Any]) -> GatewayResponse:
        """Collapse a single-chunk stream response into a response."""
        choices = data.get("choices", [])
        delta = choices[0].get("delta", {}) if choices else {}
        return GatewayResponse(
            content=delta.get("content", ""),
            model=data.get("model", ""),
            revision=data.get("revision", ""),
            finish_reason=(choices[0].get("finish_reason") if choices else "stop"),
        )


def _echo_generate(prompt: str, **kwargs: Any) -> Any:
    from silverwing_runtime.generation import GenerationConfig
    from silverwing_runtime.inference import EchoBackend

    cfg = GenerationConfig(
        max_new_tokens=kwargs.get("max_new_tokens", 256),
        temperature=kwargs.get("temperature", 0.7),
        top_k=kwargs.get("top_k"),
        top_p=kwargs.get("top_p", 0.9),
        repetition_penalty=kwargs.get("repetition_penalty", 1.0),
    )
    from silverwing_runtime.generation import GenerationRequest

    req = GenerationRequest(prompt=prompt, config=cfg)
    return EchoBackend(marker="sw-echo-dev").generate(req)


# Module-level default client (mirrors provider_gateway pattern).
default_client = SilverwingClient()
