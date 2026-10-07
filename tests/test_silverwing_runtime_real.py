"""Integration tests for the real TorchBackend with actual Silverwing weights.

These tests load the real silverwing-120m-base-v1 checkpoint (514 MB) and are
marked ``integration`` so they are SKIPPED by the default ``pytest -m "not
integration"`` run.  Run explicitly with:

    pytest tests/test_silverwing_runtime_real.py -m integration -v

They validate the full production path:
    registry -> cache -> loader -> TorchBackend load -> warmup -> generate
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

WORKSPACE = Path(__file__).resolve().parent.parent

# Ensure imports resolve
if str(WORKSPACE) not in os.sys.path:
    os.sys.path.insert(0, str(WORKSPACE))

from silverwing_runtime.backends.architecture import (
    ModelConfig,
    build_silverwing,
    count_parameters,
    expected_parameter_count,
)
from silverwing_runtime.backends.torch_backend import TorchBackend, TorchBackendError
from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.generation import GenerationConfig, GenerationRequest
from silverwing_runtime.inference import InferenceService
from silverwing_runtime.model_cache import ModelCache
from silverwing_runtime.model_loader import ModelLoader
from silverwing_runtime.model_registry import SilverwingRegistry

MODEL_REF = "silverwing-120m-base-v1"
EXPECTED_PARAMS = 120_087_552
EXPECTED_TOK_SHA = "5b09bfb6cf456dbbdc52879c133bf706bafeee34bc9f9766786fd2bda8027844"


def _make_svc():
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.refresh()
    loader = ModelLoader(reg, config=cfg)
    return InferenceService(loader, cfg)


def _model_available() -> bool:
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    entry = reg.lookup(MODEL_REF)
    if entry is None:
        return False
    return bool(entry.storage_uri)


skip_if_no_model = pytest.mark.skipif(
    not _model_available(),
    reason="silverwing-120m-base-v1 not registered / weights not accessible",
)


# --------------------------------------------------------------------------- #
# Architecture + model construction (no weights needed)
# --------------------------------------------------------------------------- #
def test_architecture_param_count():
    """Section 5: constructed parameter count == 120,087,552."""
    cfg = ModelConfig()
    model = build_silverwing(cfg)
    actual = count_parameters(model)
    assert actual == EXPECTED_PARAMS, (
        f"parameter count {actual} != expected {EXPECTED_PARAMS}"
    )
    expected = expected_parameter_count(cfg)
    assert expected == EXPECTED_PARAMS


def test_architecture_config_matches_manifest():
    """Config loaded from the registered manifest matches 120M spec."""
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    entry = reg.lookup(MODEL_REF)
    assert entry is not None
    assert entry.parameter_count == EXPECTED_PARAMS
    assert entry.vocab_size == 8192
    assert entry.context_length == 2048
    assert entry.architecture == "Silverwing Decoder"


# --------------------------------------------------------------------------- #
# TorchBackend: construction, load, verify
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_torch_backend_loads_and_verifies():
    """Sections 5, 6, 7: load, verify SHA, count params, strict checkpoint."""
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.refresh()
    loader = ModelLoader(reg, config=cfg)
    entry = reg.lookup(MODEL_REF)
    assert entry is not None

    loaded = loader.load(MODEL_REF)
    assert loaded.sha256_verified is True

    backend = TorchBackend(loaded, cfg)

    # Device + backend reporting
    assert backend.backend == "torch"
    assert backend.device in ("cuda", "cpu", "cuda:0")
    assert backend._torch_model is not None

    # Parameter count verified
    actual = count_parameters(backend._torch_model)
    assert actual == EXPECTED_PARAMS
    assert backend._verify_report["parameter_verified"] is True

    # SHA-256 verification
    assert backend._verify_report["missing_keys"] == []
    assert backend._verify_report["unexpected_keys"] == []
    assert backend._verify_report["weights_sha256"] == "verified"

    # Tokenizer SHA-256 matches manifest
    assert backend._tokenizer is not None
    assert backend._tokenizer.sha256 == EXPECTED_TOK_SHA
    assert backend._tokenizer.vocab_size == 8192

    # Metadata
    meta = backend.metadata()
    assert meta["model_id"] == entry.model_id
    assert meta["revision"] == entry.revision
    assert meta["parameter_count"] == EXPECTED_PARAMS
    assert meta["backend"] == "torch"
    assert meta["loaded"] is True
    assert meta["context_length"] == 2048
    assert meta["vocab_size"] == 8192

    backend.unload()


@skip_if_no_model
def test_torch_backend_dtype_reporting():
    """Section 8: BF16 on CUDA, FP16 on CUDA-no-BF16, FP32 on CPU."""
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.refresh()
    loader = ModelLoader(reg, config=cfg)
    loaded = loader.load(MODEL_REF)
    backend = TorchBackend(loaded, cfg)

    if "cuda" in backend.device:
        assert backend.dtype_str in ("bf16", "fp16")
    else:
        assert backend.dtype_str == "fp32"

    backend.unload()


# --------------------------------------------------------------------------- #
# Warmup (section 10)
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_warmup_passes():
    """Section 10: warmup runs one generation, verifies no NaN/Inf."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)
    health = svc.health.current()
    assert health.status.value == "healthy"
    assert health.warmup_ok is True
    assert health.parameters == EXPECTED_PARAMS
    assert health.backend == "torch"
    svc.shutdown()


