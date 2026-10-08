"""SwiGLU MLP for Silverwing.

SwiGLU(x) = Swish(x @ W_g) ⊗ (x @ W_u) @ W_d

where ⊗ is element-wise multiplication, and Swish(x) = x * sigmoid(x).
The intermediate dimension is rounded up to a multiple of `multiple_of`.
"""
import torch
from torch import nn


class SwiGLUMLP(nn.Module):
    """Gated linear layer with Swish activation and multiplication."""

    def __init__(self, d_model: int, hidden_size: int, multiple_of: int = 64,
                 use_bias: bool = False):
        super().__init__()
        # Round hidden_size up to the nearest multiple_of
        hidden_size = multiple_of * ((hidden_size + multiple_of - 1) // multiple_of)
        self.hidden_size = hidden_size

        # Gate projection (for the Swish gate)
        self.gate = nn.Linear(d_model, hidden_size, bias=use_bias)
        # Up projection
        self.up = nn.Linear(d_model, hidden_size, bias=use_bias)
        # Down projection
        self.down = nn.Linear(hidden_size, d_model, bias=use_bias)

    @staticmethod
    def _swish(x: torch.Tensor) -> torch.Tensor:
        return x * torch.sigmoid(x)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gate = self._swish(self.gate(x))
        up = self.up(x)
        return self.down(gate * up)

    def __repr__(self):
        return f"SwiGLUMLP(d_model→{self.hidden_size}→d_model, multiple_of check done)"
