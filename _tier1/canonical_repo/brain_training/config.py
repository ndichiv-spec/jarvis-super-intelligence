"""Configuration, paths, and server-side secret resolution for BRAIN training.

Secrets (spec S4):
  * ``JARVIS_HF_TOKEN`` (preferred) or the EXISTING ``HF_TOKEN`` convention is
    read from the OS environment / ``.env``.  It is resolved by reference only
    and is NEVER printed, logged, written to artifact metadata, or returned by
    any route.  ``hf_token()`` returns a non-empty string only when a token is
    present; callers must treat an empty string as "not configured".
  * Kaggle credentials (``KAGGLE_USERNAME`` / ``KAGGLE_KEY``) are read from the
    OS environment only.  Kaggle kernels inject these as kernel secrets; the
    dev box does not hold them.
  * ``JARVIS_BRAIN_API_KEY`` is resolved through the project vault; it is used
    only to drive the Brain runtime and never appears in training artifacts.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent  # F:\AI
BRAIN_RUNTIME_DIR = REPO_ROOT / "brain_runtime"
BRAIN_TRAINING_DIR = REPO_ROOT / "brain_training"
ARTIFACTS_DIR = BRAIN_TRAINING_DIR / "artifacts"
RUNS_DIR = ARTIFACTS_DIR / "runs"            # run registry (training_runs.jsonl)
EVENTS_DIR = ARTIFACTS_DIR / "events"        # training_events.jsonl
CKPT_DIR = ARTIFACTS_DIR / "checkpoints"     # checkpoint metadata
DATASET_DIR = ARTIFACTS_DIR / "datasets"     # validated dataset manifests
HF_SCAN_DIR = ARTIFACTS_DIR / "scan"         # secret-scan reports

# ---- Existing training assets (DO NOT DUPLICATE) ------------------------- #
SFT_KERNEL = REPO_ROOT / "videlisndichi-jarvis-brain-qwen3-4b-sft-train" / "jarvis_brain_sft.py"
SFT_KERNEL_REPO = "videlisndichi/jarvis-brain-sft-train"
SFT_DATASET_DIR = REPO_ROOT / "videlisndichi-jarvis-brain-v1-sft"
SFT_CORPUS = SFT_DATASET_DIR / "01_normalized.jsonl"
SFT_DATASET_MANIFEST = SFT_DATASET_DIR / "jarvis_brain_sft_dataset_manifest.json"
KAGGLE_KERNEL = REPO_ROOT / "kaggle_kernel" / "jarvis_brain_qwen3_4b.ipynb"
# Machine-readable kernel metadata (NOT the .ipynb).  Spec: never parse the
# notebook JSON for structured fields — kernel-metadata.json is the source of
# truth for accelerator/dataset_sources/enable_gpu.
KAGGLE_KERNEL_METADATA = REPO_ROOT / "videlisndichi-jarvis-brain-qwen3-4b-sft-train" / "kernel-metadata.json"
SFT_TRAIN_DIR = REPO_ROOT / "videlisndichi-jarvis-brain-qwen3-4b-sft-train"

# ---- HuggingFace namespace + repos (spec S2/S4) -------------------------- #
HF_NAMESPACE = "videlisndichi"
HF_REPO_DATASET = f"{HF_NAMESPACE}/jarvis-brain-training-data"
HF_REPO_MODEL_BASE = f"{HF_NAMESPACE}/jarvis-brain-qwen3-4b-v1"        # base release
HF_REPO_MODEL_SFT = f"{HF_NAMESPACE}/jarvis-brain-qwen3-4b-sft-v1"      # SFT adapter/model

# Qwen3-4B base (frozen — never merged into; spec S9)
BASE_MODEL_ID = "Qwen/Qwen3-4B-Base"
BASE_REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"

# ---- Brain runtime (already built & verified on :8011) -------------------- #
BRAIN_HOST = os.environ.get("JARVIS_BRAIN_HOST", "127.0.0.1")
BRAIN_PORT = int(os.environ.get("JARVIS_BRAIN_PORT", "8011"))
BRAIN_ENDPOINT = os.environ.get("JARVIS_BRAIN_ENDPOINT", "http://127.0.0.1:8011/v1")
SILVERWING_ENDPOINT = os.environ.get("SILVERWING_ENDPOINT", "http://127.0.0.1:8010")

# ---- Secret detection patterns (spec S27) -------------------------------- #
# Ordered: specific providers first, then generic.  Values are matched but
# NEVER printed verbatim — scanners return a masked match.
SECRET_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("huggingface_token", re.compile(r"hf_[A-Za-z0-9_-]{20,}")),
    ("openai_key",        re.compile(r"sk-[?:-[A-Za-z0-9]{20,}")),
    ("poolside_user_key", re.compile(r"sk_user_[A-Za-z0-9]{20,}")),
    ("github_pat",        re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("github_token",      re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("aws_access_key",    re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_key",    re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*\S+")),
    ("google_api_key",    re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("jwt",               re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("generic_env_secret", re.compile(r"(?i)\b([A-Z0-9_]*_(?:API_KEY|TOKEN|SECRET|PASSWORD|SECRET_KEY))\s*[:=]\s*['\"]?[A-Za-z0-9/_.+=-]{8,}")),
]


def _mask(value: str) -> str:
    if not value:
        return "<none>"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:3] + "..." + value[-3:] + f" (len={len(value)})"


@dataclass
class EnvSnapshot:
    """Actual observed environment state (no secrets)."""
    hf_token_name: str = "JARVIS_HF_TOKEN"        # which var supplied the token (name only)
    hf_token_present: bool = False
    hf_token_valid: bool = False                  # verified via whoami (set by probe)
    kaggle_configured: bool = False
    brain_endpoint: str = ""
    brain_model: str = ""
    silverwing_endpoint: str = ""
    brain_api_key_present: bool = False

    def summary(self) -> dict:
        return {
            "hf_token_present": self.hf_token_present,
            "hf_token_valid": self.hf_token_valid,
            "kaggle_configured": self.kaggle_configured,
            "brain_endpoint": self.brain_endpoint,
            "brain_model": self.brain_model,
            "silverwing_endpoint": self.silverwing_endpoint,
            "brain_api_key_present": self.brain_api_key_present,
        }


def hf_token() -> str:
    """Resolve the HuggingFace token from the server-side environment.

    Reads ``JARVIS_HF_TOKEN`` first (spec S4 preferred name), then the existing
    ``HF_TOKEN`` convention.  The returned value is the raw token only for use
    by a short-lived authenticated client call; it is never persisted.
    """
    return (
        os.environ.get("JARVIS_HF_TOKEN")
        or os.environ.get("HF_TOKEN")
        or ""
    )


@dataclass
class BrainTrainingConfig:
    """Frozen-ish training lifecycle configuration (mirrors _env.py defaults)."""
    repo_root: Path = field(default_factory=lambda: REPO_ROOT)
    sft_kernel: Path = field(default_factory=lambda: SFT_KERNEL)
    sft_corpus: Path = field(default_factory=lambda: SFT_CORPUS)
    sft_dataset_manifest: Path = field(default_factory=lambda: SFT_DATASET_MANIFEST)
    kaggle_kernel: Path = field(default_factory=lambda: KAGGLE_KERNEL)
    kaggle_kernel_metadata: Path = field(default_factory=lambda: KAGGLE_KERNEL_METADATA)
    sft_train_dir: Path = field(default_factory=lambda: SFT_TRAIN_DIR)
    base_model_id: str = BASE_MODEL_ID
    base_revision: str = BASE_REVISION
    brain_endpoint: str = BRAIN_ENDPOINT
    silverwing_endpoint: str = SILVERWING_ENDPOINT
    hf_namespace: str = HF_NAMESPACE
    hf_repo_model_base: str = HF_REPO_MODEL_BASE
    hf_repo_model_sft: str = HF_REPO_MODEL_SFT
    hf_repo_dataset: str = HF_REPO_DATASET

    @property
    def is_gpu_available(self) -> bool:
        try:
            import torch  # type: ignore
            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def ensure_dirs(self) -> None:
        for d in (ARTIFACTS_DIR, RUNS_DIR, EVENTS_DIR, CKPT_DIR, DATASET_DIR, HF_SCAN_DIR):
            d.mkdir(parents=True, exist_ok=True)


def env_snapshot() -> EnvSnapshot:
    """Capture actual env state (names/flags only — never secrets)."""
    hf = bool(os.environ.get("JARVIS_HF_TOKEN") or os.environ.get("HF_TOKEN"))
    kc = bool(os.environ.get("KAGGLE_USERNAME")) and bool(os.environ.get("KAGGLE_KEY"))
    snap = EnvSnapshot(
        hf_token_present=hf,
        kaggle_configured=kc,
        brain_endpoint=(os.environ.get("JARVIS_BRAIN_ENDPOINT") or "").strip(),
        brain_model=(os.environ.get("JARVIS_BRAIN_MODEL") or "").strip(),
        silverwing_endpoint=(os.environ.get("SILVERWING_ENDPOINT") or "").strip(),
        brain_api_key_present=bool((os.environ.get("JARVIS_BRAIN_API_KEY") or "").strip()),
    )
    if os.environ.get("JARVIS_HF_TOKEN"):
        snap.hf_token_name = "JARVIS_HF_TOKEN"
    elif os.environ.get("HF_TOKEN"):
        snap.hf_token_name = "HF_TOKEN"
    return snap
