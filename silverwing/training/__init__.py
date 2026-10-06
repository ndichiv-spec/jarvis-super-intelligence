"""Silverwing training package.

Contains the training loop, optimizer configuration, checkpoint management,
and evaluation utilities.
"""
from silverwing.training.train import train, evaluate
from silverwing.training.optimizer import get_optimizer, get_scheduler, TrainingState
from silverwing.training.checkpoint import CheckpointManager, CheckpointMetadata, compute_file_hash

__all__ = [
    "train",
    "evaluate",
    "get_optimizer",
    "get_scheduler",
    "TrainingState",
    "CheckpointManager",
    "CheckpointMetadata",
    "compute_file_hash",
]
