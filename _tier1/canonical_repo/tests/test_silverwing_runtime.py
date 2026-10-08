"""Silverwing runtime (Layer 2) tests.

All fixtures are fabricated in a temporary directory: tiny ``model.safetensors``
files with REAL hashes computed at runtime.  No real 514 MB weights are ever
downloaded and the real ``F:\\AI\\silverwing-models`` repo is never touched.

Tests
-----
* manifest schema + validation (status/lifecycle, capabilities whitelist)
* registry load/lookup/status/lifecycle from a temp model repository
* cache acquire/hit/evict + SHA-256 verification + tamper detection
* loader -> verified LoadedModel
* InferenceService warmup -> HEALTHY (device, parameters) + echo generation
* server API: /v1/models, /v1/health, /v1/chat/completions, /v1/generate,
  archived model rejection, unknown model 404, bearer auth
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.model_cache import ModelCache
from silverwing_runtime.model_manifest import ModelManifest
from silverwing_runtime.model_registry import SilverwingRegistry

pytestmark = pytest.mark.silverwing


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture()
def model_source(tmp_path) -> tuple[object, str]:
    """Create a local model source (dir with weights/config/tokenizer)."""
    src = tmp_path / "model-source-example"
    src.mkdir(parents=True, exist_ok=True)
    weights = b"FABRICATED-WEIGHTS-%d" % 0  # replaced by caller if needed
    (src / "model.safetensors").write_bytes(weights)
    (src / "config.json").write_text(json.dumps({"dummy": True}))
    (src / "tokenizer.json").write_text("{}")
    (src / "metadata.json").write_text(json.dumps({"step": 1}))
    weights_sha = _sha256(weights)
    return src, weights_sha


@pytest.fixture()
def runtime_env(tmp_path, model_source):
    """A temp SILVERWING_MODEL_REPO + model manifest registered to it."""
    src, weights_sha = model_source
    repo = tmp_path / "repo"
    cache = tmp_path / "cache"
    manifest_dir = repo / "example-model" / "v1"
    manifest_dir.mkdir(parents=True)

    manifest = ModelManifest(
        model_id="example-model",
        version="v1",
        revision="r1",
        architecture="TestDecoder",
        parameter_count=42_000,
        context_length=512,
        vocab_size=1000,
        capabilities=["text-generation"],
        status="experimental",
        tokenizer={"version": "test-bpe", "sha256": "0" * 64},
        weights={
            "sha256": weights_sha,
            "config_sha256": "1" * 64,
            "storage_uri": f"local:///{src.as_posix()}",
            "size_bytes": (src / "model.safetensors").stat().st_size,
        },
    )
    manifest.save(manifest_dir / "model_manifest.json")

    import os

    os.environ["SILVERWING_MODEL_REPO"] = str(repo)
    os.environ["SILVERWING_MODEL_CACHE"] = str(cache)
    os.environ["SILVERWING_REGISTRY_PATH"] = str(tmp_path / "registry.json")
    os.environ["SILVERWING_WARMUP_PROMPT"] = "hello"
    # Lightweight tests must NOT load real weights: force the explicit
    # dev/test backend (torch is the production default).
    os.environ["SILVERWING_BACKEND"] = "echo"
    return {
        "repo": repo,
        "cache": cache,
        "src": src,
        "manifest": manifest,
        "weights_sha": weights_sha,
    }


def _registry(runtime_env) -> SilverwingRegistry:
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.load()
    return reg


# --------------------------------------------------------------------------- #
# Manifest schema + validation
# --------------------------------------------------------------------------- #
def test_manifest_defaults_and_identity(runtime_env):
    m = runtime_env["manifest"]
    assert m.full_id == "example-model-v1"
    assert m.status == "experimental"
    assert m.capabilities == ["text-generation"]


def test_manifest_validate_reports_problems():
    m = ModelManifest(model_id="bad", status="nonsense")
    problems = m.validate_manifest()
    assert "status 'nonsense' not in" in "\n".join(problems)
    assert any("tokenizer.sha256" in p for p in problems)
    assert any("weights.sha256" in p for p in problems)
    assert any("storage_uri" in p for p in problems)


def test_manifest_rejects_unknown_capabilities(tmp_path):
    m = ModelManifest(
        model_id="x",
        parameter_count=1,
        capabilities=["telepathy"],
        status="experimental",
        tokenizer={"sha256": "a" * 64},
        weights={"sha256": "b" * 64, "storage_uri": "local:///tmp"},
    )
    assert any("unknown capabilities" in p for p in m.validate_manifest())


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registry_registers_from_temp_repo(runtime_env):
    reg = _registry(runtime_env)
    ids = [e.full_id for e in reg.list_models()]
    assert "example-model-v1" in ids

    entry = reg.lookup("example-model-v1")
    assert entry.status == "experimental"
    assert entry.parameter_count == 42_000
    assert entry.context_length == 512
    assert entry.capabilities == ["text-generation"]
    assert entry.storage_uri == f"local:///{runtime_env['src'].as_posix()}"
    assert entry.model_sha256 == runtime_env["weights_sha"]


def test_registry_unknown_lookup(runtime_env):
    reg = _registry(runtime_env)
    assert reg.lookup("nothing-here") is None


def test_registry_lifecycle_mark_deployed(runtime_env):
    reg = _registry(runtime_env)
    reg.mark_deployed("example-model-v1", endpoint="test", device="cpu", loaded=True, healthy=True)
    entry = reg.lookup("example-model-v1")
    assert entry.deployment is not None
    assert entry.deployment.endpoint == "test"
    assert entry.deployment.device == "cpu"
    assert entry.deployment.loaded is True
    assert entry.deployment.healthy is True


# --------------------------------------------------------------------------- #
# Cache: acquire / hit / tamper / evict
# --------------------------------------------------------------------------- #
def test_cache_acquire_verifies_and_hits(runtime_env):
    cfg = RuntimeConfig()
    cache = ModelCache(cfg.model_cache_dir)
    manifest = runtime_env["manifest"]

    assert cache.hit(manifest) is None  # cold
    path = cache.acquire(manifest)
    assert path.exists()
    assert path.name == "model.safetensors"
    assert cache.hit(manifest) == path  # now warm
    assert cache.list_cached().get("example-model") == "r1"
    assert cache.evict() >= 1
    assert cache.hit(manifest) is None


def test_cache_detects_tampered_weights(runtime_env):
    cfg = RuntimeConfig()
    cache = ModelCache(cfg.model_cache_dir)
    manifest = runtime_env["manifest"]
    path = cache.acquire(manifest)

    path.write_bytes(b"TAMPERED")
    assert cache.hit(manifest) is None  # hash mismatch -> not usable

    # acquire re-copies from the verified source and passes again.
    path2 = cache.acquire(manifest)
    assert path2.read_bytes().startswith(b"FABRICATED")


# --------------------------------------------------------------------------- #
# Loader + inference
# --------------------------------------------------------------------------- #
def test_loader_materializes_verified_model(runtime_env):
    reg = _registry(runtime_env)
    from silverwing_runtime.model_loader import ModelLoader

    loader = ModelLoader(reg, config=RuntimeConfig())
    loaded = loader.load("example-model-v1")
    assert loaded.full_id == "example-model-v1"
    assert loaded.sha256_verified is True
    assert loaded.weights_path.exists()
    # cache marker + weights on the inference machine only (never in repo)
    assert list(runtime_env["repo"].rglob("model.safetensors")) == []


async def test_inference_warmup_and_generate(runtime_env):
    reg = _registry(runtime_env)
    from silverwing_runtime.generation import GenerationConfig, GenerationRequest
    from silverwing_runtime.inference import InferenceService
    from silverwing_runtime.model_loader import ModelLoader

    cfg = RuntimeConfig()
    svc = InferenceService(ModelLoader(reg, config=cfg), cfg)
    svc.warmup("example-model-v1")

    status = svc.health.current()
    assert status.status.value == "healthy"
    assert status.model == "example-model-v1"
    assert status.parameters == 42_000
    assert status.warmup_ok is True

    res = await svc.generate(
        GenerationRequest(prompt="hello", config=GenerationConfig(max_new_tokens=16))
    )
    assert res.model == "example-model-v1"
    assert "sw-echo" in res.text  # honest echo marker, never a fabricated answer
    svc.shutdown()


# --------------------------------------------------------------------------- #
# Server API
# --------------------------------------------------------------------------- #
def _make_client(runtime_env, startup=True):
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.load()
    from silverwing_runtime.server import create_app

    app = create_app(
        registry=reg,
        config=cfg,
        startup_models=["example-model-v1"] if startup else None,
    )
    return TestClient(app)


def test_server_health_and_models(runtime_env):
    with _make_client(runtime_env) as client:
        r = client.get("/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert body["model"] == "example-model-v1"
        assert body["parameters"] == 42_000
        assert body["warmup_ok"] is True

        r = client.get("/v1/models")
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["data"]]
        assert "example-model-v1" in ids


def test_server_chat_completions_e2e(runtime_env):
    with _make_client(runtime_env) as client:
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "example-model-v1",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["object"] == "chat.completion"
        assert body["model"] == "example-model-v1"
        assert body["revision"] == "r1"
        assert "device" in body
        assert "latency_ms" in body
        assert "sw-echo" in body["choices"][0]["message"]["content"]
        assert body["usage"]["total_tokens"] >= 0


def test_server_generate_e2e(runtime_env):
    with _make_client(runtime_env) as client:
        r = client.post(
            "/v1/generate",
            json={
                "model": "example-model-v1",
                "prompt": "The capital of France is",
                "max_new_tokens": 8,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["model"] == "example-model-v1"
        assert body["revision"] == "r1"
        assert "latency_ms" in body
        assert body["choices"][0]["text"]


def test_server_unknown_model_404(runtime_env):
    with _make_client(runtime_env) as client:
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "not-registered",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert r.status_code == 404


def test_server_archived_model_rejected(runtime_env):
    cfg = RuntimeConfig()
    # re-register the same model with archived status.

    from silverwing_runtime.model_manifest import ModelManifest as Manifest

    mod = Manifest(**runtime_env["manifest"].model_dump())
    mod.status = "archived"
    mod.save(runtime_env["repo"] / "example-model" / "v1" / "model_manifest.json")

    reg = SilverwingRegistry(cfg)
    reg.load()
    from silverwing_runtime.server import create_app

    app = create_app(registry=reg, config=cfg, startup_models=["example-model-v1"])
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "example-model-v1",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert r.status_code == 400
        assert "archived" in r.text.lower()


def test_server_auth_required(runtime_env, monkeypatch):
    monkeypatch.setenv("SILVERWING_API_KEY", "secret-token")
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.load()
    from silverwing_runtime.server import create_app

    app = create_app(registry=reg, config=cfg, startup_models=["example-model-v1"])
    with TestClient(app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "example-model-v1",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert r.status_code == 401
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "example-model-v1",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"Authorization": "Bearer secret-token"},
        )
        assert r.status_code == 200


def test_server_rate_limit(runtime_env, monkeypatch):
    monkeypatch.setenv("SILVERWING_API_KEY", "")
    cfg = RuntimeConfig()
    reg = SilverwingRegistry(cfg)
    reg.load()
    from silverwing_runtime.server import create_app

    app = create_app(registry=reg, config=cfg, startup_models=["example-model-v1"])
    with TestClient(app) as client:
        for _ in range(60):
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "example-model-v1",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 2,
                },
            )
            assert r.status_code == 200
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "example-model-v1",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert r.status_code == 429
