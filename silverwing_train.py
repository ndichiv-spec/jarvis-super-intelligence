"""Silverwing Training Kernel --- Kaggle-compatible, self-contained.

Trains the Silverwing-102M decoder-only transformer from scratch on Kaggle.
Handles P100 GPU incompatibility by forcing CPU mode.

Architecture (Level 1):
    Layers:       12
    d_model:      768
    Q heads:      12
    KV heads:      4  (GQA, 3:1 ratio)
    MLP hidden:   2560 (SwiGLU)
    Position:      RoPE
    Norm:          RMSNorm
    Vocabulary:    16384
    Context:       2048
    Weight tying:  enabled
    ~102M params

Usage (Kaggle):
    Set Accelerator: GPU (the kernel will detect P100 and fall back to CPU)
    Set Internet: ON
    Push and run.

Usage (local):
    python silverwing_train.py                    # 1000 steps
    python silverwing_train.py --steps 100        # smoke test
    python silverwing_train.py --evaluate         # evaluate checkpoint
    python silverwing_train.py --evaluate --checkpoint /path/to/ckpt
    python silverwing_train.py --steps 2000 --resume   # resume from latest checkpoint
    python silverwing_train.py --resume --resume_from /path/to/ckpt

Usage (Kaggle):
    Push kernel, then set env vars RESUME_TRAINING=1 and TARGET_STEPS=2000
    in kernel settings to resume training from a checkpoint dataset.

Outputs (visible in Kaggle Output tab):
    /kaggle/working/silverwing/final/
        - model.safetensors          (trained weights)
        - config.json                (model configuration)
        - tokenizer.json             (BPE tokenizer)
        - metadata.json              (training metadata & hashes)
    /kaggle/working/silverwing/checkpoints/
        - step-{N}/                  (periodic checkpoints every 100 steps)
    /kaggle/working/silverwing/training_summary.json  (final report)
"""
from __future__ import annotations

# %% [markdown]
# ## 1. Install dependencies (idempotent)

# %% [code]
import importlib
import os
import platform
import subprocess
import sys

# == Pre-flight: detect P100 and force CPU BEFORE importing torch ======
# Tesla P100 (sm_60) is detected by torch.cuda.is_available() but PyTorch
# 2.10+cu128 has no compiled kernels for sm_60. We must hide the GPU
# BEFORE `import torch` so all operations run on CPU.
_p100_detected = False
try:
    _gpu_info = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        stderr=subprocess.DEVNULL, text=True, timeout=10
    ).strip()
    for _line in _gpu_info.split("\n"):
        _name = _line.strip()
        if "P100" in _name:
            _p100_detected = True
    if _p100_detected:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        print(f"[HARDWARE] P100 detected ({_gpu_info.split(chr(10))[0].strip()}) --- "
              "forcing CPU mode (sm_60 not supported by installed PyTorch)")
    else:
        print(f"[HARDWARE] GPU: {_gpu_info.split(chr(10))[0].strip()}")
except Exception:
    print("[HARDWARE] No NVIDIA GPU detected --- using CPU")


def _installed(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


_needs = []
if not _installed("tokenizers"):
    _needs.append("tokenizers")
if not _installed("safetensors"):
    _needs.append("safetensors")
if not _installed("torch"):
    _needs.append("torch")

if _needs:
    print("Installing dependencies:", _needs)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--no-cache-dir", *_needs],
        check=False,
    )
else:
    print("All dependencies already installed")


# %% [markdown]
# ## 2. Import torch and hardware report

# %% [code]
import torch

cuda_ok = torch.cuda.is_available()
if cuda_ok:
    try:
        _t = torch.randn(64, 64, device="cuda")
        _ = (_t @ _t).sum().item()
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    except Exception:
        cuda_ok = False
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        print("CUDA detected but kernels unavailable --- forcing CPU")

if not cuda_ok:
    print("Training on CPU --- 4 cores, will use float32")

