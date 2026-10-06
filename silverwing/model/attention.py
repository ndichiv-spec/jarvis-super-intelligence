"""Multi-head attention with Grouped-Query Attention (GQA).

In GQA, multiple query heads share a single set of key/value heads.
For Silverwing-102M: 12 query heads, 4 key/value heads (3:1 ratio).
"""
import math
from typing import Optional

import torch
from torch import nn

from silverwing.model.rotary import RotaryEmbedding, apply_rotary_pos_emb


class Attention(nn.Module):
    """Causal multi-head attention with GQA and RoPE."""

    def __init__(self, config):
        super().__init__()
        self.n_heads = config.n_heads
        self.n_kv_heads = config.n_kv_heads
        self.head_dim = config.d_model // config.n_heads
        self.n_kv_groups = self.n_heads // self.n_kv_heads  # 3 query heads per KV group

        # Q projection: d_model -> n_heads * head_dim
        self.q_proj = nn.Linear(config.d_model, self.n_heads * self.head_dim,
                                bias=config.use_bias)
        # K, V projections: d_model -> n_kv_heads * head_dim each
        self.k_proj = nn.Linear(config.d_model, self.n_kv_heads * self.head_dim,
                                bias=config.use_bias)
        self.v_proj = nn.Linear(config.d_model, self.n_kv_heads * self.head_dim,
                                bias=config.use_bias)
        # Output projection
        self.o_proj = nn.Linear(self.n_heads * self.head_dim, config.d_model,
                                bias=config.use_bias)

        self.roPE = RotaryEmbedding(self.head_dim, base=config.rope_theta)

        self.dropout = nn.Dropout(0.0)  # only used during training config

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None):
        """x: [batch, seq_len, d_model] -> same shape.

        mask: [batch, 1, seq_len, seq_len] causal mask or None.
        """
        B, T, _ = x.shape

        # Project
        q = self.q_proj(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)    # [B, n_heads, T, head_dim]
        k = self.k_proj(x).view(B, T, self.n_kv_heads, self.head_dim).transpose(1, 2)  # [B, n_kv_heads, T, head_dim]
        v = self.v_proj(x).view(B, T, self.n_kv_heads, self.head_dim).transpose(1, 2)  # [B, n_kv_heads, T, head_dim]

        # Apply RoPE
        cos, sin = self.roPE(q)
        q, k = apply_rotary_pos_emb(q, k, cos, sin)

        # Repeat K/V heads to match Q heads (GQA)
        # [B, n_kv_heads, T, head_dim] -> [B, n_heads, T, head_dim]
        k = k.repeat_interleave(self.n_kv_groups, dim=1)
        v = v.repeat_interleave(self.n_kv_groups, dim=1)

        # Scaled dot-product attention
        qk = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)  # [B, n_heads, T, T]

        if mask is not None:
            qk = qk.masked_fill(mask[:, :, :T, :T] == 0, float("-inf"))

        attn = torch.softmax(qk, dim=-1)  # [B, n_heads, T, T]
        out = torch.matmul(attn, v)  # [B, n_heads, T, head_dim]

        # Merge heads
        out = out.transpose(1, 2).contiguous().view(B, T, -1)  # [B, T, d_model]
        out = self.o_proj(out)
        return out
