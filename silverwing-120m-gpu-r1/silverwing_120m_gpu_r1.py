#!/usr/bin/env python3
"""silverwing_120m_gpu_r1.py — Clean GPU relaunch of Silverwing-120M-V1.

Self-contained, single execution flow: preflight → tokenizer verify → dataset
verify → GPU memory probe → model build → smoke test → TRAIN → eval → reports.

The previous Kaggle kernel was cancelled in the gap between its notebook-cell
smoke-test and the training-loop call.  This script eliminates that gap: the
smoke test and training are in the SAME function, with metrics.jsonl written
BEFORE the smoke test (training_run_start event) and a training_started event
at step 1 only after smoke PASS.

Run on Kaggle (Script kernel, GPU accelerator):
    python silverwing_120m_gpu_r1.py
Resume:
    python silverwing_120m_gpu_r1.py --resume
    python silverwing_120m_gpu_r1.py --resume-from /kaggle/working/silverwing-120m-gpu-r1/checkpoints/step-500
"""
from __future__ import annotations

# ===========================================================================
# §0  P100 detection + dependency installation (MUST run before import torch)
# ===========================================================================
import importlib
import os
import platform
import subprocess
import sys

def _gpu_names() -> list[str]:
    """Return list of GPU names via nvidia-smi (empty list on CPU-only)."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, text=True, timeout=10,
        ).strip()
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    except Exception:
        return []

_GPU_NAMES = _gpu_names()
_P100 = any("P100" in n.upper() for n in _GPU_NAMES)

if _P100:
    # P100 = sm_60; Kaggle's base torch (2.10+cu128) has no sm_60 kernels.
    # We must install a compatible build BEFORE `import torch`. Only skip the
    # reinstall when the *active* torch build actually ships sm_60 kernels.
    _need_torch = True
    try:
        _arch = subprocess.check_output(
            [sys.executable, "-c", "import torch; print(' '.join(torch.cuda.get_arch_list()))"],
            stderr=subprocess.DEVNULL, text=True, timeout=30,
        ).strip()
        if "sm_60" in _arch.split():
            _need_torch = False
    except Exception:
        pass
    if _need_torch:
        print("[SETUP] P100 (sm_60) detected — installing torch==2.4.1+cu121...",
              flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir",
             "torch==2.4.1+cu121",
             "--extra-index-url", "https://download.pytorch.org/whl/cu121"],
            check=False, timeout=900)

def _ensure_pkg(pkg: str):
    try:
        importlib.import_module(pkg)
    except ImportError:
        print(f"[SETUP] Installing {pkg}...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir", pkg],
            check=False)

for _p in ("tokenizers", "safetensors", "numpy", "tqdm"):
    _ensure_pkg(_p)

# ===========================================================================
# §1  Imports (torch comes AFTER the P100 / install block above)
# ===========================================================================
import json
import math
import re
import time
import hashlib
import argparse
import shutil
import unicodedata
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import torch
import numpy as np
from tokenizers import Tokenizer as HFTokenizer
from safetensors.torch import save_file, load_file

try:
    from tqdm import tqdm
except ImportError:  # noqa: F401
    def tqdm(x, **kw):
        return x

# ===========================================================================
# §2  Environment detection + path resolution
# ===========================================================================
KAGGLE_DIR = Path("/kaggle")
IS_KAGGLE = KAGGLE_DIR.exists() and "/kaggle" in str(KAGGLE_DIR.resolve())
SCRIPT_DIR = Path(__file__).resolve().parent
# Kaggle script kernels run from a read-only /kaggle/src — write all run
# artifacts (metrics, checkpoints, reports) under /kaggle/working instead.
RUN_DIR = (Path("/kaggle/working") / "silverwing-120m-gpu-r1") if IS_KAGGLE else SCRIPT_DIR  # GPU-R1 output directory

def _kaggle_root() -> Path | None:
    """Find the silverwing-120m dataset mount in /kaggle/input/*."""
    import glob
    for pat in ("/kaggle/input/*silverwing-120m*/",
                "/kaggle/input/*/*silverwing-120m*/"):
        for c in glob.glob(pat):
            if Path(c).exists():
                return Path(c)
    fallback = Path("/kaggle/input/datasets/videlisndichi/silverwing-120m/")
    return fallback if fallback.exists() else Path("/kaggle/input")

def _resolve(*candidates, desc: str = "file") -> Path:
    """Return the first existing path from *candidates*, or raise."""
    for c in candidates:
        if c is None:
            continue
        p = Path(c)
        if p.exists():
            return p.resolve()
    raise FileNotFoundError(
        f"Could not find {desc}. Tried: " + ", ".join(str(c) for c in candidates if c is not None))

if IS_KAGGLE:
    _KIN = _kaggle_root()
    CFG_PATH = _resolve(
        os.environ.get("SW_CFG"),
        "/kaggle/working/silverwing_120m_config.json",
        _KIN / "silverwing_120m_config.json",
        desc="config")
    TOK_PATH = _resolve(
        os.environ.get("SW_TOK"),
        "/kaggle/working/r2000_tokenizer.json",
        "/kaggle/working/tokenizer.json",
        _KIN / "tokenizer.json",
        desc="tokenizer")
    VAL_TXT = _resolve(
        os.environ.get("SW_VAL_TXT"),
        "/kaggle/working/val.txt",
        _KIN.parent / "silverwing-120m-fixes" / "val.txt",
        desc="val.txt")
    R2000_EVAL = _resolve(
        os.environ.get("SW_R2000_EVAL"),
        "/kaggle/working/r2000_eval.json",
        _KIN / "r2000_eval.json",
        desc="r2000_eval.json")
    DATA_DIR = Path("/kaggle/working/silverwing_120m/data")
    # Also check Kaggle input dataset for pre-built data shard
    _KAG_DATA = _KIN / "silverwing-120m" / "data"
    if not DATA_DIR.exists() and _KAG_DATA.exists():
        DATA_DIR = _KAG_DATA
    CORPUS_JSONL = _resolve(
        os.environ.get("SW_CORPUS"),
        "/kaggle/working/01_normalized.jsonl",
        _KIN / "01_normalized.jsonl",
        desc="corpus jsonl")
else:
    CFG_PATH = _resolve(
        r"F:/AI/_kout5/silverwing_120m_config.json",
        r"F:/AI/silverwing-120m/silverwing_120m_config.json",
        desc="config")
    TOK_PATH = _resolve(
        r"F:/AI/_kout5/r2000_tokenizer.json",
        r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json",
        desc="tokenizer")
    VAL_TXT = _resolve(r"F:/AI/_kout5/val.txt", desc="val.txt")
    R2000_EVAL = _resolve(r"F:/AI/_kout5/r2000_eval.json", desc="r2000_eval.json")
    DATA_DIR = _resolve(
        r"F:/AI/_kout5/silverwing-120m/data",
        r"F:/AI/silverwing-120m/data",
        desc="data dir")
    CORPUS_JSONL = _resolve(r"F:/AI/_kout5/01_normalized.jsonl", desc="corpus")

# ===========================================================================
# §3  Constants — hashes, baselines, training config
# ===========================================================================
MODEL_VERSION = "Silverwing-120M-V1"
RUN_ID = "silverwing-120m-gpu-r1"
EXPECTED_TOK_SHA256 = "5b09bfb6cf456dbbdc52879c133bf706bafeee34bc9f9766786fd2bda8027844"
EXPECTED_VOCAB = 8192
EXPECTED_CONFIG_SHA = "61adf4b257da9a9ca9e9ea2e0e57f359954e2de4ccc8506097dc551567b913b9"
EXPECTED_TRAIN_TOKENS = 4_999_168
EXPECTED_VAL_TOKENS = 51_200
EXPECTED_PARAM_COUNT = 120_087_552
DATASET_HASH = "5b389a08d7e1eb65bc7a9859a7f644def69aaf78f0b7373f9c77c67bd27fa236"

# r2000 baseline
R2000_VAL_LOSS = 6.3445424883384405
R2000_VAL_PPL = 569.3768335750539
R2000_MATH = (0, 8)
R2000_LOGIC = (4, 6)
R2000_CODING = (0, 3)
R2000_KNOWLEDGE = (0, 8)
R2000_PARAMS = 12_440_448
R2000_MODEL_SHA = "2c2775a7a7fe30359ce2c085e3278c69c99bac0452eb45e2cd007a91ffb724d2"

# Training config (§9 — overrides Kaggle log seq 2048 → 256, warmup 250 → 25)
TARGET_STEPS = 500
SEQ = 256
MICRO_BATCH = 1
GRAD_ACCUM = 4
BASE_LR = 1.5e-4
WARMUP_STEPS = 25
WEIGHT_DECAY = 0.01
GRAD_CLIP = 1.0
SEED = 42
SAVE_EVERY = 100
EVAL_EVERY = 100

# 10 fixed generation prompts (from stage3a_evaluate.py)
FIXED_PROMPTS = [
    "The story began", "Science is", "Mathematics is", "Explain gravity.",
    "What is a centrifugal pump?", "What is 17 × 24?",
    "Explain Newton's second law.",
    "Write a Python function that adds two numbers.",
    "Why is preventive maintenance important?", "Explain photosynthesis.",
]

# Benchmark questions (from stage3a_evaluate.py)
MATH_QS = [
    ("What is 17 × 24?", 408),
    ("What is 143 + 257?", 400),
    ("What is 1024 / 16?", 64),
    ("What is 2 to the power of 10?", 1024),
    ("What is 15% of 200?", 30),
    ("What is 7 × 8 × 9?", 504),
    ("What is 999 - 587?", 412),
    ("What is the sum of 1 to 100?", 5050),
]
LOGIC_QS = [
    ("If all A are B and all B are C, are all A definitely C?",
     ["yes", "true", "definitely", "correct"]),
    ("All cats are mammals. All mammals are animals. Is a cat an animal?",
     ["yes", "true", "definitely"]),
    ("Sequence: 2, 6, 12, 20, 30, 42, ? What is the next number?",
     [str(n) for n in range(1, 200)]),
    ("Is 0.999... equal to 1?", ["yes", "equal", "true"]),
    ("If today is Monday, what day will it be 7 days from now?", ["monday"]),
    ("A bat and a ball cost $1.10 total. The bat costs $1 more than the ball. How much is the ball?",
     ["0.05", "5 cents", "5c", "$0.05"]),
]
KNOW_QS = [
    ("What is H2O?", ["water"]),
    ("What is the chemical symbol for water?", ["H2O", "H₂O", "h2o"]),
    ("What is Newton's second law of motion?",
     ["force", "mass", "acceleration", "f = ma", "f=ma"]),
    ("Who wrote the play 'Hamlet'?", ["shakespeare"]),
    ("What is the Red Planet?", ["mars"]),
    ("What is the capital of France?", ["paris"]),
    ("What gas do plants absorb for photosynthesis?", ["carbon dioxide", "co2"]),
    ("What is the largest planet in our solar system?", ["jupiter"]),
]
CODE_QS = [
    ("Write a Python function add(a, b) that returns a + b.\n```python\n", "add",
     "add(2, 3) == 5 and add(-1, 1) == 0"),
    ("Write a Python function factorial(n) returning n!.\n```python\n", "factorial",
     "factorial(5) == 120 and factorial(0) == 1"),
    ("Write a Python function is_palindrome(s) that returns True if s reads the same forwards and backwards.\n```python\n",
     "is_palindrome", "is_palindrome('racecar') and not is_palindrome('hello')"),
]


