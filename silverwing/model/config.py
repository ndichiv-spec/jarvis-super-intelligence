"""Silverwing model configuration and architecture.

Level 1 — Silverwing-102M
A decoder-only causal transformer with GQA, RoPE, SwiGLU, RMSNorm.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ModelConfig:
    """All architectural constants for Silverwing."""

    # Tokenizer / embeddings
    vocab_size: int = 16384
    max_position_embeddings: int = 2048

    # Transformer
    n_layers: int = 12
    n_heads: int = 12
    n_kv_heads: int = 4          # GQA: grouped-query attention
    d_model: int = 768
    hidden_size: int = 2560      # MLP intermediate size
    multiple_of: int = 64
    norm_eps: float = 1e-5
    rope_theta: float = 10000.0

    # Flags
    use_bias: bool = False
    tie_word_embeddings: bool = True  # weight tying: LM head = input embeddings

    # Tokens
    pad_token_id: int = 0
    bos_token_id: int = 1
    eos_token_id: int = 2

    @property
    def head_dim(self) -> int:
        return self.d_model // self.n_heads

    @property
    def n_kv_heads_grouped(self) -> int:
        return self.n_heads // self.n_kv_heads  # 12 // 4 = 3 heads per KV group

    @property
    def n_kv_groups(self) -> int:
        """Alias for n_kv_heads_grouped — query heads per KV group (GQA ratio)."""
        return self.n_heads // self.n_kv_heads

    @classmethod
    def from_json(cls, path: str | Path) -> "ModelConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        m = data.get("model", data)
        return cls(**{k: v for k, v in m.items() if k in cls.__dataclass_fields__})

    def to_json(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"model": {
                "vocab_size": self.vocab_size,
                "max_position_embeddings": self.max_position_embeddings,
                "n_layers": self.n_layers,
                "n_heads": self.n_heads,
                "n_kv_heads": self.n_kv_heads,
                "d_model": self.d_model,
                "hidden_size": self.hidden_size,
                "multiple_of": self.multiple_of,
                "norm_eps": self.norm_eps,
                "rope_theta": self.rope_theta,
                "use_bias": self.use_bias,
                "tie_word_embeddings": self.tie_word_embeddings,
                "pad_token_id": self.pad_token_id,
                "bos_token_id": self.bos_token_id,
                "eos_token_id": self.eos_token_id,
            }}, f, indent=2)


def estimate_parameters(cfg: ModelConfig) -> int:
    """Rough parameter count for a given config."""
    d = cfg.d_model
    H = cfg.hidden_size
    n = cfg.n_layers
    V = cfg.vocab_size
    # Embeddings: V * d  (tied, so no separate LM head)
    emb = V * d
    # Each layer: attention + MLP + norms
    # QKV: d * (d + 2*d/n_heads_per_q * n_kv_heads) ≈ d^2 * (n_heads + 2*n_kv_heads/n_heads)
    # Simplified: d*d for q, d*d*n_kv_heads/n_heads * 2 for k,v
    q = d * d
    kv = d * d * cfg.n_kv_heads / cfg.n_heads * 2
    o = d * d
    gate_up = d * H * 2  # SwiGLU gate + up
    down = H * d
    norm = d * 2  # two RMSNorms per layer
    layer_params = q + kv + o + gate_up + down + norm
    layers = layer_params * n
    # Final RMSNorm
    final_norm = d
    return int(emb + layers + final_norm)
