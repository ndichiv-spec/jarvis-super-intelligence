"""Tests for the canonical env loader and secret redaction (spec Part Q).

Covers:
  - alias resolution (canonical name wins; legacy aliases consulted in order)
  - blank-value handling (blank does not shadow a set alias)
  - redact() output shapes (never the raw secret)
  - get_bool / get_int / get_float helpers
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from brain_runtime.env import (
    aliases_for,
    get_bool,
    get_env,
    get_float,
    get_int,
    redact,
)

pytestmark = pytest.mark.brain


def test_aliases_for_known_and_unknown():
    assert aliases_for("NVIDIA_API_KEY") == (
        "NVIDIA_API_KEY",
        "JARVIS_NVIDIA_API_KEY",
    )
    assert aliases_for("HUGGINGFACE_API_KEY") == (
        "HUGGINGFACE_API_KEY",
        "HF_TOKEN",
        "JARVIS_HF_TOKEN",
    )
    # Unknown canonical name -> single-element alias stack (= itself).
    assert aliases_for("SOME_UNKNOWN_VAR") == ("SOME_UNKNOWN_VAR",)


def test_canonical_wins_over_alias():
    env = {"NVIDIA_API_KEY": "canon", "JARVIS_NVIDIA_API_KEY": "alias"}
    with patch.dict(os.environ, env, clear=False):
        assert get_env("NVIDIA_API_KEY") == "canon"


def test_alias_used_when_canonical_absent():
    env = {"JARVIS_NVIDIA_API_KEY": "alias-only"}
    # clear=True so ambient NVIDIA_API_KEY (leaked by jarvis_backend.main's
    # load_dotenv during collection) cannot shadow the alias under test.
    with patch.dict(os.environ, env, clear=True):
        # canonical absent, alias present
        assert get_env("NVIDIA_API_KEY") == "alias-only"


def test_alias_hf_token_resolved():
    env = {"HF_TOKEN": "hf-alias-value"}
    with patch.dict(os.environ, env, clear=False):
        assert get_env("HUGGINGFACE_API_KEY") == "hf-alias-value"


def test_blank_canonical_does_not_shadow_alias():
    env = {"NVIDIA_API_KEY": "   ", "JARVIS_NVIDIA_API_KEY": "real"}
    with patch.dict(os.environ, env, clear=False):
        assert get_env("NVIDIA_API_KEY") == "real"


def test_missing_returns_default():
    with patch.dict(os.environ, {}, clear=True):
        assert get_env("DOES_NOT_EXIST_XYZ", "fallback") == "fallback"


def test_get_bool_truthy():
    env = {"MY_BOOL": "yes"}
    with patch.dict(os.environ, env, clear=False):
        assert get_bool("MY_BOOL") is True


def test_get_bool_unset_returns_default():
    with patch.dict(os.environ, {}, clear=True):
        assert get_bool("MY_BOOL", default=False) is False
        assert get_bool("MY_BOOL", default=True) is True


def test_get_int_and_get_float():
    env = {"MY_INT": "7", "MY_FLOAT": "3.5"}
    with patch.dict(os.environ, env, clear=False):
        assert get_int("MY_INT", 0) == 7
        assert get_float("MY_FLOAT", 0.0) == 3.5


def test_get_int_invalid_falls_back():
    with patch.dict(os.environ, {"MY_INT": "not-a-number"}, clear=False):
        assert get_int("MY_INT", 9) == 9


def test_redact_long_value():
    assert redact("abcdef1234") == "abc...34"


def test_redact_short_value():
    # Values of length <= 6 are fully masked.
    assert redact("abcdef") == "****"
    assert redact("xy") == "****"


def test_redact_empty_is_none():
    assert redact("") == "<none>"
    assert redact(None) == "<none>"


def test_redact_never_returns_full_secret():
    secret = "SUPERSECRETVALUE123"
    masked = redact(secret)
    assert secret not in masked
    assert masked.startswith("SUP")
    assert masked.endswith("23")