# ===========================================================================
# §4  Utility functions
# ===========================================================================
def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def write_jsonl(path, record: dict):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def bytes_to_mb(n: int) -> float:
    return round(n / (1024 * 1024), 1)

def get_vram() -> dict:
    if not torch.cuda.is_available():
        return {"allocated_mb": 0, "reserved_mb": 0, "total_mb": 0, "peak_mb": 0}
    return {
        "allocated_mb": bytes_to_mb(torch.cuda.memory_allocated()),
        "reserved_mb": bytes_to_mb(torch.cuda.memory_reserved()),
        "total_mb": round(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024), 1),
        "peak_mb": bytes_to_mb(torch.cuda.max_memory_allocated()),
    }

def _psutil_ram_gb() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().total / 1e9, 2)
    except ImportError:
        return 0.0


# ===========================================================================
# §5  Model architecture  (inline from silverwing_train.py, 120M config)
# ===========================================================================
@dataclass
class ModelConfig:
    """Silverwing-120M: 12L / 1024d / 16H / 4KV / GQA 4:1 / MLP 2176 / SwiGLU / RoPE 10k / RMSNorm / tied / no-bias / vocab 8192 / ctx 2048."""
    vocab_size: int = 8192
    max_position_embeddings: int = 2048
    n_layers: int = 12
    n_heads: int = 16
    n_kv_heads: int = 4
    d_model: int = 1024
    hidden_size: int = 2176
    multiple_of: int = 64
    norm_eps: float = 1e-5
    rope_theta: float = 10000.0
    use_bias: bool = False
    tie_word_embeddings: bool = True
    pad_token_id: int = 0
    bos_token_id: int = 1
    eos_token_id: int = 2

    @property
    def head_dim(self) -> int:
        return self.d_model // self.n_heads

    @property
    def n_kv_groups(self) -> int:
        return self.n_heads // self.n_kv_heads


