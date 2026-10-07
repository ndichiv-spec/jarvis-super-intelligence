"""Data model for provider entries in the JARVIS Provider Fabric.

A :class:`ProviderModel` is the registry unit the fabric works with: a model id
namespaced by provider (``openai:gpt-5.x``, ``nvidia:nim:...``, ``google:gemini-...``,
``aws:bedrock:...``, ``hf:...``, ``jarvis:jarvis-brain-...``, ``silverwing:...``)
together with honest per-model capability, pricing, privacy and availability
metadata (spec §32/§39/§65).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from .capabilities import Capability, serialize, validate_capabilities


class DeploymentKind(str, Enum):
    """Where the model actually runs."""

    HOSTED = "hosted"  # provider cloud API
    SELF_HOSTED = "self_hosted"  # e.g. NVIDIA NIM on your infra
    LOCAL = "local"  # weights on this machine
    ADAPTER = "adapter"  # fine-tune/adapter over a base
    REMOTE_ENDPOINT = "remote_endpoint"  # any OpenAI-compatible remote


class CostClass(str, Enum):
    """Bounded cost bucket. Never an invented number — a bucket only."""

    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PrivacyClass(str, Enum):
    """Data-privacy class for routing (spec §36)."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    SENSITIVE = "sensitive"
    LOCAL_ONLY = "local_only"


@dataclass(frozen=True)
class ProviderModel:
    """Immutable registry entry describing one model behind one provider."""

    provider: str
    model_id: str
    name: str = ""
    deployment: DeploymentKind = DeploymentKind.HOSTED
    context_length: int = 0
    max_output_tokens: int = 4096
    capabilities: frozenset[Capability] = frozenset()
    pricing_per_1k: tuple[float | None, float | None] = (None, None)  # input, output
    cost_class: CostClass = CostClass.MEDIUM
    privacy_class: PrivacyClass = PrivacyClass.PUBLIC
    latency_class: str = "medium"  # low | medium | high
    aliases: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", validate_capabilities(self.capabilities))

    @property
    def qualified_id(self) -> str:
        return f"{self.provider}:{self.model_id}"

    @property
    def supports(self) -> set[Capability]:
        return set(self.capabilities)

    def supports_capability(self, cap: Capability) -> bool:
        return cap in self.capabilities

    def declared(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model_id,
            "name": self.name or self.model_id,
            "deployment": self.deployment.value,
            "context_length": self.context_length,
            "capabilities": serialize(self.capabilities),
            "cost_class": self.cost_class.value,
            "privacy_class": self.privacy_class.value,
        }


@dataclass(frozen=True)
class ModelRef:
    """A parsed ``<provider>:<model>`` string (spec §42)."""

    provider: str
    model: str

    @classmethod
    def parse(cls, qualified: str) -> "ModelRef":
        if ":" not in qualified:
            raise ValueError(
                f"model reference {qualified!r} must be '<provider>:<model>'"
            )
        provider, model = qualified.split(":", 1)
        if not provider or not model:
            raise ValueError(f"invalid model reference {qualified!r}")
        return cls(provider=provider, model=model)

    @property
    def qualified_id(self) -> str:
        return f"{self.provider}:{self.model}"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.qualified_id


def models_from_declared(
    provider: str,
    entries: Sequence[dict],
) -> list[ProviderModel]:
    """Build :class:`ProviderModel` entries from a list of declared dicts.

    ``entries`` items carry: ``model``/``model_id``, optional ``name``,
    ``deployment``, ``context_length``, ``capabilities`` (list or comma string),
    optional ``pricing_per_1k``, ``cost_class``, ``privacy_class``,
    ``latency_class``, ``aliases``, ``metadata``.
    """
    result: list[ProviderModel] = []
    for entry in entries:
        caps = entry.get("capabilities", [])
        if isinstance(caps, (list, tuple, set)):
            caps = " ".join(str(c) for c in caps)
        pricing = tuple(entry.get("pricing_per_1k") or (None, None))
        result.append(
            ProviderModel(
                provider=provider,
                model_id=entry.get("model") or entry.get("model_id", ""),
                name=entry.get("name", ""),
                deployment=DeploymentKind(entry.get("deployment", "hosted")),
                context_length=int(entry.get("context_length", 0) or 0),
                max_output_tokens=int(entry.get("max_output_tokens", 4096) or 4096),
                capabilities=validate_capabilities(_as_caps(caps)),
                pricing_per_1k=(pricing[0], pricing[1]),
                cost_class=CostClass(entry.get("cost_class", "medium")),
                privacy_class=PrivacyClass(entry.get("privacy_class", "public")),
                latency_class=entry.get("latency_class", "medium"),
                aliases=tuple(entry.get("aliases", []) or []),
                metadata=entry.get("metadata", {}) or {},
            )
        )
    return result


def _as_caps(raw) -> list[Capability]:
    from .capabilities import parse_capability

    if isinstance(raw, str):
        return [parse_capability(p) for p in raw.replace(",", " ").split() if p]
    out: list[Capability] = []
    for item in raw:
        out.append(parse_capability(item))
    return out