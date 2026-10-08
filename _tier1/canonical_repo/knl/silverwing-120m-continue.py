#!/usr/bin/env python3
"""Phase 2 — Continue-pretrain silverwing-120m-base-v1 (canonical, device-agnostic).

Works on BOTH a local CPU box and a Kaggle GPU kernel. It avoids the two gotchas
in the legacy ``silverwing/kaggle/silverwing_train.py``:

* **Never retrains the tokenizer** — always loads the *served* tokenizer from the
  frozen checkpoint dir. A retrained tokenizer (even vocab=8192) would produce a
  different BPE merge table and silently misalign the 120M embedding table.
* **Never downscales to 12M** — always builds the architecture from the frozen
  ``config.json`` and never switches to a smaller config when on CPU.
* **Correct lineage** — reads ``tokens`` (not ``total_tokens``) from the frozen
  metadata so step/token accounting stays accurate.
* **GPU gate** — on the Kaggle path a CUDA device is required; if
  ``torch.cuda.is_available()`` is False it aborts with a clear message instead
  of silently training a 12M model.

This script NEVER writes to the frozen baseline (read-only ``--resume_from``);
all new checkpoints + metrics go to ``--output_dir``.

KAGGLE quick-start (free T4 kernel, ~3.5 h per 10M-token stage):
    1. Make dataset "silverwing-120m-base"  =  .sw_cache/silverwing-120m-base/r1/*
       (model.safetensors 514 MB, config.json, tokenizer.json, metadata.json)
    2. Make dataset "silverwing-corpus"      =  silverwing/data_pipeline/processed/{train,val}.txt
    3. Kaggle kernel: Python 3 / PyTorch (any) / Accelerator = GPU(T4) / Internet = ON,
       add BOTH datasets.
    4. Run:
       python silverwing/kaggle/silverwing_continue_gpu.py \
         --resume_from /kaggle/input/silverwing-120m-base \
         --data_dir  /kaggle/input/silverwing-corpus \
         --output_dir /kaggle/working/silverwing-continue \
         --steps 5000 --batch_size 1 --grad_accum 8 --lr 5e-5 \
         --warmup_steps 100 --save_steps 500 --eval_steps 250 --log_steps 25
    Outputs (checkpoints/metrics/summary) download from /kaggle/working/silverwing-continue.

LOCAL CPU (smoke / fallback — ~56 tok/s on this box => ~5 h / 1M tokens):
    python silverwing/kaggle/silverwing_continue_gpu.py \
        --resume_from F:\\AI\\.sw_cache\\silverwing-120m-base\\r1 \
        --data_dir  F:\\AI\\Jarvis-super-intelligence-\\silverwing\\data_pipeline\\processed \
        --output_dir F:\\AI\\Jarvis-super-intelligence-\\silverwing\\local_run\\exp_c_continue_120m \
        --steps 30 --seq_len 256 --batch_size 1 --grad_accum 4 --lr 5e-5 --warmup_steps 5 \
        --save_steps 30 --eval_steps 15 --log_steps 5
"""
from __future__ import annotations

import argparse, json, math, os, time, hashlib, sys
from pathlib import Path

import numpy as np
import torch

# ---- INLINED silverwing.training.train (self-contained Kaggle kernel) ----
# Source: Jarvis-super-intelligence-/silverwing/training/train.py
# (only ModelConfig + model + BPETokenizer; training loop below is canonical)
import os

import sys

import json

import math

import time

import hashlib

import argparse

from pathlib import Path

from dataclasses import dataclass, asdict

import torch

