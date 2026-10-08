"""Framework-independent generation interface.

`generate()` and `chat()` are the internal API of the runtime.  They do NOT
depend on torch, transformers or LangChain — they are plain requests/results
that any backend (torch, vLLM, a remote service, or a deterministic test
backend) can fulfil.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenerationConfig(BaseModel):
    max_new_tokens: int = 256
    temperature: float = 0.7
    top_k: int | None = None
    top_p: float = 0.9
    repetition_penalty: float = 1.0
    stop: list[str] | None = None


class GenerationRequest(BaseModel):
    prompt: str
    config: GenerationConfig | None = None


class GenerationResult(BaseModel):
    text: str
    finish_reason: str = "stop"
    model: str = ""
    revision: str = ""
    latency_ms: float = 0.0
    tokens_input: int = 0
    tokens_generated: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatResult(BaseModel):
    message: ChatMessage
    finish_reason: str = "stop"
    model: str = ""
    revision: str = ""
    latency_ms: float = 0.0
    usage: dict[str, int] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def messages_to_prompt(messages: list[dict[str, str]]) -> str:
    """Serialize a chat message list into a prompt (framework-neutral).

    Deterministic BASE-model template (Silverwing-120M-Base).  ``<|role|>``
    blocks are a plain formatting convention; the checkpoint is NOT
    instruction-tuned, so no instruction-tuning is claimed (section 12).
    Generation begins from the final ``<|assistant|>`` position.
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        parts.append(f"<|{role}|>\n{content}")
    if not parts:
        parts.append("<|user|>\n")
    if (messages[-1].get("role") if messages else None) != "assistant":
        parts.append("<|assistant|>\n")
    return "\n".join(parts)


def generate(
    prompt: str,
    max_new_tokens: int = 256,
    temperature: float = 0.7,
    top_k: int | None = None,
    top_p: float = 0.9,
    repetition_penalty: float = 1.0,
) -> GenerationRequest:
    """Build a :class:`GenerationRequest` (the runtime-side generation call)."""
    return GenerationRequest(
        prompt=prompt,
        config=GenerationConfig(
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
        ),
    )


def chat(
    messages: list[dict[str, str]],
    generation_config: GenerationConfig | None = None,
    tools: list[dict[str, Any]] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a framework-neutral chat payload (prompt + config).

    ``tools``/``memory`` are passed through untouched: they are assembled and
    executed by the platform (RAG, memory, tool registry), never by the model
    runtime.
    """
    return {
        "prompt": messages_to_prompt(messages),
        "config": (generation_config or GenerationConfig()).model_dump(),
        "tools": tools or [],
        "memory": memory or {},
    }
