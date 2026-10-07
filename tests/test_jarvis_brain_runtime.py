"""JARVIS BRAIN v1 runtime (Layer 2, :8011) tests.

Covers the OpenAI-compatible API contract and the stub-honesty guarantees with
no real model weights required:

* The explicitly-labeled ``stub`` backend (JARVIS_BRAIN_BACKEND=stub) still
  enforces bearer-token auth and still serves ``/v1/models`` / ``/v1/chat``
  / ``/v1/generate`` — but its ``/health`` is HTTP 503 with ``stub=true`` /
  ``available=false`` / ``production_health=false`` so the platform gateway
  never mistakes it for production Qwen3 inference (spec section 13).
* Importing ``brain_runtime`` and constructing the stub app pulls in NO heavy
  ML stack (torch / transformers are lazy-imported only by the real backend).
* When the real ``TransformersBackend`` cannot acquire weights it must raise
  (never silently fall back to a stub or echo) — verified in an integration-
  marked test that forces ``local_files_only`` so no 8 GB shard is downloaded.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_runtime.backends.base import BrainBackend
from brain_runtime.config import BrainConfig
from brain_runtime.generation import BrainGenerationConfig, BrainResult
from brain_runtime.health import BrainHealthState
from brain_runtime.model_registry import BrainCatalog
from brain_runtime.server import create_app, port_in_use

pytestmark = pytest.mark.brain

_REPO = Path("F:/AI/silverwing-models") if Path("F:/AI/silverwing-models").exists() else Path.cwd()


# --------------------------------------------------------------------------- #
# Import-time guarantees (no heavy ML stack leaked into the test process)
# --------------------------------------------------------------------------- #
def test_imports_without_torch_or_transformers():
    """Importing the Brain runtime must not eagerly pull torch/transformers.

    Checked in a *fresh subprocess* so collection of the Silverwing real-tests
    (which import torch) cannot pollute ``sys.modules`` for this assertion.
    """
    import os
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import brain_runtime, brain_runtime.server, brain_runtime.service\n"
        "import brain_runtime.model_registry, brain_runtime.config, "
        "brain_runtime.generation, brain_runtime.health, brain_runtime.backends.base\n"
        "assert 'torch' not in sys.modules, 'torch leaked at import'\n"
        "assert 'transformers' not in sys.modules, 'transformers leaked at import'\n"
        "print('brain-runtime import OK; no torch/transformers')\n"
    )
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "brain-runtime import OK" in proc.stdout


# --------------------------------------------------------------------------- #
# Catalog / lineage
# --------------------------------------------------------------------------- #
def test_brain_catalog_seeds_lineage():
    cat = BrainCatalog(_REPO)
    ids = {m.full_id for m in cat.list_models()}
    assert "jarvis-brain-qwen3-4b-v1" in ids
    assert "jarvis-brain-qwen3-4b-sft-v1" in ids


def test_brain_catalog_lookup_distinguishes_base_and_sft():
    cat = BrainCatalog(_REPO)
    base = cat.lookup("jarvis-brain-qwen3-4b-v1")
    sft = cat.lookup("jarvis-brain-qwen3-4b-sft-v1")
    assert base is not None and sft is not None
    # Distinct lineage: base never overwritten by the SFT candidate (spec §9/§20).
    assert base.repository == "Qwen/Qwen3-4B"
    assert sft.repository == "videlisndichi/jarvis-brain-qwen3-4b-sft-v1"
    assert base.training_method == "base"
    assert sft.training_method == "sft"
    assert base.full_id != sft.full_id


@pytest.mark.parametrize("ref,expected", [
    ("jarvis-brain-qwen3-4b-v1", "jarvis-brain-qwen3-4b-v1"),
    ("jarvis-brain-qwen3-4b", "jarvis-brain-qwen3-4b-v1"),
    ("jarvis-brain-qwen3-4b-sft-v1", "jarvis-brain-qwen3-4b-sft-v1"),
])
def test_brain_catalog_lookup_aliases(ref, expected):
    cat = BrainCatalog(_REPO)
    entry = cat.lookup(ref)
    assert entry is not None
    assert entry.full_id == expected


# --------------------------------------------------------------------------- #
# Test app + stub config
# --------------------------------------------------------------------------- #
def _stub_config(tmp_path) -> BrainConfig:
    return BrainConfig(
        host="127.0.0.1", port=8011, api_key="test-key",
        model="jarvis-brain-qwen3-4b-v1",
        model_repo=_REPO, model_cache=Path(tmp_path) / "brain-cache",
        backend="stub", device="cpu",
        request_timeout=30.0, default_max_tokens=8192,
        warmup_prompt="hi", local_files_only=False,
    )


@pytest.fixture()
def stub_client(tmp_path):
    cfg = _stub_config(tmp_path)
    app = create_app(config=cfg)
    # ``with`` triggers the lifespan startup (backend prepare/warmup) so /health
    # reflects the stub state rather than the initial "starting" placeholder.
    with TestClient(app) as client:
        yield client


# --------------------------------------------------------------------------- #
# /health honesty
# --------------------------------------------------------------------------- #
def test_stub_health_is_not_production(stub_client):
    r = stub_client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "stub"
    assert body["stub"] is True
    assert body["available"] is False
    assert body["production_health"] is False


# --------------------------------------------------------------------------- #
# Root + /v1/models auth
# --------------------------------------------------------------------------- #
def test_stub_root(stub_client):
    r = stub_client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "jarvis-brain-runtime"
    assert "jarvis-brain-qwen3-4b-v1" in body["models"]
    assert "jarvis-brain-qwen3-4b-sft-v1" in body["models"]


def test_stub_models_requires_valid_key(stub_client):
    # missing
    assert stub_client.get("/v1/models").status_code == 401
    # wrong
    r = stub_client.get("/v1/models", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert "invalid API key" in r.json()["detail"]
    # malformed
    r = stub_client.get("/v1/models", headers={"Authorization": "Bearer"})
    assert r.status_code == 401
    assert "malformed" in r.json()["detail"]
    # valid
    r = stub_client.get("/v1/models", headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    ids = [m["id"] for m in data["data"]]
    assert "jarvis-brain-qwen3-4b-v1" in ids
    assert "jarvis-brain-qwen3-4b-sft-v1" in ids
    base = next(m for m in data["data"] if m["id"] == "jarvis-brain-qwen3-4b-v1")
    assert base["repository"] == "Qwen/Qwen3-4B"
    # Parameter count comes from the on-disk Base manifest (overlay on lineage).
    assert base["parameters"] == 4004667392


def test_stub_model_lookup_by_id(stub_client):
    h = {"Authorization": "Bearer test-key"}
    r = stub_client.get("/v1/models/jarvis-brain-qwen3-4b-sft-v1", headers=h)
    assert r.status_code == 200
    assert r.json()["id"] == "jarvis-brain-qwen3-4b-sft-v1"
    r = stub_client.get("/v1/models/does-not-exist", headers=h)
    assert r.status_code == 404
    assert stub_client.get("/v1/models/jarvis-brain-qwen3-4b-v1").status_code == 401


# --------------------------------------------------------------------------- #
# /v1/chat/completions
# --------------------------------------------------------------------------- #
def test_stub_chat_requires_valid_key(stub_client):
    body = {"model": "jarvis-brain-qwen3-4b-v1",
            "messages": [{"role": "user", "content": "ping"}]}
    assert stub_client.post("/v1/chat/completions", json=body).status_code == 401
    assert stub_client.post("/v1/chat/completions", json=body,
                            headers={"Authorization": "Bearer bad"}).status_code == 401
    r = stub_client.post("/v1/chat/completions", json=body,
                         headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200
    out = r.json()
    assert out["object"] == "chat.completion"
    assert out["model"] == "jarvis-brain-qwen3-4b-v1"
    assert out["backend"] == "brain-stub"
    content = out["choices"][0]["message"]["content"]
    assert content.startswith("[brain-stub]")
    assert "ping" in content
    assert out["usage"]["total_tokens"] >= 0


def test_stub_chat_streaming(stub_client):
    h = {"Authorization": "Bearer test-key"}
    body = {"model": "jarvis-brain-qwen3-4b-v1",
            "messages": [{"role": "user", "content": "stream me"}],
            "stream": True}
    r = stub_client.post("/v1/chat/completions", json=body, headers=h)
    assert r.status_code == 200
    events = r.text.split("\n\n")
    assert any("[brain-stub]" in e for e in events)
    assert any("[DONE]" in e for e in events)


# --------------------------------------------------------------------------- #
# /v1/generate
# --------------------------------------------------------------------------- #
def test_stub_generate(stub_client):
    h = {"Authorization": "Bearer test-key"}
    r = stub_client.post("/v1/generate", json={"prompt": "hello", "model": "jarvis-brain-qwen3-4b-v1",
                                               "max_new_tokens": 8}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "text_completion"
    assert body["choices"][0]["text"].startswith("[brain-stub]")
    assert stub_client.post("/v1/generate", json={"prompt": "x"}).status_code == 401


# --------------------------------------------------------------------------- #
# /v1/telemetry (never contains prompt content)
# --------------------------------------------------------------------------- #
def test_stub_telemetry_requires_auth_and_no_content(stub_client):
    assert stub_client.get("/v1/telemetry").status_code == 401
    r = stub_client.post("/v1/chat/completions",
                         headers={"Authorization": "Bearer test-key"},
                         json={"messages": [{"role": "user", "content": "secret-prompt-text"}],
                               "model": "jarvis-brain-qwen3-4b-v1"})
    assert r.status_code == 200
    t = stub_client.get("/v1/telemetry", headers={"Authorization": "Bearer test-key"}).json()
    assert t["count"] >= 1
    blob = str(t["events"])
    assert "secret-prompt-text" not in blob


# --------------------------------------------------------------------------- #
# Service graceful degradation (fast, no torch) + port helper
# --------------------------------------------------------------------------- #
class FailingBackend(BrainBackend):
    """A backend whose load() always fails — exercises the OFFLINE path."""

    backend = "failing"
    device = "cpu"
    model_id = "fail"
    revision = "r0"
    parameters = 0
    loaded = False

    def load(self) -> None:
        raise RuntimeError("no weights available")

    def warmup(self, prompt: str) -> str:
        raise RuntimeError("no weights available")

    def generate(self, messages, configuration: BrainGenerationConfig) -> BrainResult:
        raise RuntimeError("no weights available")

    def close(self) -> None:
        self.loaded = False


def test_service_offline_on_load_failure(tmp_path):
    import brain_runtime.service as brain_service

    cfg = BrainConfig(
        api_key="k", model="jarvis-brain-qwen3-4b-v1",
        model_repo=_REPO, model_cache=Path(tmp_path) / "c",
        backend="transformers", device="cpu",
        request_timeout=5.0, default_max_tokens=16, warmup_prompt="hi",
        local_files_only=False,
    )
    svc = brain_service.BrainService(config=cfg)

    original = brain_service._import_transformers_backend
    brain_service._import_transformers_backend = lambda *a, **k: FailingBackend()
    try:
        ok = svc.prepare()
    finally:
        brain_service._import_transformers_backend = original

    assert ok is False
    h = svc.health.current()
    assert h.status == BrainHealthState.OFFLINE
    assert h.loaded is False
    assert h.available is False
    assert h.production_health is False
    assert h.backend == "failing"
    svc.shutdown()


def test_port_in_use_helper():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.listen(1)
        assert port_in_use("127.0.0.1", port) is True
    assert port_in_use("127.0.0.1", port) is False


# --------------------------------------------------------------------------- #
# Real TransformersBackend graceful degradation (integration: heavy ML import,
# but forces local_files_only so NO weights are downloaded).
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_real_transformers_offline_no_download(tmp_path):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from brain_runtime.service import BrainService

    cfg = BrainConfig(
        api_key="k", model="jarvis-brain-qwen3-4b-v1",
        model_repo=_REPO, model_cache=Path(tmp_path) / "cache",
        backend="transformers", device="auto", local_files_only=True,
        request_timeout=5.0, default_max_tokens=16, warmup_prompt="hi",
    )
    svc = BrainService(config=cfg)
    ok = svc.prepare()
    assert ok is False
    h = svc.health.current()
    assert h.status == BrainHealthState.OFFLINE
    assert h.available is False
    assert h.production_health is False
    # The real backend is reported honestly — never a stub masquerade.
    assert h.backend == "transformers"
    svc.shutdown()
