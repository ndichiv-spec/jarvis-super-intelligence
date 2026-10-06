"""Experiment B — Silverwing-12M trained on ~10M tokens, continued from v1.

This script continues training the Silverwing-12M-v1 checkpoint on the
newly prepared ~13.6M-token dataset (45 Gutenberg books + 229 Wikipedia
articles). It loads the frozen v1 weights, re-initialises the optimizer
with a fresh warmup, and trains for ~2,440 additional steps so the model
sees approximately 10M tokens of new data on top of the 1.024M tokens
already seen during Phase A.

Architecture: 6L / 384d / 8Q / 2KV-GQA / 1024 MLP / vocab 8192 / ctx 1024
Training:     AdamW(lr=2e-4), cosine decay, warmup=120, grad_clip=1.0,
              weight_decay=0.01, batch_size=1, grad_accum=4, seq_len=1024
              → 4,096 tokens/step → ~9.98M new tokens in 2,440 steps

USAGE:
    python train_experiment_b.py                    # full run
    python train_experiment_b.py --steps 2440         # custom steps
    python train_experiment_b.py --steps 50           # smoke test

Outputs go to silverwing/local_run/exp_b_10m/
"""
from __future__ import annotations

import os
import sys
import json
import math
import time
import hashlib
import argparse
from pathlib import Path
from dataclasses import asdict

# ── P100 / CPU pre-flight (must happen BEFORE importing torch) ──────────
import subprocess
_p100 = False
try:
    _info = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        stderr=subprocess.DEVNULL, text=True, timeout=10
    ).strip()
    for _ln in _info.split("\n"):
        if "P100" in _ln.strip():
            _p100 = True
    if _p100:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        print(f"[HW] P100 detected — forcing CPU mode")
    else:
        print(f"[HW] GPU: {_info.split(chr(10))[0].strip()}")
except Exception:
    print("[HW] No NVIDIA GPU — using CPU")

import torch
from tokenizers import Tokenizer


# ═════════════════════════════════════════════════════════════════════════
#  MODEL ARCHITECTURE  (mirrors silverwing_train.py — identical weights)
# ═════════════════════════════════════════════════════════════════════════

class RMSNorm(torch.nn.Module):
    def __init__(self, hidden_size, eps=1e-5):
        super().__init__()
        self.eps = eps
        self.weight = torch.nn.Parameter(torch.ones(hidden_size))

    def forward(self, x):
        with torch.autocast(device_type=x.device.type, enabled=False):
            x_f = x.float()
            var = x_f.pow(2).mean(-1, keepdim=True)
            x_norm = x_f * torch.rsqrt(var + self.eps)
        return self.weight * x_norm.to(x.dtype)


class RotaryEmbedding:
    def __init__(self, dim, base=10000.0):
        self.dim = dim
        self.base = base

    def __call__(self, seq_len, device):
        theta = 1.0 / (self.base ** (
            torch.arange(0, self.dim, 2, dtype=torch.float32, device=device) / self.dim
        ))
        positions = torch.arange(seq_len, dtype=torch.float32, device=device)
        freqs = torch.outer(positions, theta)
        cos = torch.zeros(seq_len, self.dim, device=device, dtype=torch.float32)
        sin = torch.zeros(seq_len, self.dim, device=device, dtype=torch.float32)
        cos[:, 0::2] = torch.cos(freqs)
        cos[:, 1::2] = torch.cos(freqs)
        sin[:, 0::2] = torch.sin(freqs)
        sin[:, 1::2] = torch.sin(freqs)
        return cos, sin


def rotate_half(x):
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2:]
    return torch.cat((-x2, x1), dim=-1)


def apply_rope(q, k, cos, sin):
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed


