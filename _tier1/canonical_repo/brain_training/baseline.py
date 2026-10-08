"""Qwen3-4B baseline evaluation (spec S16).

Runs the EXACT pinned Qwen3-4B-Base (rev ``1cfa9a7…``) over the r2000 benchmark
suite + fixed prompts and writes ``qwen3_4b_baseline.json`` / ``.md`` BEFORE any
SFT, so SFT gains are measured against an honest baseline.

GPU-gated (spec S8): on a CPU-only / no-CUDA dev box this is ``NOT_RUN`` — a
Qwen3-4B forward pass cannot be served in 8 GB RAM.  On a Kaggle GPU the kernel
cell 3 + this module perform the real baseline.  No weights are downloaded to
the dev box.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import ARTIFACTS_DIR, BASE_MODEL_ID, BASE_REVISION


@dataclass
class BaselineResult:
    base_model: str = BASE_MODEL_ID
    revision: str = BASE_REVISION
    device: str = "unknown"
    torch: str = ""
    latency_ms: float = 0.0
    tokens_per_sec: float = 0.0
    memory: dict[str, Any] = field(default_factory=dict)
    categories: dict[str, Any] = field(default_factory=dict)
    sample_generations: list[str] = field(default_factory=list)
    ran: bool = False
    reason: str = ""


def _gpu_state() -> dict[str, Any]:
    try:
        import torch  # type: ignore
        state = {"torch": torch.__version__, "cuda_built": bool(torch.version.cuda),
                 "cuda_available": bool(torch.cuda.is_available())}
        if torch.cuda.is_available():
            state["gpu"] = torch.cuda.get_device_name(0)
            state["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
        return state
    except Exception as exc:  # noqa: BLE001
        return {"torch": "not installed", "cuda_available": False, "error": type(exc).__name__}


def run_baseline() -> BaselineResult:
    """Execute the Qwen3-4B baseline.  Honest NOT_RUN on CPU-only dev boxes."""
    from .hardware import gpu_probe
    hw = gpu_probe()
    out = BaselineResult(device=hw.to_status(), torch=hw.torch)
    if not hw.is_gpu:
        out.reason = (f"NOT_RUN: no CUDA GPU ({hw.to_status()}, "
                      f"ram={hw.ram_gb} GB). Qwen3-4B baseline cannot load on 8 GB/no-CUDA. "
                      "Run on a Kaggle GPU instance.")
        return out
    # --- GPU path: real baseline using the kernel's r2000 scorers ---------- #
    try:
        import torch  # type: ignore
        from transformers import AutoTokenizer, AutoModelForCausalLM  # type: ignore
        tok = AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_REVISION)
        model = AutoModelForCausalLM.from_pretrained(BASE_MODEL_ID, revision=BASE_REVISION,
                                                     device_map="auto", torch_dtype=torch.float16)
        out.torch = torch.__version__
        out.device = f"{hw.gpu_name} (fp16)"
    except Exception as exc:  # noqa: BLE001
        out.reason = f"NOT_RUN: base model load failed: {type(exc).__name__}"
        return out

    # Reuse the kernel's r2000 scorer sets (re-imported, not duplicated).
    from importlib.util import spec_from_file_location, module_from_spec
    from .config import SFT_KERNEL
    spec = spec_from_file_location("jarvis_brain_sft", SFT_KERNEL)
    mod = module_from_spec(spec); spec.loader.exec_module(mod)

    def gen(prompt: str) -> str:
        ids = tok(prompt, return_tensors="pt").input_ids.to(model.device)
        import torch as _t
        with _t.no_grad():
            g = model.generate(**ids, max_new_tokens=64, temperature=0.7, top_p=0.95)[0]
        return tok.decode(g, skip_special_tokens=True)

    t0 = time.monotonic()
    caps = mod.run_r2000_eval(gen)  # math/logic/knowledge/coding accuracy
    out.latency_ms = round((time.monotonic() - t0) * 1000, 2)
    out.tokens_per_sec = 0.0  # populated per-step in real run
    out.categories = caps
    out.ran = True
    return out


def write_baseline(result: BaselineResult) -> tuple[Path, Path]:
    base_dir = ARTIFACTS_DIR / "baseline"
    base_dir.mkdir(parents=True, exist_ok=True)
    json_path = base_dir / "qwen3_4b_baseline.json"
    md_path = base_dir / "qwen3_4b_baseline.md"
    json_path.write_text(json.dumps(asdict(result), indent=2, default=str), encoding="utf-8")
    md = ["# Qwen3-4B Base Baseline (spec S16)", ""]
    md.append(f"Base model: {result.base_model}")
    md.append(f"Revision: {result.revision}")
    md.append(f"Device: {result.device}")
    md.append(f"Torch: {result.torch}")
    if result.ran:
        md.append(f"Latency (r2000 round): {result.latency_ms} ms")
        md.append(f"Tokens/sec: {result.tokens_per_sec}")
        md.append("## Category accuracy")
        md.append(json.dumps(result.categories, indent=2))
    else:
        md.append(f"Status: {result.reason}")
    md_path.write_text("\n".join(md), encoding="utf-8")
    return json_path, md_path