# --------------------------------------------------------------------------- #
# Generation (section 11)
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_generate_basic():
    """Section 11: generate() returns real model output."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    res = asyncio.run(svc.generate(
        GenerationRequest(
            prompt="The capital of France is",
            config=GenerationConfig(max_new_tokens=16, temperature=0.7, top_p=0.9),
        ),
        model_ref=MODEL_REF,
    ))
    assert res.model == MODEL_REF
    assert res.revision == "r1"
    assert res.tokens_generated > 0
    assert res.latency_ms > 0
    assert "sw-echo" not in res.text
    svc.shutdown()


@skip_if_no_model
def test_generate_greedy():
    """Greedy (temperature=0) generation."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    res = asyncio.run(svc.generate(
        GenerationRequest(
            prompt="The capital of France is",
            config=GenerationConfig(max_new_tokens=8, temperature=0.0),
        ),
        model_ref=MODEL_REF,
    ))
    assert res.tokens_generated == 8
    assert "sw-echo" not in res.text
    svc.shutdown()


@skip_if_no_model
def test_generate_context_limit():
    """Generation cannot exceed model context (section 11)."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    long_prompt = "word " * 3000
    with pytest.raises((TorchBackendError, Exception)):
        asyncio.run(svc.generate(
            GenerationRequest(
                prompt=long_prompt,
                config=GenerationConfig(max_new_tokens=4),
            ),
            model_ref=MODEL_REF,
        ))
    svc.shutdown()


@skip_if_no_model
def test_generate_repetition_penalty():
    """Repetition penalty is honored."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    res = asyncio.run(svc.generate(
        GenerationRequest(
            prompt="hello hello hello",
            config=GenerationConfig(
                max_new_tokens=8, temperature=0.7, repetition_penalty=1.5,
            ),
        ),
        model_ref=MODEL_REF,
    ))
    assert "sw-echo" not in res.text
    svc.shutdown()


