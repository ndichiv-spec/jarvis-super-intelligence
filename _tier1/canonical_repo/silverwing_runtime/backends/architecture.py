"""Config-driven Silverwing decoder for the torch inference backend.

State-dict layout matches the training checkpoint 1:1 (keys below), so a
`strict` load against a checkpoint header can be validated exactly:

    embed_tokens.weight                 [vocab_size, d_model]
    layers.{i}.attention.q_proj.weight  [d_model, d_model]
    layers.{i}.attention.k_proj.weight  [d_model, n_kv_heads*head_dim]
    layers.{i}.attention.v_proj.weight  [d_model, n_kv_heads*head_dim]
    layers.{i}.attention.o_proj.weight  [d_model, d_model]
    layers.{i}.mlp.gate.weight          [hidden_size, d_model]
    layers.{i}.mlp.up.weight            [hidden_size, d_model]
    layers.{i}.mlp.down.weight          [d_model, hidden_size]
    layers.{i}.ln1.weight / ln2.weight  [d_model]
    norm_f.weight                       [d_model]
    lm_head.weight (tied)               [vocab_size, d_model]

Architecture (Silverwing-120M): 12 layers, d_model=1024, 16 Q heads, 4 KV
heads (GQA 4:1), head_dim=64, SwiGLU MLP=2176, RMSNorm, RoPE theta=10000,
vocab=8192, context=2048, weight tying, no bias -> 120,087,552 parameters.

The architecture is built purely from the registered model configuration; it
is NOT hard-coded around 120M (section 27).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import torch
from torch import nn

CONFIG_FIELDS = {
    "vocab_size",
    "max_position_embeddings",
    "n_layers",
    "n_heads",
    "n_kv_heads",
    "d_model",
    "hidden_size",
    "multiple_of",
    "norm_eps",
    "rope_theta",
    "use_bias",
    "tie_word_embeddings",
    "pad_token_id",
    "bos_token_id",
    "eos_token_id",
}


@dataclass
class ModelConfig:
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelConfig":
        payload = data.get("model", data) if isinstance(data.get("model"), dict) else data
        kwargs = {k: v for k, v in payload.items() if k in CONFIG_FIELDS}
        return cls(**kwargs)

    @classmethod
    def from_json(cls, path: str | Path) -> "ModelConfig":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if k in CONFIG_FIELDS}


def count_parameters(model: nn.Module) -> int:
    """Parameter count with weight tying de-duplicated (unique tensors only)."""
    return sum(p.numel() for p in {id(p): p for p in model.parameters()}.values())


class RMSNorm(nn.Module):
    """Root-mean-square normalisation (computed in fp32 for stability)."""

    def __init__(self, hidden_size: int, eps: float = 1e-5):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(hidden_size))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        with torch.autocast(device_type=x.device.type, enabled=False):
            x_f = x.float()
            variance = x_f.pow(2).mean(-1, keepdim=True)
            x_norm = x_f * torch.rsqrt(variance + self.eps)
        return self.weight * x_norm.to(x.dtype)


class RotaryEmbedding(nn.Module):
    """Interleaved RoPE precomputation (theta base configurable)."""

    def __init__(self, dim: int, base: float = 10000.0, max_len: int = 2048):
        super().__init__()
        self.dim = dim
        self.base = base
        self.register_buffer(
            "cos",
            self._build(max_len)[0],
            persistent=False,
        )
        self.register_buffer("sin", self._build(max_len)[1], persistent=False)

    def _build(self, seq_len: int) -> tuple[torch.Tensor, torch.Tensor]:
        theta = 1.0 / (self.base ** (torch.arange(0, self.dim, 2) / self.dim))
        freqs = torch.outer(torch.arange(seq_len).float(), theta)
        cos = torch.zeros(seq_len, self.dim)
        sin = torch.zeros(seq_len, self.dim)
        cos[:, 0::2] = torch.cos(freqs)
        cos[:, 1::2] = torch.cos(freqs)
        sin[:, 0::2] = torch.sin(freqs)
        sin[:, 1::2] = torch.sin(freqs)
        return cos, sin

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        seq_len = x.shape[-2]
        cos = self.cos[:seq_len].unsqueeze(0).unsqueeze(0).to(x.dtype)
        sin = self.sin[:seq_len].unsqueeze(0).unsqueeze(0).to(x.dtype)
        return cos, sin


def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x[..., : x.shape[-1] // 2], x[..., x.shape[-1] // 2 :]
    return torch.cat((-x2, x1), dim=-1)


def _apply_rope(q: torch.Tensor, k: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor):
    q_emb = q * cos + _rotate_half(q) * sin
    k_emb = k * cos + _rotate_half(k) * sin
    return q_emb, k_emb


class Attention(nn.Module):
    """Grouped-query attention with RoPE (causal)."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.n_heads = config.n_heads
        self.n_kv_heads = config.n_kv_heads
        self.head_dim = config.head_dim
        self.n_kv_groups = self.n_heads // self.n_kv_heads
        self.q_proj = nn.Linear(config.d_model, config.n_heads * self.head_dim, bias=config.use_bias)
        self.k_proj = nn.Linear(
            config.d_model, config.n_kv_heads * self.head_dim, bias=config.use_bias
        )
        self.v_proj = nn.Linear(
            config.d_model, config.n_kv_heads * self.head_dim, bias=config.use_bias
        )
        self.o_proj = nn.Linear(
            config.n_heads * self.head_dim, config.d_model, bias=config.use_bias
        )
        self.rowpe = RotaryEmbedding(self.head_dim, config.rope_theta, config.max_position_embeddings)

    def full_forward(
        self, x: torch.Tensor, mask: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        B, T, _ = x.shape
        q = self.q_proj(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, T, self.n_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, T, self.n_kv_heads, self.head_dim).transpose(1, 2)
        cos, sin = self.rowpe(x)
        q, k = _apply_rope(q, k, cos, sin)
        k_rep = k.repeat_interleave(self.n_kv_groups, dim=1)
        v_rep = v.repeat_interleave(self.n_kv_groups, dim=1)
        scores = torch.matmul(q, k_rep.transpose(-2, -1)) / math.sqrt(self.head_dim)
        scores = scores.masked_fill(mask[:, :, :T, :T] == 0, float("-inf"))
        attn = torch.softmax(scores, dim=-1)
        out = torch.matmul(attn, v_rep).transpose(1, 2).contiguous().view(
            B, T, self.n_heads * self.head_dim
        )
        return self.o_proj(out), k, v

    def step(self, x: torch.Tensor, kc: torch.Tensor, vc: torch.Tensor, pos: int):
        """One-token step against cached keys/values.

        Returns ``(out, kc, vc)`` where ``kc``/``vc`` are the append caches.
        """
        n_kv = self.n_kv_heads
        hd = self.head_dim
        k = self.k_proj(x).view(1, 1, n_kv, hd).transpose(1, 2)
        v = self.v_proj(x).view(1, 1, n_kv, hd).transpose(1, 2)
        cos = self.rowpe.cos[pos].unsqueeze(0).unsqueeze(0).unsqueeze(0).to(x.dtype)
        sin = self.rowpe.sin[pos].unsqueeze(0).unsqueeze(0).unsqueeze(0).to(x.dtype)
        q = self.q_proj(x).view(1, 1, self.n_heads, hd).transpose(1, 2)
        q, k = _apply_rope(q, k, cos, sin)
        kc = torch.cat([kc, k], dim=2)
        vc = torch.cat([vc, v], dim=2)
        k_rep = kc.repeat_interleave(self.n_kv_groups, dim=1)
        v_rep = vc.repeat_interleave(self.n_kv_groups, dim=1)
        scores = torch.matmul(q, k_rep.transpose(-2, -1)) / math.sqrt(hd)
        attn = torch.softmax(scores, dim=-1)
        out = torch.matmul(attn, v_rep).transpose(1, 2).contiguous().view(
            1, 1, self.n_heads * hd
        )
        return self.o_proj(out), kc, vc


class SwiGLUMLP(nn.Module):
    def __init__(self, d_model: int, hidden_size: int, multiple_of: int = 64, use_bias: bool = False):
        super().__init__()
        hidden_size = multiple_of * ((hidden_size + multiple_of - 1) // multiple_of)
        self.gate = nn.Linear(d_model, hidden_size, bias=use_bias)
        self.up = nn.Linear(d_model, hidden_size, bias=use_bias)
        self.down = nn.Linear(hidden_size, d_model, bias=use_bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.down(torch.sigmoid(self.gate(x)) * self.up(x))


class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.attention = Attention(config)
        self.mlp = SwiGLUMLP(config.d_model, config.hidden_size, config.multiple_of, config.use_bias)
        self.ln1 = RMSNorm(config.d_model, config.norm_eps)
        self.ln2 = RMSNorm(config.d_model, config.norm_eps)

    def full_forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        attn_out, _, _ = self.attention.full_forward(self.ln1(x), mask)
        x = x + attn_out
        return x + self.mlp(self.ln2(x))

    def step(self, x: torch.Tensor, kc: torch.Tensor, vc: torch.Tensor, pos: int):
        out, kc, vc = self.attention.step(self.ln1(x), kc, vc, pos)
        x = x + out
        return x + self.mlp(self.ln2(x)), kc, vc


class SilverwingDecoder(nn.Module):
    """Decoder-only causal transformer built from a :class:`ModelConfig`."""

    config: ModelConfig

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.embed_tokens = nn.Embedding(config.vocab_size, config.d_model)
        self.embed_tokens.weight.requires_grad_(False)
        self.layers = nn.ModuleList([TransformerBlock(config) for _ in range(config.n_layers)])
        self.norm_f = RMSNorm(config.d_model, config.norm_eps)
        if config.tie_word_embeddings:
            self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)
            self.lm_head.weight = self.embed_tokens.weight
        else:
            self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

    @property
    def device(self) -> str:
        return str(next(self.parameters()).device)

    def _causal_mask(self, seq_len: int, device: str) -> torch.Tensor:
        mask = torch.tril(torch.ones(seq_len, seq_len, device=device, dtype=torch.bool))
        return mask.unsqueeze(0).unsqueeze(0)

    def full_forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        x = self.embed_tokens(input_ids) * math.sqrt(self.config.d_model)
        mask = self._causal_mask(x.shape[1], x.device)
        for layer in self.layers:
            x = layer.full_forward(x, mask)
        return self.lm_head(self.norm_f(x))

    def step(self, input_id: torch.Tensor, kvc: list[tuple[torch.Tensor, torch.Tensor]], pos: int):
        """One-token forward with KV caching.

        Returns ``(logits_last, kvc)``. ``input_id`` shape [1]. ``kvc`` is a
        list of ``(kc, vc)`` per layer (may be fresh empties).
        """
        x = self.embed_tokens(input_id.unsqueeze(0)).unsqueeze(1) * math.sqrt(
            self.config.d_model
        )
        new_kvc: list[tuple[torch.Tensor, torch.Tensor]] = []
        for i, layer in enumerate(self.layers):
            kc, vc = kvc[i]
            if kc is None:
                kc = torch.zeros(1, self.config.n_kv_heads, 0, self.config.head_dim, device=x.device)
                vc = torch.zeros(1, self.config.n_kv_heads, 0, self.config.head_dim, device=x.device)
            x, kc, vc = layer.step(x, kc, vc, pos)
            new_kvc.append((kc, vc))
        out = self.lm_head(self.norm_f(x))
        return out[:, 0, :], new_kvc


def expected_parameter_count(config: ModelConfig) -> int:
    """Closed-form parameter count for the configured decoder.

    Counts each unique tensor once (embedding shared with the tied LM head):
    ``vocab*d`` embeddings + per-layer attention/MLP/norms + final norm.
    """
    d = config.d_model
    head_dim = config.head_dim
    kv_dim = config.n_kv_heads * head_dim
    if config.use_bias:
        attn = 2 * (d * d + d) + 2 * (kv_dim * d + kv_dim)
    else:
        attn = 2 * d * d + 2 * kv_dim * d
    rounded = config.multiple_of * (
        (config.hidden_size + config.multiple_of - 1) // config.multiple_of
    )
    if config.use_bias:
        mlp = 2 * (rounded * d + rounded) + d * rounded + d
    else:
        mlp = 2 * rounded * d + d * rounded
    embeds = config.vocab_size * d * (1 if config.tie_word_embeddings else 2)
    return embeds + config.n_layers * (2 * d + attn + mlp) + d


def build_silverwing(config: ModelConfig) -> SilverwingDecoder:
    """Construct the decoder and force-validate the exact architecture.

    Parameter identity (tied embedding shared with the LM head) must hold
    against the closed-form count for the configured architecture.
    """
    model = SilverwingDecoder(config)
    actual = count_parameters(model)
    expected = expected_parameter_count(config)
    if actual != expected:
        raise ArchitectureError(
            f"constructed parameter count {actual} != expected tied-embedding "
            f"count {expected}"
        )
    return model


class ArchitectureError(RuntimeError):
    pass


# Re-export the field list used by schema validation.
def serialize_config(config: ModelConfig) -> dict[str, Any]:
    return {f: getattr(config, f) for f in fields(ModelConfig)}