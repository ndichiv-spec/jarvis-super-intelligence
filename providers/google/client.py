"""Google ProviderAdapter (Vertex AI / Gemini, spec §7).

Uses ``google.genai``. Testable via an injected models_api (see `GoogleAdapter`).
"""

from __future__ import annotations

import json
import time
from typing import Iterator, Optional, Sequence

from ..base import (
    Message,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    StreamChunk,
    ToolCall,
    Usage,
)
from ..capabilities import Capability
from ..errors import ProviderUnconfigured
from ..health import HealthStatus, ProviderHealth
from ..models import PrivacyClass
from ..secrets import SecretManager
from ..telemetry import ProviderTelemetry
from .capabilities import GOOGLE_ADAPTER_CAPABILITIES
from .config import GoogleConfig
from .health import google_health_probe
from .models import GOOGLE_MODELS
from .models_api import GoogleModelsAPI


class GoogleAdapter(ProviderAdapter):
    provider_id = "google"
    display_name = "Google Vertex AI / Gemini"
    declared_capabilities = GOOGLE_ADAPTER_CAPABILITIES

    def __init__(
        self,
        config: Optional[GoogleConfig] = None,
        secrets: Optional[SecretManager] = None,
        telemetry: Optional[ProviderTelemetry] = None,
        models_api: Optional[GoogleModelsAPI] = None,
    ) -> None:
        super().__init__(secrets=secrets, telemetry=telemetry)
        self.config = config or GoogleConfig.from_environ(secrets=secrets)
        self._injected_api = models_api

    @property
    def configured(self) -> bool:
        return self.config.configured

    def _models_api(self) -> GoogleModelsAPI:
        if self._injected_api is None:
            self._injected_api = GoogleModelsAPI(
                api_key=self.config.api_key,
                project=self.config.project,
                location=self.config.location,
            )
        return self._injected_api

    def _resolve_model(self, request: ProviderRequest) -> str:
        return request.model or self.config.model or self._default_model()

    def _default_model(self) -> str:
        raise ProviderUnconfigured(
            "google: no model configured "
            "(set JARVIS_GOOGLE_MODEL / JARVIS_VERTEX_MODEL or pass request.model)"
        )

    def _build_models(self):
        return GOOGLE_MODELS

    def _probe_health(self) -> ProviderHealth:
        if not self.configured:
            return ProviderHealth(
                provider=self.provider_id, status=HealthStatus.UNCONFIGURED
            )
        try:
            return google_health_probe(self._models_api(), provider=self.provider_id)
        except ProviderUnconfigured as exc:
            return ProviderHealth(
                provider=self.provider_id,
                status=HealthStatus.UNCONFIGURED,
                detail=str(exc),
            )

    # -- helpers ---------------------------------------------------------------
    def _contents(self, request: ProviderRequest) -> tuple[list[dict], Optional[str]]:
        system: list[str] = []
        contents: list[dict] = []
        for item in request.messages:
            msg = item if isinstance(item, Message) else Message.from_mapping(item)
            if msg.role == "system":
                system.append(msg.content if isinstance(msg.content, str) else str(msg.content))
                continue
            role = "model" if msg.role in ("assistant",) else ("user" if msg.role in ("user", "tool") else "user")
            text = msg.content if isinstance(msg.content, str) else str(msg.content or "")
            contents.append({"role": role, "parts": [{"text": text}]})
        if not contents:
            contents = [{"role": "user", "parts": [{"text": ""}]}]
        return contents, ("\n".join(system) if system else None)

    def _config(
        self,
        request: ProviderRequest,
        tools: Optional[list[dict]] = None,
        extra: Optional[dict] = None,
    ) -> dict:
        cfg: dict = {}
        if request.temperature is not None:
            cfg["temperature"] = request.temperature
        if request.max_tokens is not None:
            cfg["max_output_tokens"] = request.max_tokens
        fmt = request.response_format or {}
        mime = None
        if fmt.get("type") in ("json_object", "json_schema"):
            mime = "application/json"
        if fmt.get("response_mime_type"):
            mime = fmt["response_mime_type"]
        if mime:
            cfg["response_mime_type"] = mime
        if tools:
            declarations = []
            for tool in tools:
                function = tool.get("function") or {}
                declarations.append(
                    {
                        "name": function.get("name", ""),
                        "description": function.get("description", ""),
                        "parameters": function.get("parameters"),
                    }
                )
            cfg["tools"] = [{"function_declarations": declarations}]
        if extra:
            cfg.update(extra)
        return cfg

    # -- chat ------------------------------------------------------------------
    def chat(self, request: ProviderRequest) -> ProviderResponse:
        self._ensure(Capability.CHAT)
        self._guard_context(request)
        model = self._resolve_model(request)
        contents, system = self._contents(request)
        t0 = time.monotonic()
        response = self._models_api().generate_content(
            model,
            contents,
            system_instruction=system,
            **self._config(request, tools=request.tools),
        )
        latency = (time.monotonic() - t0) * 1000.0
        text = getattr(response, "text", None) or ""
        usage = _usage_from(response)
        tool_calls: list[ToolCall] = []
        for part in _parts(response):
            fc = getattr(part, "function_call", None)
            if fc is not None:
                tool_calls.append(
                    ToolCall(
                        id=fc.name or "",
                        name=fc.name or "",
                        arguments=json.dumps(getattr(fc, "args", {}) or {}),
                    )
                )
        result = ProviderResponse(
            provider=self.provider_id,
            model=model,
            text=text,
            tool_calls=tool_calls or None,
            usage=usage,
            latency_ms=latency,
            finish_reason=getattr(response, "finish_reason", None) or getattr(
                _candidate(response), "finish_reason", None),
            request_id=request.request_id,
            raw=getattr(response, "model_dump", lambda: {})() if hasattr(response, "model_dump") else {},
        )
        self.telemetry.event(
            provider=self.provider_id, model=model, request_id=request.request_id,
            kind="request", latency_ms=latency,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            privacy_class=request.privacy_class.value,
        )
        return result

    # -- streaming --------------------------------------------------------------
    def stream(self, request: ProviderRequest) -> Iterator[StreamChunk]:
        self._ensure(Capability.STREAMING)
        self._guard_context(request)
        model = self._resolve_model(request)
        contents, system = self._contents(request)
        t0 = time.monotonic()
        stream_iter = self._models_api().generate_content_stream(
            model,
            contents,
            system_instruction=system,
            temperature=self.config_temperature(request),
            max_output_tokens=request.max_tokens,
        )
        for chunk in stream_iter:
            delta = getattr(chunk, "text", None)
            if delta:
                yield StreamChunk(provider=self.provider_id, model=model, text=delta)
        latency = (time.monotonic() - t0) * 1000.0
        self.telemetry.event(
            provider=self.provider_id, model=model, request_id=request.request_id,
            kind="stream", latency_ms=latency,
        )
        yield StreamChunk(provider=self.provider_id, model=model, done=True)

    def config_temperature(self, request: ProviderRequest) -> Optional[float]:
        return request.temperature

    # -- embeddings ---------------------------------------------------------------
    def embeddings(
        self, texts: Sequence[str], model: Optional[str] = None
    ) -> list[list[float]]:
        self._ensure(Capability.EMBEDDINGS)
        model = model or "text-embedding-004"
        vectors = self._models_api().embed_content(model, list(texts))
        self.telemetry.event(
            provider=self.provider_id, model=model, kind="embedding",
            bytes=sum(len(t) for t in texts),
        )
        return vectors


def _candidate(response) -> Optional[object]:
    candidates = getattr(response, "candidates", None)
    if candidates:
        return candidates[0]
    return None


def _parts(response) -> list:
    candidate = _candidate(response)
    if candidate is None:
        return []
    content = getattr(candidate, "content", None)
    if content is None:
        return []
    return list(getattr(content, "parts", []) or [])


def _usage_from(response) -> Optional[Usage]:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return None
    return Usage(
        prompt_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
        completion_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
    )