# --------------------------------------------------------------------------- #
# Chat (section 12)
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_chat_basic():
    """Section 12: chat() uses deterministic message formatting."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    res = asyncio.run(svc.chat(
        [{"role": "user", "content": "Hello, how are you?"}],
        generation_config=GenerationConfig(max_new_tokens=16, temperature=0.7),
        model_ref=MODEL_REF,
    ))
    assert res.model == MODEL_REF
    assert res.revision == "r1"
    assert res.usage["input_tokens"] > 0
    assert res.usage["output_tokens"] > 0
    assert res.usage["total_tokens"] == res.usage["input_tokens"] + res.usage["output_tokens"]
    assert "sw-echo" not in res.message.content
    assert "Silverwing-120M-Base" == res.metadata.get("model_label")
    svc.shutdown()


# --------------------------------------------------------------------------- #
# Health states (section 17)
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_health_states():
    """Section 17: health transitions and final state are accurate."""
    svc = _make_svc()

    h0 = svc.health.current()
    assert h0.status.value == "starting"

    svc.warmup(MODEL_REF)
    h1 = svc.health.current()
    assert h1.status.value == "healthy"
    assert h1.model == MODEL_REF
    assert h1.revision == "r1"
    assert h1.backend == "torch"
    assert h1.loaded is True
    assert h1.warmup_ok is True
    assert h1.parameters == EXPECTED_PARAMS

    svc.shutdown()


# --------------------------------------------------------------------------- #
# Token usage (section 15)
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_token_usage_accurate():
    """Token usage counts must come from actual tokenizer activity."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    prompt = "Explain photosynthesis in one sentence."
    res = asyncio.run(svc.generate(
        GenerationRequest(prompt=prompt, config=GenerationConfig(max_new_tokens=20)),
        model_ref=MODEL_REF,
    ))
    assert res.tokens_input > 0
    tok = svc._backends[MODEL_REF]._tokenizer
    manual = len(tok.encode(prompt)) + 1  # +1 for BOS
    assert res.tokens_input == manual
    svc.shutdown()


# --------------------------------------------------------------------------- #
# Model hash verification (section 7)
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_weights_hash_verified():
    """Weights SHA-256 is verified before serving."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    backend = svc._backends[MODEL_REF]
    assert backend.model.sha256_verified is True
    assert backend.model.sha256_verified_str == "verified"
    assert backend._verify_report["weights_sha256"] == "verified"
    svc.shutdown()


# --------------------------------------------------------------------------- #
# The production inference test (section 21)
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_real_inference_centrifugal_pump():
    """Section 21: 'Explain what a centrifugal pump is and give three maintenance precautions.'"""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    prompt = "Explain what a centrifugal pump is and give three maintenance precautions."
    t0 = time.monotonic()
    res = asyncio.run(svc.generate(
        GenerationRequest(
            prompt=prompt,
            config=GenerationConfig(
                max_new_tokens=64, temperature=0.7, top_p=0.9,
            ),
        ),
        model_ref=MODEL_REF,
    ))
    wall = time.monotonic() - t0

    print("\n=== REAL INFERENCE TEST ===")
    print(f"  model:      {res.model}")
    print("  backend:    torch")
    print(f"  device:     {svc._backends[MODEL_REF].device}")
    print(f"  revision:   {res.revision}")
    print(f"  latency:    {res.latency_ms}ms (wall {wall:.1f}s)")
    print(f"  in_tokens:  {res.tokens_input}")
    print(f"  out_tokens: {res.tokens_generated}")
    print(f"  response:   {res.text!r}")

    assert res.model == MODEL_REF
    assert "sw-echo" not in res.text
    assert res.tokens_generated > 0
    assert res.latency_ms > 0

    svc.shutdown()


# --------------------------------------------------------------------------- #
# Cache + loader integration
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_cache_acquires_and_verifies_weights():
    """Cache downloads/copies and verifies SHA-256 before exposing path."""
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    entry = reg.lookup(MODEL_REF)
    assert entry is not None

    from silverwing_runtime.model_manifest import ModelManifest
    manifest = ModelManifest.load(Path(entry.manifest_path))
    cache = ModelCache(cfg.model_cache_dir)
    path = cache.acquire(manifest)
    assert path.exists()
    assert path.name == "model.safetensors"
    assert cache.hit(manifest) is not None


# --------------------------------------------------------------------------- #
# No EchoBackend fallback
# --------------------------------------------------------------------------- #
@skip_if_no_model
def test_no_echo_fallback_on_success():
    """Section 16: successful generation does NOT use EchoBackend."""
    svc = _make_svc()
    svc.warmup(MODEL_REF)

    assert svc.config.backend == "torch"
    backend = svc._backends[MODEL_REF]
    assert backend.backend == "torch"

    res = asyncio.run(svc.generate(
        GenerationRequest(prompt="Hello", config=GenerationConfig(max_new_tokens=4)),
        model_ref=MODEL_REF,
    ))
    assert "sw-echo" not in res.text
    assert res.metadata.get("backend") == "torch"
    svc.shutdown()
