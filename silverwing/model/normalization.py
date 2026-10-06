"""RMSNorm — Silverwing uses RMSNorm instead of LayerNorm."""
import torch
import torch.nn as nn


class RMSNorm(nn.Module):
    """Root-mean-square layer normalisation.

    RMSNorm(x) = x / sqrt(mean(x^2) + eps) * gamma
    No bias parameter, no subtraction of mean.
    """

    def __init__(self, hidden_size: int, eps: float = 1e-5):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(hidden_size))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Use float32 for the norm computation for numerical stability
        with torch.autocast(device_type=x.device.type, enabled=False):
            x_f = x.float()
            variance = x_f.pow(2).mean(-1, keepdim=True)
            x_norm = x_f * torch.rsqrt(variance + self.eps)
        return self.weight * x_norm.to(x.dtype)

    def __repr__(self):
        return f"RMSNorm(dim={self.weight.numel()}, eps={self.eps})"
