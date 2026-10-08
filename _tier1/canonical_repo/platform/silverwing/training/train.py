"""Silverwing Training Script — Self-contained for Kaggle.

Trains the Silverwing decoder-only transformer on Kaggle (CPU or GPU).
Handles P100 GPU incompatibility by forcing CPU mode.

Usage:
    python train.py                    # train (1000 steps)
    python train.py --steps 10000      # custom steps
    python train.py --evaluate         # evaluate checkpoint
    python train.py --evaluate --checkpoint /path/to/ckpt
"""
from __future__ import annotations

import os
import sys
import json
import math
import time
import hashlib
import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict

# ── Pre-flight: detect P100 and force CPU ─────────────────────────────
# P100 (sm_60) is not supported by PyTorch 2.10+cu128. Detect it and
# set CUDA_VISIBLE_DEVICES="" BEFORE importing torch.
try:
    _gpu_info = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        stderr=subprocess.DEVNULL, text=True, timeout=10
    ).strip()
    _gpu_name = _gpu_info.split("\n")[0].strip()
    if "P100" in _gpu_name:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        print(f"[HARDWARE] GPU is {_gpu_name} (sm_60) — forcing CPU mode")
    else:
        print(f"[HARDWARE] GPU detected: {_gpu_name}")
except Exception:
    print("[HARDWARE] No NVIDIA GPU detected — using CPU")

import torch  # noqa: E402  (must come after CUDA_VISIBLE_DEVICES)


# ── Model Configuration ─────────────────────────────────────────────

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


# ── RMSNorm ──────────────────────────────────────────────────────────

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


# ── Rotary Positional Embedding ──────────────────────────────────────

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


# ── Multi-Head Attention with GQA ──────────────────────────────────

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


# ── SwiGLU MLP ────────────────────────────────────────────────────────

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


# ── Transformer Block ─────────────────────────────────────────────────

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


# ── Silverwing Model ──────────────────────────────────────────────────

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


# ── Tokenizer ─────────────────────────────────────────────────────────

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


# ── Data Pipeline ───────────────────────────────────────────────────

GUTENBERG_BOOKS = [
    ("https://www.gutenberg.org/files/1342/1342-0.txt", "pride_prejudice.txt"),
    ("https://www.gutenberg.org/files/84/84-0.txt", "frankenstein.txt"),
    ("https://www.gutenberg.org/files/1661/1661-0.txt", "sherlock.txt"),
    ("https://www.gutenberg.org/files/11/11-0.txt", "alice.txt"),
    ("https://www.gutenberg.org/cache/epub/1342/pg1342-images.html", "dummy"),  # skipped if fails
]
# Filter out invalid URLs
GUTENBERG_BOOKS = [(u, n) for u, n in GUTENBERG_BOOKS if n != "dummy"]


def download_gutenberg_books(data_dir: Path) -> list[str]:
    """Download Project Gutenberg books for training data."""
    import urllib.request

    texts = []
    for url, name in GUTENBERG_BOOKS:
        try:
            dest = data_dir / name
            if not dest.exists():
                print(f"  Downloading {name}...")
                urllib.request.urlretrieve(url, str(dest))
            with open(dest, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            # Strip Gutenberg header/footer
            start = content.find("*** START")
            end = content.rfind("*** END")
            if start > 0 and end > start:
                content = content[start:end]
            texts.append(content)
            print(f"  ✓ {name}: {len(content):,} chars")
        except Exception as e:
            print(f"  ✗ Failed {name}: {e}")
    return texts


def get_training_data(work_dir: Path) -> tuple[str, str]:
    """Load or download training and validation data.

    Returns paths to train.txt and val.txt.
    """
    data_dir = work_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    split_dir = data_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)

    train_file = split_dir / "train.txt"
    val_file = split_dir / "val.txt"

    if train_file.exists() and val_file.exists():
        print(f"[DATA] Found existing splits: {train_file}, {val_file}")
        return str(train_file), str(val_file)

    # Download books
    print("[DATA] Downloading training data...")
    texts = download_gutenberg_books(data_dir)

    if not texts:
        # Fallback: try HuggingFace datasets
        print("[DATA] Trying HuggingFace wikitext dataset...")
        try:
            from datasets import load_dataset
            ds = load_dataset("wikitext", "wikitext-2-raw-v1", split="train")
            for item in ds:
                text = item.get("text", "")
                if text and len(text.strip()) > 10:
                    texts.append(text)
            print(f"  Loaded {len(ds)} wikitext entries")
        except Exception as e:
            print(f"  Could not load wikitext: {e}")

    if not texts:
        print("[DATA] Using synthetic fallback data")
        sample = (
            "The quick brown fox jumps over the lazy dog. "
            "Silverwing is a language model trained on books and text. "
            "It uses grouped query attention, rotary embeddings, "
            "SwiGLU activations, and RMSNorm. "
        ) * 5000
        texts = [sample]

    # Combine and split 98/2
    all_text = "\n\n".join(texts)
    split_idx = int(len(all_text) * 0.98)
    train_text = all_text[:split_idx]
    val_text = all_text[split_idx:]

    with open(train_file, "w", encoding="utf-8") as f:
        f.write(train_text)
    with open(val_file, "w", encoding="utf-8") as f:
        f.write(val_text)

    print(f"[DATA] Train: {len(train_text):,} chars, Val: {len(val_text):,} chars")
    return str(train_file), str(val_file)


