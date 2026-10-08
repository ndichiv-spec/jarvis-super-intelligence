"""Seed the model lifecycle registry from real platform sources (spec §16, §33).

Seeding is *idempotent* and never mutates existing identities:
:meth:`ModelRegistry.ensure` returns the existing record when the
``(provider, model_id)`` identity already exists, so repeated seeding cannot
overwrite the canonical brain lineage (spec §20), re-parent records, or
collapse Silverwing into the JARVIS family (spec §33).
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from .registry import ModelRegistry
from .types import ModelLifecycleType

log = logging.getLogger("model_lifecycle.discovery")

#: Documented Silverwing model references (family identity only; the runtime
#: registry under ``silverwing_runtime/evaluation/registry.py`` stays canonical).
SILVERWING_REFS: dict[str, str] = {
    "n12m-base-r2000": "silverwing base (r2000, 12M)",
    "n120m-base-v1": "silverwing base (v1, 120M)",
}

#: Firm capability set for all JARVIS brain Qwen3-4B lineage records.
_BRAIN_CAPS = ["chat", "reasoning", "structured_output", "streaming"]


def seed_brain_lineage(
    registry: ModelRegistry,
    lineage: Optional[dict[str, dict[str, Any]]] = None,
    *,
    actor: str = "brain_registry",
) -> list[str]:
    """Register the canonical JARVIS brain lineage (spec §20) without ever
    overwriting it.  The Base entry is recorded as ``JARVIS_BASE`` and the SFT
    candidate as ``JARVIS_CANDIDATE`` with its parent set to the Base row."""
    from brain_runtime.model_registry import BRAIN_MODEL_LINEAGE

    lineage = lineage or BRAIN_MODEL_LINEAGE
    full_ids = list(lineage)
    roots: dict[str, str] = {}  # full_id of the base row -> record_id

    produced: list[str] = []

    # Pass 1: register base rows first so candidates can parent on them.
    root_record_id: Optional[str] = None
    for full_id in full_ids:
        entry = lineage[full_id]
        training_method = str(entry.get("training_method", ""))
        if training_method == "base":
            repo = str(entry.get("repository", full_id))
            record = registry.ensure(
                provider="hf",
                model_id=repo,
                lifecycle_type=ModelLifecycleType.JARVIS_BASE,
                name=str(entry.get("model_id", full_id)),
                family="jarvis-brain",
                revision=str(entry.get("hf_revision", "")),
                capabilities=list(_BRAIN_CAPS),
                deployment="remote_endpoint",  # weights are HF-authoritative
                architecture="qwen3-4b",
                context_length=0,
                source="brain_registry",
                metadata={
                    "brain_full_id": full_id,
                    "training_method": training_method,
                    "notes": entry.get("notes", ""),
                },
                actor=actor,
            )
            roots[full_id] = record.record_id
            root_record_id = record.record_id
            produced.append(full_id)

    # Pass 2: candidates parent on the base row.
    for full_id in full_ids:
        entry = lineage[full_id]
        training_method = str(entry.get("training_method", ""))
        if training_method == "base":
            continue
        repo = str(entry.get("repository", full_id))
        record = registry.ensure(
            provider="hf",
            model_id=repo,
            lifecycle_type=ModelLifecycleType.JARVIS_CANDIDATE,
            name=str(entry.get("model_id", full_id)),
            family="jarvis-brain",
            revision=str(entry.get("hf_revision", "")),
            capabilities=list(_BRAIN_CAPS),
            deployment="remote_endpoint",
            architecture="qwen3-4b",
            source="brain_registry",
            parent_model=root_record_id,
            metadata={
                "brain_full_id": full_id,
                "training_method": training_method,
                "notes": entry.get("notes", ""),
            },
            actor=actor,
        )
        produced.append(full_id)

    return produced


def seed_provider_models(
    registry: ModelRegistry,
    adapters: dict[str, Any],
    *,
    providers: Iterable[str] = ("openai", "nvidia", "google", "aws", "hf"),
    actor: str = "provider_fabric",
) -> int:
    """Register every model advertised by the configured provider adapters as
    ``EXTERNAL_PROVIDER_MODEL`` rows (spec §16).  Idempotent by identity."""
    count = 0
    for pid in providers:
        adapter = adapters.get(pid)
        if adapter is None or not getattr(adapter, "configured", False):
            continue
        models = getattr(adapter, "models", None) or []
        for pm in models:
            registry.ensure(
                provider=pid,
                model_id=pm.model_id,
                lifecycle_type=ModelLifecycleType.EXTERNAL_PROVIDER_MODEL,
                name=pm.name or pm.model_id,
                family=pid,
                deployment=pm.deployment.value,
                capabilities=sorted(c.value for c in pm.capabilities),
                architecture=getattr(pm, "metadata", {}).get("architecture", "unknown"),
                context_length=getattr(pm, "context_length", 0) or 0,
                source="provider_fabric",
                actor=actor,
            )
            count += 1
    return count


def seed_huggingface_discovery(
    registry: ModelRegistry,
    adapter: Any,
    *,
    limit: int = 20,
    actor: str = "huggingface_discovery",
) -> int:
    """Register live-discovered Hub models (spec §2).  Existing identities —
    including the JARVIS brain lineage — are returned untouched."""
    count = 0
    if not getattr(adapter, "configured", False):
        return 0
    try:
        rows = adapter.discover_models(limit=limit)
    except Exception as exc:  # live network can fail; seeding must not raise
        log.warning("hf discovery failed: %s", exc)
        return 0
    for row in rows:
        registry.ensure(
            provider="hf",
            model_id=row.get("model_id", ""),
            lifecycle_type=ModelLifecycleType.EXTERNAL_PROVIDER_MODEL,
            name=row.get("model_id", "").split("/")[-1],
            family="hf",
            revision=row.get("sha") or "",
            capabilities=sorted(c.value for c in row.get("capabilities", [])),
            deployment="remote_endpoint",
            architecture=row.get("architecture", "unknown"),
            context_length=row.get("context_length") or 0,
            source="huggingface_discovery",
            metadata={
                "pipeline_tag": row.get("pipeline_tag") or "",
                "downloads": row.get("downloads", 0),
                "likes": row.get("likes", 0),
                "gated": bool(row.get("gated")),
            },
            actor=actor,
        )
        count += 1
    return count


def seed_silverwing(
    registry: ModelRegistry,
    *,
    refs: Optional[dict[str, str]] = None,
    actor: str = "silverwing_registry",
) -> int:
    """Record Silverwing model identities in their *own* family (spec §33).
    The distinct family keeps the Silverwing line from ever merging into the
    JARVIS brain lineage."""
    count = 0
    for model_id, label in (refs or SILVERWING_REFS).items():
        registry.ensure(
            provider="silverwing",
            model_id=model_id,
            lifecycle_type=ModelLifecycleType.LOCAL_MODEL,
            name=label,
            family="silverwing",
            deployment="local",
            architecture="silverwing",
            source="silverwing_registry",
            actor=actor,
        )
        count += 1
    return count


def seed_all(
    registry: ModelRegistry,
    adapters: Optional[dict[str, Any]] = None,
    *,
    include_hf_discovery: bool = True,
    hf_discovery_limit: int = 20,
) -> dict:
    """Seed everything in one call (brain lineage, provider models, optional
    live HF discovery, Silverwing).  Returns a summary dict."""
    brain = seed_brain_lineage(registry)
    silverwing = seed_silverwing(registry)
    provider = 0
    hf = 0
    if adapters:
        provider = seed_provider_models(registry, adapters)
        if include_hf_discovery and adapters.get("hf"):
            hf = seed_huggingface_discovery(
                registry, adapters["hf"], limit=hf_discovery_limit
            )
    return {
        "brain_lineage": brain,
        "provider_models": provider,
        "hf_discovered": hf,
        "silverwing": silverwing,
        "records": len(registry),
    }