"""Unit tests for the Browser's provider-aware model routing (ADV-12).

These prove the honesty contract (§62): the browser never suggests a cloud
provider as a fallback unless that provider is genuinely configured (API key
present in the environment). Previously the fallback was a hardcoded "openai",
which would route to a provider that may not be connected.
"""
from __future__ import annotations

from jarvis_backend.routers import browser as br

_PROVIDER_KEY_ENVS = [
    "OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI",
    "ANTHROPIC_API_KEY", "JARVIS_API_KEY_CLAUDE",
    "GOOGLE_API_KEY", "JARVIS_API_KEY_GEMINI",
    "HF_TOKEN",
    "JARVIS_API_KEY_WHISPER", "JARVIS_API_KEY_STABLEDIFFUSION",
    "JARVIS_API_KEY_CODEMUSE",
]


def _scrub(monkeypatch):
    for k in _PROVIDER_KEY_ENVS:
        monkeypatch.delenv(k, raising=False)


def test_fallback_is_none_when_no_provider_configured(monkeypatch):
    _scrub(monkeypatch)
    fb = br._select_browser_cloud_fallback()
    # Never fakes "openai" -- if nothing is configured, report None.
    assert fb["provider"] is None
    assert fb["capability"] is None
    assert "no cloud provider configured" in fb["reason"]


def test_fallback_picks_openai_only_when_key_present(monkeypatch):
    _scrub(monkeypatch)
    assert br._select_browser_cloud_fallback()["provider"] is None
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    assert br._select_browser_cloud_fallback()["provider"] == "openai"


def test_fallback_is_not_hardcoded_openai_without_openai_key(monkeypatch):
    # If only Gemini is configured, the browser must select gemini -- not the
    # previously hardcoded "openai" (which would fail at runtime).
    _scrub(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-not-a-real-key")
    assert br._select_browser_cloud_fallback()["provider"] == "gemini"