def compute_hash(path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Training ──────────────────────────────────────────────────────────

@dataclass
class TrainConfig:
    """Training hyperparameters."""
    model: ModelConfig = None  # set in main
    vocab_size: int = 16384
    n_layers: int = 12
    n_heads: int = 12
    n_kv_heads: int = 4
    d_model: int = 768
    hidden_size: int = 2560

    lr: float = 2e-4
    betas: tuple = (0.9, 0.95)
    eps: float = 1e-8
    weight_decay: float = 0.01

    steps: int = 1000
    batch_size: int = 1
    grad_accum: int = 8
    max_seq_len: int = 1024
    warmup_ratio: float = 0.05
    grad_clip: float = 1.0
    seed: int = 42

    log_steps: int = 10
    save_steps: int = 100
    eval_steps: int = 100


def get_lr(step, base_lr, warmup_steps, total_steps):
    """Cosine learning rate schedule with linear warmup."""
    if step < warmup_steps:
        return base_lr * step / max(1, warmup_steps)
    progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
    return 0.5 * base_lr * (1 + math.cos(math.pi * progress))


def train(args):
    """Main training function."""
    work_dir = Path("/kaggle/working/silverwing")
    work_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}")
    print(f"[TRAIN] Device: {device}")
    print(f"[TRAIN] PyTorch: {torch.__version__}")
    print(f"[TRAIN] Python: {sys.version.split()[0]}")
    print(f"{'='*60}\n")

    # Set seed
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    # ── Data ────────────────────────────────────────────
    train_file, val_file = get_training_data(work_dir)

    # ── Tokenizer ───────────────────────────────────────
    tok_dir = work_dir / "tokenizer"
    tok_dir.mkdir(parents=True, exist_ok=True)
    tok_path = tok_dir / "tokenizer.json"

    if tok_path.exists():
        print("[TOKENIZER] Loading existing tokenizer...")
        tokenizer = BPETokenizer.from_file(str(tok_path))
    else:
        print("[TOKENIZER] Training BPE tokenizer (vocab_size=16384)...")
        tokenizer = BPETokenizer.train_from_text(
            [train_file], vocab_size=args.vocab_size
        )
        tokenizer.save(str(tok_path))
        print(f"[TOKENIZER] Saved: vocab_size={tokenizer.vocab_size}")

    # ── Model ───────────────────────────────────────────
    config = ModelConfig(
        vocab_size=min(tokenizer.vocab_size, args.vocab_size),
        n_layers=args.n_layers,
        n_heads=args.n_heads,
        n_kv_heads=args.n_kv_heads,
        d_model=args.d_model,
        hidden_size=args.hidden_size,
    )

    model = SilverwingModel(config)
    model = model.to(device)

    n_params = model.num_parameters()
    est_params = estimate_parameters(config)
    print(f"\n[MODEL] Architecture: Silverwing-{args.n_layers}L-{args.d_model}d-GQA")
    print(f"[MODEL] Parameters: {n_params:,}")
    print(f"[MODEL] Estimated:  {est_params:,}")
    print(f"[MODEL] Layers: {config.n_layers}")
    print(f"[MODEL] d_model: {config.d_model}, heads: {config.n_heads}, "
          f"kv_heads: {config.n_kv_heads}, group_ratio: {config.n_kv_groups}:1")
    print(f"[MODEL] Hidden (SwiGLU): {config.hidden_size}")
    print(f"[MODEL] Vocab: {config.vocab_size}, Context: {config.max_position_embeddings}")
    print(f"[MODEL] Weight tying: {config.tie_word_embeddings}")

    # ── Optimizer ───────────────────────────────────────
    decay_params = []
    no_decay_params = []
    for name, param in model.named_parameters():
        if param.dim() > 1 and "embed" not in name.lower():
            decay_params.append(param)
        else:
            no_decay_params.append(param)

    optimizer = torch.optim.AdamW(
        [
            {"params": decay_params, "weight_decay": args.weight_decay},
            {"params": no_decay_params, "weight_decay": 0.0},
        ],
        lr=args.lr, betas=args.betas, eps=args.eps,
    )

    # ── Tokenizer / data loading ───────────────────────
    print("\n[DATA] Tokenizing text files...")
    with open(train_file, "r", encoding="utf-8", errors="replace") as f:
        train_text = f.read()
    with open(val_file, "r", encoding="utf-8", errors="replace") as f:
        val_text = f.read()

    train_ids = tokenizer.encode(train_text)
    val_ids = tokenizer.encode(val_text) if val_text else train_ids[:10000]
    del train_text, val_text
    print(f"[DATA] Train tokens: {len(train_ids):,}, Val tokens: {len(val_ids):,}")

    # ── Training loop ───────────────────────────────────
    max_len = min(config.max_position_embeddings, args.max_seq_len)
    grad_accum = args.grad_accum
    warmup_steps = max(1, int(args.steps * args.warmup_ratio))

    total_tokens = 0
    global_step = 0
    best_val_loss = float("inf")
    ckpt_dir = work_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    data_ptr = 0
    model.train()

    print(f"\n{'='*60}")
    print(f"[TRAIN] Starting training: {args.steps} steps")
    print(f"  batch_size={args.batch_size}, grad_accum={grad_accum}, "
          f"effective_batch={args.batch_size * grad_accum}")
    print(f"  seq_len={max_len}, lr={args.lr}, warmup={warmup_steps} steps")
    print(f"{'='*60}\n")

    start_time = time.time()

    for step in range(args.steps):
        optimizer.zero_grad()
        total_loss = 0.0

        for _ in range(grad_accum):
            # Wrap around if we run out of data
            if data_ptr + max_len + 1 > len(train_ids):
                data_ptr = 0

            batch_ids = torch.tensor(
                train_ids[data_ptr : data_ptr + max_len + 1],
                dtype=torch.long, device=device,
            )
            data_ptr += max_len + 1
            total_tokens += max_len

            input_ids = batch_ids[:-1].unsqueeze(0)
            labels = batch_ids[1:].unsqueeze(0)

            outputs = model(input_ids, labels=labels)
            loss = outputs["loss"] / grad_accum
            loss.backward()
            total_loss += loss.item()

        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)

        # Learning rate schedule
        current_lr = get_lr(step, args.lr, warmup_steps, args.steps)
        for pg in optimizer.param_groups:
            pg["lr"] = current_lr

        optimizer.step()
        global_step += 1

        if global_step % args.log_steps == 0 or global_step == 1:
            elapsed = time.time() - start_time
            avg_loss = total_loss
            ppl = math.exp(min(avg_loss, 20.0))
            tokens_per_sec = total_tokens / max(1, elapsed)
            print(f"  step {global_step:5d}/{args.steps} | "
                  f"loss {avg_loss:.4f} | ppl {ppl:.2f} | "
                  f"lr {current_lr:.2e} | {tokens_per_sec:.0f} tok/s | "
                  f"{elapsed:.1f}s")

        # Save checkpoint
        if global_step % args.save_steps == 0:
            _save_checkpoint(ckpt_dir, model, optimizer, config, global_step,
                             total_loss, total_tokens, train_file, tokenizer,
                             args, device, step_time=elapsed)

            # Periodic evaluation
            if global_step % args.eval_steps == 0:
                val_loss, val_ppl = _evaluate(model, val_ids, config, device, max_len)
                print(f"  [EVAL] val_loss={val_loss:.4f}, val_ppl={val_ppl:.2f}")
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_dir = ckpt_dir / "best"
                    best_dir.mkdir(exist_ok=True)
                    _save_checkpoint(best_dir, model, optimizer, config, global_step,
                                     total_loss, total_tokens, train_file, tokenizer,
                                     args, device, val_loss=val_loss, tag="best")

    elapsed = time.time() - start_time
    print(f"\n[TRAIN] Training complete in {elapsed:.1f}s "
          f"({total_tokens/elapsed:.0f} tokens/s)")

    # ── Final evaluation ─────────────────────────────────
    val_loss, val_ppl = _evaluate(model, val_ids, config, device, max_len)
    print(f"\n{'='*60}")
    print(f"[RESULT] Steps: {global_step}")
    print(f"[RESULT] Tokens: {total_tokens:,}")
    print(f"[RESULT] Final train loss: {total_loss:.4f}")
    print(f"[RESULT] Val loss: {val_loss:.4f}")
    print(f"[RESULT] Val perplexity: {val_ppl:.2f}")
    print(f"[RESULT] Best val loss: {best_val_loss:.4f}")
    print(f"{'='*60}")

    # ── Save final model ──────────────────────────────────
    final_dir = work_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    _save_checkpoint(final_dir, model, optimizer, config, global_step,
                     total_loss, total_tokens, train_file, tokenizer, args,
                     device, val_loss=val_loss, tag="final")
    print(f"\n[SAVE] Final model: {final_dir}")

    # ── Save model summary ───────────────────────────────
    summary = {
        "model": "silverwing",
        "architecture": {
            "n_layers": config.n_layers,
            "n_heads": config.n_heads,
            "n_kv_heads": config.n_kv_heads,
            "d_model": config.d_model,
            "hidden_size": config.hidden_size,
            "vocab_size": config.vocab_size,
            "max_position_embeddings": config.max_position_embeddings,
            "tie_word_embeddings": config.tie_word_embeddings,
        },
        "training": {
            "steps": global_step,
            "batch_size": args.batch_size,
            "grad_accum": grad_accum,
            "max_seq_len": max_len,
            "lr": args.lr,
            "warmup_steps": warmup_steps,
            "total_tokens": total_tokens,
            "train_loss": total_loss,
            "val_loss": val_loss,
            "val_perplexity": val_ppl,
            "best_val_loss": best_val_loss,
        },
        "config_hash": compute_hash(str(final_dir / "config.json")),
        "torch_version": torch.__version__,
    }
    with open(work_dir / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    return model, tokenizer


def _save_checkpoint(directory: Path, model: SilverwingModel,
                     optimizer: torch.optim.Optimizer, config: ModelConfig,
                     step: int, train_loss: float, total_tokens: int,
                     train_file: str, tokenizer: BPETokenizer,
                     args: argparse.Namespace, device: torch.device,
                     val_loss: float = None, tag: str = None):
    """Save a training checkpoint with model, optimizer, config, and metadata."""
    directory.mkdir(parents=True, exist_ok=True)

    # Save model weights
    try:
        from safetensors.torch import save_file
        tensors = {}
        seen_data_ptrs = set()
        for k, v in model.state_dict().items():
            v_contig = v.contiguous().cpu()
            # Handle tied weights by cloning
            ptr = v_contig.data_ptr()
            if ptr in seen_data_ptrs:
                v_contig = v_contig.clone()
            seen_data_ptrs.add(ptr)
            tensors[k] = v_contig
        save_file(tensors, str(directory / "model.safetensors"))
    except ImportError:
        torch.save(model.state_dict(), str(directory / "model.pt"))

    # Save optimizer state
    torch.save({
        "global_step": step,
        "total_tokens": total_tokens,
        "optimizer": optimizer.state_dict(),
    }, str(directory / "optimizer.pt"))

    # Save model config
    with open(directory / "config.json", "w") as f:
        json.dump(asdict(config), f, indent=2)

    # Save tokenizer manifest
    tok_manifest = {
        "vocab_size": tokenizer.vocab_size,
        "special_tokens": {
            "<pad>": tokenizer.pad_token_id,
            "<bos>": tokenizer.bos_token_id,
            "<eos>": tokenizer.eos_token_id,
            "<unk>": tokenizer.unk_token_id,
        },
        "dataset_sha256": compute_hash(train_file),
    }
    with open(directory / "tokenizer_manifest.json", "w") as f:
        json.dump(tok_manifest, f, indent=2)

    # Save training metadata
    model_file = "model.safetensors" if (directory / "model.safetensors").exists() else "model.pt"
    meta = {
        "step": step,
        "tag": tag or "checkpoint",
        "train_loss": train_loss,
        "val_loss": val_loss,
        "total_tokens": total_tokens,
        "learning_rate": optimizer.param_groups[0]["lr"],
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "max_seq_len": args.max_seq_len,
        "model_sha256": compute_hash(str(directory / model_file)),
        "torch_version": torch.__version__,
        "seed": args.seed,
    }
    with open(directory / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)


def _evaluate(model: SilverwingModel, val_ids: list, config: ModelConfig,
              device: torch.device, max_len: int) -> tuple[float, float]:
    """Evaluate model on validation data, return (loss, perplexity)."""
    model.eval()
    val_loss = 0.0
    val_count = 0
    with torch.no_grad():
        for i in range(0, min(len(val_ids), max_len * 10), max_len + 1):
            batch = torch.tensor(
                val_ids[i : i + max_len + 1], dtype=torch.long, device=device
            )
            if len(batch) < 2:
                break
            input_ids = batch[:-1].unsqueeze(0)
            labels = batch[1:].unsqueeze(0)
            outputs = model(input_ids, labels=labels)
            val_loss += outputs["loss"].item()
            val_count += 1
    model.train()
    avg_val_loss = val_loss / max(val_count, 1)
    val_ppl = math.exp(min(avg_val_loss, 20.0))
    return avg_val_loss, val_ppl


def evaluate(args):
    """Evaluate a checkpoint."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    ckpt_dir = Path(args.checkpoint)
    if not ckpt_dir.exists():
        print(f"[ERROR] Checkpoint not found: {ckpt_dir}")
        sys.exit(1)

    # Load config
    with open(ckpt_dir / "config.json") as f:
        config = ModelConfig(**json.load(f))

    # Load model
    model = SilverwingModel(config).to(device)
    model_file = ckpt_dir / "model.safetensors"
    if model_file.exists():
        from safetensors.torch import load_file
        state = load_file(str(model_file))
    else:
        model_file = ckpt_dir / "model.pt"
        state = torch.load(str(model_file), map_location=device)
    model.load_state_dict(state, strict=False)
    print(f"[EVAL] Loaded checkpoint: {ckpt_dir}")
    print(f"[EVAL] Parameters: {model.num_parameters():,}")

    # Load tokenizer
    tok_path = ckpt_dir / "tokenizer.json"
    if tok_path.exists():
        tokenizer = BPETokenizer.from_file(str(tok_path))
    else:
        tok_path = Path("/kaggle/working/silverwing/tokenizer/tokenizer.json")
        if tok_path.exists():
            tokenizer = BPETokenizer.from_file(str(tok_path))
        else:
            print("[EVAL] Training tokenizer for evaluation...")
            train_file, _ = get_training_data(Path("/kaggle/working/silverwing"))
            tokenizer = BPETokenizer.train_from_text([train_file])

    # Load data
    _, val_file = get_training_data(Path("/kaggle/working/silverwing"))
    with open(val_file, "r", encoding="utf-8", errors="replace") as f:
        val_text = f.read()
    val_ids = tokenizer.encode(val_text)

    max_len = min(config.max_position_embeddings, args.max_seq_len)
    val_loss, val_ppl = _evaluate(model, val_ids, config, device, max_len)

    # Text generation test
    print("\n[EVAL] Generating sample text...")
    test_prompt = "The quick brown fox"
    input_ids = torch.tensor(
        [tokenizer.encode(test_prompt)], dtype=torch.long, device=device
    )
    model.eval()
    with torch.no_grad():
        generated = model.generate(input_ids, max_new_tokens=50, temperature=0.8)
    generated_text = tokenizer.decode(generated[0].cpu())
    print(f"Prompt: {test_prompt}")
    print(f"Output: {generated_text}\n")

    # Benchmark tests
    print("[EVAL] Running benchmark tests...")
    prompts = [
        "In the year",
        "The story began",
        "Science is",
        "Mathematics is",
        "The meaning of life is",
    ]
    for prompt in prompts:
        ids = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long, device=device)
        with torch.no_grad():
            generated = model.generate(ids, max_new_tokens=30, temperature=0.8)
        text = tokenizer.decode(generated[0].cpu())
        continuation = text[len(prompt):].strip()
        print(f"  '{prompt}' → '{continuation}'")

    print(f"\n[RESULT] Validation loss: {val_loss:.4f}")
    print(f"[RESULT] Validation perplexity: {val_ppl:.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train Silverwing language model"
    )
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=8)
    parser.add_argument("--max_seq_len", type=int, default=1024)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--warmup_ratio", type=float, default=0.05)
    parser.add_argument("--grad_clip", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log_steps", type=int, default=10)
    parser.add_argument("--save_steps", type=int, default=100)
    parser.add_argument("--eval_steps", type=int, default=100)

    # Model config
    parser.add_argument("--n_layers", type=int, default=12)
    parser.add_argument("--n_heads", type=int, default=12)
    parser.add_argument("--n_kv_heads", type=int, default=4)
    parser.add_argument("--d_model", type=int, default=768)
    parser.add_argument("--hidden_size", type=int, default=2560)
    parser.add_argument("--vocab_size", type=int, default=16384)

    # Modes
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--checkpoint", type=str, default="")

    args = parser.parse_args()

    if args.evaluate:
        evaluate(args)
    else:
        train(args)