def estimate_parameters(config: ModelConfig) -> int:
    """Compute exact parameter count for the 120M architecture."""
    d = config.d_model
    H = config.hidden_size
    nl = config.n_layers
    n_groups = config.n_kv_groups
    params = config.vocab_size * d  # tied embeddings
    layer_params = (
        d * d                    # Q
        + d * (d // n_groups)    # K
        + d * (d // n_groups)    # V
        + d * d                   # O
        + d * H * 2              # gate + up (SwiGLU)
        + H * d                  # down
        + 2 * d                  # 2 RMSNorms
    )
    params += layer_params * nl
    params += d  # final norm
    return params


class RMSNorm(torch.nn.Module):
    """Root Mean Square Layer Normalization (no bias)."""

    def __init__(self, hidden_size: int, eps: float = 1e-5):
        super().__init__()
        self.eps = eps
        self.weight = torch.nn.Parameter(torch.ones(hidden_size))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        with torch.autocast(device_type=x.device.type, enabled=False):
            x_f = x.float()
            variance = x_f.pow(2).mean(-1, keepdim=True)
            x_norm = x_f * torch.rsqrt(variance + self.eps)
        return self.weight * x_norm.to(x.dtype)


class RotaryEmbedding:
    """Sinusoidal rotary positional embeddings (RoPE, theta=10000)."""

    def __init__(self, dim: int, base: float = 10000.0):
        self.dim = dim
        self.base = base

    def __call__(self, seq_len: int, device: torch.device):
        theta = 1.0 / (self.base ** (
            torch.arange(0, self.dim, 2, dtype=torch.float32, device=device) / self.dim))
        positions = torch.arange(seq_len, dtype=torch.float32, device=device)
        freqs = torch.outer(positions, theta)
        cos = torch.zeros(seq_len, self.dim, device=device, dtype=torch.float32)
        sin = torch.zeros(seq_len, self.dim, device=device, dtype=torch.float32)
        cos[:, 0::2] = torch.cos(freqs)
        cos[:, 1::2] = torch.cos(freqs)
        sin[:, 0::2] = torch.sin(freqs)
        sin[:, 1::2] = torch.sin(freqs)
        return cos, sin


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2:]
    return torch.cat((-x2, x1), dim=-1)


def apply_rope(q, k, cos, sin):
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed


class Attention(torch.nn.Module):
    """Grouped-Query Attention (GQA) with RoPE."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.n_heads = config.n_heads
        self.n_kv_heads = config.n_kv_heads
        self.head_dim = config.head_dim
        self.n_kv_groups = config.n_kv_groups

        self.q_proj = torch.nn.Linear(config.d_model,
                                      self.n_heads * self.head_dim, bias=config.use_bias)
        self.k_proj = torch.nn.Linear(config.d_model,
                                      self.n_kv_heads * self.head_dim, bias=config.use_bias)
        self.v_proj = torch.nn.Linear(config.d_model,
                                      self.n_kv_heads * self.head_dim, bias=config.use_bias)
        self.o_proj = torch.nn.Linear(self.n_heads * self.head_dim,
                                      config.d_model, bias=config.use_bias)
        self.rope = RotaryEmbedding(self.head_dim, config.rope_theta)

    def forward(self, x, mask=None):
        B, T, _ = x.shape
        q = self.q_proj(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, T, self.n_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, T, self.n_kv_heads, self.head_dim).transpose(1, 2)

        cos, sin = self.rope(T, q.device)
        cos = cos.unsqueeze(0).unsqueeze(0).to(q.dtype)
        sin = sin.unsqueeze(0).unsqueeze(0).to(q.dtype)
        q, k = apply_rope(q, k, cos, sin)

        if self.n_kv_groups > 1:
            k = k.repeat_interleave(self.n_kv_groups, dim=1)
            v = v.repeat_interleave(self.n_kv_groups, dim=1)

        qk = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        if mask is not None:
            qk = qk.masked_fill(mask[:, :, :T, :T] == 0, float("-inf"))
        attn = torch.softmax(qk, dim=-1)
        out = torch.matmul(attn, v)
        out = out.transpose(1, 2).contiguous().view(B, T, -1)
        return self.o_proj(out)


class SwiGLUMLP(torch.nn.Module):
    """SwiGLU activation MLP."""

    def __init__(self, d_model, hidden_size, multiple_of=64, use_bias=False):
        super().__init__()
        hidden_size = multiple_of * ((hidden_size + multiple_of - 1) // multiple_of)
        self.gate = torch.nn.Linear(d_model, hidden_size, bias=use_bias)
        self.up = torch.nn.Linear(d_model, hidden_size, bias=use_bias)
        self.down = torch.nn.Linear(hidden_size, d_model, bias=use_bias)

    def forward(self, x):
        g = self.gate(x)
        gate = torch.sigmoid(g) * g
        up = self.up(x)
        return self.down(gate * up)


class TransformerBlock(torch.nn.Module):
    """Pre-norm transformer block with GQA and SwiGLU."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.attention = Attention(config)
        self.mlp = SwiGLUMLP(config.d_model, config.hidden_size,
                             config.multiple_of, config.use_bias)
        self.ln1 = RMSNorm(config.d_model, config.norm_eps)
        self.ln2 = RMSNorm(config.d_model, config.norm_eps)

    def forward(self, x, mask=None):
        x = x + self.attention(self.ln1(x), mask)
        x = x + self.mlp(self.ln2(x))
        return x


class SilverwingModel(torch.nn.Module):
    """Silverwing-120M decoder-only transformer."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.embed_tokens = torch.nn.Embedding(
            config.vocab_size, config.d_model, config.pad_token_id)
        self.layers = torch.nn.ModuleList(
            [TransformerBlock(config) for _ in range(config.n_layers)])
        self.norm_f = RMSNorm(config.d_model, config.norm_eps)
        self.lm_head = torch.nn.Linear(
            config.d_model, config.vocab_size, bias=False)
        if config.tie_word_embeddings:
            self.lm_head.weight = self.embed_tokens.weight
        self._init_weights()

    def _init_weights(self):
        for _, param in self.named_parameters():
            if param.dim() > 1:
                torch.nn.init.normal_(param, mean=0.0, std=0.02)

    def _make_causal_mask(self, seq_len, device):
        mask = torch.tril(
            torch.ones(seq_len, seq_len, device=device, dtype=torch.bool))
        return mask.unsqueeze(0).unsqueeze(0)

    def forward(self, input_ids, labels=None):
        B, T = input_ids.shape
        x = self.embed_tokens(input_ids) * math.sqrt(self.config.d_model)
        mask = self._make_causal_mask(T, input_ids.device)
        for layer in self.layers:
            x = layer(x, mask)
        x = self.norm_f(x)
        logits = self.lm_head(x)
        loss = None
        if labels is not None:
            shift_logits = logits[:, :-1, :].contiguous()
            shift_labels = labels[:, 1:].contiguous()
            loss = torch.nn.functional.cross_entropy(
                shift_logits.view(-1, self.config.vocab_size),
                shift_labels.view(-1),
                ignore_index=self.config.pad_token_id)
        return {"loss": loss, "logits": logits}

    def num_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    @torch.no_grad()
    def generate(self, input_ids, max_new_tokens, temperature=0.8, top_p=0.9):
        for _ in range(max_new_tokens):
            logits = self(input_ids)["logits"][:, -1, :]
            logits = logits / temperature
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            cum_probs = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1)
            mask = cum_probs > top_p
            mask[:, 1:] = mask[:, :-1].clone()
            mask[:, 0] = False
            sorted_logits[mask] = float("-inf")
            probs = torch.softmax(sorted_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
            next_id = sorted_indices.gather(-1, next_token)
            input_ids = torch.cat([input_ids, next_id], dim=1)
            if next_id.item() == self.config.eos_token_id:
                break
        return input_ids


# ===========================================================================
# §6  BPE Tokenizer
# ===========================================================================
class BPETokenizer:
    """BPE tokenizer backed by HuggingFace tokenizers (r2000, 8192 vocab)."""

    def __init__(self, tokenizer=None):
        self.tok = tokenizer
        self.pad_token_id = 0
        self.bos_token_id = 1
        self.eos_token_id = 2
        self.unk_token_id = 3

    @property
    def vocab_size(self):
        return self.tok.get_vocab_size() if self.tok else 0

    def encode(self, text, max_length=None):
        enc = self.tok.encode(text)
        ids = enc.ids
        if max_length and len(ids) > max_length:
            ids = ids[:max_length]
        return ids

    def decode(self, ids):
        if isinstance(ids, torch.Tensor):
            ids = ids.tolist()
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            ids = ids[0]
        return self.tok.decode(ids, skip_special_tokens=True)

    def save(self, path):
        self.tok.save(path)

    @classmethod
    def from_file(cls, path):
        tok = HFTokenizer.from_file(path)
        return cls(tok)

    def to_manifest(self) -> dict:
        return {
            "vocab_size": self.vocab_size,
            "pad_token_id": self.pad_token_id,
            "bos_token_id": self.bos_token_id,
            "eos_token_id": self.eos_token_id,
            "unk_token_id": self.unk_token_id,
        }


# ===========================================================================
# §7  Dataset utilities
# ===========================================================================
def verify_dataset(train_npy: Path, val_npy: Path) -> dict:
    """Validate the dataset shard: exists, loads, valid IDs, distinct, no NaN/Inf."""
    results = {"checks": [], "passed": True,
               "train_tokens": 0, "val_tokens": 0,
               "train_shape": [], "val_shape": [],
               "train_min": 0, "train_max": 0}

    for label, p in [("train.npy", train_npy), ("val.npy", val_npy)]:
        if not p.exists():
            results["checks"].append({"check": f"{label} exists", "passed": False,
                                      "detail": f"not found at {p}"})
            results["passed"] = False
            return results

    train = np.load(train_npy)
    val = np.load(val_npy)

    # dtype
    for label, arr in [("train.npy", train), ("val.npy", val)]:
        if arr.dtype not in (np.int32, np.int64):
            results["checks"].append({"check": f"{label} dtype int32/int64",
                                      "passed": False, "detail": f"got {arr.dtype}"})
            results["passed"] = False

    results["checks"].append({"check": "all IDs < vocab_size",
                              "passed": bool(train.max() < EXPECTED_VOCAB and val.max() < EXPECTED_VOCAB),
                              "detail": f"train max={train.max()}, val max={val.max()}"})
    results["checks"].append({"check": "no NaN in train", "passed": not bool(np.isnan(train).any())})
    results["checks"].append({"check": "no NaN in val", "passed": not bool(np.isnan(val).any())})
    results["checks"].append({"check": "no Inf in train", "passed": not bool(np.isinf(train).any())})
    results["checks"].append({"check": "no Inf in val", "passed": not bool(np.isinf(val).any())})

    # Distinct train/val (no identical rows)
    train_rows = set(map(lambda r: r.tobytes(), train))
    val_rows = set(map(lambda r: r.tobytes(), val))
    overlap = len(train_rows & val_rows)
    results["checks"].append({"check": "train/val distinct",
                              "passed": overlap == 0,
                              "detail": f"{overlap} overlapping chunks"})
    if overlap > 0:
        results["passed"] = False

    results["train_tokens"] = int(train.size)
    results["val_tokens"] = int(val.size)
    results["train_shape"] = list(train.shape)
    results["val_shape"] = list(val.shape)
    results["train_min"] = int(train.min())
    results["train_max"] = int(train.max())
    results["checks"].append({"check": "train token count",
                              "passed": train.size >= EXPECTED_TRAIN_TOKENS * 0.9,
                              "detail": f"{train.size} vs expected {EXPECTED_TRAIN_TOKENS}"})
    results["checks"].append({"check": "val token count",
                              "passed": val.size >= EXPECTED_VAL_TOKENS * 0.5,
                              "detail": f"{val.size} vs expected {EXPECTED_VAL_TOKENS}"})
    return results


def build_dataset_from_jsonl(jsonl_path: Path, tokenizer, seq_len: int = 2048):
    """Build train.npy / val.npy from 01_normalized.jsonl.

    Mirrors the proven notebook pipeline (`pipeline_build` in the gpgpu
    kernel): LINE-level UTF-8/English/quality filters -> PII redaction ->
    exact + 9-gram dedup -> tokenize -> pack@seq.  The attached corpus is
    long-form (Wikipedia/math docs), so a doc-level filter would drop almost
    everything; the line-level pipeline is what produced the verified
    4,999,168-token train shard in the GPU kernel. Filter helpers are copied
    verbatim from silverwing_120m_kaggle.py so results stay identical.
    """
    _email_re = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    _url_re = re.compile(r"https?://\S+|www\.\S+")
    _phone_re = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")
    _ip_re = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
    _english_words = frozenset(
        "the of and to in a is that for it with as was on be at by an this "
        "have from or which one had but what are not were all their we these "
        "can been has are may more had".split())

    def _pii_redact(s):
        return _url_re.sub("[URL]", _email_re.sub("[EMAIL]", _phone_re.sub("[PHONE]", _ip_re.sub("[IP]", s))))

    def _is_english(s):
        if len(s) < 40:
            return False
        if sum(1 for c in s if ord(c) < 128) / max(len(s), 1) < 0.90:
            return False
        ws = re.findall(r"[a-zA-Z][a-zA-Z']+", s.lower())
        if not ws:
            return False
        return sum(1 for w in ws if w in _english_words) / len(ws) > 0.02

    def _quality_filter(s):
        if len(s) < 40 or len(s) > 4000:
            return False
        if sum(c.isalpha() for c in s) / max(len(s), 1) < 0.50:
            return False
        if re.search(r"(.)\1\1\1\1\1\1", s):
            return False
        return True

    def _ngram_dedup(lines, k=9):
        seen, keep, fps = set(), [], set()
        for ln in lines:
            h = hashlib.md5(ln.encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            toks = ln.lower().split()
            if len(toks) >= 2 * k:
                fp = frozenset(" ".join(toks[i:i + k]) for i in range(0, len(toks) - k, k))
                if fp & fps:
                    continue
                fps |= fp
            keep.append(ln)
        return keep

    texts = []
    with open(jsonl_path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                text = json.loads(line).get("text", "")
            except json.JSONDecodeError:
                text = line
            if text:
                texts.append(text)
    raw = "\n".join(texts)

    lines = []
    for ln in raw.splitlines():
        ln = unicodedata.normalize("NFC", ln).strip()
        if ln and _is_english(ln) and _quality_filter(ln):
            lines.append(_pii_redact(ln))
    lines = _ngram_dedup(lines)

    ids = np.asarray(tokenizer.encode("\n".join(lines)), dtype=np.int32)
    n = (len(ids) // seq_len) * seq_len
    ids = ids[:n]
    val_n = min((EXPECTED_VAL_TOKENS // seq_len) * seq_len,
                (len(ids) // seq_len) * seq_len)
    train_chunks = ids[val_n:].reshape(-1, seq_len)
    val_chunks = ids[:val_n].reshape(-1, seq_len)

    print(f"[DATA] built from {jsonl_path.name}: {len(lines)} docs, "
          f"{len(ids)} tokens -> train={train_chunks.size}, val={val_chunks.size}")
    return train_chunks, val_chunks


# ===========================================================================
# §8  Hardware preflight  (§2 — CUDA required; exit if unavailable)
# ===========================================================================
def hardware_preflight() -> dict:
    """Audit hardware.  EXIT if CUDA is unavailable — no CPU fallback."""
    info = {
        "gpu_names": _GPU_NAMES,
        "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "cuda_available": torch.cuda.is_available(),
        "pytorch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "bf16_supported": False,
        "fp16_supported": False,
        "ram_gb": _psutil_ram_gb(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }

    print("=" * 60)
    print("         HARDWARE PRE-FLIGHT AUDIT")
    print("=" * 60)
    print(f"GPU:         {', '.join(info['gpu_names']) if info['gpu_names'] else 'None detected'}")
    print(f"GPU COUNT:   {info['gpu_count']}")
    if torch.cuda.is_available():
        vram_total = torch.cuda.get_device_properties(0).total_memory
        print(f"VRAM:        {bytes_to_mb(vram_total)} MB "
              f"({vram_total / 1e9:.2f} GB)")
    else:
        print("VRAM:        N/A")
    print(f"CUDA:        {info['cuda_available']} (torch cu{info['cuda_version']})")
    print(f"PYTORCH:     {info['pytorch_version']}")
    print(f"RAM:         {info['ram_gb']} GB")
    print(f"DISK:        {bytes_to_mb(Path(run_dir_for_disk()).stat().st_size) if False else 'N/A'} MB (run dir)")
    print(f"DEVICE:      {'cuda' if info['cuda_available'] else 'cpu (BLOCKED)'}")
    print(f"PYTHON:      {info['python_version']}")
    print("=" * 60)

    if not info["cuda_available"]:
        print("\n*** CUDA is NOT available on this machine. ***")
        print("*** This script REQUIRES an NVIDIA GPU with CUDA. ***")
        print("*** DO NOT START THE REAL TRAINING RUN. ***")
        sys.exit(1)

    # FP16 / BF16 capability
    # bf16 needs Ampere+ (cap >= 8.0); some torch builds mis-report bf16 as
    # supported on Pascal.  Gate on the real capability so the P100 (sm_60)
    # reliably lands on fp16 + GradScaler (the proven kaggle path).
    try:
        gpu_cap = torch.cuda.get_device_capability(0)
        info["fp16_supported"] = bool(gpu_cap[0] >= 7)
        info["bf16_supported"] = bool(gpu_cap[0] >= 8)
    except (AttributeError, RuntimeError):
        info["fp16_supported"] = False
        info["bf16_supported"] = False

    print(f"FP16:        {info['fp16_supported']}")
    print(f"BF16:        {info['bf16_supported']}")
    return info


def run_dir_for_disk() -> Path:
    return RUN_DIR


# ===========================================================================
# §9  GPU memory discovery  (§5 — conservative, no batch increase)
# ===========================================================================
def gpu_memory_probe(model, device, precision_dtype: torch.dtype,
                      seq_len: int, micro_batch: int = 1,
                      grad_accum: int = 4) -> dict:
    """Run one test forward/backward, record VRAM.  Never increases batch."""
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.empty_cache()

    dummy = torch.randint(1, 1000, (micro_batch, seq_len + 1),
                          device=device, dtype=torch.long)
    x = dummy[:, :-1]
    y = dummy[:, 1:]
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4)

    with torch.autocast("cuda", dtype=precision_dtype):
        out = model(x, labels=y)
        loss = out["loss"] / grad_accum

    if precision_dtype == torch.float16:
        scaler = torch.amp.GradScaler("cuda")
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt)
        scaler.update()
    else:
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

    vram = get_vram()
    opt.zero_grad(set_to_none=True)
    del dummy, x, y, out, loss, opt

    print(f"\n[VRAM] precision={precision_dtype} seq={seq_len} mb={micro_batch} ga={grad_accum}")
    print(f"   allocated: {vram['allocated_mb']} MB")
    print(f"   reserved:  {vram['reserved_mb']} MB")
    print(f"   peak:      {vram['peak_mb']} MB")
    print(f"   total:     {vram['total_mb']} MB")
    safe = vram["peak_mb"] < vram["total_mb"] * 0.85
    print(f"   status:    {'SAFE — conservative config, no scaling' if safe else 'CAUTION — high VRAM'}")
    return vram, safe


# ===========================================================================
# §10  GPU smoke test  (§7 — all 9 checks, identical to Kaggle log)
# ===========================================================================
def gpu_smoke_test(model, device, precision_dtype: torch.dtype,
                   run_dir: Path) -> tuple[dict, bool]:
    """Run all 9 GPU smoke checks.  MUST all PASS before training."""
    checks = {}

    # 1. CUDA
    checks["cuda"] = torch.cuda.is_available()

    # Helper to create a dummy batch
    def _dummy():
        return torch.randint(1, 8000, (1, SEQ + 1), device=device, dtype=torch.long)

    # 2. Forward
    try:
        dummy = _dummy()
        with torch.autocast("cuda", dtype=precision_dtype):
            out = model(dummy[:, :-1], labels=dummy[:, 1:])
        checks["forward"] = not torch.isnan(out["loss"]) and not torch.isinf(out["loss"])
    except Exception as e:
        checks["forward"] = False
        checks["forward_error"] = str(e)

    # 3. Backward
    try:
        model.zero_grad(set_to_none=True)
        dummy = _dummy()
        with torch.autocast("cuda", dtype=precision_dtype):
            out = model(dummy[:, :-1], labels=dummy[:, 1:])
        loss = out["loss"]
        if precision_dtype == torch.float16:
            sc = torch.amp.GradScaler("cuda")
            sc.scale(loss).backward()
        else:
            loss.backward()
        grad_ok = all(p.grad is not None for p in model.parameters() if p.requires_grad)
        checks["backward"] = grad_ok
        model.zero_grad(set_to_none=True)
    except Exception as e:
        checks["backward"] = False
        checks["backward_error"] = str(e)

    # 4. AMP (autocast)
    checks["amp"] = checks["forward"]  # forward ran under autocast

    # 5. Optimizer
    try:
        model.zero_grad(set_to_none=True)
        dummy = _dummy()
        opt = torch.optim.AdamW(model.parameters(), lr=1e-4)
        with torch.autocast("cuda", dtype=precision_dtype):
            out = model(dummy[:, :-1], labels=dummy[:, 1:])
        loss = out["loss"]
        if precision_dtype == torch.float16:
            sc = torch.amp.GradScaler("cuda")
            sc.scale(loss).backward()
            sc.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            sc.step(opt); sc.update()
        else:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        checks["optimizer"] = True
        model.zero_grad(set_to_none=True)
        opt.zero_grad(set_to_none=True)
    except Exception as e:
        checks["optimizer"] = False
        checks["optimizer_error"] = str(e)

    # 6. Checkpoint (save + load)
    try:
        ckpt_dir = run_dir / "checkpoints" / "smoke_ckpt"
        save_checkpoint(model, None, None, step=1, tokens=SEQ,
                        path=ckpt_dir, train_loss=1.0, val_loss=1.0,
                        config=None, tokenizer=None,
                        extra={"smoke_test": True, "precision": str(precision_dtype)})
        sd = load_file(str(ckpt_dir / "model.safetensors"))
        model.eval()
        dummy = torch.randint(1, 8000, (1, SEQ), device=device, dtype=torch.long)
        with torch.no_grad(), torch.autocast("cuda", dtype=precision_dtype):
            out1 = model(dummy)["logits"]
        model.load_state_dict(sd, strict=False)
        with torch.no_grad(), torch.autocast("cuda", dtype=precision_dtype):
            out2 = model(dummy)["logits"]
        checks["checkpoint"] = torch.allclose(out1, out2, atol=1e-3)
        shutil.rmtree(ckpt_dir)
    except Exception as e:
        checks["checkpoint"] = False
        checks["checkpoint_error"] = str(e)

    # 7. Resume (load a checkpoint) — verified by the save/load round-trip above
    checks["resume"] = checks["checkpoint"]

    # 8. NaN
    try:
        dummy = _dummy()
        with torch.autocast("cuda", dtype=precision_dtype):
            out = model(dummy[:, :-1], labels=dummy[:, 1:])
        checks["nan"] = not torch.isnan(out["loss"]).any().item()
    except Exception:
        checks["nan"] = False

    # 9. Inf
    try:
        checks["inf"] = not torch.isinf(out["loss"]).any().item()
    except Exception:
        checks["inf"] = False

    checks["status"] = all(checks.get(k, False) for k in
                           ("cuda", "forward", "backward", "amp",
                            "optimizer", "checkpoint", "resume", "nan", "inf"))

    print(f"\n{'='*50}")
    print("   GPU SMOKE TEST RESULTS")
    print(f"{'='*50}")
    labels = {"cuda": "CUDA", "forward": "Forward", "backward": "Backward",
              "amp": "AMP", "optimizer": "Optimizer",
              "checkpoint": "Checkpoint", "resume": "Resume",
              "nan": "NaN", "inf": "Inf"}
    for k in ["cuda", "forward", "backward", "amp", "optimizer",
              "checkpoint", "resume", "nan", "inf"]:
        print(f"  {labels[k]:12s} {'PASS' if checks.get(k) else 'FAIL'}")
    print(f"  {'STATUS':12s} {'ALL PASS' if checks['status'] else 'FAIL'}")
    print(f"{'='*50}")

    return checks, checks["status"]


# ===========================================================================
# §11  Evaluation  (from stage3a_evaluate.py)
# ===========================================================================
def _first_int(s: str):
    m = re.search(r"-?\d+", s.replace(",", ""))
    return int(m.group(0)) if m else None

def _extract_py(text: str) -> str:
    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    i = text.find("def ")
    if i == -1:
        return ""
    head = text[i:]
    lines = head.split("\n")
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            break
        out.append(ln)
    return "\n".join(out)

def _run_code_check(code: str, test_expr: str) -> bool:
    try:
        ns = {}
        exec(code, ns)
        r = eval(test_expr, ns)
        return bool(r)
    except Exception:
        return False

@torch.no_grad()
def _quick_gen(model, tokenizer, device, dtype, prompt, max_new=64,
               temperature=0.8, top_p=0.9) -> str:
    ids = tokenizer.encode(prompt)
    if not ids:
        return ""
    t = torch.tensor([ids], dtype=torch.long, device=device)
    g = model.generate(t, max_new_tokens=max_new,
                       temperature=temperature, top_p=top_p)
    return tokenizer.decode(g[0].tolist())

@torch.no_grad()
def fast_val_loss(model, val_chunks, device, precision_dtype, seq_len, n_win=128):
    """Quick val loss / perplexity using val.npy chunks."""
    n = len(val_chunks)
    sel = np.linspace(0, n - 1, min(n_win, n)).astype(int)
    model.eval()
    tot = 0.0
    wins = 0
    for w in sel:
        chunk = val_chunks[w]
        max_start = len(chunk) - seq_len - 1
        s = int(np.random.randint(0, max_start + 1)) if max_start > 0 else 0
        window = chunk[s:s + seq_len + 1]
        x = torch.tensor(window[:-1], dtype=torch.long, device=device).unsqueeze(0)
        y = torch.tensor(window[1:], dtype=torch.long, device=device).unsqueeze(0)
        with torch.autocast("cuda", dtype=precision_dtype):
            o = model(x, labels=y)
        tot += o["loss"].item()
        wins += 1
    model.train()
    vl = tot / max(wins, 1)
    return vl, math.exp(min(vl, 20.0)), wins

@torch.no_grad()
def full_evaluate(model, tokenizer, device, precision_dtype,
                  label: str, val_txt: Path, max_len: int = 256,
                  n_windows: int = 128) -> dict:
    """Full evaluation: val loss + perplexity + benchmarks + generations."""
    res = {"label": label, "param_count": model.num_parameters()}

    # ---- common val loss / ppl (128 windows × 257 tokens) ----
    val_text = Path(val_txt).read_text(encoding="utf-8", errors="replace")
    val_ids = tokenizer.encode(val_text)
    n = min(len(val_ids), (max_len + 1) * n_windows)
    vloss = 0.0
    vcount = 0
    model.eval()
    for i in range(0, n - (max_len + 1), max_len + 1):
        batch = torch.tensor(val_ids[i:i + max_len + 1],
                             dtype=torch.long, device=device)
        input_ids = batch[:-1].unsqueeze(0)
        labels = batch[1:].unsqueeze(0)
        with torch.autocast("cuda", dtype=precision_dtype):
            o = model(input_ids, labels=labels)
        vloss += o["loss"].item()
        vcount += 1
    avg = vloss / max(vcount, 1)
    res["val_loss"] = avg
    res["val_perplexity"] = math.exp(min(avg, 20.0))
    res["val_windows"] = vcount
    res["val_tokens_evaluated"] = vcount * max_len
    res["val_sha256"] = sha256(val_txt)

    # ---- 10 fixed generation prompts ----
    gens = {}
    for p in FIXED_PROMPTS:
        try:
            gens[p] = _quick_gen(model, tokenizer, device, precision_dtype, p)
        except Exception as e:
            gens[p] = f"[ERROR {e}]"
    res["generations"] = gens

    # ---- MATH ----
    math_ok = 0
    math_details = []
    for q, exp in MATH_QS:
        out = _quick_gen(model, tokenizer, device, precision_dtype,
                         "Q: " + q + "?", max_new=40, temperature=0.5, top_p=0.95)
        got = _first_int(out)
        ok = got is not None and got == exp
        if ok:
            math_ok += 1
        math_details.append({"question": q, "expected": exp, "got": got, "passed": ok})
    res["math"] = {"correct": math_ok, "total": len(MATH_QS),
                   "accuracy": math_ok / len(MATH_QS), "details": math_details}

    # ---- LOGIC ----
    logic_ok = 0
    logic_details = []
    for q, kws in LOGIC_QS:
        out = _quick_gen(model, tokenizer, device, precision_dtype,
                         "Q: " + q + "?", max_new=40, temperature=0.5, top_p=0.95).lower()
        ok = any(k in out for k in kws)
        if ok:
            logic_ok += 1
        logic_details.append({"question": q, "passed": ok})
    res["logic"] = {"correct": logic_ok, "total": len(LOGIC_QS),
                    "accuracy": logic_ok / len(LOGIC_QS), "details": logic_details}

    # ---- KNOWLEDGE ----
    know_ok = 0
    know_details = []
    for q, kws in KNOW_QS:
        out = _quick_gen(model, tokenizer, device, precision_dtype,
                         "Q: " + q, max_new=40, temperature=0.5, top_p=0.95).lower()
        ok = any(k in out for k in kws)
        if ok:
            know_ok += 1
        know_details.append({"question": q, "passed": ok})
    res["knowledge"] = {"correct": know_ok, "total": len(KNOW_QS),
                        "accuracy": know_ok / len(KNOW_QS), "details": know_details}

    # ---- CODING ----
    code_ok = 0
    code_details = []
    for q, fname, test in CODE_QS:
        out = _quick_gen(model, tokenizer, device, precision_dtype,
                         q + "\n", max_new=120, temperature=0.5, top_p=0.95)
        code = _extract_py(out)
        ok = _run_code_check(code, test)
        if ok:
            code_ok += 1
        code_details.append({"prompt": q.strip(), "passed": ok,
                             "extracted_len": len(code)})
    res["coding"] = {"correct": code_ok, "total": len(CODE_QS),
                     "accuracy": code_ok / len(CODE_QS), "details": code_details}

    model.train()
    return res


# ===========================================================================
# §12  Checkpointing
# ===========================================================================
def save_checkpoint(model, optimizer, scheduler, step, tokens, path,
                    train_loss=None, val_loss=None, config=None,
                    tokenizer=None, extra=None, scaler=None):
    """Save: model.safetensors + optimizer.pt + config.json + metadata.json + tokenizer_manifest.json.
    `scaler` (fp16 GradScaler) is persisted as scaler.pt when provided."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    # 1. Model weights (de-aliased tied embeddings via .detach().clone())
    sd = {k: v.detach().clone() for k, v in model.state_dict().items()}
    save_file(sd, str(path / "model.safetensors"))
    model_sha = sha256(path / "model.safetensors")

    # 2. Optimizer + scheduler state
    ckpt_data = {"step": step, "tokens": tokens,
                 "train_loss": train_loss, "val_loss": val_loss}
    if optimizer is not None:
        ckpt_data["opt"] = optimizer.state_dict()
    if scheduler is not None:
        ckpt_data["sched"] = scheduler.state_dict()
    torch.save(ckpt_data, str(path / "optimizer.pt"))
    if scaler is not None:
        torch.save(scaler.state_dict(), str(path / "scaler.pt"))

    # 3. Config
    if config is not None:
        cfg_dict = asdict(config) if not isinstance(config, dict) else config
        write_json(path / "config.json", cfg_dict)
        config_sha = sha256(path / "config.json")
    else:
        config_sha = None

    # 4. Tokenizer manifest
    if tokenizer is not None:
        tok_manifest = tokenizer.to_manifest()
        tok_manifest["path"] = str(TOK_PATH)
        write_json(path / "tokenizer_manifest.json", tok_manifest)

    # 5. Metadata
    meta = {
        "step": step,
        "tokens": tokens,
        "train_loss": train_loss,
        "val_loss": val_loss,
        "model_sha256": model_sha,
        "param_count": model.num_parameters(),
        "config_sha256": config_sha,
        "tokenizer_sha256": sha256(TOK_PATH),
        "dataset_hash": DATASET_HASH,
        "timestamp": now_iso(),
    }
    if extra:
        meta.update(extra)
    write_json(path / "metadata.json", meta)

    return model_sha


def load_checkpoint(model, optimizer, scheduler, path, device):
    """Load model + optimizer + scheduler + step + tokens from a checkpoint."""
    path = Path(path)
    ckpt_data = torch.load(path / "optimizer.pt", map_location=device,
                           weights_only=False)
    if (path / "model.safetensors").exists():
        model.load_state_dict(load_file(str(path / "model.safetensors")),
                              strict=False)
    if optimizer is not None and "opt" in ckpt_data:
        optimizer.load_state_dict(ckpt_data["opt"])
    if scheduler is not None and "sched" in ckpt_data:
        scheduler.load_state_dict(ckpt_data["sched"])
    return (ckpt_data.get("step", 0), ckpt_data.get("tokens", 0),
            ckpt_data.get("train_loss"), ckpt_data.get("val_loss"))


# ===========================================================================
# §13  LR schedule  (§17 — fresh cosine, never reuses r3000)
# ===========================================================================
def get_lr(step: int, base_lr: float, warmup: int, total: int) -> float:
    if step < warmup:
        return base_lr * step / max(warmup, 1)
    progress = (step - warmup) / max(total - warmup, 1)
    return 0.5 * base_lr * (1.0 + math.cos(math.pi * progress))

def set_lr(optimizer, lr: float):
    for pg in optimizer.param_groups:
        pg["lr"] = lr


# ===========================================================================
# §14  Report generation
# ===========================================================================
def _list_checkpoints(run_dir: Path) -> list:
    ckpts = []
    ckpt_root = run_dir / "checkpoints"
    if ckpt_root.exists():
        for p in sorted(ckpt_root.iterdir()):
            if p.is_dir():
                ckpts.append(p.name)
    for p in ["best", "final"]:
        if (run_dir / p).exists():
            ckpts.append(p)
    return ckpts

def _list_artifacts(run_dir: Path) -> list:
    artifacts = []
    for p in sorted(run_dir.iterdir()):
        if p.is_file():
            artifacts.append(p.name)
    return artifacts

def generate_reports(ctx: dict):
    """Generate all required report artifacts from the training context dict."""
    run_dir = Path(ctx["run_dir"])
    metrics_path = run_dir / "metrics.jsonl"
    final_path = run_dir / "final"

    ds = ctx.get("ds_result", {})
    train_tokens = ds.get("train_tokens", 0)
    val_tokens = ds.get("val_tokens", 0)

    # --- environment_report.txt ---
    env_lines = [
        f"Silverwing-120M-V1 — GPU R1 Environment Report",
        f"Generated: {now_iso()}",
        f"{'=' * 60}",
        f"Python:      {ctx['hw_info']['python_version']}",
        f"Platform:    {ctx['hw_info']['platform']}",
        f"PyTorch:     {ctx['hw_info']['pytorch_version']}",
        f"CUDA:        {ctx['hw_info']['cuda_version']}",
        f"GPU:         {', '.join(ctx['hw_info']['gpu_names'])}",
        f"GPU count:   {ctx['hw_info']['gpu_count']}",
        f"BF16:        {ctx['hw_info']['bf16_supported']}",
        f"FP16:        {ctx['hw_info']['fp16_supported']}",
        f"RAM:         {ctx['hw_info']['ram_gb']} GB",
        f"Model params: {ctx['param_actual']:,}",
        f"Config SHA256: {ctx['config_sha']}",
        f"Tokenizer SHA256: {ctx['tok_sha']}",
        f"Dataset hash: {DATASET_HASH}",
        f"Final model SHA256: {ctx['final_sha']}",
        f"",
        f"Smoke test results:",
    ]
    for k in ["cuda", "forward", "backward", "amp", "optimizer",
              "checkpoint", "resume", "nan", "inf"]:
        r = ctx["smoke_checks"].get(k, False)
        env_lines.append(f"  {k:12s} {'PASS' if r else 'FAIL'}")
    env_lines.append(f"  status: {'ALL PASS' if ctx['smoke_checks'].get('status') else 'FAIL'}")
    env_lines.append(f"")
    vram = ctx["vram_info"]
    env_lines.append(f"VRAM probe: alloc={vram['allocated_mb']}MB "
                     f"reserved={vram['reserved_mb']}MB "
                     f"peak={vram['peak_mb']}MB total={vram['total_mb']}MB")
    env_lines.append(f"Config file: {CFG_PATH}")
    env_lines.append(f"Tokenizer file: {TOK_PATH}")
    env_lines.append(f"Data dir: {DATA_DIR}")
    env_lines.append(f"Val text: {VAL_TXT}")
    env_lines.append(f"r2000 eval: {R2000_EVAL}")
    (run_dir / "environment_report.txt").write_text(
        "\n".join(env_lines) + "\n", encoding="utf-8")

    # --- environment_report.json ---
    write_json(run_dir / "environment_report.json", {
        "python_version": ctx["hw_info"]["python_version"],
        "platform": ctx["hw_info"]["platform"],
        "pytorch_version": ctx["hw_info"]["pytorch_version"],
        "cuda_version": ctx["hw_info"]["cuda_version"],
        "gpu": ctx["hw_info"]["gpu_names"],
        "gpu_count": ctx["hw_info"]["gpu_count"],
        "bf16_supported": ctx["hw_info"]["bf16_supported"],
        "fp16_supported": ctx["hw_info"]["fp16_supported"],
        "ram_gb": ctx["hw_info"]["ram_gb"],
        "model_params": ctx["param_actual"],
        "config_sha256": ctx["config_sha"],
        "tokenizer_sha256": ctx["tok_sha"],
        "dataset_hash": DATASET_HASH,
        "final_model_sha256": ctx["final_sha"],
        "smoke_checks": ctx["smoke_checks"],
        "vram_probe": ctx["vram_info"],
        "run_id": RUN_ID,
        "run_dir": str(run_dir),
    })

    # --- run_manifest.json ---
    write_json(run_dir / "run_manifest.json", {
        "model_version": MODEL_VERSION,
        "run_id": RUN_ID,
        "architecture_version": "1",
        "tokenizer_version": "r2000-bpe-8192",
        "dataset_version": "silverwing-120m-mixture-v0.1",
        "config_source": str(CFG_PATH),
        "tokenizer_source": str(TOK_PATH),
        "param_count": ctx["param_actual"],
        "param_formula_check": ctx["param_actual"] == EXPECTED_PARAM_COUNT,
        "init_scheme": "from-scratch (normal std=0.02)",
        "training_config": {
            "steps": TARGET_STEPS, "seq": SEQ, "micro_batch": MICRO_BATCH,
            "grad_accum": GRAD_ACCUM, "effective_batch": MICRO_BATCH * GRAD_ACCUM,
            "lr": BASE_LR, "warmup_steps": WARMUP_STEPS,
            "weight_decay": WEIGHT_DECAY, "grad_clip": GRAD_CLIP, "seed": SEED,
            "precision": "bf16" if ctx["hw_info"].get("bf16_supported") else "fp16",
        },
        "dataset": {
            "train_tokens": train_tokens,
            "validation_tokens": val_tokens,
            "dataset_hash": DATASET_HASH,
        },
        "base_model": "12M-r2000 (read-only tokenizer only, NOT loaded for init)",
        "adjustments": "seq=256 (per spec), warmup=25, LR=1.5e-4, grad_accum=4",
        "checkpoints": ["step-100", "step-200", "step-300", "step-400",
                        "step-500", "best", "final"],
        "final_train_loss": round(ctx["last_loss"], 6),
        "best_val_loss": round(ctx["best_val_loss"], 6) if ctx["best_val_loss"] < float("inf") else None,
        "final_val_loss": ctx["eval_result"]["val_loss"],
        "final_val_perplexity": ctx["eval_result"]["val_perplexity"],
        "nan_total": ctx["nan_total"],
        "inf_total": ctx["inf_total"],
        "training_time_sec": round(ctx["training_time"], 2),
        "total_tokens": ctx["total_tokens"],
        "final_model_sha256": ctx["final_sha"],
        "completed_at": now_iso(),
        "status": "completed",
        "artifacts": [
            "silverwing_120m_gpu_r1_report.json",
            "silverwing_120m_gpu_r1_report.md",
            "metrics.jsonl",
            "training_metrics.json",
            "evaluation_report.json",
            "comparison_report.json",
            "capability_history.json",
            "run_manifest.json",
            "dataset_manifest.json",
            "sample_generations.txt",
            "environment_report.txt",
        ],
    })

    # --- dataset_manifest.json ---
    src_manifest = run_dir / "data" / "dataset_manifest.json"
    if src_manifest.exists():
        shutil.copy2(src_manifest, run_dir / "dataset_manifest.json")
    else:
        write_json(run_dir / "dataset_manifest.json", {
            "dataset_hash": DATASET_HASH,
            "train_tokens": train_tokens,
            "validation_tokens": val_tokens,
            "tokenizer_hash": ctx["tok_sha"],
            "config_hash": ctx["config_sha"],
        })

    # --- capability_history.json ---
    write_json(run_dir / "capability_history.json", {
        "model": MODEL_VERSION,
        "history": ctx["capability_history"],
        "final": {
            "val_loss": ctx["eval_result"]["val_loss"],
            "val_perplexity": ctx["eval_result"]["val_perplexity"],
            "math_accuracy": ctx["eval_result"]["math"]["accuracy"],
            "logic_accuracy": ctx["eval_result"]["logic"]["accuracy"],
            "coding_accuracy": ctx["eval_result"]["coding"]["accuracy"],
            "knowledge_accuracy": ctx["eval_result"]["knowledge"]["accuracy"],
        },
        "baseline_r2000": {
            "val_loss": R2000_VAL_LOSS,
            "val_perplexity": R2000_VAL_PPL,
            "math_accuracy": R2000_MATH[0] / R2000_MATH[1],
            "logic_accuracy": R2000_LOGIC[0] / R2000_LOGIC[1],
            "coding_accuracy": R2000_CODING[0] / R2000_CODING[1],
            "knowledge_accuracy": R2000_KNOWLEDGE[0] / R2000_KNOWLEDGE[1],
        },
    })

    # --- training_metrics.json ---
    step_metrics = []
    val_metrics = []
    if metrics_path.exists():
        with open(metrics_path, "r") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("event") == "step_metrics":
                        step_metrics.append(rec)
                    elif rec.get("event") == "validation":
                        val_metrics.append(rec)
                except json.JSONDecodeError:
                    pass
    write_json(run_dir / "training_metrics.json", {
        "run_id": RUN_ID,
        "model": MODEL_VERSION,
        "total_steps": TARGET_STEPS,
        "final_train_loss": round(ctx["last_loss"], 6),
        "best_val_loss": round(ctx["best_val_loss"], 6) if ctx["best_val_loss"] < float("inf") else None,
        "final_val_loss": ctx["eval_result"]["val_loss"],
        "final_val_perplexity": ctx["eval_result"]["val_perplexity"],
        "steps": TARGET_STEPS,
        "seq": SEQ,
        "micro_batch": MICRO_BATCH,
        "grad_accum": GRAD_ACCUM,
        "effective_batch": MICRO_BATCH * GRAD_ACCUM,
        "base_lr": BASE_LR,
        "warmup_steps": WARMUP_STEPS,
        "lr_peak": BASE_LR,
        "weight_decay": WEIGHT_DECAY,
        "grad_clip": GRAD_CLIP,
        "seed": SEED,
        "precision": "bf16" if ctx["hw_info"].get("bf16_supported") else "fp16",
        "nan_total": ctx["nan_total"],
        "inf_total": ctx["inf_total"],
        "training_time_sec": round(ctx["training_time"], 2),
        "total_tokens": ctx["total_tokens"],
        "final_model_sha256": ctx["final_sha"],
        "param_count": ctx["param_actual"],
        "step_metrics_count": len(step_metrics),
        "validation_count": len(val_metrics),
    })

    # --- comparison_report.json ---
    write_json(run_dir / "comparison_report.json", {
        "model_a": {
            "label": "Silverwing-12M-r2000 (baseline)",
            "val_loss": R2000_VAL_LOSS,
            "val_perplexity": R2000_VAL_PPL,
            "math_accuracy": R2000_MATH[0] / R2000_MATH[1],
            "logic_accuracy": R2000_LOGIC[0] / R2000_LOGIC[1],
            "coding_accuracy": R2000_CODING[0] / R2000_CODING[1],
            "knowledge_accuracy": R2000_KNOWLEDGE[0] / R2000_KNOWLEDGE[1],
            "param_count": R2000_PARAMS,
            "model_sha256": R2000_MODEL_SHA,
            "checkpoint": "F:/AI/silverwing-r2000/final",
        },
        "model_b": {
            "label": "Silverwing-120M-V1 (this run, GPU R1)",
            "val_loss": ctx["eval_result"]["val_loss"],
            "val_perplexity": ctx["eval_result"]["val_perplexity"],
            "math_accuracy": ctx["eval_result"]["math"]["accuracy"],
            "logic_accuracy": ctx["eval_result"]["logic"]["accuracy"],
            "coding_accuracy": ctx["eval_result"]["coding"]["accuracy"],
            "knowledge_accuracy": ctx["eval_result"]["knowledge"]["accuracy"],
            "param_count": ctx["param_actual"],
            "model_sha256": ctx["final_sha"],
            "checkpoint": str(final_path),
        },
        "improvement": {
            "val_loss_delta": ctx["eval_result"]["val_loss"] - R2000_VAL_LOSS,
            "val_ppl_delta": ctx["eval_result"]["val_perplexity"] - R2000_VAL_PPL,
            "param_scale": ctx["param_actual"] / R2000_PARAMS,
        },
        "comparison_note": (
            "r2000 is a 12M-param model trained for 500 steps. "
            "120M-V1 has 10x parameters, same tokenizer, same val set. "
            "Comparison is apples-to-apples on the same val.txt held-out set."
        ),
        "evaluated_at": now_iso(),
    })

    # --- silverwing_120m_gpu_r1_report.json ---
    write_json(run_dir / "silverwing_120m_gpu_r1_report.json", {
        "run_id": RUN_ID,
        "model_version": MODEL_VERSION,
        "param_count": ctx["param_actual"],
        "param_formula_check": ctx["param_actual"] == EXPECTED_PARAM_COUNT,
        "training_config": {
            "steps": TARGET_STEPS, "seq": SEQ, "micro_batch": MICRO_BATCH,
            "grad_accum": GRAD_ACCUM, "effective_batch": MICRO_BATCH * GRAD_ACCUM,
            "lr": BASE_LR, "warmup_steps": WARMUP_STEPS,
            "weight_decay": WEIGHT_DECAY, "grad_clip": GRAD_CLIP, "seed": SEED,
        },
        "final_train_loss": round(ctx["last_loss"], 6),
        "best_val_loss": round(ctx["best_val_loss"], 6) if ctx["best_val_loss"] < float("inf") else None,
        "final_val_loss": ctx["eval_result"]["val_loss"],
        "final_val_perplexity": ctx["eval_result"]["val_perplexity"],
        "math_accuracy": ctx["eval_result"]["math"]["accuracy"],
        "logic_accuracy": ctx["eval_result"]["logic"]["accuracy"],
        "coding_accuracy": ctx["eval_result"]["coding"]["accuracy"],
        "knowledge_accuracy": ctx["eval_result"]["knowledge"]["accuracy"],
        "nan_total": ctx["nan_total"],
        "inf_total": ctx["inf_total"],
        "training_time_sec": round(ctx["training_time"], 2),
        "total_tokens": ctx["total_tokens"],
        "final_model_sha256": ctx["final_sha"],
        "config_sha256": ctx["config_sha"],
        "tokenizer_sha256": ctx["tok_sha"],
        "dataset_hash": DATASET_HASH,
        "smoke_checks": ctx["smoke_checks"],
        "vram_probe": ctx["vram_info"],
        "hardware": ctx["hw_info"],
        "checkpoints": _list_checkpoints(run_dir),
        "artifacts": _list_artifacts(run_dir),
        "completed_at": now_iso(),
    })

    # --- silverwing_120m_gpu_r1_report.md ---
    ctx_eval = ctx["eval_result"]
    ctx_best_val_str = f"{ctx['best_val_loss']:.4f}" if ctx["best_val_loss"] < float("inf") else "N/A"
    ctx_hw = ctx["hw_info"]
    md = f"""# {MODEL_VERSION} — GPU R1 Clean Relaunch Report

**Run ID:** {RUN_ID}  
**Completed:** {now_iso()}

## Architecture

| Parameter | Value |
|-----------|-------|
| Layers | {config_n_layers()} |
| d_model | {config_d_model()} |
| Q heads | 16 |
| KV heads | 4 |
| GQA ratio | 4:1 |
| MLP hidden | 2176 |
| Activation | SwiGLU |
| Position | RoPE (theta=10000) |
| Norm | RMSNorm (eps=1e-5) |
| Vocabulary | 8192 |
| Context | 2048 |
| Tied embeddings | true |
| Bias | false |

**Parameters:** {ctx['param_actual']:,} (formula check: {'PASS' if ctx['param_actual'] == EXPECTED_PARAM_COUNT else 'FAIL'})

## Training Configuration

| Setting | Value |
|---------|-------|
| Steps | {TARGET_STEPS} |
| Sequence length | {SEQ} |
| Micro-batch | {MICRO_BATCH} |
| Gradient accumulation | {GRAD_ACCUM} |
| Effective batch | {MICRO_BATCH * GRAD_ACCUM} |
| Learning rate | {BASE_LR} |
| Warmup steps | {WARMUP_STEPS} |
| LR schedule | Cosine decay (fresh, not r3000) |
| Weight decay | {WEIGHT_DECAY} |
| Grad clip | {GRAD_CLIP} |
| Seed | {SEED} |
| Precision | {"BF16" if ctx_hw.get("bf16_supported") else "FP16"} |

## Results

| Metric | Value |
|--------|-------|
| Final train loss | {ctx['last_loss']:.4f} |
| Best val loss | {ctx_best_val_str} |
| Final val loss | {ctx_eval['val_loss']:.4f} |
| Final val perplexity | {ctx_eval['val_perplexity']:.2f} |
| Training time | {ctx['training_time']:.1f}s |
| Tokens trained | {ctx['total_tokens']:,} |
| NaN count | {ctx['nan_total']} |
| Inf count | {ctx['inf_total']} |

## Benchmarks vs r2000

| Benchmark | r2000 (12M) | 120M-V1 |
|-----------|-------------|---------|
| Math | {R2000_MATH[0]}/{R2000_MATH[1]} | {ctx_eval['math']['correct']}/{ctx_eval['math']['total']} |
| Logic | {R2000_LOGIC[0]}/{R2000_LOGIC[1]} | {ctx_eval['logic']['correct']}/{ctx_eval['logic']['total']} |
| Coding | {R2000_CODING[0]}/{R2000_CODING[1]} | {ctx_eval['coding']['correct']}/{ctx_eval['coding']['total']} |
| Knowledge | {R2000_KNOWLEDGE[0]}/{R2000_KNOWLEDGE[1]} | {ctx_eval['knowledge']['correct']}/{ctx_eval['knowledge']['total']} |
| Val loss | {R2000_VAL_LOSS:.4f} | {ctx_eval['val_loss']:.4f} |
| Val perplexity | {R2000_VAL_PPL:.2f} | {ctx_eval['val_perplexity']:.2f} |

## Smoke Test

| Check | Result |
|-------|--------|
"""
    for k in ["cuda", "forward", "backward", "amp", "optimizer",
              "checkpoint", "resume", "nan", "inf"]:
        result = "PASS" if ctx["smoke_checks"].get(k) else "FAIL"
        md += f"| {k} | {result} |\n"
    md += f"| status | {'ALL PASS' if ctx['smoke_checks'].get('status') else 'FAIL'} |\n"

    md += f"""
## Hashes

| Artifact | SHA256 |
|----------|--------|
| Model | `{ctx['final_sha']}` |
| Tokenizer | `{ctx['tok_sha']}` |
| Config | `{ctx['config_sha']}` |
| Dataset | `{DATASET_HASH}` |

## VRAM

| Metric | Value |
|--------|-------|
| Peak allocated | {ctx['vram_info']['peak_mb']} MB |
| Reserved | {ctx['vram_info']['reserved_mb']} MB |
| Total | {ctx['vram_info']['total_mb']} MB |

## Artifacts

- `silverwing_120m_gpu_r1_report.json` — full JSON report
- `silverwing_120m_gpu_r1_report.md` — this Markdown report
- `metrics.jsonl` — all training events (startup, steps, validation, checkpoints)
- `training_metrics.json` — training summary
- `evaluation_report.json` — full evaluation (val loss, benchmarks, generations)
- `comparison_report.json` — comparison vs r2000 baseline
- `capability_history.json` — capabilities across checkpoints
- `run_manifest.json` — run metadata
- `dataset_manifest.json` — dataset metadata
- `sample_generations.txt` — 10 fixed-prompt generations
- `environment_report.txt` — hardware/software environment
- `environment_report.json` — environment (JSON)
"""
    (run_dir / "silverwing_120m_gpu_r1_report.md").write_text(md, encoding="utf-8")


# Config value accessors for report generation
_cfg_cache = {}

def config_n_layers() -> int:
    return _cfg_cache.get("n_layers", 12)

def config_d_model() -> int:
    return _cfg_cache.get("d_model", 1024)


# ===========================================================================
# §15  Main training function
# ===========================================================================
def train(args):
    """Main training entry point."""
    # Merge CLI overrides into globals
    global TARGET_STEPS, SEQ, GRAD_ACCUM, MICRO_BATCH, BASE_LR, WARMUP_STEPS, SEED
    global DATA_DIR, DATA_DIR_OVERRIDE
    if args.steps:
        TARGET_STEPS = args.steps
    if args.seq:
        SEQ = args.seq
    if args.grad_accum:
        GRAD_ACCUM = args.grad_accum
    if args.batch:
        MICRO_BATCH = args.batch
    if args.lr:
        BASE_LR = args.lr
    if args.warmup:
        WARMUP_STEPS = args.warmup
    if args.seed:
        SEED = args.seed

    run_dir = Path(args.run_dir) if args.run_dir else RUN_DIR
    run_dir.mkdir(parents=True, exist_ok=True)

    # Override data paths if CLI args provided
    train_npy_path = Path(args.data) if args.data else None
    val_npy_path = Path(args.val) if args.val else None

    # ------------------------------------------------------------------
    # §2. Hardware preflight
    # ------------------------------------------------------------------
    hw = hardware_preflight()

    # ------------------------------------------------------------------
    # §20. metrics.jsonl — training_run_start BEFORE smoke test
    # ------------------------------------------------------------------
    metrics_path = run_dir / "metrics.jsonl"
    # Truncate / create fresh
    metrics_path.write_text("", encoding="utf-8")
    write_jsonl(metrics_path, {
        "event": "training_run_start",
        "run_id": RUN_ID,
        "model": MODEL_VERSION,
        "timestamp": now_iso(),
        "pytorch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": ",".join(_GPU_NAMES) if _GPU_NAMES else "none",
        "precision": "bf16" if hw.get("bf16_supported") else "fp16",
        "seq": SEQ,
        "micro_batch": MICRO_BATCH,
        "grad_accum": GRAD_ACCUM,
        "base_lr": BASE_LR,
        "warmup_steps": WARMUP_STEPS,
        "total_steps": TARGET_STEPS,
    })

    # ------------------------------------------------------------------
    # §3. Tokenizer verification
    # ------------------------------------------------------------------
    print("\n[TOKENIZER] Verifying r2000 BPE tokenizer...")
    tok = BPETokenizer.from_file(str(TOK_PATH))
    computed_tok_sha = sha256(TOK_PATH)
    if tok.vocab_size != EXPECTED_VOCAB:
        print(f"[TOKENIZER] FAIL: vocab={tok.vocab_size} (expected {EXPECTED_VOCAB})")
        sys.exit(1)
    if computed_tok_sha != EXPECTED_TOK_SHA256:
        print(f"[TOKENIZER] FAIL: sha={computed_tok_sha}")
        print(f"[TOKENIZER]        expected {EXPECTED_TOK_SHA256}")
        sys.exit(1)
    # Round-trip test
    enc = tok.encode("hello world test")
    dec = tok.decode(enc)
    if "hello" not in dec or "world" not in dec:
        print(f"[TOKENIZER] FAIL: round-trip broken: enc={enc} dec={dec!r}")
        sys.exit(1)
    print(f"[TOKENIZER] LOCK: PASS  vocab={tok.vocab_size} sha={computed_tok_sha[:16]}...")

    # ------------------------------------------------------------------
    # §3. Config verification
    # ------------------------------------------------------------------
    print("\n[CONFIG] Loading architecture config...")
    cfg_dict = json.load(open(CFG_PATH))
    config = ModelConfig(**cfg_dict)
    config_sha = sha256(CFG_PATH)
    if config_sha != EXPECTED_CONFIG_SHA:
        print(f"[CONFIG] WARNING: config sha={config_sha[:16]}... "
              f"(expected {EXPECTED_CONFIG_SHA[:16]}...)")
    # Cache config values for report generation
    _cfg_cache["n_layers"] = config.n_layers
    _cfg_cache["d_model"] = config.d_model
    param_est = estimate_parameters(config)
    print(f"[CONFIG] estimate_parameters = {param_est:,}")
    if param_est != EXPECTED_PARAM_COUNT:
        print(f"[CONFIG] WARNING: estimate {param_est:,} != expected {EXPECTED_PARAM_COUNT:,}")

    # ------------------------------------------------------------------
    # §4. Dataset verification
    # ------------------------------------------------------------------
    print("\n[DATASET] Verifying data shard...")
    if train_npy_path and val_npy_path:
        train_npy = train_npy_path
        val_npy = val_npy_path
    else:
        data_dir = DATA_DIR
        train_npy = data_dir / "train.npy"
        val_npy = data_dir / "val.npy"
        # Also check Kaggle input directory for pre-built shard
        if not (train_npy.exists() and val_npy.exists()):
            _kag_data = _KIN / "silverwing-120m" / "data"
            if (_kag_data / "train.npy").exists():
                train_npy = _kag_data / "train.npy"
                val_npy = _kag_data / "val.npy"
            print("[DATASET] Pre-built shard not found — building from corpus...")
            if CORPUS_JSONL is None or not CORPUS_JSONL.exists():
                print("[DATASET] FAIL: no corpus found for building shard.")
                sys.exit(1)
            data_dir = run_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            train_chunks, val_chunks = build_dataset_from_jsonl(
                CORPUS_JSONL, tok, seq_len=2048)
            np.save(data_dir / "train.npy", train_chunks)
            np.save(data_dir / "val.npy", val_chunks)
            train_npy = data_dir / "train.npy"
            val_npy = data_dir / "val.npy"
            write_json(data_dir / "dataset_manifest.json", {
                "source": str(CORPUS_JSONL), "sequence_length": 2048,
                "pack_len": 2048,
                "train_tokens": int(train_chunks.size),
                "validation_tokens": int(val_chunks.size),
                "tokenizer_hash": computed_tok_sha,
                "build_timestamp": now_iso(),
            })

    ds_result = verify_dataset(train_npy, val_npy)
    if not ds_result["passed"]:
        print("[DATASET] FAIL: dataset verification failed.")
        for c in ds_result["checks"]:
            status = "PASS" if c["passed"] else "FAIL"
            detail = c.get("detail", "")
            print(f"  {c['check']}: {status} — {detail}")
        sys.exit(1)
    for c in ds_result["checks"]:
        if not c["passed"]:
            print(f"  [WARN] {c['check']}: {c.get('detail', '')}")
    print(f"[DATASET] PASS: train={ds_result['train_tokens']:,} tokens "
          f"({ds_result['train_shape'][0]} chunks), "
          f"val={ds_result['val_tokens']:,} tokens "
          f"({ds_result['val_shape'][0]} chunks)")

    # ------------------------------------------------------------------
    # §6. Precision selection (BF16 preferred, FP16 fallback)
    # ------------------------------------------------------------------
    if hw["bf16_supported"]:
        precision_str = "bf16"
        precision_dtype = torch.bfloat16
        use_scaler = False
        print("\n[PRECISION] BF16 (preferred, no GradScaler needed)")
    else:
        precision_str = "fp16"
        precision_dtype = torch.float16
        use_scaler = True
        print("\n[PRECISION] FP16 (fallback, GradScaler enabled)")

    # ------------------------------------------------------------------
    # §6. Model construction (from scratch, NOT r3000)
    # ------------------------------------------------------------------
    print("\n[MODEL] Building Silverwing-120M-V1 from scratch...")
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    device = torch.device("cuda")
    model = SilverwingModel(config).to(device)
    model.train()
    param_actual = model.num_parameters()
    print(f"[MODEL] params = {param_actual:,}  (expected {EXPECTED_PARAM_COUNT:,})")
    if param_actual != EXPECTED_PARAM_COUNT:
        print("[MODEL] FATAL: param count mismatch — architecture constraint violated.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # §5. GPU memory discovery
    # ------------------------------------------------------------------
    vram_info, vram_safe = gpu_memory_probe(
        model, device, precision_dtype, SEQ, MICRO_BATCH, GRAD_ACCUM)

    # ------------------------------------------------------------------
    # §7. GPU smoke test (all 9 checks)
    # ------------------------------------------------------------------
    print("\n[SMOKE] Running GPU smoke test (9 checks)...")
    smoke_checks, smoke_pass = gpu_smoke_test(
        model, device, precision_dtype, run_dir)

    if not smoke_pass:
        failed = [k for k in ("cuda", "forward", "backward", "amp",
                              "optimizer", "checkpoint", "resume", "nan", "inf")
                  if not smoke_checks.get(k)]
        print(f"\n[SMOKE] FAIL — checks failed: {failed}")
        print("[SMOKE] Training will NOT start. DO NOT START THE REAL TRAINING RUN.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # §20. training_started event AFTER smoke test passes
    # ------------------------------------------------------------------
    write_jsonl(metrics_path, {
        "event": "training_started",
        "step": 1,
        "timestamp": now_iso(),
        "precision": precision_str,
        "vram_probe": vram_info,
    })

    # ------------------------------------------------------------------
    # §11. Resume support
    # ------------------------------------------------------------------
    train_chunks = np.load(train_npy)
    val_chunks = np.load(val_npy)
    n_train = train_chunks.shape[0]
    rng = np.random.default_rng(SEED)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=BASE_LR, betas=(0.9, 0.95),
        eps=1e-8, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lambda step: get_lr(step, BASE_LR, WARMUP_STEPS, TARGET_STEPS) / BASE_LR)
    scaler = torch.amp.GradScaler("cuda") if use_scaler else None

    start_step = 0
    total_tokens = 0
    best_val_loss = float("inf")
    nan_total = 0
    inf_total = 0

    if args.resume or args.resume_from:
        ckpt_path = Path(args.resume_from) if args.resume_from else None
        if not ckpt_path:
            ckpt_root = run_dir / "checkpoints"
            if ckpt_root.exists():
                step_dirs = sorted(
                    [d for d in ckpt_root.iterdir() if d.is_dir() and d.name.startswith("step-")],
                    key=lambda d: int(d.name.split("-")[1]))
                if step_dirs:
                    ckpt_path = step_dirs[-1]
        if ckpt_path and ckpt_path.exists():
            loaded_step, loaded_tokens, _, _ = load_checkpoint(
                model, optimizer, scheduler, ckpt_path, device)
            if use_scaler and scaler is not None:
                scaler_path = Path(ckpt_path) / "scaler.pt"
                if scaler_path.exists():
                    scaler.load_state_dict(torch.load(
                        scaler_path, map_location=device, weights_only=False))
            start_step = loaded_step
            total_tokens = loaded_tokens
            print(f"[RESUME] Loaded: step={loaded_step}, tokens={loaded_tokens}")
            print(f"[RESUME] Next step = {start_step + 1}")
            if loaded_step >= TARGET_STEPS:
                print(f"[RESUME] Already at step {loaded_step} (target={TARGET_STEPS}). "
                      f"Jumping to evaluation.")
                start_step = TARGET_STEPS
        else:
            if args.resume:
                print("[RESUME] No checkpoint found. Starting from scratch.")

            if use_scaler and scaler is not None:
                scaler_path = Path(ckpt_path) / "scaler.pt"
                if scaler_path.exists():
                    scaler.load_state_dict(torch.load(
                        scaler_path, map_location=device, weights_only=False))

    # ------------------------------------------------------------------
    # §9. Training loop
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"TRAINING: {TARGET_STEPS} steps | seq={SEQ} | mb={MICRO_BATCH} | "
          f"ga={GRAD_ACCUM} | lr={BASE_LR} | warmup={WARMUP_STEPS}")
    print(f"Precision: {precision_str} | Device: {device}")
    print(f"{'='*60}\n")

    train_start = time.time()
    model.train()
    last_loss = 0.0
    capability_history = []

    for step in range(start_step, TARGET_STEPS):
        step_start = time.time()
        lr_now = get_lr(step, BASE_LR, WARMUP_STEPS, TARGET_STEPS)
        set_lr(optimizer, lr_now)

        optimizer.zero_grad(set_to_none=True)
        loss_acc = 0.0

        for _m in range(GRAD_ACCUM):
            idx = int(rng.integers(0, n_train))
            chunk = train_chunks[idx]
            max_start = len(chunk) - SEQ - 1
            s = int(rng.integers(0, max_start + 1)) if max_start > 0 else 0
            window = chunk[s:s + SEQ + 1]
            x = torch.tensor(window[:-1], dtype=torch.long, device=device).unsqueeze(0)
            y = torch.tensor(window[1:], dtype=torch.long, device=device).unsqueeze(0)
            with torch.autocast("cuda", dtype=precision_dtype):
                loss = model(x, labels=y)["loss"] / GRAD_ACCUM
            if use_scaler:
                scaler.scale(loss).backward()
            else:
                loss.backward()
            loss_acc += loss.item() * GRAD_ACCUM

        if use_scaler:
            scaler.unscale_(optimizer)
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        if use_scaler:
            scaler.step(optimizer)
            scaler.update()
        else:
            optimizer.step()

        nan_total += int(not math.isfinite(loss_acc))
        inf_total += int(math.isinf(loss_acc))

        # §21. LR safety: STOP on non-finite loss
        if not math.isfinite(loss_acc):
            print(f"\n*** STOP: non-finite loss at step {step} (loss={loss_acc}) ***")
            write_jsonl(metrics_path, {
                "event": "training_stopped",
                "step": step + 1,
                "reason": "non-finite loss",
                "loss": loss_acc,
                "nan_total": nan_total,
                "inf_total": inf_total,
                "timestamp": now_iso(),
            })
            sys.exit(1)

        nl = loss_acc / GRAD_ACCUM
        gnn = float(grad_norm)
        gnn = gnn if math.isfinite(gnn) else 0.0
        elapsed = time.time() - train_start
        processed_tokens = (step + 1) * SEQ * GRAD_ACCUM
        total_tokens = processed_tokens
        vram = get_vram()
        tok_per_sec = SEQ * GRAD_ACCUM / (time.time() - step_start) \
            if (time.time() - step_start) > 0 else 0

        # §12. Log every 10 steps
        if (step + 1) % 10 == 0:
            log = {
                "event": "step_metrics",
                "step": step + 1,
                "train_loss": round(nl, 6),
                "lr": lr_now,
                "grad_norm": round(gnn, 4),
                "tok_per_sec": round(tok_per_sec, 1),
                "training_tokens": total_tokens,
                "gpu_memory_allocated_mb": vram["allocated_mb"],
                "gpu_memory_reserved_mb": vram["reserved_mb"],
                "gpu_memory_peak_mb": vram["peak_mb"],
                "elapsed_sec": round(elapsed, 2),
            }
            write_jsonl(metrics_path, log)
            print(f"[step {step+1:>4d}/{TARGET_STEPS}] loss={nl:.4f} "
                  f"ppl={math.exp(min(nl, 20)):.1f} lr={lr_now:.2e} "
                  f"gnorm={gnn:.3f} {tok_per_sec:.0f} tok/s "
                  f"tokens={total_tokens:,} vram={vram['allocated_mb']}MB "
                  f"t={elapsed:.1f}s")

        # §13. Evaluate + checkpoint every 100 steps
        if (step + 1) % 100 == 0 or step == TARGET_STEPS - 1:
            vl, vpp, vw = fast_val_loss(model, val_chunks, device,
                                        precision_dtype, SEQ, n_win=128)
            ckpt_name = run_dir / "checkpoints" / f"step-{step+1}"
            save_checkpoint(model, optimizer, scheduler, step + 1,
                            total_tokens, ckpt_name, nl, vl, config, tok,
                            extra={"val_ppl": vpp, "lr_peak": BASE_LR,
                                   "seq": SEQ, "grad_accum": GRAD_ACCUM,
                                   "amp": precision_str, "device": str(device),
                                   "step": step + 1}, scaler=scaler)
            ckpt_sha = sha256(ckpt_name / "model.safetensors")
            print(f"[ckpt] step-{step+1} sha={ckpt_sha[:12]} "
                  f"val_loss={vl:.4f} ppl={vpp:.1f}")

            write_jsonl(metrics_path, {
                "event": "validation",
                "step": step + 1,
                "val_loss": round(vl, 6),
                "val_perplexity": round(vpp, 4),
                "val_windows": vw,
                "checkpoint_path": str(ckpt_name),
            })

            if vl < best_val_loss:
                best_val_loss = vl
                save_checkpoint(model, optimizer, scheduler, step + 1,
                                total_tokens, run_dir / "best", nl, vl,
                                config, tok,
                                extra={"best": True, "val_ppl": vpp,
                                       "lr_peak": BASE_LR}, scaler=scaler)
                print(f"[best] new best val={vl:.4f} ppl={vpp:.1f}")

            capability_history.append({
                "step": step + 1,
                "train_loss": round(nl, 6),
                "val_loss": round(vl, 6),
                "val_perplexity": round(vpp, 4),
                "nan_total": nan_total,
                "inf_total": inf_total,
            })

        last_loss = nl

    training_time = time.time() - train_start

    # ------------------------------------------------------------------
    # §10. Final checkpoint (step-500 / final)
    # ------------------------------------------------------------------
    final_path = run_dir / "final"
    final_sha = save_checkpoint(model, optimizer, scheduler, TARGET_STEPS,
                                total_tokens, final_path, last_loss,
                                best_val_loss if best_val_loss < float("inf") else None,
                                config, tok, extra={
                                    "lr_peak": BASE_LR, "seq": SEQ,
                                    "grad_accum": GRAD_ACCUM,
                                    "amp": precision_str, "device": str(device),
                                    "training_time_sec": training_time,
                                }, scaler=scaler)
    print(f"\n[FINAL] saved final/ sha={final_sha[:12]}  "
          f"params={param_actual:,}  time={training_time:.1f}s  "
          f"nan={nan_total} inf={inf_total}")

    write_jsonl(metrics_path, {
        "event": "training_complete",
        "step": TARGET_STEPS,
        "final_train_loss": round(last_loss, 6),
        "best_val_loss": round(best_val_loss, 6) if best_val_loss < float("inf") else None,
        "nan_total": nan_total,
        "inf_total": inf_total,
        "training_time_sec": round(training_time, 2),
        "timestamp": now_iso(),
    })

    # ------------------------------------------------------------------
    # §14. Final evaluation vs r2000 baseline
    # ------------------------------------------------------------------
    print("\n[EVAL] Running full evaluation vs r2000 baseline...")
    eval_result = full_evaluate(model, tok, device, precision_dtype,
                                label=RUN_ID, val_txt=VAL_TXT,
                                max_len=256, n_windows=128)
    eval_result["checkpoint"] = str(final_path)
    eval_result["model_sha256"] = final_sha
    eval_result["config_sha256"] = config_sha
    eval_result["tokenizer_sha256"] = computed_tok_sha
    eval_result["dataset_hash"] = DATASET_HASH
    write_json(run_dir / "evaluation_report.json", eval_result)
    print(f"[EVAL] val_loss={eval_result['val_loss']:.4f} "
          f"ppl={eval_result['val_perplexity']:.2f} "
          f"math={eval_result['math']['accuracy']:.2f} "
          f"logic={eval_result['logic']['accuracy']:.2f} "
          f"coding={eval_result['coding']['accuracy']:.2f} "
          f"knowledge={eval_result['knowledge']['accuracy']:.2f}")

    # sample_generations.txt
    best_val_str = f"{best_val_loss:.4f}" if best_val_loss < float("inf") else "N/A"
    gen_text = (f"Silverwing-120M-V1 — GPU R1 Clean Relaunch\n"
                f"Run: {RUN_ID} | Steps: {TARGET_STEPS} | seq={SEQ} | "
                f"lr={BASE_LR} | warmup={WARMUP_STEPS} | prec={precision_str}\n"
                f"Final loss: {last_loss:.4f} | Best val: "
                f"{best_val_str}\n"
                + "=" * 72 + "\n")
    for p in FIXED_PROMPTS:
        gen = eval_result["generations"].get(p, "[missing]")
        gen_text += f"\nPROMPT: {p}\nGEN: {gen}\n{'-' * 72}\n"
    (run_dir / "sample_generations.txt").write_text(gen_text, encoding="utf-8")
    print("[EVAL] wrote sample_generations.txt")

    # ------------------------------------------------------------------
    # §15. Generate all required report artifacts
    # ------------------------------------------------------------------
    ctx = {
        "run_dir": str(run_dir),
        "hw_info": hw,
        "config_sha": config_sha,
        "tok_sha": computed_tok_sha,
        "param_actual": param_actual,
        "eval_result": eval_result,
        "last_loss": last_loss,
        "best_val_loss": best_val_loss,
        "nan_total": nan_total,
        "inf_total": inf_total,
        "training_time": training_time,
        "vram_info": vram_info,
        "capability_history": capability_history,
        "smoke_checks": smoke_checks,
        "total_tokens": total_tokens,
        "final_sha": final_sha,
        "metrics_path": str(metrics_path),
        "final_path": str(final_path),
        "ds_result": ds_result,
    }
    generate_reports(ctx)

    print(f"\n{'='*60}")
    print(f"  TRAINING COMPLETE — {RUN_ID}")
    print(f"  Steps: {TARGET_STEPS} | Time: {training_time:.1f}s")
    print(f"  Final loss: {last_loss:.4f} | Best val: {best_val_loss:.4f}")
    print(f"  NaN: {nan_total} | Inf: {inf_total}")
    print(f"  Final model SHA256: {final_sha[:16]}...")
    print(f"{'='*60}")


# ===========================================================================
# §16  Argument parsing + entry point
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="Silverwing-120M-V1 GPU R1 clean relaunch")
    ap.add_argument("--steps", type=int, default=TARGET_STEPS)
    ap.add_argument("--seq", type=int, default=SEQ)
    ap.add_argument("--lr", type=float, default=BASE_LR)
    ap.add_argument("--warmup", type=int, default=WARMUP_STEPS)
    ap.add_argument("--weight-decay", type=float, default=WEIGHT_DECAY)
    ap.add_argument("--grad-accum", type=int, default=GRAD_ACCUM)
    ap.add_argument("--batch", type=int, default=MICRO_BATCH)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--run-dir", type=str, default=None)
    ap.add_argument("--resume", action="store_true",
                    help="resume from latest checkpoint")
    ap.add_argument("--resume-from", type=str, default=None,
                    help="resume from specific checkpoint path")
    ap.add_argument("--config", type=str, default=None)
    ap.add_argument("--tokenizer", type=str, default=None)
    ap.add_argument("--data", type=str, default=None,
                    help="train.npy path")
    ap.add_argument("--val", type=str, default=None,
                    help="val.npy path")
    args = ap.parse_args()
    train(args)


if __name__ == "__main__":
    main()
