"""Canonical integration env (_env.py) — loading + production guard.

Verifies JARVIS BRAIN variables and the existing Silverwing defaults are
applied idempotently, secrets are never hardcoded, and production refuses to
start without required admin/Brain config.  Never asserts/secrets values.
"""
from __future__ import annotations

import os
import sys

REPO_ROOT = r"F:\AI"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _clean_env():
    for k in (
        "JARVIS_ENV", "JARVIS_ADMIN_EMAIL",
        "JARVIS_BRAIN_ENDPOINT", "JARVIS_BRAIN_MODEL", "JARVIS_BRAIN_API_KEY",
        "SILVERWING_ENDPOINT", "SILVERWING_MODEL", "JARVIS_MODEL",
    ):
        os.environ.pop(k, None)
    import importlib
    for m in list(sys.modules):
        if m == "_env" or m.startswith("_env."):
            del sys.modules[m]
    import _env as e
    return e


def test_apply_sets_brain_and_silverwing_defaults():
    import _env as e
    _clean_env()
    e.apply()
    assert os.environ["JARVIS_BRAIN_MODEL"] == "jarvis-brain-qwen3-4b-sft-v1"
    assert os.environ["SILVERWING_MODEL"] == "silverwing-120m-base-v1"
    assert os.environ["JARVIS_MODEL"] == "silverwing-120m-base-v1"
    assert os.environ["SILVERWING_ENDPOINT"] == "http://127.0.0.1:8010"
    # Dev default: dedicated local Brain runtime on :8011 (spec §34); the
    # bearer key is NEVER defaulted — it must come from .env / the OS.
    assert os.environ["JARVIS_BRAIN_ENDPOINT"] == "http://127.0.0.1:8011/v1"
    assert os.environ["JARVIS_BRAIN_API_KEY"] == ""


def test_apply_never_overrides_existing_values():
    import _env as e
    _clean_env()
    os.environ["JARVIS_BRAIN_MODEL"] = "my-custom-brain"
    os.environ["SILVERWING_ENDPOINT"] = "http://custom:9999"
    e.apply()
    assert os.environ["JARVIS_BRAIN_MODEL"] == "my-custom-brain"
    assert os.environ["SILVERWING_ENDPOINT"] == "http://custom:9999"


def test_production_requires_admin_email():
    import _env as e
    _clean_env()
    os.environ["JARVIS_ENV"] = "production"
    try:
        e.require_production()
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "JARVIS_ADMIN_EMAIL" in str(exc)
    assert raised


def test_production_requires_brain_api_key_when_endpoint_set():
    import _env as e
    _clean_env()
    os.environ["JARVIS_ENV"] = "production"
    os.environ["JARVIS_ADMIN_EMAIL"] = "ops@example.com"
    os.environ["JARVIS_BRAIN_ENDPOINT"] = "https://brain.example/v1"
    try:
        e.require_production()
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "JARVIS_BRAIN_API_KEY" in str(exc)
    assert raised
    # With the key present the same config is accepted.
    os.environ["JARVIS_BRAIN_API_KEY"] = "sk-not-a-real-key"
    e.require_production()  # must not raise


def test_secrets_not_in_source():
    import _env as e
    src = open(e.__file__, encoding="utf-8").read().lower()
    for secretish in ("hf_", "sk-", "secret", "token_hex"):
        assert secretish not in src.split("secret")[0].split("= '")[-1], secretish