@dataclass
class ModelConfig:
    """Silverwing model architecture configuration."""
    vocab_size: int = 16384
    max_position_embeddings: int = 2048
    n_layers: int = 12
    n_heads: int = 12
    n_kv_heads: int = 4       # GQA: 12 query heads / 4 KV heads = 3:1 ratio
    d_model: int = 768
    hidden_size: int = 2560   # SwiGLU intermediate size
    multiple_of: int = 64
    norm_eps: float = 1e-5
    rope_theta: float = 10000.0
    use_bias: bool = False
    tie_word_embeddings: bool = True  # weight tying: LM head shares embedding weights
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
    """Estimate total parameter count for the model."""
    d, h, nh, nkv, hs, nl = (config.d_model, config.d_model,
                              config.n_heads, config.n_kv_heads,
                              config.hidden_size, config.n_layers)
    head_dim = d // nh
    n_groups = nh // nkv
    # Embeddings (tied, so only counted once)
    params = config.vocab_size * d  # embedding
    # Per layer
    # Q: d*d, K: d*(d//n_groups), V: d*(d//n_groups), O: d*d
    # Gate: d*hs, Up: d*hs, Down: hs*d, 2 RMSNorm: 2*d
    layer_params = (d * d + d * (d // n_groups) + d * (d // n_groups) + d * d
                    + d * hs + d * hs + hs * d + 2 * d)
    params += layer_params * nl
    params += d  # final norm
    return params

class RMSNorm(torch.nn.Module):
    """Root Mean Square Layer Normalization."""

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
    """Pre-computed sinusoidal rotary positional embeddings."""

    def __init__(self, dim: int, base: float = 10000.0):
        self.dim = dim
        self.base = base

    def __call__(self, seq_len: int, device: torch.device):
        theta = 1.0 / (self.base ** (
            torch.arange(0, self.dim, 2, dtype=torch.float32, device=device) / self.dim
        ))
        positions = torch.arange(seq_len, dtype=torch.float32, device=device)
        freqs = torch.outer(positions, theta)
        # Build interleaved cos/sin matching pair structure used by rotate_half
        cos = torch.zeros(seq_len, self.dim, device=device, dtype=torch.float32)
        sin = torch.zeros(seq_len, self.dim, device=device, dtype=torch.float32)
        cos[:, 0::2] = torch.cos(freqs)
        cos[:, 1::2] = torch.cos(freqs)
        sin[:, 0::2] = torch.sin(freqs)
        sin[:, 1::2] = torch.sin(freqs)
        return cos, sin

def rotate_half(x: torch.Tensor) -> torch.Tensor:
    """Rotate half the hidden dims for RoPE application."""
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2:]
    return torch.cat((-x2, x1), dim=-1)

def apply_rope(q: torch.Tensor, k: torch.Tensor,
               cos: torch.Tensor, sin: torch.Tensor) -> tuple:
    """Apply rotary positional embeddings to queries and keys."""
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed

