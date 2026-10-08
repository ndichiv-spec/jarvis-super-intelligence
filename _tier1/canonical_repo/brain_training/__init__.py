"""JARVIS BRAIN v1 — training orchestration package.

This package is the **lifecycle orchestration layer** for JARVIS Brain v1.  It
reuses the EXISTING training engine and corpus (it does NOT duplicate them):

  * Training engine : ``videlisndichi-jarvis-brain-qwen3-4b-sft-train/jarvis_brain_sft.py``
      (Kaggle GPU kernel: LoRA/QLoRA SFT, r2000 eval, NaN/Inf gate, adapter
      save/reload smoke).  Run ONLY on a CUDA GPU.
  * SFT corpus      : ``videlisndichi-jarvis-brain-v1-sft/01_normalized.jsonl``
      (292 seed passages + ``jarvis_brain_sft_dataset_manifest.json``).
  * Kaggle entry     : ``kaggle_kernel/jarvis_brain_qwen3_4b.ipynb``.

What THIS package provides (spec S1-S31):

  * environment + secret resolution (server-side only; never printed)
  * hardware probe (GPU/VRAM/CUDA/BF16/FP16 — honest CPU fallback)
  * dataset pipeline validation + reproducibility manifest + secret scan
  * HuggingFace connection probe + authenticated publish workflow (gated)
  * Kaggle configuration / kernel-status probe (gated)
  * run registry + append-only training event log + checkpoint manifest schema
  * baseline / pilot / train / evaluate / promote / deploy stage gates
  * operations status command (actual state only; never fabricated)

Honesty (spec S30): every stage reports its REAL observed state.  Stages that
require a CUDA GPU, network to HuggingFace, or Kaggle credentials report
``NOT RUN`` / ``NOT CONNECTED`` / ``UNKNOWN`` on a CPU-only dev box — they are
never claimed to have executed.
"""
from __future__ import annotations

__all__ = [
    "BrainTrainingConfig",
    "env_snapshot",
    "EnvSnapshot",
    "SECRET_PATTERNS",
    "gpu_probe",
    "validate_corpus",
    "secret_scan_artifact",
    "hf_probe",
    "kaggle_probe",
    "RunRegistry",
    "TrainingEventLogger",
    "CheckpointMeta",
    "promotion_gate",
    "load_config",
    "resolve_model",
    "probe_brain_endpoint",
    "run_pipeline",
    "status",
    "run_baseline",
]
__version__ = "1.0.0"

from .config import (  # noqa: F401
    BrainTrainingConfig,
    EnvSnapshot,
    SECRET_PATTERNS,
    env_snapshot,
    hf_token,
)
from .hardware import gpu_probe  # noqa: F401
from .dataset import validate_corpus, write_validation_report  # noqa: F401
from .hf import probe as hf_probe, secret_scan_artifact  # noqa: F401
from .kaggle import probe as kaggle_probe  # noqa: F401
from .registry import RunRegistry, TrainingEventLogger, CheckpointMeta  # noqa: F401
from .promote import gate as promotion_gate  # noqa: F401
from .deploy import load_config, resolve_model, probe_brain_endpoint  # noqa: F401
from .pipeline import run_pipeline  # noqa: F401
from .status import status  # noqa: F401
from .baseline import run_baseline  # noqa: F401
