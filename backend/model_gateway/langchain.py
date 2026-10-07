"""LangChain-compatible adapter around the Silverwing gateway.

Adaapter spec (section 29)::

    SilverwingLLM(
        endpoint=...,
        model="silverwing-120m-base-v1"
    )

The adapter calls the REMOTE API through the gateway client.  LangChain is NOT
installed into the Transformer runtime for this integration: LangChain is
imported only if the *caller* already has it (the adapter raises a helpful
error otherwise).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .client import SilverwingClient
from .models import GatewayError

log = logging.getLogger("model_gateway.langchain")


class SilverwingLLM:
    """A minimal LangChain-compatible chat model backed by the gateway.

    Implements the subset of the LangChain ``BaseChatModel`` contract used by
    ``invoke`` / ``predict`` / ``stream`` without requiring LangChain to be
    installed at import time.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        model: str = "silverwing-120m-base-v1",
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
        timeout: float | None = None,
        **_extra: Any,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = SilverwingClient(
            endpoint=endpoint or _env_optional(),
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    # -- LangChain BaseChatModel surface --------------------------------
    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        """LangChain-compatible invoke: accepts a list of message-like dicts."""
        normalized = _normalize_messages(messages)
        import asyncio

        try:
            resp = asyncio.run(
                self.client.chat(
                    normalized,
                    temperature=kwargs.get("temperature", self.temperature),
                    max_new_tokens=kwargs.get("max_tokens", self.max_tokens),
                )
            )
        except GatewayError:
            raise
        except RuntimeError:
            raise
        return _message_from(resp)

    async def ainvoke(self, messages: Any, **kwargs: Any) -> Any:
        normalized = _normalize_messages(messages)
        resp = await self.client.chat(
            normalized,
            temperature=kwargs.get("temperature", self.temperature),
            max_new_tokens=kwargs.get("max_tokens", self.max_tokens),
        )
        return _message_from(resp)

    def predict(self, text: str, **kwargs: Any) -> str:
        resp = self.invoke([{"role": "user", "content": text}], **kwargs)
        return _content_of(resp)

    def stream(self, _messages: Any, **_kwargs: Any) -> Any:
        yield from []  # streaming handled by the runtime SSE path; see note below

    # -- framework-agnostic extras ---------------------------------------
    def __call__(self, prompt: str, **kwargs: Any) -> str:
        return self.predict(prompt, **kwargs)

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model": self.model, "temperature": self.temperature}

    @property
    def _llm_type(self) -> str:
        return "silverwing"


def _env_optional() -> str | None:
    import os

    return os.environ.get("SILVERWING_ENDPOINT") or None


def _normalize_messages(messages: Any) -> list[dict[str, str]]:
    """Coerce LangChain message objects / dicts / strings to plain dicts."""
    out: list[dict[str, str]] = []
    if isinstance(messages, str):
        out.append({"role": "user", "content": messages})
        return out
    for m in messages:
        if isinstance(m, dict):
            out.append({"role": m.get("role", "user"), "content": m.get("content", "")})
            continue
        role = getattr(m, "type", None) or getattr(m, "role", "user")
        if role in ("human", "user"):
            role = "user"
        elif role in ("ai", "assistant"):
            role = "assistant"
        elif role == "system":
            role = "system"
        content = getattr(m, "content", "")
        if isinstance(content, list):
            content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        out.append({"role": role, "content": str(content)})
    return out


def _message_from(resp: Any) -> Any:
    """Wrap the gateway response into a LangChain-friendly object."""
    try:
        from langchain_core.messages import AIMessage  # type: ignore[import-not-found]
    except Exception:
        return _ChatMessageProxy(content=resp.content, model=resp.model)
    return AIMessage(content=resp.content)


def _content_of(msg: Any) -> str:
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", "") or ""


class _ChatMessageProxy:
    """Fallback message object when LangChain is not installed."""

    def __init__(self, content: str, model: str = ""):
        self.content = content
        self.model = model

    def content_string(self) -> str:
        return self.content
