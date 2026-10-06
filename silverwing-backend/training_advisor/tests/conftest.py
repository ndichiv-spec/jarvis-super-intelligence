"""Shared fixtures for the Training Advisor test suite.

SILVERWING_PERSIST=0 is inherited from backend/conftest.py; we also guard it
here so these tests can run in isolation.
"""
import os

os.environ.setdefault("SILVERWING_PERSIST", "0")

import dataclasses
import pytest

from training_advisor import AdvisorConfig, TrainingAdvisor


def _cfg(**overrides):
    """A config with gemini DISABLED (no key in the test env)."""
    c = AdvisorConfig()
    return dataclasses.replace(c, **overrides)


def _cfg_with_key(monkeypatch, **overrides):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    c = AdvisorConfig()
    return dataclasses.replace(c, **overrides)


@pytest.fixture
def cfg():
    return _cfg()


@pytest.fixture
def cfg_fast():
    # Fast interval/ttl for cache + interval-gating tests.
    return _cfg(advisory_interval_seconds=60.0, cache_ttl_seconds=60.0)


@pytest.fixture
def cfg_key(monkeypatch):
    return _cfg_with_key(monkeypatch)


@pytest.fixture
def ta(cfg):
    return TrainingAdvisor(cfg)


@pytest.fixture
def ta_key(cfg_key):
    return TrainingAdvisor(cfg_key)
