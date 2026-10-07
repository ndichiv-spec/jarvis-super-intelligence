"""Capability model for the JARVIS Provider Fabric.

A *capability* is an ability a provider may (or may not) implement: chat,
responses, streaming, tool calling, vision, audio, embeddings, reranking,
structured output, reasoning, batch, fine-tuning, evaluation, web/file search,
computer use.

An adapter declares its capabilities once (spec §3, §7). The rest of the platform
never asks a provider to do something it did not declare — that is the "never
pretend" rule. ``validate_capabilities`` makes it impossible to register a
typo'd or invented capability.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Sequence


class Capability(str, Enum):
    """Single source of truth for what "a capability" is.

    Values are stable lowercase hyphenated strings so they can be persisted in
    provider metadata / model catalogs as plain JSON.
    """

    CHAT = "chat"
    RESPONSES = "responses"
    STREAMING = "streaming"
    TOOL_CALLING = "tool_calling"
    VISION = "vision"
    AUDIO = "audio"
    EMBEDDINGS = "embeddings"
    RERANKING = "reranking"
    STRUCTURED_OUTPUT = "structured_output"
    REASONING = "reasoning"
    BATCH = "batch"
    FINE_TUNING = "fine_tuning"
    EVALUATION = "evaluation"
    WEB_SEARCH = "web_search"
    FILE_SEARCH = "file_search"
    COMPUTER_USE = "computer_use"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


ALL_CAPABILITIES: tuple[str, ...] = tuple(sorted(cap.value for cap in Capability))

_BY_VALUE = {cap.value: cap for cap in Capability}

# Capabilities that describe model-quality / multiplier dimensions (per-model),
# versus platform service capabilities that are provider-wide.
QUALITY_CAPABILITIES = frozenset(
    {Capability.REASONING, Capability.VISION, Capability.AUDIO}
)


def parse_capability(raw: str | Capability) -> Capability:
    """Coerce ``raw`` into a :class:`Capability`, rejecting unknown values."""
    if isinstance(raw, Capability):
        return raw
    try:
        return _BY_VALUE[raw.strip().lower()]
    except KeyError:
        known = ", ".join(ALL_CAPABILITIES)
        raise ValueError(
            f"Unknown capability {raw!r}. Known capabilities: {known}"
        ) from None


def parse_capabilities(
    raw: str | Sequence[str | Capability] | None,
) -> frozenset[Capability]:
    """Parse a capability declaration from a comma string or iterable."""
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        parts = [p for p in (part.strip() for part in raw.split(",")) if p]
    else:
        parts = list(raw)
    return frozenset(parse_capability(p) for p in parts)


def validate_capabilities(caps: Iterable[Capability]) -> frozenset[Capability]:
    """Raise if any capability is not a known :class:`Capability`.

    Guards provider metadata against invented or misspelled capability names so
    the registry can never advertise a capability nobody implements.
    """
    result = frozenset(caps)
    for cap in result:
        if not isinstance(cap, Capability):
            raise ValueError(f"Not a Capability: {cap!r}")
    return result


def serialize(caps: Iterable[Capability]) -> list[str]:
    return sorted(cap.value for cap in caps)