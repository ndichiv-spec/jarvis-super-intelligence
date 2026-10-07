"""Remote JARVIS Brain client (platform side).

Mirrors :class:`backend.model_gateway.client.SilverwingClient` but for the
dedicated Brain runtime on ``http://127.0.0.1:8011/v1`` (spec sections 1, 5, 12).

The platform calls the Brain runtime strictly over HTTP.  It never downloads
weights (they live on the GPU host) and never imports a transformer.  Every
``/v1/*`` call carries ``Authorization: Bearer <JARVIS_BRAIN_API_KEY>``; the key
is read from the vault (or env) and is never logged or echoed in errors.

Honesty gate (spec section 12 & 13): ``chat`` only proceeds when ``/health``
reports ``available=true`` AND ``stub=false``.  A stub/unavailable/unreachable
Brain raises ``GatewayError(code="gw_brain_unavailable")`` so the platform
gateway falls back to Silverwing instead of presenting a stub reply as real.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .health import GatewayHealth, HealthLevel
from .models import (
    GatewayError,
    GatewayResponse,
    GatewayToolCall,
    GatewayUsage,
)

log = logging.getLogger("model_gateway.brain_client")


def _env(name: str, default: str = "") -> str:
    import os

    return os.environ.get(name, default)


def _mask(value: str | None) -> str:
    """Never reveal the credential; show only a safe fingerprint."""
    if not value:
        return "<none>"
    if len(value) <= 6:
        return "****"
    return value[:4] + "..." + value[-2:]


class BrainClient:
    """HTTP client to the JARVIS Brain runtime (OpenAI-compatible)."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        *,
        _httpx_client: Any = None,  # injected test double
    ) -> None:
        raw = (endpoint or _env("JARVIS_BRAIN_ENDPOINT", "")).rstrip("/")
        # Normalise to an OpenAI-compatible ``.../v1`` base for /v1/* calls,
        # accepting either ``http://host`` or ``http://host/v1``.
        if not raw:
            self.endpoint = ""
            self._root = ""
        elif raw.endswith("/v1"):
            self.endpoint = raw
            self._root = raw[:-3]
        else:
            self.endpoint = raw + "/v1"
            self._root = raw
        self.api_key = api_key or _env("JARVIS_BRAIN_API_KEY", "")
        self.model = (model or _env("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1")).strip()
        self.timeout = float(timeout or _env("JARVIS_BRAIN_TIMEOUT", "30") or 30)
        self._client = _httpx_client  # injected (async httpx-like) client
        self._health_cache: GatewayHealth | None = None
        self._health_at = 0.0
        self._hc_cache: dict[str, Any] | None = None  # raw /health payload cache

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #
    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint)

    @property
    def is_remote(self) -> bool:
        return bool(self.endpoint)

    @property
    def api_key_masked(self) -> str:
        return _mask(self.api_key)

    def _headers(self, *, include_auth: bool = True) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if include_auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _redact_exc(exc: BaseException) -> str:
        """Return a connection-error message that never includes the URL/key."""
        name = type(exc).__name__
        return f"brain endpoint unreachable ({name})"

    async def _http(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        *,
        with_auth: bool = True,
        timeout: float | None = None,
        root: bool = False,  # /health lives under the root base, not /v1
    ) -> Any:
        if not self.is_remote:
            raise GatewayError(
                "JARVIS BRAIN_ENDPOINT is not configured", code="gw_not_configured"
            )
        base = self._root if root else self.endpoint
        url = f"{base}{path}"
        if self._client is not None:
            # Test double — uses the real httpx-like interface.
            return await self._client.request(
                method, url,
                json=json_body, headers=self._headers(include_auth=with_auth),
                timeout=timeout or self.timeout,
            )
        import httpx

        async with httpx.AsyncClient(
            timeout=timeout or self.timeout, headers=self._headers(include_auth=with_auth)
        ) as c:
            if method == "GET":
                resp = await c.get(url)
            else:
                resp = await c.post(url, json=json_body or {})
        return resp

    @staticmethod
    def _parse_json(resp: Any) -> dict[str, Any]:
        try:
            return resp.json()
        except Exception:
            raise GatewayError(
                f"invalid JSON from Brain runtime (HTTP {getattr(resp, 'status_code', '?')})",
                code="gw_bad_response",
                status=getattr(resp, "status_code", None),
            )

    # ------------------------------------------------------------------ #
    # Health (cached; /health is unauthenticated)
    # ------------------------------------------------------------------ #
    async def health(self, *, refresh: bool = False) -> GatewayHealth:
        now = time.monotonic()
        if not refresh and self._health_cache and now - self._health_at < 3.0:
            return self._health_cache
        if not self.is_remote:
            h = GatewayHealth(
                status=HealthLevel.OFFLINE, detail="brain endpoint not configured",
                available=False, latency_ms=0.0,
            )
            self._cache_health(h)
            return h
        start = time.monotonic()
        try:
            resp = await self._http("GET", "/health", with_auth=False, root=True)
        except Exception as exc:
            latency = round((time.monotonic() - start) * 1000, 2)
            h = GatewayHealth(
                status=HealthLevel.OFFLINE,
                detail=self._redact_exc(exc),
                available=False,
                latency_ms=latency,
            )
            self._cache_health(h)
            return h
        latency = round((time.monotonic() - start) * 1000, 2)
        data = self._parse_json(resp)
        self._hc_cache = data
        stub = bool(data.get("stub"))
        available = bool(data.get("available")) and not stub
        if resp.status_code == 200 and available and data.get("status") == "healthy":
            status = HealthLevel.HEALTHY
        elif stub or resp.status_code in (503, 500):
            status = HealthLevel.OFFLINE
        else:
            status = HealthLevel.DEGRADED
        h = GatewayHealth(
            status=status,
            model=data.get("model", self.model),
            revision=data.get("revision", ""),
            loaded=data.get("loaded", False),
            device=data.get("device", ""),
            backend=data.get("backend", ""),
            parameters=data.get("parameters", 0) or 0,
            warmup_ok=data.get("warmup_ok", False),
            available=available,
            latency_ms=latency,
            detail=data.get("detail") or (f"HTTP {resp.status_code}" if resp.status_code != 200 else None),
            checked_at=time.time(),
        )
        self._cache_health(h)
        return h

    def _cache_health(self, h: GatewayHealth) -> None:
        self._health_cache = h
        self._health_at = time.monotonic()

    # ------------------------------------------------------------------ #
    # Models
    # ------------------------------------------------------------------ #
    async def models(self) -> list[dict[str, Any]]:
        """Return the raw model catalog entries from the Brain runtime."""
        resp = await self._http("GET", "/models", with_auth=True)
        if resp.status_code != 200:
            raise GatewayError(
                f"brain /v1/models failed: HTTP {resp.status_code}",
                code="gw_models_failed", status=resp.status_code,
            )
        data = self._parse_json(resp)
        return list(data.get("data", []))

    # ------------------------------------------------------------------ #
    # Chat (with honesty gate)
    # ------------------------------------------------------------------ #
    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> GatewayResponse:
        """Call POST /v1/chat/completions; returns a normalized GatewayResponse.

        Raises ``GatewayError`` with code ``gw_brain_unavailable`` when the
        Brain is a stub / offline / unreachable (so the platform may fall back
        to Silverwing), and ``gw_chat_transient`` on timeout (retryable).
        """
        brain_model = kwargs.get("model") or self.model
        system = kwargs.get("system")
        timeout = kwargs.get("timeout") or self.timeout

        # Honesty gate: only a confirmed-available (non-stub) Brain serves.
        h = await self.health()
        if not h.is_healthy:
            detail = h.detail or "brain not healthy"
            if h.status == HealthLevel.OFFLINE:
                log.info("brain not available (redacted); routing onward", extra={"brain_health": "offline"})
                raise GatewayError(
                    "JARVIS Brain is not available (offline/stub/unreachable)",
                    code="gw_brain_unavailable", retryable=False,
                ) from None
            # degraded but technically up: still refuse to present as production
            raise GatewayError(
                f"JARVIS Brain is {detail}",
                code="gw_brain_unavailable", retryable=False,
            ) from None

        all_messages: list[dict[str, Any]] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        body = {
            "model": brain_model,
            "messages": all_messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", kwargs.get("max_new_tokens", 8192)),
            "top_p": kwargs.get("top_p", 0.9),
            "top_k": kwargs.get("top_k"),
            "repetition_penalty": kwargs.get("repetition_penalty", 1.0),
            "stream": kwargs.get("stream", False),
        }
        start = time.monotonic()
        import httpx

        try:
            resp = await self._http("POST", "/chat/completions", json_body=body, timeout=timeout)
        except httpx.TimeoutException:
            raise GatewayError(
                "JARVIS Brain timed out", code="gw_chat_transient", retryable=True, status=504,
            )
        except httpx.ConnectError:
            # Confirmed unreachable -> eligible for Silverwing fallback.
            raise GatewayError(
                "JARVIS Brain endpoint is unreachable", code="gw_brain_unavailable",
                retryable=False, status=0,
            )
        except httpx.HTTPError:
            raise GatewayError(
                "JARVIS Brain endpoint is unreachable", code="gw_brain_unavailable",
                retryable=False, status=0,
            )

        latency_ms = round((time.monotonic() - start) * 1000, 2)
        if resp.status_code != 200:
            raise GatewayError(
                f"Brain chat failed: HTTP {resp.status_code}",
                code="gw_brain_unavailable", retryable=False, status=resp.status_code,
            )
        data = self._parse_json(resp)
        if data.get("object") == "chat.completion.chunk":
            return self._collect_stream(data)
        try:
            message = data["choices"][0]["message"]
            content = message.get("content", "") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise GatewayError(
                "Brain returned an invalid chat payload", code="gw_brain_unavailable",
                retryable=False, status=resp.status_code,
            ) from exc

        # Honesty guard: empty content is never a real answer.
        if not content.strip():
            raise GatewayError(
                "JARVIS Brain returned an empty response", code="gw_brain_unavailable",
                retryable=False, status=resp.status_code,
            )

        usage = data.get("usage", {})
        tool_calls = message.get("tool_calls", [])
        # A stub Brain (if it ever returned content here) is rejected upstream by
        # the health gate; this is a second line of defense.
        if content.strip().startswith("[brain-stub]"):
            raise GatewayError(
                "JARVIS Brain returned a stub response", code="gw_brain_unavailable",
                retryable=False, status=resp.status_code,
            )
        return GatewayResponse(
            content=content,
            model=data.get("model", brain_model),
            revision=data.get("revision", ""),
            latency_ms=latency_ms,
            finish_reason=data.get("choices", [{}])[0].get("finish_reason", "stop"),
            usage=GatewayUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            tool_calls=[GatewayToolCall(**t) for t in tool_calls] if tool_calls else [],
            metadata={
                "device": data.get("device", ""),
                "backend": data.get("backend", ""),
                "provider": "jarvis-brain",
                "stub": bool(data.get("backend", "").endswith("brain-stub")),
            },
        )

    # ------------------------------------------------------------------ #
    # Generate (prompt-style, used by probe / generate surfaces)
    # ------------------------------------------------------------------ #
    async def generate(self, prompt: str, **kwargs: Any) -> GatewayResponse:
        if not kwargs.get("skip_health_check"):
            h = await self.health()
            if not h.is_healthy:
                raise GatewayError(
                    "JARVIS Brain is not available", code="gw_brain_unavailable",
                    retryable=False,
                )
        ref = kwargs.get("model") or self.model
        body = {
            "prompt": prompt,
            "model": ref,
            "max_new_tokens": kwargs.get("max_new_tokens", 256),
            "temperature": kwargs.get("temperature", 0.7),
            "top_p": kwargs.get("top_p", 0.9),
            "top_k": kwargs.get("top_k"),
            "repetition_penalty": kwargs.get("repetition_penalty", 1.0),
        }
        import httpx

        start = time.monotonic()
        try:
            resp = await self._http("POST", "/generate", json_body=body)
        except httpx.TimeoutException:
            raise GatewayError("JARVIS Brain timed out", code="gw_chat_transient",
                               retryable=True, status=504)
        except httpx.HTTPError as exc:
            raise GatewayError(
                self._redact_exc(exc), code="gw_brain_unavailable",
                retryable=False, status=0,
            )
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        if resp.status_code != 200:
            raise GatewayError(
                f"Brain generate failed: HTTP {resp.status_code}", code="gw_brain_unavailable",
                status=resp.status_code,
            )
        data = self._parse_json(resp)
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return GatewayResponse(
            content=choice.get("text", ""),
            model=data.get("model", ref),
            revision=data.get("revision", ""),
            latency_ms=latency_ms if latency_ms else float(data.get("latency_ms", 0.0)),
            finish_reason=choice.get("finish_reason", "stop"),
            usage=GatewayUsage(
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            metadata={"provider": "jarvis-brain", "backend": data.get("backend", ""),
                      "device": data.get("device", "")},
        )

    # -- streaming helper ------------------------------------------------
    @staticmethod
    def _collect_stream(data: dict[str, Any]) -> GatewayResponse:
        choices = data.get("choices", [])
        delta = choices[0].get("delta", {}) if choices else {}
        return GatewayResponse(
            content=delta.get("content", ""),
            model=data.get("model", ""),
            revision=data.get("revision", ""),
            finish_reason=(choices[0].get("finish_reason") if choices else "stop"),
        )


# Module-level default client (mirrors SilverwingClient.default_client).
default_brain_client = BrainClient()
