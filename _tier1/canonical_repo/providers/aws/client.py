"""AWS Bedrock ProviderAdapter (spec §8)."""

from __future__ import annotations

import json
import time
from typing import Iterator, List, Optional, Sequence

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
from ..secrets import SecretManager
from ..telemetry import ProviderTelemetry
from .capabilities import AWS_ADAPTER_CAPABILITIES
from .clients import BedrockClients
from .config import AwsConfig
from .health import aws_health_probe
from .models import AWS_MODELS


class AwsBedrockAdapter(ProviderAdapter):
    provider_id = "aws"
    display_name = "AWS Bedrock"
    declared_capabilities = AWS_ADAPTER_CAPABILITIES

    def __init__(
        self,
        config: Optional[AwsConfig] = None,
        secrets: Optional[SecretManager] = None,
        telemetry: Optional[ProviderTelemetry] = None,
        clients: Optional[BedrockClients] = None,
    ) -> None:
        super().__init__(secrets=secrets, telemetry=telemetry)
        self.config = config or AwsConfig.from_environ(secrets=secrets)
        self._injected_clients = clients

    @property
    def configured(self) -> bool:
        return self.config.configured

    def _clients(self) -> BedrockClients:
        if self._injected_clients is None:
            self._injected_clients = BedrockClients(
                region=self.config.region,
                access_mode=self.config.access_mode,
                profile=self.config.profile,
            )
        return self._injected_clients

    def _resolve_model(self, request: ProviderRequest) -> str:
        return request.model or self.config.model or self._default_model()

    def _default_model(self) -> str:
        raise ProviderUnconfigured(
            "aws: no model configured (set JARVIS_AWS_MODEL or pass request.model)"
        )

    def _build_models(self):
        return AWS_MODELS

    def _probe_health(self) -> ProviderHealth:
        if not self.configured:
            return ProviderHealth(
                provider=self.provider_id, status=HealthStatus.UNCONFIGURED
            )
        try:
            return aws_health_probe(self._clients(), provider=self.provider_id)
        except ProviderUnconfigured as exc:
            return ProviderHealth(
                provider=self.provider_id,
                status=HealthStatus.UNCONFIGURED,
                detail=str(exc),
            )

    # -- helpers ---------------------------------------------------------------
    def _system_and_messages(self, request: ProviderRequest) -> tuple[List[str], List[dict]]:
        system: list[str] = []
        messages: list[dict] = []
        for item in request.messages:
            msg = item if isinstance(item, Message) else Message.from_mapping(item)
            if msg.role == "system":
                system.append(msg.content if isinstance(msg.content, str) else str(msg.content))
                continue
            role = "assistant" if msg.role == "assistant" else "user"
            text = msg.content if isinstance(msg.content, str) else str(msg.content or "")
            messages.append({"role": role, "content": [{"text": text}]})
        if not messages:
            messages = [{"role": "user", "content": [{"text": ""}]}]
        return system, messages

    def _to_bedrock_tools(self, tools: Optional[List[dict]]) -> Optional[List[dict]]:
        if not tools:
            return None
        result: list[dict] = []
        for tool in tools:
            function = tool.get("function") or {}
            result.append(
                {
                    "toolSpec": {
                        "name": function.get("name", ""),
                        "description": function.get("description", ""),
                        "inputSchema": {"json": function.get("parameters", {"type": "object"})},
                    }
                }
            )
        return result

    # -- chat ------------------------------------------------------------------
    def chat(self, request: ProviderRequest) -> ProviderResponse:
        self._ensure(Capability.CHAT)
        self._guard_context(request)
        model = self._resolve_model(request)
        system, messages = self._system_and_messages(request)
        t0 = time.monotonic()
        response = self._clients().converse(
            model=model,
            system=system,
            messages=messages,
            tools=self._to_bedrock_tools(request.tools),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        latency = (time.monotonic() - t0) * 1000.0
        output_message = (response.get("output") or {}).get("message") or {}
        content = output_message.get("content") or []
        text = "".join(part.get("text", "") for part in content if part.get("text"))
        tool_calls: list[ToolCall] = []
        for part in content:
            if part.get("toolUse"):
                use = part["toolUse"]
                tool_calls.append(
                    ToolCall(
                        id=use.get("toolUseId", ""),
                        name=use.get("name", ""),
                        arguments=json.dumps(use.get("input", {}) or {}),
                    )
                )
        usage_data = response.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_data.get("inputTokens", 0) or 0),
            completion_tokens=int(usage_data.get("outputTokens", 0) or 0),
        )
        self.telemetry.event(
            provider=self.provider_id, model=model, request_id=request.request_id,
            kind="request", latency_ms=latency,
            prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
            privacy_class=request.privacy_class.value,
        )
        return ProviderResponse(
            provider=self.provider_id,
            model=model,
            text=text,
            tool_calls=tool_calls or None,
            usage=usage,
            latency_ms=latency,
            finish_reason=response.get("stopReason"),
            request_id=request.request_id,
            raw=response,
        )

    # -- streaming --------------------------------------------------------------
    def stream(self, request: ProviderRequest) -> Iterator[StreamChunk]:
        self._ensure(Capability.STREAMING)
        self._guard_context(request)
        model = self._resolve_model(request)
        system, messages = self._system_and_messages(request)
        t0 = time.monotonic()
        usage = Usage()
        for chunk in self._clients().converse_stream(
            model=model,
            system=system,
            messages=messages,
            tools=self._to_bedrock_tools(request.tools),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ):
            if "contentBlockDelta" in chunk:
                delta = (chunk["contentBlockDelta"].get("delta") or {}).get("text", "")
                if delta:
                    yield StreamChunk(provider=self.provider_id, model=model, text=delta)
            elif "messageStop" in chunk:
                reason = chunk["messageStop"].get("stopReason")
                latency = (time.monotonic() - t0) * 1000.0
                self.telemetry.event(
                    provider=self.provider_id, model=model, request_id=request.request_id,
                    kind="stream", latency_ms=latency,
                )
                yield StreamChunk(
                    provider=self.provider_id, model=model,
                    finish_reason=reason, usage=usage, done=True,
                )
            elif "metadata" in chunk:
                meta_usage = (chunk["metadata"].get("usage") or {})
                usage = Usage(
                    prompt_tokens=int(meta_usage.get("inputTokens", 0) or 0),
                    completion_tokens=int(meta_usage.get("outputTokens", 0) or 0),
                )
        yield StreamChunk(provider=self.provider_id, model=model, done=True)

    # -- embeddings ---------------------------------------------------------------
    def embeddings(
        self, texts: Sequence[str], model: Optional[str] = None
    ) -> list[list[float]]:
        self._ensure(Capability.EMBEDDINGS)
        model = model or "amazon.titan-embed-text-v2:0"
        vectors = self._clients().invoke_embedding(model=model, input_texts=list(texts))
        self.telemetry.event(
            provider=self.provider_id, model=model, kind="embedding",
            bytes=sum(len(t) for t in texts),
        )
        return vectors