class Attention(torch.nn.Module):
    """GQA: 8 query heads, 2 KV heads (4:1 ratio)."""
    def __init__(self, d_model, n_heads, n_kv_heads, head_dim, rope_theta=10000.0, use_bias=False):
        super().__init__()
        self.n_heads = n_heads
        self.n_kv_heads = n_kv_heads
        self.head_dim = head_dim
        self.n_kv_groups = n_heads // n_kv_heads
        self.q_proj = torch.nn.Linear(d_model, n_heads * head_dim, bias=use_bias)
        self.k_proj = torch.nn.Linear(d_model, n_kv_heads * head_dim, bias=use_bias)
        self.v_proj = torch.nn.Linear(d_model, n_kv_heads * head_dim, bias=use_bias)
        self.o_proj = torch.nn.Linear(n_heads * head_dim, d_model, bias=use_bias)
        self.rope = RotaryEmbedding(self.head_dim, rope_theta)

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
    def __init__(self, d_model, hidden_size, multiple_of=64, use_bias=False):
        super().__init__()
        hidden_size = multiple_of * ((hidden_size + multiple_of - 1) // multiple_of)
        self.gate = torch.nn.Linear(d_model, hidden_size, bias=use_bias)
        self.up = torch.nn.Linear(d_model, hidden_size, bias=use_bias)
        self.down = torch.nn.Linear(hidden_size, d_model, bias=use_bias)

    def forward(self, x):
        gate = torch.sigmoid(self.gate(x)) * self.gate(x)
        up = self.up(x)
        return self.down(gate * up)


class TransformerBlock(torch.nn.Module):
    def __init__(self, d_model, n_heads, n_kv_heads, hidden_size, multiple_of, norm_eps, rope_theta, use_bias):
        super().__init__()
        head_dim = d_model // n_heads
        self.attention = Attention(d_model, n_heads, n_kv_heads, head_dim, rope_theta, use_bias)
        self.mlp = SwiGLUMLP(d_model, hidden_size, multiple_of, use_bias)
        self.ln1 = RMSNorm(d_model, norm_eps)
        self.ln2 = RMSNorm(d_model, norm_eps)

    def forward(self, x, mask=None):
        x = x + self.attention(self.ln1(x), mask)
        x = x + self.mlp(self.ln2(x))
        return x


class SilverwingModel(torch.nn.Module):
    """Silverwing-12M: 6L/384d/8Q/2KV-GQA/SwiGLU/RMSNorm/RoPE, tied weights."""
    def __init__(self, vocab_size=8192, max_position_embeddings=1024,
                 n_layers=6, n_heads=8, n_kv_heads=2, d_model=384,
                 hidden_size=1024, multiple_of=64, norm_eps=1e-5,
                 rope_theta=10000.0, use_bias=False, tie_word_embeddings=True,
                 pad_token_id=0, bos_token_id=1, eos_token_id=2):
        super().__init__()
        self.config = {
            "vocab_size": vocab_size, "max_position_embeddings": max_position_embeddings,
            "n_layers": n_layers, "n_heads": n_heads, "n_kv_heads": n_kv_heads,
            "d_model": d_model, "hidden_size": hidden_size,
            "multiple_of": multiple_of, "norm_eps": norm_eps, "rope_theta": rope_theta,
            "use_bias": use_bias, "tie_word_embeddings": tie_word_embeddings,
            "pad_token_id": pad_token_id, "bos_token_id": bos_token_id, "eos_token_id": eos_token_id,
        }
        self.pad_token_id = pad_token_id
        self.eos_token_id = eos_token_id
        self.bos_token_id = bos_token_id

        self.embed_tokens = torch.nn.Embedding(vocab_size, d_model, pad_token_id)
        self.layers = torch.nn.ModuleList([
            TransformerBlock(d_model, n_heads, n_kv_heads, hidden_size,
                             multiple_of, norm_eps, rope_theta, use_bias)
            for _ in range(n_layers)
        ])
        self.norm_f = RMSNorm(d_model, norm_eps)
        self.lm_head = torch.nn.Linear(d_model, vocab_size, bias=False)
        if tie_word_embeddings:
            self.lm_head.weight = self.embed_tokens.weight
        self._init_weights()

    def _init_weights(self):
        for _, param in self.named_parameters():
            if param.dim() > 1:
                torch.nn.init.normal_(param, mean=0.0, std=0.02)

    def _make_causal_mask(self, seq_len, device):
        mask = torch.tril(torch.ones(seq_len, seq_len, device=device, dtype=torch.bool))
        return mask.unsqueeze(0).unsqueeze(0)

    def forward(self, input_ids, labels=None):
        B, T = input_ids.shape
        x = self.embed_tokens(input_ids) * math.sqrt(self.config["d_model"])
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
                shift_logits.view(-1, self.config["vocab_size"]),
                shift_labels.view(-1),
                ignore_index=self.pad_token_id,
            )
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
            if next_id.item() == self.eos_token_id:
                break
        return input_ids

    def get_config_dict(self):
        return dict(self.config)


