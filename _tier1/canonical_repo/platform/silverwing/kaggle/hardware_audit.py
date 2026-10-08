"""Silverwing Hardware & Environment Audit.

Run at the start of every Kaggle session to record the actual compute
environment.  Never assume the accelerator.
"""
import os
import sys
import shutil
import subprocess
import platform

# ── Pre-flight GPU check ──────────────────────────────────────────────
# Tesla P100 (sm_60) is detected by PyTorch but has no compatible kernels.
# Hide it before importing torch so the entire pipeline falls back to CPU.
_p100_detected = False
try:
    _gpu_info = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,memory.total",
         "--format=csv,noheader"],
        stderr=subprocess.DEVNULL, text=True, timeout=10
    ).strip()
    for _line in _gpu_info.split("\n"):
        _name = _line.split(",")[0].strip()
        if "P100" in _name:
            _p100_detected = True
    if _p100_detected:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
except Exception:
    pass

import torch

# ── Hardware report ───────────────────────────────────────────────────
gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
gpu_names = [torch.cuda.get_device_name(i) for i in range(gpu_count)]
total_vram = sum(torch.cuda.get_device_properties(i).total_memory for i in range(gpu_count)) / 1e9 if gpu_count else 0

bf16_supported = torch.cuda.is_available()
try:
    if bf16_supported:
        _t = torch.zeros(2, 2, device="cuda", dtype=torch.bfloat16)
        _t.sum().item()
    else:
        bf16_supported = False
except Exception:
    bf16_supported = False

fp16_supported = torch.cuda.is_available()
try:
    if fp16_supported:
        _t = torch.zeros(2, 2, device="cuda", dtype=torch.float16)
        _t.sum().item()
    else:
        fp16_supported = False
except Exception:
    fp16_supported = False

# CPU info
cpu_count = os.cpu_count()
ram_total = 0
try:
    with open("/proc/meminfo", "r") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                ram_total = int(line.split()[1]) / (1024**3)
                break
except Exception:
    pass
# Windows fallback
if not ram_total:
    try:
        import platform
        if platform.system() == "Windows":
            _out = subprocess.check_output("wmic computersystem get TotalPhysicalMemory", shell=True, text=True).strip()
            ram_total = int(_out.split("\n")[1].strip()) / (1024**3)
    except Exception:
        pass

# Disk
disk_total, disk_used, disk_free = shutil.disk_usage("/")
disk_free_gb = disk_free / (1024**3)

print("=" * 50)
print("SILVERWING KAGGLE HARDWARE REPORT")
print("=" * 50)
print()
print("GPU:")
print(f"GPU COUNT: {gpu_count if gpu_count else '(P100 sm_60 — CUDA disabled, CPU fallback)'}")
print(f"VRAM: {total_vram:.1f} GB" if total_vram else "VRAM: N/A (CPU mode)")
if gpu_names:
    for n in gpu_names:
        print(f"  - {n}")
print(f"CUDA: {'available' if torch.cuda.is_available() else 'NOT available (CPU fallback)'}")
print()
print(f"PYTORCH: {torch.__version__}")
print(f"PYTHON: {sys.version.split()[0]}")
print(f"RAM: {ram_total:.1f} GB")
print(f"DISK: {disk_free_gb:.1f} GB free")
print(f"BF16: {'supported' if bf16_supported else 'not supported'}")
print(f"FP16: {'supported' if fp16_supported else 'not supported'}")
print(f"DEVICE: {'cuda' if torch.cuda.is_available() else 'cpu'}")
print()
print("=" * 50)
print(f"CPU cores: {cpu_count}")
print(f"Platform: {platform.platform()}")
print(f"P100 detected at boot: {_p100_detected}")
print(f"CUDA capability: {torch.cuda.get_device_capability(0) if gpu_count else 'N/A'}")
print("=" * 50)

# Save report for the training script to read
os.makedirs("/kaggle/working/silverwing", exist_ok=True)
os.makedirs("/kaggle/working/silverwing/logs", exist_ok=True)
with open("/kaggle/working/silverwing/logs/hardware_report.json", "w") as f:
    import json
    json.dump({
        "gpu_count": gpu_count,
        "gpu_names": gpu_names,
        "total_vram_gb": round(total_vram, 1),
        "cuda_available": torch.cuda.is_available(),
        "bf16_supported": bf16_supported,
        "fp16_supported": fp16_supported,
        "torch_version": torch.__version__,
        "python_version": sys.version.split()[0],
        "ram_gb": round(ram_total, 1),
        "disk_free_gb": round(disk_free_gb, 1),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "cpu_cores": cpu_count,
        "platform": platform.platform(),
        "p100_detected": _p100_detected,
    }, f, indent=2)
print("\nHardware report saved to /kaggle/working/silverwing/logs/hardware_report.json")
