"""Optimizer, scheduler, and learning-rate utilities for Silverwing."""
from __future__ import annotations

import math
import torch
from torch import nn
from torch.optim.lr_scheduler import LambdaLR


def get_optimizer(model: nn.Module, lr: float = 2e-4, weight_decay: float = 0.01,
                  betas: tuple = (0.9, 0.95), eps: float = 1e-8) -> torch.optim.Optimizer:
    """AdamW optimizer with no weight decay on bias/norm parameters.

    Returns a configured optimizer ready for training.
    """
    decay_params = []
    no_decay_params = []

    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        # No weight decay for biases, LayerNorm/RMSNorm weights, and embeddings
        if param.ndim < 2 or "norm" in name.lower() or "bias" in name.lower():
            no_decay_params.append(param)
        else:
            decay_params.append(param)

    param_groups = [
        {"params": decay_params, "weight_decay": weight_decay},
        {"params": no_decay_params, "weight_decay": 0.0},
    ]

    return torch.optim.AdamW(
        param_groups,
        lr=lr,
        betas=betas,
        eps=eps,
    )


def get_scheduler(optimizer: torch.optim.Optimizer,
                  name: str = "cosine_with_warmup",
                  num_warmup_steps: int = 100,
                  num_training_steps: int = 1000) -> LambdaLR:
    """Cosine annealing with linear warmup."""

    def lr_lambda(current_step: int) -> float:
        if current_step < num_warmup_steps:
            return float(current_step) / float(max(1, num_warmup_steps))
        progress = float(current_step - num_warmup_steps) / float(max(1, num_training_steps - num_warmup_steps))
        progress = min(1.0, max(0.0, progress))
        # Cosine annealing
        return 0.5 * (1.0 + math.cos(math.pi * progress))

    return LambdaLR(optimizer, lr_lambda=lr_lambda)


class TrainingState:
    """Track training state for checkpointing and recovery."""

    def __init__(self, global_step: int = 0, tokens_seen: int = 0,
                 epoch: int = 0, best_val_loss: float = float("inf")):
        self.global_step = global_step
        self.tokens_seen = tokens_seen
        self.epoch = epoch
        self.best_val_loss = best_val_loss

    def to_dict(self) -> dict:
        return {
            "global_step": self.global_step,
            "tokens_seen": self.tokens_seen,
            "epoch": self.epoch,
            "best_val_loss": self.best_val_loss,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrainingState":
        return cls(
            global_step=d.get("global_step", 0),
            tokens_seen=d.get("tokens_seen", 0),
            epoch=d.get("epoch", 0),
            best_val_loss=d.get("best_val_loss", float("inf")),
        )
