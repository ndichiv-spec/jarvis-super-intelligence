"""The ProviderAdapter contract — core of the JARVIS Provider Fabric (spec §3, §7).

A :class:`ProviderAdapter` is one provider behind a single capability-facing
surface. The adapter *declares* what it can do (``declared_capabilities``), is
never asked to do anything else (``require`` raises), and admits when it is not
configured (``ProviderUnconfigured``) rather than faking a call.

``chat`` / ``stream`` / ``responses`` / ``embeddings`` all funnel through the same
secret-isolation guard: any configured credential value found inside the outbound
context aborts the request (spec §16/§69: "Brain sees tool capability, never the
secret").
"""

from __future__ import annotations

import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Iterator, Optional, Sequence

from .capabilities import Capability
from .errors import (
    ProviderUnconfigured,
    SecretLeakError,
    UnsupportedCapability,
)
from .health import (
    HealthCache,
    HealthStatus,
    ProviderHealth,
    record_inference_result,
)
from .models import PrivacyClass, ProviderModel
from .secrets import SecretManager, get_secret_manager
from .telemetry import ProviderTelemetry, get_telemetry


@dataclass
class ToolCall:
    index: int = 0
    id: str = ""
    name: str = ""
    arguments: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": int(self.prompt_tokens or 0),
            "completion_tokens": int(self.completion_tokens or 0),
            "total_tokens": self.total_tokens,
        }


@dataclass
class Message:
    role: str = "user"
    content: Any = ""  # str or list of part dicts ({"type": "text", ...}, ...)
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None

    def as_openai(self) -> dict:
        msg: dict[str, Any] = {"role": self.role}
        if self.content and not isinstance(self.content, str):
            msg["content"] = self.content
        elif isinstance(self.content, str):
            msg["content"] = self.content
        else:
            msg["content"] = self.content or ""
        if self.name:
            msg["name"] = self.name
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return msg

    @staticmethod
    def system(text: str) -> "Message":
        return Message(role="system", content=text)

    @staticmethod
    def user(text: str) -> "Message":
        return Message(role="user", content=text)

    @staticmethod
    def from_mapping(mapping: dict | Message) -> "Message":
        if isinstance(mapping, Message):
            return mapping
        tool_calls = None
        raw_calls = mapping.get("tool_calls")
        if raw_calls:
            tool_calls = [
                ToolCall(
                    index=i,
                    id=call.get("id", ""),
                    name=(call.get("function") or {}).get("name", ""),
                    arguments=(call.get("function") or {}).get("arguments"),
                )
                for i, call in enumerate(raw_calls)
            ]
        return Message(
            role=mapping.get("role", "user"),
            content=mapping.get("content", ""),
            name=mapping.get("name"),
            tool_call_id=mapping.get("tool_call_id"),
            tool_calls=tool_calls,
        )


@dataclass
class ProviderRequest:
    """Normalized request every adapter understands."""

    messages: list[Message] = field(default_factory=list)
    model: Optional[str] = None  # adapter/model default if omitted
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list[dict]] = None  # OpenAI tool schema list
    response_format: Optional[dict] = None
    privacy_class: PrivacyClass = PrivacyClass.PUBLIC
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timeout: Optional[float] = None
    extra: dict = field(default_factory=dict)

    def as_openai_messages(self) -> list[dict]:
        return [m.as_openai() if isinstance(m, Message) else Message.from_mapping(m).as_openai() for m in self.messages]

    def to_safe_text(self) -> str:
        """Serialized context (for the secret-isolation guard)."""
        parts: list[str] = []
        for m in self.messages:
            content = m.content if isinstance(m, Message) else m.get("content")
            if isinstance(content, str):
                parts.append(content)
            else:
                parts.append(str(content))
        return "\n".join(parts)


@dataclass
class ProviderResponse:
    provider: str
    model: str
    text: str = ""
    reasoning: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    usage: Optional[Usage] = None
    latency_ms: Optional[float] = None
    finish_reason: Optional[str] = None
    request_id: str = ""
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "text": self.text,
            "reasoning": self.reasoning,
            "tool_calls": [tc.to_dict() for tc in (self.tool_calls or [])],
            "usage": self.usage.to_dict() if self.usage else None,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "request_id": self.request_id,
        }


@dataclass
class StreamChunk:
    provider: str = ""
    model: str = ""
    text: str = ""
    reasoning: str = ""
    finish_reason: Optional[str] = None
    done: bool = False
    usage: Optional[Usage] = None
    tool_calls: Optional[list[ToolCall]] = None


def _default_request_id() -> str:
    return uuid.uuid4().hex[:16]