import json
import math
import time
import hashlib
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict


# %% [markdown]
# ## 3. Silverwing Model Architecture (inline, self-contained)

# %% [code]
@dataclass
class ModelConfig:
    """Silverwing-102M architecture configuration."""
    vocab_size: int = 16384
    max_position_embeddings: int = 2048
    n_layers: int = 12
    n_heads: int = 12
    n_kv_heads: int = 4       # GQA: 12 query / 4 KV = 3:1 ratio
    d_model: int = 768
    hidden_size: int = 2560   # SwiGLU intermediate
    multiple_of: int = 64
    norm_eps: float = 1e-5
    rope_theta: float = 10000.0
    use_bias: bool = False
    tie_word_embeddings: bool = True  # LM head shares embedding weights
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
    """Estimate total parameter count."""
    d = config.d_model
    H = config.hidden_size
    nl = config.n_layers
    n_groups = config.n_kv_groups
    params = config.vocab_size * d  # tied embeddings
    layer_params = (d * d  # Q
                    + d * (d // n_groups)  # K
                    + d * (d // n_groups)  # V
                    + d * d  # O
                    + d * H * 2  # gate + up (SwiGLU)
                    + H * d  # down
                    + 2 * d)  # 2 RMSNorms
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
    """Sinusoidal rotary positional embeddings (RoPE)."""

    def __init__(self, dim: int, base: float = 10000.0):
        self.dim = dim
        self.base = base

    def __call__(self, seq_len: int, device: torch.device):
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


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2:]
    return torch.cat((-x2, x1), dim=-1)


def apply_rope(q, k, cos, sin):
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed


class Attention(torch.nn.Module):
    """Grouped-Query Attention (GQA)."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.n_heads = config.n_heads
        self.n_kv_heads = config.n_kv_heads
        self.head_dim = config.head_dim
        self.n_kv_groups = config.n_kv_groups

        self.q_proj = torch.nn.Linear(config.d_model, self.n_heads * self.head_dim, bias=config.use_bias)
        self.k_proj = torch.nn.Linear(config.d_model, self.n_kv_heads * self.head_dim, bias=config.use_bias)
        self.v_proj = torch.nn.Linear(config.d_model, self.n_kv_heads * self.head_dim, bias=config.use_bias)
        self.o_proj = torch.nn.Linear(self.n_heads * self.head_dim, config.d_model, bias=config.use_bias)
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
        gate = torch.sigmoid(self.gate(x)) * self.gate(x)
        up = self.up(x)
        return self.down(gate * up)


class TransformerBlock(torch.nn.Module):
    """Pre-norm transformer block with GQA and SwiGLU."""

    def __init__(self, config):
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
    """Silverwing decoder-only transformer with GQA, RoPE, RMSNorm, SwiGLU."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        self.embed_tokens = torch.nn.Embedding(config.vocab_size, config.d_model, config.pad_token_id)
        self.layers = torch.nn.ModuleList([TransformerBlock(config) for _ in range(config.n_layers)])
        self.norm_f = RMSNorm(config.d_model, config.norm_eps)

        self.lm_head = torch.nn.Linear(config.d_model, config.vocab_size, bias=False)
        if config.tie_word_embeddings:
            self.lm_head.weight = self.embed_tokens.weight

        self._init_weights()

    def _init_weights(self):
        for name, param in self.named_parameters():
            if param.dim() > 1:
                torch.nn.init.normal_(param, mean=0.0, std=0.02)

    def _make_causal_mask(self, seq_len, device):
        mask = torch.tril(torch.ones(seq_len, seq_len, device=device, dtype=torch.bool))
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
                ignore_index=self.config.pad_token_id,
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
            if next_id.item() == self.config.eos_token_id:
                break
        return input_ids


# %% [markdown]
# ## 4. BPE Tokenizer

# %% [code]
class BPETokenizer:
    """BPE tokenizer using HuggingFace tokenizers."""

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
        from tokenizers import Tokenizer
        tok = Tokenizer.from_file(path)
        return cls(tok)

    @classmethod
    def train_from_text(cls, text_files, vocab_size=16384):
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
            special_tokens=[("<pad>", 0), ("<bos>", 1), ("<eos>", 2), ("<unk>", 3)],
        )
        tokenizer.decoder = ByteLevelDecoder()

        trainer = BpeTrainer(
            vocab_size=vocab_size, min_frequency=2,
            special_tokens=["<pad>", "<bos>", "<eos>", "<unk>"],
            show_progress=True,
        )
        tokenizer.train(files=text_files, trainer=trainer)
        return cls(tokenizer)