class Attention(torch.nn.Module):
    """Grouped-Query Attention (GQA) implementation."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.n_heads = config.n_heads
        self.n_kv_heads = config.n_kv_heads
        self.head_dim = config.head_dim
        self.n_kv_groups = config.n_kv_groups

        self.q_proj = torch.nn.Linear(
            config.d_model, self.n_heads * self.head_dim, bias=config.use_bias
        )
        self.k_proj = torch.nn.Linear(
            config.d_model, self.n_kv_heads * self.head_dim, bias=config.use_bias
        )
        self.v_proj = torch.nn.Linear(
            config.d_model, self.n_kv_heads * self.head_dim, bias=config.use_bias
        )
        self.o_proj = torch.nn.Linear(
            self.n_heads * self.head_dim, config.d_model, bias=config.use_bias
        )
        self.rope = RotaryEmbedding(self.head_dim, config.rope_theta)

    def forward(self, x: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
        B, T, _ = x.shape

        q = self.q_proj(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, T, self.n_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, T, self.n_kv_heads, self.head_dim).transpose(1, 2)

        # Apply RoPE to both Q and K
        cos, sin = self.rope(T, q.device)
        cos = cos.unsqueeze(0).unsqueeze(0).to(q.dtype)
        sin = sin.unsqueeze(0).unsqueeze(0).to(q.dtype)
        q, k = apply_rope(q, k, cos, sin)

        # GQA: repeat KV heads to match number of query heads
        if self.n_kv_groups > 1:
            k = k.repeat_interleave(self.n_kv_groups, dim=1)
            v = v.repeat_interleave(self.n_kv_groups, dim=1)

        # Scaled dot-product attention
        qk = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        if mask is not None:
            qk = qk.masked_fill(mask[:, :, :T, :T] == 0, float("-inf"))
        attn = torch.softmax(qk, dim=-1)
        out = torch.matmul(attn, v)

        out = out.transpose(1, 2).contiguous().view(B, T, -1)
        return self.o_proj(out)

class SwiGLUMLP(torch.nn.Module):
    """SwiGLU activation MLP."""

    def __init__(self, d_model: int, hidden_size: int,
                 multiple_of: int = 64, use_bias: bool = False):
        super().__init__()
        # Align hidden size to multiple_of
        hidden_size = multiple_of * ((hidden_size + multiple_of - 1) // multiple_of)
        self.gate = torch.nn.Linear(d_model, hidden_size, bias=use_bias)
        self.up = torch.nn.Linear(d_model, hidden_size, bias=use_bias)
        self.down = torch.nn.Linear(hidden_size, d_model, bias=use_bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # SwiGLU: gate(x) * SiLU(gate(x)) * up(x) * down
        gate = torch.sigmoid(self.gate(x)) * self.gate(x)
        up = self.up(x)
        return self.down(gate * up)

class TransformerBlock(torch.nn.Module):
    """Pre-norm transformer block with GQA and SwiGLU."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.attention = Attention(config)
        self.mlp = SwiGLUMLP(
            config.d_model, config.hidden_size,
            config.multiple_of, config.use_bias,
        )
        self.ln1 = RMSNorm(config.d_model, config.norm_eps)
        self.ln2 = RMSNorm(config.d_model, config.norm_eps)

    def forward(self, x: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
        x = x + self.attention(self.ln1(x), mask)
        x = x + self.mlp(self.ln2(x))
        return x

class SilverwingModel(torch.nn.Module):
    """Silverwing decoder-only transformer with GQA, RoPE, RMSNorm, SwiGLU."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        self.embed_tokens = torch.nn.Embedding(
            config.vocab_size, config.d_model, config.pad_token_id
        )
        self.layers = torch.nn.ModuleList([
            TransformerBlock(config) for _ in range(config.n_layers)
        ])
        self.norm_f = RMSNorm(config.d_model, config.norm_eps)

        # Language modeling head (tied with embeddings or independent)
        self.lm_head = torch.nn.Linear(
            config.d_model, config.vocab_size, bias=False
        )
        if config.tie_word_embeddings:
            self.lm_head.weight = self.embed_tokens.weight

        self._init_weights()

    def _init_weights(self):
        """Initialize weights with N(0, 0.02)."""
        for name, param in self.named_parameters():
            if param.dim() > 1:
                torch.nn.init.normal_(param, mean=0.0, std=0.02)

    def _make_causal_mask(self, seq_len: int, device: torch.device) -> torch.Tensor:
        """Create a causal attention mask."""
        mask = torch.tril(
            torch.ones(seq_len, seq_len, device=device, dtype=torch.bool)
        )
        return mask.unsqueeze(0).unsqueeze(0)

    def forward(self, input_ids: torch.Tensor,
                labels: torch.Tensor | None = None) -> dict:
        B, T = input_ids.shape

        # Token embeddings scaled by sqrt(d_model)
        x = self.embed_tokens(input_ids) * math.sqrt(self.config.d_model)

        # Causal mask
        mask = self._make_causal_mask(T, input_ids.device)

        # Transformer layers
        for layer in self.layers:
            x = layer(x, mask)

        x = self.norm_f(x)
        logits = self.lm_head(x)

        # Compute loss if labels provided
        loss = None
        if labels is not None:
            shift_logits = logits[:, :-1, :].contiguous()
            shift_labels = labels[:, 1:].contiguous()
            loss = torch.nn.functional.cross_entropy(
                shift_logits.view(-1, self.config.vocab_size),
                shift_labels.view(-1),
                ignore_index=self.config.pad_token_id,
            )

        return {"loss": loss, "logits": logits}

    def num_parameters(self) -> int:
        """Count total trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    @torch.no_grad()
    def generate(self, input_ids: torch.Tensor, max_new_tokens: int,
                 temperature: float = 0.8, top_p: float = 0.9) -> torch.Tensor:
        """Generate text autoregressively."""
        for _ in range(max_new_tokens):
            outputs = self(input_ids)
            logits = outputs["logits"][:, -1, :]  # (B, vocab)
            logits = logits / temperature

            # Top-p (nucleus) sampling
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            cum_probs = torch.cumsum(
                torch.softmax(sorted_logits, dim=-1), dim=-1
            )
            mask = cum_probs > top_p
            mask[:, 1:] = mask[:, :-1].clone()
            mask[:, 0] = False
            sorted_logits[mask] = float("-inf")

            probs = torch.softmax(sorted_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
            next_id = sorted_indices.gather(-1, next_token)

            input_ids = torch.cat([input_ids, next_id], dim=1)
        return input_ids

class BPETokenizer:
    """BPE tokenizer wrapper using HuggingFace tokenizers."""

    def __init__(self, tokenizer=None):
        self.tok = tokenizer
        self.pad_token_id = 0
        self.bos_token_id = 1
        self.eos_token_id = 2
        self.unk_token_id = 3

    @property
    def vocab_size(self) -> int:
        return self.tok.get_vocab_size() if self.tok else 0

    def encode(self, text: str, max_length: int | None = None) -> list[int]:
        enc = self.tok.encode(text)
        ids = enc.ids
        if max_length and len(ids) > max_length:
            ids = ids[:max_length]
        return ids

    def decode(self, ids) -> str:
        if isinstance(ids, torch.Tensor):
            ids = ids.tolist()
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            ids = ids[0]
        return self.tok.decode(ids, skip_special_tokens=True)

    def save(self, path: str):
        self.tok.save(path)

    @classmethod
    def from_file(cls, path: str) -> "BPETokenizer":
        from tokenizers import Tokenizer
        tok = Tokenizer.from_file(path)
        return cls(tok)

    @classmethod
    def train_from_text(cls, text_files: list[str], vocab_size: int = 16384,
                        pad_token_id: int = 0, bos_token_id: int = 1,
                        eos_token_id: int = 2, unk_token_id: int = 3) -> "BPETokenizer":
        """Train a BPE tokenizer from text files."""
        from tokenizers import Tokenizer
        from tokenizers.models import BPE
        from tokenizers.trainers import BpeTrainer
        from tokenizers.pre_tokenizers import ByteLevel
        from tokenizers.decoders import ByteLevel as ByteLevelDecoder
        from tokenizers.processors import TemplateProcessing

        tokenizer = Tokenizer(BPE(unk_token="<unk>"))
        tokenizer.pre_tokenizer = ByteLevel(add_prefix_space=True)
        tokenizer.post_processor = TemplateProcessing(
            single="<bos> $A <eos>",
            special_tokens=[
                ("<pad>", pad_token_id),
                ("<bos>", bos_token_id),
                ("<eos>", eos_token_id),
                ("<unk>", unk_token_id),
            ],
        )
        tokenizer.decoder = ByteLevelDecoder()

        trainer = BpeTrainer(
            vocab_size=vocab_size,
            min_frequency=2,
            special_tokens=["<pad>", "<bos>", "<eos>", "<unk>"],
            show_progress=True,
        )
        tokenizer.train(files=text_files, trainer=trainer)
        return cls(tokenizer)

# ---- end inlined bundle ----
from safetensors.torch import load_file, save_file


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def shard_ids(ids: np.ndarray, n: int, seq_len: int, rng: np.random.Generator) -> np.ndarray:
    """Pick ``n`` random contiguous seq_len-chunks from ``ids`` -> (n, seq_len) int64."""
    T = seq_len
    out = np.empty((n, T), dtype=np.int64)
    for i in range(n):
        j = int(rng.integers(0, max(1, len(ids) - T - 1)))
        out[i] = ids[j:j + T]
    return out


@torch.no_grad()
def eval_val_loss(model, val_ids: np.ndarray, tok, seq_len: int, n: int = 16) -> float:
    if len(val_ids) < seq_len + 1:
        return float("nan")
    rng = np.random.default_rng(0)
    batches = shard_ids(val_ids, n, seq_len, rng).astype(np.int32)
    losses = []
    for b in batches:
        x = torch.from_numpy(b).long().unsqueeze(0)
        with torch.no_grad():
            out = model(x, labels=x)
        losses.append(float(out["loss"]))
    return float(np.mean(losses))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume_from", type=str, required=False,
                    default=os.environ.get("SW_RESUME",
                        "/kaggle/input/silverwing-120m-base-v1"
                        if Path("/kaggle/input/silverwing-120m-base-v1").exists() else None),
                    help="dir with model.safetensors+config.json+tokenizer.json+metadata.json")
    ap.add_argument("--data_dir", type=str, default=os.environ.get("SW_DATA",
                        "/kaggle/input/silverwing-training-corpus-v1"
                        if Path("/kaggle/input/silverwing-training-corpus-v1").exists() else None),
                    help="dir containing train.txt + val.txt (the reproducible corpus)")
    ap.add_argument("--output_dir", type=str, required=False,
                    default=os.environ.get("SW_OUT", "/kaggle/working/silverwing-continue"),
                    help="where new checkpoints + metrics go (NEVER the frozen baseline)")
    # Production defaults = Stage C-10M (override via env SW_* when needed):
    # 1250 steps x (1 x 1024 x 8) = ~10.2M new tokens from step-400 base.
    ap.add_argument("--steps", type=int, default=int(os.environ.get("SW_STEPS", 1250)))
    ap.add_argument("--seq_len", type=int, default=int(os.environ.get("SW_SEQ", 1024)))
    ap.add_argument("--batch_size", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=int(os.environ.get("SW_GRAD_ACCUM", 8)))
    ap.add_argument("--lr", type=float, default=float(os.environ.get("SW_LR", 5e-5)))
    ap.add_argument("--warmup_steps", type=int, default=100)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument("--grad_clip", type=float, default=1.0)
    ap.add_argument("--log_steps", type=int, default=25)
    ap.add_argument("--eval_steps", type=int, default=125)
    ap.add_argument("--save_steps", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", type=str, default="auto", choices=["auto", "cuda", "cpu"])
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rng = np.random.default_rng(args.seed)

    if not args.resume_from or not Path(args.resume_from).exists():
        print(f"[FATAL] --resume_from missing: {args.resume_from!r}. "
              "Attach dataset 'silverwing-120m-base-v1' to the kernel.")
        return 2

    # ---- device / GPU gate ------------------------------------------------ #
    if args.device == "cuda" or (args.device == "auto" and not torch.cuda.is_available()):
        if torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            print("[FATAL] CUDA not available. On Kaggle: enable an Accelerator=GPU(T4) kernel "
                  "and DON'T run unaccelerated (the legacy trainer would silently drop to 12M).")
            return 2
    else:
        device = torch.device("cpu")
        torch.set_num_threads(max(1, os.cpu_count() or 1))
        print("[WARN] CPU path — continuing LOCAL only. A Kaggle GPU(T4) kernel is ~10-20x faster.")

    frozen = Path(args.resume_from)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ckpt_dir = out / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    print(f"[OUTPUT] {out}")

    # ---- config + model (strict, from frozen) --------------------------- #
    cfg = ModelConfig(**json.loads((frozen / "config.json").read_text()))
    model = SilverwingModel(cfg).to(device)
    base_meta = json.loads((frozen / "metadata.json").read_text()) \
        if (frozen / "metadata.json").exists() else {}
    base_step   = int(base_meta.get("step", 0))
    base_tokens = int(base_meta.get("tokens", base_meta.get("total_tokens", 0)))
    sd = load_file(str(frozen / "model.safetensors"))
    missing, unexpected = model.load_state_dict(sd, strict=True)
    print(f"[LOAD] params={sum(p.numel() for p in model.parameters())} "
          f"step={base_step} tokens={base_tokens:,} "
          f"strict_load missing={len(missing)} unexpected={len(unexpected)}")
    assert not missing and not unexpected, "checkpoint <-> SilverwingModel key mismatch!"

    # ---- SERVED tokenizer (NEVER retrain) --------------------------------- #
    tok = BPETokenizer.from_file(str(frozen / "tokenizer.json"))
    print(f"[TOKENIZER] loaded frozen tokenizer vocab={tok.vocab_size} "
          f"sha256={file_sha256(frozen/'tokenizer.json')}")

    # ---- corpus (cache encoded ids) -------------------------------------- #
    cache_train = out / "corpus_train.npy"
    cache_val = out / "corpus_val.npy"
    if cache_train.exists() and cache_val.exists():
        print("[DATA] loading cached token-id arrays ...")
        train_ids = np.load(cache_train)
        val_ids = np.load(cache_val)
    else:
        if not args.data_dir:
            print("[FATAL] --data_dir required on first run (no cached corpus).")
            return 2
        data = Path(args.data_dir)
        t0 = time.time()
        train_text = (data / "train.txt").read_text("utf-8", "replace")
        val_text = (data / "val.txt").read_text("utf-8", "replace")
        train_ids = np.asarray(tok.encode(train_text), dtype=np.int32)
        val_ids = np.asarray(tok.encode(val_text), dtype=np.int32)
        np.save(cache_train, train_ids)
        np.save(cache_val, val_ids)
        print(f"[DATA] train={len(train_ids)} val={len(val_ids)} tokens ({round(time.time()-t0,1)}s)")

    dataset_hash = file_sha256(Path(args.data_dir) / "train.txt") if args.data_dir else base_meta.get("dataset_hash")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, betas=(0.9, 0.95),
                            weight_decay=args.weight_decay, eps=1e-8)
    tokens_per_step = args.batch_size * args.seq_len * args.grad_accum

    metrics_path = out / "metrics.jsonl"
    lineage = {
        "base_model": "silverwing-120m-base-v1 r1",
        "base_model_sha256": file_sha256(frozen / "model.safetensors"),
        "base_config_sha256": file_sha256(frozen / "config.json"),
        "base_tokenizer_sha256": file_sha256(frozen / "tokenizer.json"),
        "base_step": base_step, "base_tokens": base_tokens,
        "base_train_loss": base_meta.get("train_loss"),
        "base_val_loss": base_meta.get("val_loss"),
        "dataset_train_sha256": dataset_hash,
    }
    print(f"[TRAIN] step {base_step} -> {base_step + args.steps} "
          f"(|{tokens_per_step} tok/optim-step, ~{round(args.steps*tokens_per_step/1e6,2)}M new tokens)")

    model.train()
    t0 = time.time(); running = 0.0; count = 0; gstep = base_step
    for s in range(1, args.steps + 1):
        opt.zero_grad(set_to_none=True)
        if gstep - base_step < args.warmup_steps:
            lr_scale = (gstep - base_step + 1) / max(1, args.warmup_steps)
        else:
            prog = (gstep - base_step - args.warmup_steps) / max(1, args.steps - args.warmup_steps)
            lr_scale = 0.5 * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = args.lr * lr_scale
        for _ in range(args.grad_accum):
            x = shard_ids(train_ids, args.batch_size, args.seq_len, rng).astype(np.int32)
            x = torch.from_numpy(x).long().to(device)
            mout = model(x, labels=x)
            loss = mout["loss"] / args.grad_accum
            loss.backward()
            running += float(loss.detach()) * args.grad_accum
            count += 1
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        opt.step()
        gstep += 1
        if s % args.log_steps == 0:
            elapsed = time.time() - t0
            trained = gstep - base_step
            print(f"[step {gstep}] loss={running/count:.4f} lr={opt.param_groups[0]['lr']:.2e} "
                  f"tok={base_tokens + trained*tokens_per_step:,} "
                  f"tok/s~{round(trained*tokens_per_step/elapsed)} elapsed={round(elapsed)}s")
        if s % args.eval_steps == 0:
            vl = eval_val_loss(model, val_ids, tok, args.seq_len, n=16)
            print(f"[eval] val_loss@step{gstep}={vl:.4f} (frozen val_loss={base_meta.get('val_loss')})")
            with open(metrics_path, "a") as f:
                f.write(json.dumps({"step": gstep, "val_loss": round(vl, 6)}) + "\n")
        if s % args.save_steps == 0:
            d = ckpt_dir / f"step-{gstep}"
            d.mkdir(exist_ok=True)
            sd = {k: v.contiguous().cpu() for k, v in model.state_dict().items()}
            _ptrs = {}
            for _k, _v in list(sd.items()):
                _p = _v.data_ptr()
                if _p in _ptrs:
                    sd[_k] = _v.clone()
                else:
                    _ptrs[_p] = _k
            save_file(sd, str(d / "model.safetensors"))
            (d / "tokenizer.json").write_bytes((frozen / "tokenizer.json").read_bytes())
            meta = dict(lineage)
            meta.update({"step": gstep, "new_tokens_trained": (gstep - base_step)*tokens_per_step,
                          "total_tokens": base_tokens + (gstep - base_step)*tokens_per_step,
                          "lr_peak": args.lr, "device": str(device), "torch": torch.__version__,
                          "config": {"n_layers": cfg.n_layers, "n_heads": cfg.n_heads,
                                     "n_kv_heads": cfg.n_kv_heads, "d_model": cfg.d_model,
                                     "hidden_size": cfg.hidden_size, "vocab_size": cfg.vocab_size,
                                     "max_position_embeddings": cfg.max_position_embeddings}})
            (d / "metadata.json").write_text(json.dumps(meta, indent=2))
            print(f"[ckpt] saved {d}")

    elapsed = time.time() - t0
    trained_tokens = (gstep - base_step) * tokens_per_step
    summary = dict(lineage)
    summary.update({
        "experiment": "exp_c_continue_120m", "step_start": base_step, "step_end": gstep,
        "steps_trained": args.steps, "tokens_trained": trained_tokens,
        "elapsed_s": round(elapsed, 2), "tok_s": round(trained_tokens / elapsed),
        "lr_peak": args.lr, "seq_len": args.seq_len, "batch": args.batch_size,
        "grad_accum": args.grad_accum,
    })
    (out / "training_summary.json").write_text(json.dumps(summary, indent=2))
    print("[DONE] " + json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
