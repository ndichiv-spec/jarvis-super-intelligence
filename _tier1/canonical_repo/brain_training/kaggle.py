"""Kaggle connection / kernel-status probe (spec S8/S13).

Kaggle credentials (``KAGGLE_USERNAME``/``KAGGLE_KEY``) are OS-env only; the
dev box does not hold them — Kaggle injects these as kernel secrets at runtime
inside the kernel UI.  The machine-readable ``kernel-metadata.json`` (NOT the
.ipynb) + the SFT kernel script are inspected as READ-ONLY artifacts so the
status reflects the actual configured training plan, not a fabricated claim.

Reality on this box (spec S30):
  * ``kaggle`` CLI is installed but NOT authenticated (no creds) -> NOT CONFIGURED.
  * Kernel requests GPU + internet, dataset source ``videlisndichi/jarvis-brain-v1-sft``,
    code_file ``jarvis_brain_sft.py`` — the plan is defined; launching requires Kaggle auth.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import KAGGLE_KERNEL, KAGGLE_KERNEL_METADATA, SFT_KERNEL


@dataclass
class KaggleProbe:
    configured: bool = False                 # KAGGLE_USERNAME + KAGGLE_KEY present in env
    username_present: bool = False
    key_present: bool = False
    api_installed: bool = False              # `kaggle --version` works at all
    api_executable: str = ""                 # path to the CLI (not a secret)
    kernel_path: str = ""
    kernel_metadata: dict[str, Any] = field(default_factory=dict)
    expected_accelerator: str = "GPU (set in kernel UI)"
    error: str = ""

    def summary(self) -> dict[str, Any]:
        md = self.kernel_metadata or {}
        return {
            "configured": self.configured,
            "api_installed": self.api_installed,
            "api_executable": self.api_executable or "(not found)",
            "username_present": self.username_present,
            "key_present": self.key_present,
            "kernel_id": md.get("id"),
            "kernel_title": md.get("title"),
            "code_file": md.get("code_file"),
            "dataset_sources": md.get("dataset_sources"),
            "enable_gpu": md.get("enable_gpu"),
            "enable_internet": md.get("enable_internet"),
            "kernel_type": md.get("kernel_type"),
            "language": md.get("language"),
            "error": self.error or ("NOT CONFIGURED (KAGGLE_USERNAME/KAGGLE_KEY absent; "
                                   "Kaggle injects these as kernel secrets at runtime)"
                                   if not self.configured else ""),
        }


def probe() -> KaggleProbe:
    p = KaggleProbe()
    p.kernel_path = str(KAGGLE_KERNEL)
    p.username_present = bool(os.environ.get("KAGGLE_USERNAME"))
    p.key_present = bool(os.environ.get("KAGGLE_KEY"))
    p.configured = p.username_present and p.key_present
    exe = shutil.which("kaggle")
    p.api_installed = exe is not None
    p.api_executable = exe or ""

    # Prefer the machine-readable kernel-metadata.json for structured fields.
    if KAGGLE_KERNEL_METADATA.exists():
        try:
            p.kernel_metadata = json.loads(KAGGLE_KERNEL_METADATA.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            p.error = f"kernel-metadata.json unreadable: {exc}"
    elif KAGGLE_KERNEL.exists():
        p.error = (f"kernel metadata missing ({KAGGLE_KERNEL_METADATA}); "
                   f"notebook at {KAGGLE_KERNEL} is a .ipynb (not machine-scanned for fields)")
    else:
        p.error = "kernel metadata + notebook not found"

    errors: list[str] = []
    if p.error:
        errors.append(p.error)
    if not p.api_installed:
        errors.append("kaggle CLI not installed")
    if not p.configured:
        errors.append("KAGGLE_USERNAME/KAGGLE_KEY absent (Kaggle auth not configured on dev box)")
    p.error = "; ".join(errors) if errors else ""
    return p


def kaggle_gpu_requirements() -> dict[str, Any]:
    """The GPU/env contract the kernel expects (from kernel-metadata.json)."""
    return {
        "accelerator": "GPU",
        "internet": True,
        "runtime": "Python",
        "packages": ["torch==2.4.1+cu121", "transformers>=4.46", "peft>=0.12",
                     "bitsandbytes", "safetensors", "tokenizers", "datasets",
                     "httpx", "huggingface_hub", "tqdm"],
        "dataset_source": "videlisndichi/jarvis-brain-v1-sft",
        "note": ("Do NOT assume T4/P100/L4; kernel cell 1 prints the ACTUAL "
                 "accelerator (platform/python/torch/cuda/GPU props/CPU/RAM/disk)."),
    }
