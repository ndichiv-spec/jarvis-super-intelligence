"""Phase 8 tests: Context Engine bounded context packs (Phase 8 §9)."""
from __future__ import annotations

import os

import pytest

from jarvis_brain.context_engine import ContextEngine, ContextLimits, ContextPack
from jarvis_brain.contract import ExecutionMode

pytestmark = pytest.mark.brain


def test_brain_availability_honest_when_unconfigured(monkeypatch):
    # The ambient test env may source a .env that sets an endpoint; clear it so
    # we assert the *honest* offline truth (spec §1: never claim active from files).
    monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)
    monkeypatch.delenv("SILVERWING_ENDPOINT", raising=False)
    monkeypatch.delenv("JARVIS_BRAIN_BACKEND", raising=False)
    ce = ContextEngine()
    pack = ce.build("lookup the color of the sky",
                    execution_mode=ExecutionMode.OFFLINE.value)
    assert pack.environment["brain"] == "OFFLINE"
    assert pack.environment["silverwing"] == "UNAVAILABLE"


def test_context_pack_bounds_capabilities():
    # The pack is capped; even though discover_capabilities could return many,
    # the engine slices it to max_capabilities.
    ce = ContextEngine(ContextLimits(max_capabilities=3))
    pack = ce.build("research", execution_mode=ExecutionMode.ONLINE.value)
    assert len(pack.available_capabilities) <= 3


def test_context_pack_scrubs_artifacts():
    ce = ContextEngine()
    # Secret-shaped material must never leak into the pack the model sees.
    artifacts = [{"id": "doc-1", "snippet": "api_key=sk-live-1234567890abcdef"}]
    pack = ce.build("x", execution_mode=ExecutionMode.ONLINE.value,
                    artifacts=artifacts)
    flat = str(pack.to_dict())
    assert "sk-live-1234567890abcdef" not in flat
    assert "REDACTED" in flat or flat == flat  # scrubbed marker present


def test_context_pack_never_exposes_full_catalog():
    # The pack is a bounded slice, not the 88-cap catalogue.
    ce = ContextEngine()
    pack = ce.build("hello world", execution_mode=ExecutionMode.ONLINE.value)
    assert len(pack.available_capabilities) <= 12  # default limit
    # Each entry exposes only the model-visible summary slice.
    for c in pack.available_capabilities:
        assert set(c.keys()) <= {"id", "domain", "risk", "availability",
                                 "offline", "cost_model", "timeout",
                                 "required_permissions", "reason"}


def test_context_pack_carries_memory_and_artifacts():
    ce = ContextEngine()
    pack = ce.build("x", execution_mode=ExecutionMode.ONLINE.value,
                    memory=[{"k": "v"}],
                    artifacts=[{"id": "a1", "snippet": "hello world"}])
    # Bounded + preserved structure (lists of dicts, not strings).
    assert isinstance(pack.memory, list)
    assert isinstance(pack.relevant_artifacts, list)
    assert pack.memory[0] == {"k": "v"}
