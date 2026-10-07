"""Shared OpenAI-compatible implementation for fabric adapters.

OpenAI, NVIDIA NIM, Hugging Face Inference, Google Vertex (OpenAI-compat surface),
vLLM/llama.cpp/Ollama and the local Brain/Silverwing runtimes all speak
``/v1/chat/completions``. This mixin implements chat/stream/embeddings once, in
terms of :class:`~providers.http.OpenAICompatibleClient`. Each adapter still picks
its *own* declared capabilities, health probe and model catalog — so a provider can
never accidentally claim chat streaming it does not actually expose.
"""

from __future__ import annotations

import time
from typing import Iterator, Optional, Sequence

from .base import (
    Message,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    StreamChunk,
    ToolCall,
    Usage,
)
from .capabilities import Capability
from .http import OpenAICompatibleClient


class OpenAICompatChatMixin:
    """Implement chat/stream/embeddings over an OpenAI-compatible surface."""

    # subclasses set: base_url, api_key, auth_header, default_model
    base_url: str = ""
    api_key: Optional[str] = None
    auth_header: str = "Authorization"
    default_model: Optional[str] = None

    def _client(self) -> OpenAICompatibleClient:
        if getattr(self, "_http_client", None) is None:
            self._http_client = OpenAICompatibleClient(
                base_url=self.base_url,
                api_key=self.api_key,
                extra_auth_header=self.auth_header,
            )
        return self._http_client

    def _resolve_model(self, request: ProviderRequest) -> str:
        model = request.model or self.default_model
        if not model:
            raise self._unconfigured_model()
        return model

    def _unconfigured_model(self):  # pragma: no cover - subclass override
        from .errors import ProviderUnconfigured

        raise ProviderUnconfigured(
            f"{self.provider_id}: no model configured "
            f"(set JARVIS_{self.provider_id.upper()}_MODEL or pass request.model)"
        )

    # -- chat ----------------------------------------------------------------
    def chat(self, request: ProviderRequest) -> ProviderResponse:
        self._ensure(Capability.CHAT)
        self._guard_context(request)
        if request.stream:
            chunks = list(self.stream(request))
            text = "".join(c.text for c in chunks)
            finish = next((c.finish_reason for c in chunks if c.finish_reason), None)
            usage = None
            for chunk in chunks:
                if chunk.usage is not None:
                    usage = chunk.usage
            return ProviderResponse(
                provider=self.provider_id,
                model=self._resolve_model(request),
                text=text,
                finish_reason=finish,
                usage=usage,
                request_id=request.request_id,
            )

        model = self._resolve_model(request)
        t0 = time.monotonic()
        data = self._client().chat_completions(
            model=model,
            messages=request.as_openai_messages(),
            tools=request.tools,
            response_format=request.response_format,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            extra=request.extra,
        )
        latency = (time.monotonic() - t0) * 1000.0
        response = _parse_chat_completion(
            data, provider=self.provider_id, model=model, latency_ms=latency,
            request_id=request.request_id,
        )
        self._record_request(request, response, latency)
        return response

    # -- streaming -----------------------------------------------------------
    def stream(self, request: ProviderRequest) -> Iterator[StreamChunk]:
        self._ensure(Capability.STREAMING)
        self._guard_context(request)
        model = self._resolve_model(request)
        t0 = time.monotonic()
        chunks = self._client().stream_chat_completions(
            model=model,
            messages=request.as_openai_messages(),
            tools=request.tools,
            response_format=request.response_format,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            extra=request.extra,
        )
        pending: dict[int, ToolCall] = {}
        usage = None
        finish_reason = None
        for data in chunks:
            choices = data.get("choices") or []
            if not choices:
                if data.get("usage"):
                    u = data["usage"] or {}
                    usage = Usage(
                        prompt_tokens=int(u.get("prompt_tokens", 0)),
                        completion_tokens=int(u.get("completion_tokens", 0)),
                    )
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            finish = choice.get("finish_reason")
            tool_call_deltas: list[ToolCall] = []
            if delta.get("tool_calls"):
                for tc in delta["tool_calls"]:
                    idx = int(tc.get("index", 0))
                    call = pending.setdefault(idx, ToolCall(index=idx))
                    if tc.get("id"):
                        call.id = tc["id"]
                    func = tc.get("function") or {}
                    if func.get("name"):
                        call.name += func["name"]
                    arguments = func.get("arguments") or ""
                    if arguments:
                        call.arguments = (call.arguments or "") + arguments
                    tool_call_deltas.append(ToolCall(
                        index=idx,
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=arguments,
                    ))
            yield StreamChunk(
                provider=self.provider_id,
                model=model,
                # Reasoning models (e.g. NVIDIA Nemotron) stream thinking tokens
                # in ``reasoning_content`` and only the answer in ``content``.
                # Surfacing both keeps progressive output honest instead of
                # appearing to stall until the answer arrives.
                reasoning=delta.get("reasoning_content") or "",
                text=(delta.get("content") or ""),
                tool_calls=tool_call_deltas or None,
                finish_reason=finish,
            )
            if finish:
                finish_reason = finish
                latency = (time.monotonic() - t0) * 1000.0
                self.telemetry.event(
                    provider=self.provider_id, model=model,
                    request_id=request.request_id, kind="stream",
                    latency_ms=latency,
                    completion_tokens=usage.completion_tokens if usage else 0,
                )
        # A single terminal chunk, emitted only after the stream is exhausted.
        # OpenAI-compatible endpoints send the usage block *after* the chunk
        # carrying ``finish_reason``; emitting the terminal chunk at finish time
        # would therefore always report zero tokens.
        yield StreamChunk(
            provider=self.provider_id,
            model=model,
            finish_reason=finish_reason,
            tool_calls=[pending[index] for index in sorted(pending)] or None,
            usage=usage,
            done=True,
        )

    # -- embeddings ----------------------------------------------------------
    def embeddings(
        self, texts: Sequence[str], model: Optional[str] = None
    ) -> list[list[float]]:
        self._ensure(Capability.EMBEDDINGS)
        model = model or self.default_model
        if not model:
            self._unconfigured_model()
        _, data = self._client().request(
            "POST", "/v1/embeddings", json_body={"model": model, "input": list(texts)}
        )
        results = sorted(data.get("data", []), key=lambda r: r.get("index", 0))
        vectors: list[list[float]] = []
        for item in results:
            vectors.append([float(v) for v in (item.get("embedding") or [])])
        self.telemetry.event(
            provider=self.provider_id, model=model, kind="embedding",
            bytes=sum(len(t) for t in texts),
        )
        return vectors

    # -- telemetry -----------------------------------------------------------
    def _record_request(self, request: ProviderRequest, response: ProviderResponse, latency_ms: float) -> None:
        usage = response.usage or Usage()
        self.telemetry.event(
            provider=self.provider_id,
            model=response.model,
            request_id=request.request_id,
            kind="request",
            latency_ms=latency_ms,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            privacy_class=request.privacy_class.value,
        )


def _parse_chat_completion(
    data: dict,
    *,
    provider: str,
    model: str,
    latency_ms: float,
    request_id: str,
) -> ProviderResponse:
    from .errors import ProviderContractError

    try:
        choice = data["choices"][0]
    except (KeyError, IndexError, TypeError):
        raise ProviderContractError(
            f"{provider}: chat/completions response missing choices"
        ) from None
    message = choice.get("message") or {}
    text = message.get("content") or ""
    tool_calls: list[ToolCall] = []
    for i, tc in enumerate(message.get("tool_calls") or []):
        function = tc.get("function") or {}
        tool_calls.append(
            ToolCall(
                index=i,
                id=tc.get("id", ""),
                name=function.get("name", ""),
                arguments=function.get("arguments"),
            )
        )
    usage_data = data.get("usage") or {}
    return ProviderResponse(
        provider=provider,
        model=model,
        text=text,
        tool_calls=tool_calls or None,
        usage=Usage(
            prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
            completion_tokens=int(usage_data.get("completion_tokens", 0)),
        ),
        latency_ms=latency_ms,
        finish_reason=choice.get("finish_reason"),
        request_id=request_id,
        raw=data,
    )