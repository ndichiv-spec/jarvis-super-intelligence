"""Hardware reality probe for JARVIS Brain training (spec S8).

Detects the ACTUAL accelerator.  Never assumes T4/P100/L4.  On this dev box the
result is honestly CPU-only (no CUDA).  GPU-gated stages (baseline/pilot/train/
evaluate) consult ``gpu_probe().cuda`` before doing anything that would OOM an
8 GB-RAM / no-CUDA host.
"""
from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HardwareProbe:
    platform: str
    python: str
    torch: str = "not installed"
    torch_cuda_built: bool = False
    cuda_available: bool = False
    vram_gb: Optional[float] = None
    gpu_name: Optional[str] = None
    bf16_supported: bool = False
    fp16_supported: bool = False
    cpu_cores_logical: int = 0
    cpu_cores_physical: int = 0
    ram_gb: Optional[float] = None
    disk_free_gb: Optional[float] = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_gpu(self) -> bool:
        return bool(self.cuda_available and self.gpu_name)

    @property
    def can_train(self) -> bool:
        # LoRA/QLoRA SFT of Qwen3-4B needs a CUDA GPU with enough VRAM.
        return bool(self.is_gpu and (self.vram_gb or 0) >= 12.0)

    def to_status(self) -> str:
        if self.is_gpu:
            return "GPU"
        return "CPU (no CUDA)"

    def summary(self) -> dict:
        return {
            "device": self.to_status(),
            "gpu_name": self.gpu_name,
            "vram_gb": self.vram_gb,
            "cuda_available": self.cuda_available,
            "cuda_built": self.torch_cuda_built,
            "bf16_supported": self.bf16_supported,
            "fp16_supported": self.fp16_supported,
            "ram_gb": self.ram_gb,
            "cpu_cores_logical": self.cpu_cores_logical,
            "disk_free_gb": self.disk_free_gb,
            "can_train_qwen3_4b_sft": self.can_train,
            "torch": self.torch,
        }


def _psutil_int(fn, default=0):
    try:
        import psutil  # type: ignore
        return fn(psutil)
    except Exception:
        return default


def gpu_probe() -> HardwareProbe:
    p = HardwareProbe(platform=platform.platform(), python=platform.python_version())

    p.cpu_cores_logical = _psutil_int(lambda ps: ps.cpu_count(logical=True), 0) or 0
    p.cpu_cores_physical = _psutil_int(lambda ps: ps.cpu_count(logical=False), 0) or 0
    try:
        import psutil  # type: ignore
        p.ram_gb = round(psutil.virtual_memory().total / 1e9, 2)
    except Exception:
        pass

    try:
        p.disk_free_gb = round(shutil.disk_usage("/").free / 1e9, 2)
    except Exception:
        pass

    try:
        import torch  # type: ignore
        p.torch = torch.__version__
        p.torch_cuda_built = bool(torch.version.cuda)
        p.cuda_available = bool(torch.cuda.is_available())
        if p.cuda_available:
            p.gpu_name = torch.cuda.get_device_name(0)
            try:
                p.vram_gb = round(
                    torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2
                )
            except Exception:
                pass
            try:
                p.bf16_supported = bool(torch.cuda.is_bf16_supported())
            except Exception:
                pass
            p.fp16_supported = True  # CUDA implies fp16 capability
        else:
            p.notes.append("CUDA not available — CPU-only dev box. "
                            "Qwen3-4B LoRA/QLoRA SFT cannot run here (8 GB RAM/no CUDA).")
            p.notes.append("Training stages are GPU-gated; run on a Kaggle GPU instance.")
    except ImportError:
        p.torch = "not installed"
        p.notes.append("torch not installed in this environment.")
    return p