# %% [markdown]
# ## 5. Data Pipeline --- download Project Gutenberg books

# %% [code]
GUTENBERG_BOOKS = [
    ("https://www.gutenberg.org/files/1342/1342-0.txt", "pride_prejudice.txt"),
    ("https://www.gutenberg.org/files/84/84-0.txt", "frankenstein.txt"),
    ("https://www.gutenberg.org/files/1661/1661-0.txt", "sherlock.txt"),
    ("https://www.gutenberg.org/files/11/11-0.txt", "alice.txt"),
]


def download_gutenberg_books(data_dir):
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
            print(f"  [OK] {name}: {len(content):,} chars")
        except Exception as e:
            print(f"  [FAIL] Failed {name}: {e}")
    return texts


def get_training_data(work_dir):
    """Download or load training data. Returns (train_file, val_file)."""
    data_dir = work_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    split_dir = data_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)

    train_file = split_dir / "train.txt"
    val_file = split_dir / "val.txt"

    if train_file.exists() and val_file.exists():
        print(f"[DATA] Found existing splits: {train_file}, {val_file}")
        return str(train_file), str(val_file)

    print("[DATA] Downloading training data from Project Gutenberg...")
    texts = download_gutenberg_books(data_dir)

    if not texts:
        # Fallback: try loading SFT dataset
        print("[DATA] Trying SFT dataset...")
        sft_candidates = [
            "/kaggle/input/jarvis-skills-sft/sft_skills.jsonl",
            "/kaggle/input/jarvis-sft/sft_skills.jsonl",
        ]
        for path in sft_candidates:
            if Path(path).exists():
                print(f"  Loading SFT data: {path}")
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            entry = json.loads(line)
                            if "messages" in entry:
                                for msg in entry["messages"]:
                                    texts.append(msg["content"])
                break

    if not texts:
        # Last resort: synthetic data
        print("[DATA] Using synthetic fallback data")
        sample = ("Silverwing is a decoder-only transformer language model. "
                  "It uses grouped-query attention, rotary positional embeddings, "
                  "SwiGLU activations, and RMSNorm. ") * 5000
        texts = [sample]

    all_text = "\n\n".join(texts)
    split_idx = int(len(all_text) * 0.98)
    train_text = all_text[:split_idx]
    val_text = all_text[split_idx:]

    with open(train_file, "w", encoding="utf-8") as f:
        f.write(train_text)
    with open(val_file, "w", encoding="utf-8") as f:
        f.write(val_text)

    total_chars = len(train_text) + len(val_text)
    print(f"[DATA] Total: {total_chars:,} chars (train: {len(train_text):,} val: {len(val_text):,})")
    return str(train_file), str(val_file)


def compute_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# %% [markdown]
# ## 6. Training utilities

# %% [code]
def get_lr(step, base_lr, warmup_steps, total_steps):
    """Cosine learning rate with linear warmup."""
    if step < warmup_steps:
        return base_lr * step / max(1, warmup_steps)
    progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
    return 0.5 * base_lr * (1 + math.cos(math.pi * progress))


