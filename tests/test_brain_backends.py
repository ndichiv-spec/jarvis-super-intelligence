"""Tests for Brain backend selection + config recognition (spec Part C/D/E).

These exercise *configuration* and *dispatch* only — they never load a model
or touch the network, so no provider credentials are required and torch is
not imported (the local/transformers path is intentionally not exercised here
to preserve the torch-free import contract).
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from brain_runtime.backends.nvidia_backend import NvidiaBrainBackend
from brain_runtime.backends.huggingface_backend import HuggingFaceBrainBackend
from brain_runtime.backends.remote import RemoteBrainBackend
from brain_runtime.config import BrainConfig
from brain_runtime.service import BrainService, _import_huggingface_backend, _import_nvidia_backend

pytestmark = pytest.mark.brain


class TestBackendTypeRecognition:
    def test_nvidia_backend_type(self):
        cfg = BrainConfig(backend="nvidia")
        assert cfg.backend_type == "nvidia"
        assert cfg.is_nvidia is True
        # nvidia back-ends are also classified as remote (they delegate to an
        # OpenAI-compatible remote endpoint).
        assert cfg.is_remote is True

    def test_huggingface_backend_type(self):
        cfg = BrainConfig(backend="huggingface")
        assert cfg.backend_type == "huggingface"
        assert cfg.is_huggingface is True
        assert cfg.is_remote is True

    def test_legacy_hf_alias_still_remote(self):
        cfg = BrainConfig(backend="hf")
        assert cfg.backend_type == "remote"
        assert cfg.is_remote is True

    def test_stub_is_not_remote(self):
        cfg = BrainConfig(backend="stub")
        assert cfg.is_stub is True
        assert cfg.is_remote is False


class TestBuildBackendDispatch:
    def test_build_backend_nvidia(self):
        cfg = BrainConfig(backend="nvidia", model="nvidia/nemotron-3-ultra-550b-a55b")
        svc = BrainService(config=cfg)
        backend = svc.build_backend()
        assert isinstance(backend, NvidiaBrainBackend)
        assert backend.provider == "nvidia"
        assert backend.backend == "nvidia"

    def test_build_backend_huggingface(self):
        cfg = BrainConfig(backend="huggingface", model="hf-internal-id")
        svc = BrainService(config=cfg)
        backend = svc.build_backend()
        assert isinstance(backend, HuggingFaceBrainBackend)
        assert backend.provider == "hf-inference"
        assert backend.backend == "huggingface"

    def test_build_backend_remote(self):
        cfg = BrainConfig(
            backend="remote",
            remote_endpoint="https://api.example.com/v1",
            remote_api_key="k",
            remote_model="m",
        )
        svc = BrainService(config=cfg)
        backend = svc.build_backend()
        assert isinstance(backend, RemoteBrainBackend)

    def test_build_backend_stub(self):
        cfg = BrainConfig(backend="stub", model="jarvis-brain-qwen3-4b-v1")
        svc = BrainService(config=cfg)
        backend = svc.build_backend()
        assert backend.backend == "brain-stub"
        assert backend.stream_support is False


class TestNvidiaBackendDefaults:
    def test_nvidia_backend_reads_config_fields(self):
        backend = _import_nvidia_backend(
            BrainConfig(
                backend="nvidia",
                remote_endpoint="https://integrate.api.nvidia.com/v1",
                remote_api_key="remote-key",
                remote_model="nvidia/nemotron-3-ultra-550b-a55b",
            )
        )
        assert backend._endpoint == "https://integrate.api.nvidia.com/v1"
        assert backend.model_id == "nvidia/nemotron-3-ultra-550b-a55b"
        assert backend.provider == "nvidia"
        assert backend.stream_support is True


class TestHuggingFaceBackendDefaults:
    def test_hf_backend_reads_config_fields(self):
        env = {
            "HUGGINGFACE_API_KEY": "hf-token",
            "JARVIS_HF_INFERENCE_ENDPOINT": "https://hf.example.com/v1",
            "JARVIS_HF_MODEL": "user/hf-model",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = BrainConfig(backend="huggingface")
            backend = _import_huggingface_backend(cfg)
            assert backend._endpoint == "https://hf.example.com/v1"
            assert backend.model_id == "user/hf-model"
            assert backend.provider == "hf-inference"