# ═════════════════════════════════════════════════════════════════════════
#  TOKENIZER
# ═════════════════════════════════════════════════════════════════════════

class BPETokenizer:
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

    @classmethod
    def from_file(cls, path):
        tok = Tokenizer.from_file(path)
        return cls(tok)


# ═════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ═════════════════════════════════════════════════════════════════════════

def compute_hash(path):
    """SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_lr(step, base_lr, warmup_steps, total_steps):
    """Cosine learning rate schedule with linear warmup."""
    if step < warmup_steps:
        return base_lr * step / max(1, warmup_steps)
    progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
    return base_lr * 0.5 * (1.0 + math.cos(math.pi * progress))


def evaluate_model(model, val_ids, config, device, max_len):
    """Evaluate perplexity on validation data."""
    model.eval()
    val_loss = 0.0
    val_count = 0
    with torch.no_grad():
        for i in range(0, min(len(val_ids), max_len * 10), max_len + 1):
            batch = torch.tensor(val_ids[i:i + max_len + 1], dtype=torch.long, device=device)
            if len(batch) < 2:
                break
            input_ids = batch[:-1].unsqueeze(0)
            labels = batch[1:].unsqueeze(0)
            out = model(input_ids, labels=labels)
            val_loss += out["loss"].item()
            val_count += 1
    model.train()
    avg_loss = val_loss / max(val_count, 1)
    ppl = math.exp(min(avg_loss, 20.0))
    return avg_loss, ppl


def save_checkpoint(directory, model, optimizer, config, step, train_loss,
                    total_tokens, tokenizer, args, val_loss=None, tag="checkpoint"):
    """Save a full training checkpoint."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    # Model weights (safetensors, handling tied weights)
    from safetensors.torch import save_file
    tensors = {}
    seen_ptrs = set()
    for k, v in model.state_dict().items():
        v_contig = v.contiguous().cpu()
        ptr = v_contig.data_ptr()
        if ptr in seen_ptrs:
            v_contig = v_contig.clone()
        seen_ptrs.add(ptr)
        tensors[k] = v_contig
    save_file(tensors, str(directory / "model.safetensors"))

    # Optimizer state
    torch.save({"global_step": step, "total_tokens": total_tokens,
                "optimizer": optimizer.state_dict()},
               str(directory / "optimizer.pt"))

    # Config
    with open(directory / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    # Tokenizer manifest
    tok_manifest = {
        "vocab_size": tokenizer.vocab_size,
        "special_tokens": {"<pad>": 0, "<bos>": 1, "<eos>": 2, "<unk>": 3},
    }
    with open(directory / "tokenizer_manifest.json", "w") as f:
        json.dump(tok_manifest, f, indent=2)

    # Metadata
    meta = {
        "step": step, "tag": tag, "train_loss": train_loss, "val_loss": val_loss,
        "total_tokens": total_tokens, "lr": optimizer.param_groups[0]["lr"],
        "batch_size": args.batch_size, "grad_accum": args.grad_accum,
        "max_seq_len": args.max_seq_len, "torch_version": torch.__version__,
        "seed": args.seed, "model_sha256": compute_hash(str(directory / "model.safetensors")),
    }
    with open(directory / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)


# ═════════════════════════════════════════════════════════════════════════
#  TRAINING
# ═════════════════════════════════════════════════════════════════════════

def train_experiment_b():
    parser = argparse.ArgumentParser(description="Experiment B — Silverwing-12M continuation training")
    parser.add_argument("--steps", type=int, default=2440,
                        help="Number of NEW training steps (excluding v1's 1000)")
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=4)
    parser.add_argument("--max_seq_len", type=int, default=1024)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--warmup_steps", type=int, default=120)
    parser.add_argument("--grad_clip", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log_steps", type=int, default=10)
    parser.add_argument("--save_steps", type=int, default=200)
    parser.add_argument("--eval_steps", type=int, default=200)
    parser.add_argument("--checkpoint", type=str, default="silverwing/local_run/final",
                        help="Path to v1 checkpoint to resume from")
    parser.add_argument("--work_dir", type=str, default="silverwing/local_run/exp_b_10m",
                        help="Output directory for Experiment B")
    parser.add_argument("--resume", type=str, default=None,
                        help="Resume from a checkpoint directory within work_dir (e.g. 'checkpoints/step-400')")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[HW] Device: {device} | PyTorch: {torch.__version__}")

    # ── Load v1 checkpoint ──────────────────────────────────────────────
    print(f"\n[CKPT] Loading v1 checkpoint from: {args.checkpoint}")
    ckpt_dir = Path(args.checkpoint)

    with open(ckpt_dir / "config.json") as f:
        v1_config_dict = json.load(f)
    print(f"[CKPT] v1 config: {v1_config_dict}")

    model = SilverwingModel(**v1_config_dict).to(device)
    n_params = model.num_parameters()
    print(f"[CKPT] Model parameters: {n_params:,}")

    from safetensors.torch import load_file
    state_dict = load_file(str(ckpt_dir / "model.safetensors"))
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    print(f"[CKPT] Loaded {len(state_dict)} tensors | missing: {len(missing)} | unexpected: {len(unexpected)}")

    # Verify v1 SHA256 hasn't been tampered with (safety check)
    v1_sha = compute_hash(str(ckpt_dir / "model.safetensors"))
    v1_meta = json.load(open(ckpt_dir / "metadata.json"))
    expected_sha = v1_meta.get("model_sha256", "")
    if expected_sha and v1_sha != expected_sha:
        print(f"[ERROR] v1 checkpoint SHA256 mismatch! Expected {expected_sha}, got {v1_sha}")
        sys.exit(1)
    print(f"[CKPT] v1 checksum verified: {v1_sha[:16]}...")

    # ── Tokenizer ───────────────────────────────────────────────────────
    tok_path = work_dir / "tokenizer" / "tokenizer.json"
    if not tok_path.exists():
        tok_path = Path("silverwing/local_run/tokenizer/tokenizer.json")
    tokenizer = BPETokenizer.from_file(str(tok_path))
    print(f"[TOK] Vocab size: {tokenizer.vocab_size}")

    # ── Data ────────────────────────────────────────────────────────────
    train_file = work_dir / "data" / "splits" / "train.txt"
    val_file = work_dir / "data" / "splits" / "val.txt"
    if not train_file.exists():
        train_file = Path("silverwing/data_pipeline/processed/train.txt")
        val_file = Path("silverwing/data_pipeline/processed/val.txt")

    print(f"[DATA] Train file: {train_file}")
    print(f"[DATA] Val file:   {val_file}")

    with open(train_file, "r", encoding="utf-8", errors="replace") as f:
        train_text = f.read()
    with open(val_file, "r", encoding="utf-8", errors="replace") as f:
        val_text = f.read()

    print("[DATA] Tokenizing...")
    train_ids = tokenizer.encode(train_text)
    val_ids = tokenizer.encode(val_text) if val_text else train_ids[:10000]
    del train_text, val_text
    print(f"[DATA] Train: {len(train_ids):,} tokens | Val: {len(val_ids):,} tokens")

    max_len = min(v1_config_dict.get("max_position_embeddings", 1024), args.max_seq_len)
    grad_accum = args.grad_accum
    warmup_steps = args.warmup_steps
    start_step = 1000  # v1's final step
    total_new_steps = args.steps

    # ── Optimizer (fresh, continuing from v1 weights) ──────────────────
    decay_params, no_decay_params = [], []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        if param.ndim >= 2 and "embed" not in name.lower():
            decay_params.append(param)
        else:
            no_decay_params.append(param)

    optimizer = torch.optim.AdamW(
        [{"params": decay_params, "weight_decay": 0.01},
         {"params": no_decay_params, "weight_decay": 0.0}],
        lr=args.lr, betas=(0.9, 0.95), eps=1e-8,
    )

    # ── Resume from mid-training checkpoint ─────────────────────────────
    total_tokens = 1024000  # v1's tokens_processed (default)
    if args.resume:
        resume_dir = work_dir / args.resume
        if not resume_dir.exists():
            resume_dir = Path(args.resume)
        if resume_dir.exists():
            print(f"\n[RESUME] Loading from: {resume_dir}")
            state_dict = load_file(str(resume_dir / "model.safetensors"))
            model.load_state_dict(state_dict, strict=False)
            opt_data = torch.load(str(resume_dir / "optimizer.pt"),
                                  map_location="cpu", weights_only=False)
            optimizer.load_state_dict(opt_data["optimizer"])
            start_step = opt_data["global_step"]
            total_tokens = opt_data["total_tokens"]
            print(f"[RESUME] Step {start_step} | total_tokens {total_tokens:,} | OK")
        else:
            print(f"[RESUME] Warning: {resume_dir} not found — starting from v1")

    # Recalculate remaining steps based on (possibly resumed) start_step
    target_step = 1000 + args.steps  # intended final global step
    total_new_steps = target_step - start_step

    # ── Print training summary ──────────────────────────────────────────
    n_new_tokens_calc = total_new_steps * max_len * grad_accum
    n_params_est = 6 * 384 * 384 * 2 + 6 * (384 * 1024 * 2 + 1024 * 384) + 8192 * 384
    print(f"\n{'='*60}")
    print(f"SILVERWING EXPERIMENT B — Training Continuation")
    print(f"{'='*60}")
    print(f"  Device:        {device}")
    print(f"  Architecture:  {v1_config_dict['n_layers']}L/{v1_config_dict['d_model']}d/"
          f"{v1_config_dict['n_heads']}H/{v1_config_dict['n_kv_heads']}KVH/GQA")
    print(f"  Parameters:    {n_params:,}")
    print(f"  Vocab size:    {v1_config_dict['vocab_size']}")
    print(f"  Context:       {max_len}")
    print(f"  Weight tying:  {v1_config_dict['tie_word_embeddings']}")
    print(f"  GQA ratio:     {v1_config_dict['n_heads']//v1_config_dict['n_kv_heads']}:1 "
          f"({v1_config_dict['n_heads']} Q / {v1_config_dict['n_kv_heads']} KV)")
    print(f"  SwiGLU hidden: {v1_config_dict['hidden_size']}")
    print(f"  LR:            {args.lr} -> cosine warmup {warmup_steps} steps")
    print(f"  Batch:         {args.batch_size} x {grad_accum} = {args.batch_size * grad_accum} effective")
    print(f"  Seq len:       {max_len}")
    print(f"  Warmup:        {warmup_steps} steps")
    print(f"  Grad clip:     {args.grad_clip}")
    print(f"  Weight decay:  0.01")
    print(f"  v1 steps:      {start_step} (474K tokens seen in v1)")
    print(f"  New steps:     {total_new_steps} (~{n_new_tokens_calc:,} new tokens)")
    print(f"  Total tokens:  ~{total_tokens + n_new_tokens_calc:,}")
    print(f"  Save every:    {args.save_steps} steps")
    print(f"  Eval every:    {args.eval_steps} steps")
    print(f"  Work dir:      {work_dir}")
    print(f"{'='*60}\n")

    # ── Training loop ───────────────────────────────────────────────────
    global_step = start_step
    best_val_loss = float("inf")
    data_ptr = 0
    model.train()
    start_time = time.time()

    print(f"Starting training: {total_new_steps} new steps (continuing from step {start_step})\n")

    for new_step in range(total_new_steps):
        optimizer.zero_grad()
        total_loss = 0.0

        for _ in range(grad_accum):
            if data_ptr + max_len + 1 > len(train_ids):
                data_ptr = 0
            batch_ids = torch.tensor(train_ids[data_ptr:data_ptr + max_len + 1],
                                     dtype=torch.long, device=device)
            data_ptr += max_len + 1
            total_tokens += max_len

            input_ids = batch_ids[:-1].unsqueeze(0)
            labels = batch_ids[1:].unsqueeze(0)
            outputs = model(input_ids, labels=labels)
            loss = outputs["loss"] / grad_accum
            loss.backward()
            total_loss += loss.item()

        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        current_lr = get_lr(new_step, args.lr, warmup_steps, total_new_steps)
        for pg in optimizer.param_groups:
            pg["lr"] = current_lr
        optimizer.step()
        global_step += 1

        if global_step % args.log_steps == 0 or global_step == start_step + 1:
            elapsed = time.time() - start_time
            ppl = math.exp(min(total_loss, 20.0))
            tps = total_tokens / max(elapsed, 1)
            print(f"  step {global_step:5d} | loss {total_loss:.4f} | ppl {ppl:.2f} | "
                  f"lr {current_lr:.2e} | {tps:.0f} tok/s | {elapsed:.1f}s")

        # Periodic checkpointing + evaluation
        if global_step % args.save_steps == 0:
            ckpt_dir_step = work_dir / "checkpoints" / f"step-{global_step}"
            save_checkpoint(
                ckpt_dir_step, model, optimizer, model.get_config_dict(),
                global_step, total_loss, total_tokens, tokenizer, args,
                val_loss=None, tag=f"step-{global_step}"
            )

            if global_step % args.eval_steps == 0:
                vl, vp = evaluate_model(model, val_ids, model.get_config_dict(), device, max_len)
                print(f"  [EVAL] step {global_step} | val_loss={vl:.4f} | val_ppl={vp:.2f}")
                if vl < best_val_loss:
                    best_val_loss = vl
                    best_dir = work_dir / "checkpoints" / "best"
                    save_checkpoint(
                        best_dir, model, optimizer, model.get_config_dict(),
                        global_step, total_loss, total_tokens, tokenizer, args,
                        val_loss=vl, tag="best"
                    )

    elapsed = time.time() - start_time
    val_loss, val_ppl = evaluate_model(model, val_ids, model.get_config_dict(), device, max_len)

    # Save final checkpoint
    final_dir = work_dir / "final"
    save_checkpoint(
        final_dir, model, optimizer, model.get_config_dict(),
        global_step, total_loss, total_tokens, tokenizer, args,
        val_loss=val_loss, tag="final"
    )

    print(f"\n{'='*60}")
    print(f"SILVERWING EXPERIMENT B COMPLETE")
    print(f"  Model:       Silverwing-12M-ExpB-10M")
    print(f"  Steps:       {global_step} ({start_step} v1 + {total_new_steps} new)")
    print(f"  Tokens:      {total_tokens:,}")
    print(f"  Val loss:    {val_loss:.4f}")
    print(f"  Val PPL:     {val_ppl:.2f}")
    print(f"  Best val:    {best_val_loss:.4f}")
    print(f"  Time:        {elapsed:.1f}s ({total_tokens/elapsed:.0f} tok/s)")
    print(f"  Model:       {final_dir}")
    print(f"{'='*60}")

    # Save summary
    summary = {
        "experiment": "B",
        "model_name": "Silverwing-12M-ExpB-10M",
        "continued_from": "Silverwing-12M-v1",
        "v1_checkpoint_sha256": v1_sha,
        "params": n_params,
        "v1_steps": 1000,
        "new_steps": total_new_steps,
        "total_steps": global_step,
        "v1_tokens": 1024000,
        "new_tokens": n_new_tokens_calc,
        "total_tokens": total_tokens,
        "train_loss": total_loss,
        "val_loss": val_loss,
        "val_perplexity": val_ppl,
        "best_val_loss": best_val_loss,
        "elapsed_s": round(elapsed, 1),
        "device": str(device),
        "torch_version": torch.__version__,
        "config": model.get_config_dict(),
        "training_config": {
            "optimizer": "AdamW",
            "learning_rate": args.lr,
            "lr_decay": "cosine",
            "weight_decay": 0.01,
            "warmup_steps": warmup_steps,
            "grad_clip": args.grad_clip,
            "batch_size": args.batch_size,
            "grad_accum": grad_accum,
            "max_seq_len": max_len,
            "seed": args.seed,
        },
    }
    with open(work_dir / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    train_experiment_b()