def save_checkpoint(directory, model, optimizer, config, step, train_loss,
                    total_tokens, tokenizer, args, val_loss=None, tag="checkpoint"):
    """Save a full training checkpoint."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    # Model weights (safetensors, handling tied weights)
    try:
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
    except ImportError:
        torch.save(model.state_dict(), str(directory / "model.pt"))

    # Optimizer state
    torch.save({"global_step": step, "total_tokens": total_tokens,
                "optimizer": optimizer.state_dict()},
               str(directory / "optimizer.pt"))

    # Config
    with open(directory / "config.json", "w") as f:
        json.dump(asdict(config), f, indent=2)

    # Tokenizer manifest
    tok_manifest = {
        "vocab_size": tokenizer.vocab_size,
        "special_tokens": {"<pad>": 0, "<bos>": 1, "<eos>": 2, "<unk>": 3},
    }
    with open(directory / "tokenizer_manifest.json", "w") as f:
        json.dump(tok_manifest, f, indent=2)

    # Metadata
    model_file = "model.safetensors" if (directory / "model.safetensors").exists() else "model.pt"
    meta = {
        "step": step, "tag": tag, "train_loss": train_loss, "val_loss": val_loss,
        "total_tokens": total_tokens, "lr": optimizer.param_groups[0]["lr"],
        "batch_size": args.batch_size, "grad_accum": args.grad_accum,
        "max_seq_len": args.max_seq_len, "torch_version": torch.__version__,
        "seed": args.seed, "model_sha256": compute_hash(str(directory / model_file)),
    }
    with open(directory / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)


def evaluate_model(model, val_ids, config, device, max_len):
    """Evaluate perplexity on validation data."""
    model.eval()
    val_loss, val_count = 0.0, 0
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


# %% [markdown]
# ## 6b. Checkpoint loading (resume support)


def load_checkpoint(ckpt_path, model, optimizer, device):
    """Load model weights, optimizer state, and metadata from a checkpoint.

    Returns (config, global_step, total_tokens, metadata_dict).
    """
    ckpt_path = Path(ckpt_path)

    # Load config
    with open(ckpt_path / "config.json") as f:
        config = ModelConfig(**json.load(f))

    # Load model weights
    model_file = ckpt_path / "model.safetensors"
    if model_file.exists():
        from safetensors.torch import load_file
        state = load_file(str(model_file))
    else:
        model_file = ckpt_path / "model.pt"
        state = torch.load(str(model_file), map_location=device)
    model.load_state_dict(state, strict=False)

    # Load optimizer state (may not be included in shared checkpoints)
    opt_file = ckpt_path / "optimizer.pt"
    if opt_file.exists():
        opt_data = torch.load(str(opt_file), map_location=device, weights_only=False)
        if optimizer is not None:
            optimizer.load_state_dict(opt_data["optimizer"])
        step = opt_data.get("global_step", 0)
        total_tokens = opt_data.get("total_tokens", 0)
    else:
        print("[RESUME] Warning: optimizer.pt not found, "
              "optimizer will restart from scratch")
        opt_data = {}
        step = 0
        total_tokens = 0

    # Load metadata
    with open(ckpt_path / "metadata.json") as f:
        meta = json.load(f)

    # Prefer metadata for step/total_tokens if optimizer data is missing
    if not opt_data:
        step = meta.get("step", 0)
        total_tokens = meta.get("total_tokens", 0)

    print(f"[RESUME] Loaded checkpoint: step={step}, tokens={total_tokens:,}")
    return config, step, total_tokens, meta


# %% [markdown]
# ## 7. Main training loop

# %% [code]
def main():
    parser = argparse.ArgumentParser(description="Train Silverwing")
    parser.add_argument("--steps", type=int, default=2000)
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
    # Model config overrides
    parser.add_argument("--n_layers", type=int, default=12)
    parser.add_argument("--n_heads", type=int, default=12)
    parser.add_argument("--n_kv_heads", type=int, default=4)
    parser.add_argument("--d_model", type=int, default=768)
    parser.add_argument("--hidden_size", type=int, default=2560)
    parser.add_argument("--vocab_size", type=int, default=16384)
    parser.add_argument("--max_position_embeddings", type=int, default=2048)
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--checkpoint", type=str, default="")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from the latest checkpoint")
    parser.add_argument("--resume_from", type=str, default="",
                        help="Path to a specific checkpoint directory to resume from")
    args = parser.parse_args()

    work_dir = Path(os.environ.get("SILVERWING_WORK_DIR", "/kaggle/working/silverwing"))
    work_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # == Auto-scale for CPU: P100 detected -> CPU-only training ==========
    # The full Silverwing-102M (12L/768d) would take ~72h on a 4-core CPU.
    # On CPU we automatically switch to Silverwing-12M (6L/384d) which
    # trains in ~2-3h for 1000 steps while preserving the same architecture
    # features (GQA, RoPE, RMSNorm, SwiGLU, weight tying).
    if device.type == "cpu":
        print("[CONFIG] CPU detected --- using Silverwing-12M config for feasible training time")
        args.n_layers = 6
        args.n_heads = 8
        args.n_kv_heads = 2
        args.d_model = 384
        args.hidden_size = 1024
        args.vocab_size = 8192
        args.max_seq_len = 256
        args.max_position_embeddings = 1024
        args.grad_accum = 4
        print(f"  Scaled: {args.n_layers}L/{args.d_model}d/{args.n_heads}H/{args.n_kv_heads}KVH, "
              f"vocab={args.vocab_size}, seq_len={args.max_seq_len}, grad_accum={args.grad_accum}")
    else:
        print(f"[CONFIG] GPU detected --- using Silverwing-102M config")

    if args.evaluate:
        evaluate_checkpoint(args, work_dir, device)
        return

    # == Seed ============================================
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    # == Data ============================================
    train_file, val_file = get_training_data(work_dir)

    # == Tokenizer =======================================
    tok_dir = work_dir / "tokenizer"
    tok_dir.mkdir(parents=True, exist_ok=True)
    tok_path = tok_dir / "tokenizer.json"

    if tok_path.exists():
        print("[TOKENIZER] Loading existing tokenizer...")
        tokenizer = BPETokenizer.from_file(str(tok_path))
    else:
        # Check Kaggle input dataset for pre-trained tokenizer
        ds_tok = Path("/kaggle/input/silverwing-checkpoints/tokenizer/tokenizer.json")
        if ds_tok.exists():
            print(f"[TOKENIZER] Loading from dataset: {ds_tok}")
            tokenizer = BPETokenizer.from_file(str(ds_tok))
            tokenizer.save(str(tok_path))
        else:
            print(f"[TOKENIZER] Training BPE tokenizer (vocab_size={args.vocab_size})...")
            tokenizer = BPETokenizer.train_from_text([train_file], vocab_size=args.vocab_size)
            tokenizer.save(str(tok_path))
            print(f"[TOKENIZER] Saved: vocab_size={tokenizer.vocab_size}")

    # == Model ===========================================
    config = ModelConfig(vocab_size=min(tokenizer.vocab_size, args.vocab_size),
                         max_position_embeddings=args.max_position_embeddings,
                         n_layers=args.n_layers, n_heads=args.n_heads,
                         n_kv_heads=args.n_kv_heads, d_model=args.d_model,
                         hidden_size=args.hidden_size)

    model = SilverwingModel(config).to(device)
    n_params = model.num_parameters()
    est = estimate_parameters(config)

    model_name = "silverwing-102m" if config.n_layers == 12 and config.d_model == 768 else f"silverwing-{n_params // 1000000}m"

    print(f"\n{'='*60}")
    print(f"SILVERWING TRAINING --- {model_name.upper()}")
    print(f"{'='*60}")
    print(f"  Device:        {device}")
    print(f"  PyTorch:       {torch.__version__}")
    print(f"  Architecture:  {config.n_layers}L/{config.d_model}d/{config.n_heads}H/{config.n_kv_heads}KVH/GQA")
    print(f"  Parameters:    {n_params:,} (actual) / {est:,} (estimated)")
    print(f"  Vocab size:    {config.vocab_size}")
    print(f"  Context:       {config.max_position_embeddings}")
    print(f"  Weight tying:  {config.tie_word_embeddings}")
    print(f"  GQA ratio:     {config.n_kv_groups}:1 ({config.n_heads} Q / {config.n_kv_heads} KV)")
    print(f"  SwiGLU hidden: {config.hidden_size}")
    print(f"  LR:            {args.lr} -> cosine warmup {int(args.steps * args.warmup_ratio)} steps")
    print(f"  Batch:         {args.batch_size} x {args.grad_accum} = {args.batch_size * args.grad_accum} effective")
    print(f"  Seq len:       {min(config.max_position_embeddings, args.max_seq_len)}")
    print(f"  Steps:         {args.steps}")
    print(f"{'='*60}\n")

    # == Optimizer =======================================
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

    # == Tokenize ========================================
    print("[DATA] Tokenizing...")
    with open(train_file, "r", encoding="utf-8", errors="replace") as f:
        train_text = f.read()
    with open(val_file, "r", encoding="utf-8", errors="replace") as f:
        val_text = f.read()

    train_ids = tokenizer.encode(train_text)
    val_ids = tokenizer.encode(val_text) if val_text else train_ids[:10000]
    del train_text, val_text
    print(f"[DATA] Train: {len(train_ids):,} tokens | Val: {len(val_ids):,} tokens")

    # == Training loop ===================================
    max_len = min(config.max_position_embeddings, args.max_seq_len)
    grad_accum = args.grad_accum
    warmup_steps = max(1, int(args.steps * args.warmup_ratio))

    total_tokens = 0
    global_step = 0
    best_val_loss = float("inf")
    data_ptr = 0
    start_step = 0

    # == Resume from checkpoint =========================================
    if args.resume or args.resume_from:
        if args.resume_from:
            ckpt_path = Path(args.resume_from)
        else:
            # Auto-detect latest checkpoint:
            #   1. Kaggle input dataset (silverwing-checkpoints)
            #   2. Local working directory checkpoints
            candidates = [
                Path("/kaggle/input/silverwing-checkpoints"),
                work_dir / "checkpoints",
            ]
            ckpt_path = None
            for base in candidates:
                if base.exists():
                    steps = sorted(base.glob("step-*"), key=lambda p: int(p.name.split("-")[1]))
                    if steps:
                        ckpt_path = steps[-1]
                        break

        if ckpt_path and ckpt_path.exists():
            print(f"\n[RESUME] Loading checkpoint from {ckpt_path}")

            # Read config from checkpoint to ensure architecture matches
            with open(ckpt_path / "config.json") as f:
                ckpt_config = ModelConfig(**json.load(f))

            # Recreate model + optimizer with checkpoint config
            config = ckpt_config
            model = SilverwingModel(config).to(device)
            n_params = model.num_parameters()
            est = estimate_parameters(config)

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

            # Load weights + optimizer state + metadata in one pass
            _, ckpt_step, ckpt_tokens, meta = load_checkpoint(
                ckpt_path, model, optimizer, device
            )

            start_step = ckpt_step
            global_step = start_step
            total_tokens = ckpt_tokens
            max_len = min(config.max_position_embeddings, args.max_seq_len)
            data_ptr = int(total_tokens * (max_len + 1) / max_len) % max(1, len(train_ids))
            best_val_loss = meta.get("val_loss") or float("inf")

            # Update model name to reflect resumed architecture
            model_name = ("silverwing-102m" if config.n_layers == 12
                          and config.d_model == 768
                          else f"silverwing-{n_params // 1000000}m")

            print(f"[RESUME] Resuming from step {start_step}")
            print(f"[RESUME] Target: step {args.steps}  (+{args.steps - start_step} more steps)")
            print(f"[RESUME] total_tokens={total_tokens:,}, data_ptr={data_ptr}")
            print(f"[RESUME] best_val_loss={best_val_loss:.4f}")
        else:
            print("[RESUME] --resume specified but no checkpoint found; "
                  "starting from scratch")

    model.train()
    start_time = time.time()

    if start_step > 0:
        print(f"\nStarting training (resumed): step {start_step} -> {args.steps}\n")
    else:
        print(f"\nStarting training: {args.steps} steps\n")
    for step in range(start_step, args.steps):
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

        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        # Stability monitoring (read-only observation; does not change numerics)
        _g_nan = 0
        _g_inf = 0
        for _p in model.parameters():
            if _p.grad is not None:
                _g = _p.grad
                _g_nan += int(torch.isnan(_g).sum().item())
                _g_inf += int(torch.isinf(_g).sum().item())
        current_lr = get_lr(step, args.lr, warmup_steps, args.steps)
        for pg in optimizer.param_groups:
            pg["lr"] = current_lr
        optimizer.step()
        global_step += 1

        if global_step % args.log_steps == 0 or global_step == 1:
            elapsed = time.time() - start_time
            ppl = math.exp(min(total_loss, 20.0))
            tps = total_tokens / max(elapsed, 1)
            _metrics = {
                "step": global_step, "tokens": total_tokens,
                "train_loss": total_loss, "ppl": ppl, "lr": current_lr,
                "grad_norm": float(grad_norm),
                "grad_nan": _g_nan, "grad_inf": _g_inf,
                "tok_per_s": tps, "elapsed_s": elapsed,
            }
            with open(work_dir / "metrics.jsonl", "a") as _mf:
                _mf.write(json.dumps(_metrics) + "\n")
            print(f"  step {global_step:5d}/{args.steps} | loss {total_loss:.4f} | "
                  f"ppl {ppl:.2f} | lr {current_lr:.2e} | grad_norm {float(grad_norm):.4f} | "
                  f"nan {_g_nan} inf {_g_inf} | {tps:.0f} tok/s | {elapsed:.1f}s")

        if global_step % args.save_steps == 0:
            ckpt_dir = work_dir / "checkpoints" / f"step-{global_step}"
            save_checkpoint(ckpt_dir, model, optimizer, config, global_step,
                           total_loss, total_tokens, tokenizer, args, tag=f"step-{global_step}")

            if global_step % args.eval_steps == 0:
                vl, vp = evaluate_model(model, val_ids, config, device, max_len)
                print(f"  [EVAL] val_loss={vl:.4f}, val_ppl={vp:.2f}")
                if vl < best_val_loss:
                    best_val_loss = vl
                    best_dir = work_dir / "checkpoints" / "best"
                    save_checkpoint(best_dir, model, optimizer, config, global_step,
                                   total_loss, total_tokens, tokenizer, args,
                                   val_loss=vl, tag="best")

    elapsed = time.time() - start_time
    val_loss, val_ppl = evaluate_model(model, val_ids, config, device, max_len)

    # == Save final ======================================
    final_dir = work_dir / "final"
    save_checkpoint(final_dir, model, optimizer, config, global_step,
                    total_loss, total_tokens, tokenizer, args,
                    val_loss=val_loss, tag="final")

    print(f"\n{'='*60}")
    print(f"SILVERWING TRAINING COMPLETE")
    print(f"  Model:       {model_name}")
    print(f"  Steps:       {global_step}")
    print(f"  Tokens:      {total_tokens:,}")
    print(f"  Train loss:  {total_loss:.4f}")
    print(f"  Val loss:    {val_loss:.4f}")
    print(f"  Val PPL:     {val_ppl:.2f}")
    print(f"  Best val:    {best_val_loss:.4f}")
    print(f"  Time:        {elapsed:.1f}s ({total_tokens/elapsed:.0f} tok/s)")
    print(f"  Model:       {final_dir}")
    print(f"{'='*60}")

    # Save summary
    summary = {
        "model": model_name,
        "params": n_params,
        "steps": global_step,
        "tokens": total_tokens,
        "train_loss": total_loss,
        "val_loss": val_loss,
        "val_perplexity": val_ppl,
        "best_val_loss": best_val_loss,
        "elapsed_s": round(elapsed, 1),
        "device": str(device),
        "torch_version": torch.__version__,
    }
    with open(work_dir / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


def evaluate_checkpoint(args, work_dir, device):
    """Load a checkpoint and run evaluation."""
    ckpt_dir = Path(args.checkpoint or work_dir / "final")
    if not ckpt_dir.exists():
        print(f"[ERROR] Checkpoint not found: {ckpt_dir}")
        sys.exit(1)

    with open(ckpt_dir / "config.json") as f:
        config = ModelConfig(**json.load(f))

    model = SilverwingModel(config).to(device)
    model_file = ckpt_dir / "model.safetensors"
    if model_file.exists():
        from safetensors.torch import load_file
        model.load_state_dict(load_file(str(model_file)), strict=False)
    else:
        model.load_state_dict(torch.load(ckpt_dir / "model.pt", map_location=device), strict=False)
    print(f"[EVAL] Loaded: {ckpt_dir}")
    print(f"[EVAL] Parameters: {model.num_parameters():,}")

    # Load tokenizer
    tok_path = ckpt_dir / "tokenizer.json"
    if not tok_path.exists():
        tok_path = work_dir / "tokenizer" / "tokenizer.json"
    tokenizer = BPETokenizer.from_file(str(tok_path)) if tok_path.exists() else None

    if tokenizer:
        _, val_file = get_training_data(work_dir)
        with open(val_file, "r", encoding="utf-8", errors="replace") as f:
            val_text = f.read()
        val_ids = tokenizer.encode(val_text)
        max_len = min(config.max_position_embeddings, args.max_seq_len)
        vl, vp = evaluate_model(model, val_ids, config, device, max_len)
        print(f"\n[EVAL] Val loss: {vl:.4f} | Val PPL: {vp:.2f}")

        # Generation test
        print("\n[EVAL] Generation tests:")
        prompts = ["The quick brown fox", "In the year", "Science is",
                   "The story began", "Mathematics is"]
        for p in prompts:
            ids = torch.tensor([tokenizer.encode(p)], dtype=torch.long, device=device)
            with torch.no_grad():
                gen = model.generate(ids, max_new_tokens=40, temperature=0.8)
            print(f"  '{p}' -> '{tokenizer.decode(gen[0].cpu())}'")


if __name__ == "__main__":
    # Auto-resume from Kaggle checkpoint dataset if available.
    # This makes the kernel resume training without needing to pass
    # --resume explicitly as a kernel parameter.
    _ckpt_dir = Path("/kaggle/input/silverwing-checkpoints/step-1000")
    if _ckpt_dir.exists() and "--resume" not in sys.argv and "--resume_from" not in sys.argv:
        sys.argv.append("--resume")
        print("[STARTUP] Auto-detected checkpoint dataset, enabling --resume")

    # Environment variable support for Kaggle kernel settings.
    if os.environ.get("RESUME_TRAINING", "").lower() in ("1", "true", "yes"):
        if "--resume" not in sys.argv:
            sys.argv.append("--resume")
    _target_steps = os.environ.get("TARGET_STEPS")
    if _target_steps and "--steps" not in sys.argv:
        sys.argv.extend(["--steps", str(int(_target_steps))])
    main()
