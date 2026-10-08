"""Gateway data models.

Frameworks (pydantic) are used only for validation; the gateway itself is
HTTP-based and framework-independent.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GatewayModel(BaseModel):
    """A model known to the gateway (mirrors /v1/models)."""

    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "silverwing"
    context_length: int | None = None
    parameters: int | None = None
    capabilities: list[str] = Field(default_factory=list)
    status: str = ""

    @property
    def is_eligible(self) -> bool:
        return self.status not in ("archived", "deprecated")


class GatewayMessage(BaseModel):
    role: str = "user"
    content: str = ""


class GatewayUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class GatewayToolCall(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class GatewayResponse(BaseModel):
    """Normalized response returned by ``generate`` / ``chat``."""

    content: str = ""
    model: str = ""
    revision: str = ""
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    usage: GatewayUsage = Field(default_factory=GatewayUsage)
    tool_calls: list[GatewayToolCall] = Field(default_factory=list)
    verification: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GatewayError(Exception):
    """Raised when the Silverwing runtime is unreachable or errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "gw_error",
        retryable: bool = False,
        status: int | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.status = status

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"
