"""Tests for capability-aware Brain backend routing (spec Part F).

No real provider is exercised: candidates are injected fakes so the priority
order + health-gating logic is verified without credentials or network.
"""
from __future__ import annotations

import pytest

from brain_runtime.backends.base import BrainBackend
from brain_runtime.config import BrainConfig
from brain_runtime.generation import BrainGenerationConfig
from brain_runtime.routing import BrainRouter


class _FakeBackend(BrainBackend):
    """Minimal in-memory backend used only to exercise the router."""

    def __init__(self, name: str, *, fail_load: bool = False, fail_warmup: bool = False) -> None:
        self._name = name
        self.backend = name
        self.device = "cpu"
        self.model_id = f"model-{name}"
        self.parameters = 0
        self.revision = "fake"
        self.stream_support = False
        self.provider = name
        self._fail_load = fail_load
        self._fail_warmup = fail_warmup
        self.load_called = False
        self.warmup_called = False

    def load(self) -> None:
        self.load_called = True
        if self._fail_load:
            raise RuntimeError(f"{self._name} load fails")
        self.loaded = True

    def warmup(self, prompt: str) -> str:
        self.warmup_called = True
        if self._fail_warmup:
            raise RuntimeError(f"{self._name} warmup fails")
        return f"warm-{self._name}"

    def generate(self, messages, configuration: BrainGenerationConfig):
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - not used by router
        pass


@pytest.mark.brain
class TestBrainRouterPriority:
    def test_selects_first_healthy_in_priority_order(self):
        first = _FakeBackend("good-a")
        second = _FakeBackend("good-b")
        router = BrainRouter(
            BrainConfig(backend="stub"),
            candidates=[
                ("good-a", lambda: first, True),
                ("good-b", lambda: second, True),
            ],
        )
        backend, reason = router.select()
        assert backend is first
        assert reason == "selected:good-a"
        assert first.load_called and first.warmup_called
        assert not second.load_called  # never probed the winner's successor

    def test_skips_unhealthy_then_falls_through(self):
        bad = _FakeBackend("bad", fail_load=True)
        good = _FakeBackend("good")
        router = BrainRouter(
            BrainConfig(backend="stub"),
            candidates=[
                ("bad", lambda: bad, True),
                ("good", lambda: good, True),
            ],
        )
        backend, reason = router.select()
        assert backend is good
        assert reason == "selected:good"
        assert bad.load_called  # probed then skipped

    def test_skips_warmup_failure(self):
        bad = _FakeBackend("bad", fail_warmup=True)
        good = _FakeBackend("good")
        router = BrainRouter(
            BrainConfig(backend="stub"),
            candidates=[
                ("bad", lambda: bad, True),
                ("good", lambda: good, True),
            ],
        )
        backend, reason = router.select()
        assert backend is good
        assert bad.warmup_called and bad.load_called

    def test_no_healthy_configured_returns_none(self):
        router = BrainRouter(
            BrainConfig(backend="stub"),
            candidates=[
                ("bad", lambda: _FakeBackend("bad", fail_load=True), True),
            ],
        )
        backend, reason = router.select()
        assert backend is None
        assert "no healthy configured backend" in reason

    def test_unconfigured_candidates_are_not_probed(self):
        """A candidate flagged not-configured must never be probed (honesty: never
        probe a credential we do not have)."""
        probed = []
        good = _FakeBackend("good")
        router = BrainRouter(
            BrainConfig(backend="stub"),
            candidates=[
                ("absent", lambda: probed.append("touched") or good, False),
                ("good", lambda: good, True),
            ],
        )
        backend, reason = router.select()
        assert backend is good
        assert probed == []  # the not-configured candidate was never built

    def test_candidate_names_only_configured(self):
        router = BrainRouter(
            BrainConfig(backend="stub"),
            candidates=[
                ("nvidia", lambda: None, False),
                ("stub", lambda: _FakeBackend("stub"), True),
            ],
        )
        assert router.candidate_names() == ["stub"]
