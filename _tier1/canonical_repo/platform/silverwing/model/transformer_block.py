"""A single Transformer decoder block: attention + MLP with residual + norm."""
import torch
from torch import nn

from silverwing.model.attention import Attention
from silverwing.model.mlp import SwiGLUMLP
from silverwing.model.normalization import RMSNorm


class TransformerBlock(nn.Module):
    """Pre-norm transformer block.

    x = x + Attention(RMSNorm(x))
    x = x + MLP(RMSNorm(x))
    """

    def __init__(self, config):
        super().__init__()
        self.attention = Attention(config)
        self.mlp = SwiGLUMLP(config.d_model, config.hidden_size,
                             config.multiple_of, config.use_bias)
        self.ln1 = RMSNorm(config.d_model, config.norm_eps)
        self.ln2 = RMSNorm(config.d_model, config.norm_eps)

    def forward(self, x: torch.Tensor, mask=None):
        # Self-attention sub-layer (pre-norm)
        x = x + self.attention(self.ln1(x), mask)
        # MLP sub-layer (pre-norm)
        x = x + self.mlp(self.ln2(x))
        return x