class ProviderAdapter(ABC):
    """Base class every provider adapter implements.

    Subclasses must set ``provider_id`` and ``declared_capabilities`` and implement
    ``chat`` at minimum. Everything else defaults to an *honest* refusal.
    """

    provider_id: str = ""
    display_name: str = ""
    declared_capabilities: frozenset[Capability] = frozenset()

    def __init__(
        self,
        secrets: Optional[SecretManager] = None,
        telemetry: Optional[ProviderTelemetry] = None,
    ) -> None:
        if not self.provider_id:
            raise ValueError("ProviderAdapter subclasses must set provider_id")
        self.secrets = secrets or get_secret_manager()
        self.telemetry = telemetry or get_telemetry()
        self._health_cache: HealthCache | None = None
        self._models: list[ProviderModel] | None = None

    # -- capability declaration ---------------------------------------------
    def supports(self, capability: Capability | str) -> bool:
        cap = capability.value if isinstance(capability, Capability) else capability
        return any(c.value == cap for c in self.declared_capabilities)

    def require(self, capability: Capability, detail: str = "") -> None:
        if not self.supports(capability):
            raise UnsupportedCapability(
                self.provider_id, capability.value, detail=detail
            )

    @property
    def configured(self) -> bool:  # overridden where a config object exists
        return True

    # -- models -------------------------------------------------------------
    @property
    def models(self) -> list[ProviderModel]:
        if self._models is None:
            self._models = self._build_models()
        return self._models

    def find_model(self, model_id: str) -> Optional[ProviderModel]:
        for model in self.models:
            if model.model_id == model_id or model_id in model.aliases:
                return model
        return None

    def _build_models(self) -> list[ProviderModel]:
        return []

    def list_models(self, refresh: bool = False) -> list[ProviderModel]:
        if refresh:
            self._models = None
        return self.models

    # -- health -------------------------------------------------------------
    def _probe_health(self) -> ProviderHealth:
        if not self.configured:
            return ProviderHealth(
                provider=self.provider_id, status=HealthStatus.UNCONFIGURED
            )
        return ProviderHealth(
            provider=self.provider_id, status=HealthStatus.UNKNOWN
        )

    def _build_health_cache(self) -> HealthCache:
        return HealthCache(self.provider_id, self._probe_health)
    def health(self, force: bool = False) -> ProviderHealth:
        if self._health_cache is None:
            self._health_cache = self._build_health_cache()
        result = self._health_cache.get(force=force)
        self.telemetry.event(
            provider=self.provider_id,
            kind="health",
            status=result.status.value,
            latency_ms=result.latency_ms,
        )
        return result

    def mark_inference_verified(self, models_found: int = 0) -> None:
        if self._health_cache is None:
            self._health_cache = self._build_health_cache()
        current = self._health_cache.get(force=False)
        updated = replace(
            current,
            status=HealthStatus.HEALTHY,
            endpoint_reachable=True,
            credential_authorized=True,
            inference_verified=True,
            models_found=max(current.models_found, models_found),
        )
        self._health_cache.set(updated)
        record_inference_result(
            self.provider_id,
            HealthStatus.HEALTHY,
            models_found=updated.models_found,
        )

    def mark_inference_failed(
        self,
        detail: str = "",
        status: HealthStatus = HealthStatus.AUTHENTICATION_FAILED,
    ) -> None:
        if self._health_cache is None:
            self._health_cache = self._build_health_cache()
        current = self._health_cache.get(force=False)
        updated = replace(
            current,
            status=status,
            endpoint_reachable=True,
            credential_authorized=False if status is HealthStatus.AUTHENTICATION_FAILED else None,
            inference_verified=False,
            detail=detail or current.detail,
        )
        self._health_cache.set(updated)
        record_inference_result(
            self.provider_id,
            status,
            models_found=updated.models_found,
            detail=updated.detail,
        )

    # -- guards ---------------------------------------------------------------
    def _guard_context(self, request: ProviderRequest) -> None:
        """Never let a configured credential reach the model context.

        Scans *all* secrets known to the SecretManager against the serialized
        request text (spec §16/§69: "Brain sees tool capability, never the
        secret").  Any match raises :class:`SecretLeakError` before the
        request is dispatched.
        """
        if not request.messages:
            return
        try:
            self.secrets.assert_no_secrets(
                request.to_safe_text(), force_scan_all=True
            )
        except SecretLeakError:
            self.telemetry.event(
                provider=self.provider_id,
                kind="error",
                error="secret_leak_refused",
                request_id=request.request_id,
            )
            raise

    def _ensure(self, capability: Capability) -> None:
        self.require(capability)
        if not self.configured:
            raise ProviderUnconfigured(
                f"{self.provider_id} is not configured for {capability.value}"
            )

    # -- public surface (adapters implement at least chat) -----------------
    @abstractmethod
    def chat(self, request: ProviderRequest) -> ProviderResponse:
        """Single non-streamed completion."""

    def stream(self, request: ProviderRequest) -> Iterator[StreamChunk]:
        """Streamed completion as chunk iterator. Honest default refusals."""
        self._ensure(Capability.STREAMING)
        chunk = StreamChunk(provider=self.provider_id, model=request.model or "")
        chunk.done = True
        yield chunk

    def responses(self, request: ProviderRequest) -> ProviderResponse:
        """OpenAI-style Responses API where supported."""
        self.require(Capability.RESPONSES, detail="responses endpoint")
        raise UnsupportedCapability(
            self.provider_id, Capability.RESPONSES.value, "not implemented"
        )

    def embeddings(
        self, texts: Sequence[str], model: Optional[str] = None
    ) -> list[list[float]]:
        self.require(Capability.EMBEDDINGS, detail="embeddings endpoint")
        raise UnsupportedCapability(
            self.provider_id, Capability.EMBEDDINGS.value, "not implemented"
        )

    def rerank(
        self, query: str, documents: Sequence[str], model: Optional[str] = None
    ) -> list[float]:
        self.require(Capability.RERANKING, detail="rerank endpoint")
        raise UnsupportedCapability(
            self.provider_id, Capability.RERANKING.value, "not implemented"
        )


_default_lock = threading.Lock()
