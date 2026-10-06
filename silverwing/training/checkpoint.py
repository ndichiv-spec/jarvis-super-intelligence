"""Checkpoint save/load and state management for Silverwing."""
from __future__ import annotations

import os
import json
import shutil
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import torch

logger = logging.getLogger(__name__)


@dataclass
class CheckpointMetadata:
    """Metadata stored alongside every checkpoint.

    Per the Silverwing directive, EVERY checkpoint must contain:
    model weights, optimizer state, scheduler state, global step,
    training tokens, dataset version, tokenizer version,
    model configuration, random seed, metrics.
    """
    global_step: int
    tokens_seen: int
    epoch: int
    dataset_hash: str
    tokenizer_hash: str
    model_config: dict
    optimizer_config: dict
    scheduler_config: dict
    learning_rate: float
    train_loss: float
    val_loss: Optional[float] = None
    perplexity: Optional[float] = None
    random_seed: int = 42
    model_name: str = "Silverwing-102M"
    torch_version: str = ""
    python_version: str = ""
    device: str = "cpu"


class CheckpointManager:
    """Manages checkpoint saving, loading, and retention."""

    def __init__(self, checkpoint_dir: str, keep_last_n: int = 3,
                 save_every_steps: int = 100):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.keep_last_n = keep_last_n
        self.save_every_steps = save_every_steps

    def should_save(self, global_step: int) -> bool:
        return global_step > 0 and global_step % self.save_every_steps == 0

    def save(self, model, optimizer, scheduler, state: CheckpointMetadata,
             rng_state: dict | None = None) -> str:
        """Save a full checkpoint to disk."""
        step_dir = self.checkpoint_dir / f"step-{state.global_step}"
        step_dir.mkdir(parents=True, exist_ok=True)

        # Model weights (safetensors for weights, but we use torch.save for full state)
        model_path = step_dir / "model.safetensors"
        # Save model state dict as safetensors
        try:
            from safetensors.torch import save_file
            # Convert state dict to contiguous format
            tensors = {k: v.contiguous() for k, v in model.state_dict().items()}
            save_file(tensors, str(model_path))
        except ImportError:
            # Fallback to torch.save if safetensors not available
            model_path = step_dir / "model.safetensors"
            torch.save(model.state_dict(), str(step_dir / "model.pt"))

        # Optimizer state
        opt_path = step_dir / "optimizer.pt"
        torch.save({
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict() if scheduler else None,
        }, str(opt_path))

        # RNG state
        if rng_state is not None:
            torch.save({"rng_state": rng_state}, str(step_dir / "rng_state.pt"))

        # Metadata
        meta_path = step_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(state.__dict__, f, indent=2, default=str)

        # Clean up old checkpoints
        self._cleanup()

        logger.info(f"Checkpoint saved: {step_dir}")
        return str(step_dir)

    def load(self, model, optimizer=None, scheduler=None,
             checkpoint_path: str | None = None, device: str = "cpu") -> CheckpointMetadata:
        """Load a checkpoint from disk."""
        if checkpoint_path is None:
            # Find the latest checkpoint
            checkpoints = sorted(self.checkpoint_dir.glob("step-*"),
                                 key=lambda p: int(p.name.split("-")[1]))
            if not checkpoints:
                raise FileNotFoundError("No checkpoints found")
            checkpoint_path = str(checkpoints[-1])

        checkpoint_path = Path(checkpoint_path)
        logger.info(f"Loading checkpoint from {checkpoint_path}")

        # Load model
        model_file = checkpoint_path / "model.safetensors"
        if model_file.exists():
            from safetensors.torch import load_file
            state_dict = load_file(str(model_file))
            model.load_state_dict(state_dict, strict=False)
        else:
            # Fallback to .pt
            model_file = checkpoint_path / "model.pt"
            state_dict = torch.load(model_file, map_location=device)
            model.load_state_dict(state_dict, strict=False)

        # Load optimizer and scheduler
        if optimizer is not None:
            opt_path = checkpoint_path / "optimizer.pt"
            if opt_path.exists():
                opt_data = torch.load(opt_path, map_location=device, weights_only=False)
                optimizer.load_state_dict(opt_data["optimizer"])
                if scheduler is not None and opt_data.get("scheduler"):
                    scheduler.load_state_dict(opt_data["scheduler"])

        # Load RNG state
        rng_path = checkpoint_path / "rng_state.pt"
        rng_state = None
        if rng_path.exists():
            rng_data = torch.load(rng_path, map_location=device, weights_only=False)
            rng_state = rng_data.get("rng_state")

        # Load metadata
        meta_path = checkpoint_path / "metadata.json"
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_dict = json.load(f)
        metadata = CheckpointMetadata(**meta_dict)

        return metadata

    def _cleanup(self):
        """Remove old checkpoints beyond keep_last_n."""
        checkpoints = sorted(self.checkpoint_dir.glob("step-*"),
                            key=lambda p: int(p.name.split("-")[1]))
        while len(checkpoints) > self.keep_last_n:
            old = checkpoints.pop(0)
            shutil.rmtree(old, ignore_errors=True)
            logger.info(f"Removed old checkpoint: {old}")


def compute_file_hash(path: str, algorithm: str = "sha256") -> str:
    """Compute the hash of a file."""
    import hashlib
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_text_hash(text: str, algorithm: str = "sha256") -> str:
    """Compute the hash of a string."""
    import hashlib
    h = hashlib.new(algorithm)
    h.update(text.encode("utf-8"))
    return h.hexdigest()
