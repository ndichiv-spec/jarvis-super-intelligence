"""Rotary Positional Embedding (RoPE) for Silverwing.

Implements the standard RoPE with configurable base frequency (rope_theta).
Applied to Q and K projections before attention.
"""
import torch
from torch import nn


def _rope_angles(seq_len: int, dim: int, base: float = 10000.0, device: str = "cpu"):
    """Precompute interleaved cos/sin for RoPE.

    Returns cos, sin of shape [seq_len, dim] where dim is interleaved as
    [cos_0, sin_0, cos_1, sin_1, ...].
    """
    # Compute the frequencies: theta_i = base^(-2i/dim)
    theta = 1.0 / (base ** (torch.arange(0, dim, 2, dtype=torch.float32, device=device) / dim))
    positions = torch.arange(seq_len, dtype=torch.float32, device=device)
    # freqs: [seq_len, dim/2]
    freqs = torch.outer(positions, theta)
    # Build interleaved cos/sin: [seq_len, dim]
    # Pattern: cos_0, sin_0, cos_1, sin_1, ...
    cos = torch.zeros(seq_len, dim, device=device, dtype=torch.float32)
    sin = torch.zeros(seq_len, dim, device=device, dtype=torch.float32)
    cos[:, 0::2] = torch.cos(freqs)
    cos[:, 1::2] = torch.cos(freqs)
    sin[:, 0::2] = torch.sin(freqs)
    sin[:, 1::2] = torch.sin(freqs)
    return cos, sin


class RotaryEmbedding(nn.Module):
    """RoPE: rotates query/key vectors element-wise."""

    def __init__(self, dim: int, base: float = 10000.0):
        super().__init__()
        self.dim = dim
        self.base = base

    def forward(self, x: torch.Tensor, seq_dim: int = 2) -> tuple[torch.Tensor, torch.Tensor]:
        """Return (cos, sin) tensors for the given sequence length.

        x: [batch, heads, seq_len, head_dim]
        Returns cos, sin: [1, 1, seq_len, head_dim]
        """
        seq_len = x.shape[seq_dim]
        cos, sin = _rope_angles(seq_len, self.dim, self.base, x.device)
        # Add batch and head dimensions
        cos = cos.unsqueeze(0).unsqueeze(0).to(x.dtype)  # [1, 1, seq_len, dim]
        sin = sin.unsqueeze(0).unsqueeze(0).to(x.dtype)
        return cos, sin


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    """Rotate half the dimensions: [x1, x2] -> [-x2, x1]."""
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2 :]
    return torch.cat((-x2, x1), dim=-1)


def apply_rotary_pos_emb(q: torch.Tensor, k: torch.Tensor,
                         cos: torch.Tensor, sin: torch.Tensor):
    """Apply RoPE to queries and keys.

    q, k: [batch, heads, seq_len, head_dim]
    cos, sin: [1, 1, seq_len, head_dim]

    Uses the standard formula:
        q_embed = q * cos + rotate_half(q) * sin
        k_embed = k * cos + rotate_half(k) * sin
    """
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed
