"""Model manifest schema.

A ``model_manifest.json`` is the immutable identity document for one version
of a Silverwing model.  It carries every fact the runtime needs to acquire,
verify and load a model WITHOUT storing the weights in the platform repo.

Schema mirrors the example in the architecture specification (section 5).
All hashes are real artifact hashes; they are never fabricated.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

MANIFEST_FILENAME = "model_manifest.json"

# Allowed lifecycle statuses (section 33).
LIFECYCLE_STATUSES = (
    "training",
    "experimental",
    "evaluated",
    "approved",
    "active",
    "deprecated",
    "archived",
)

# Capabilities are declared ONLY when actually validated (section 17).
KNOWN_CAPABILITIES = (
    "text-generation",
    "chat",
    "reasoning",
    "coding",
    "math",
    "long-context",
    "vision",
    "image-generation",
    "tool-use",
    "embeddings",
)


class TokenizerSpec(BaseModel):
    version: str = "r2000-bpe"
    type: str = "bpe"
    vocab_size: int | None = None
    sha256: str = ""


class WeightsSpec(BaseModel):
    format: str = "safetensors"
    sha256: str = ""
    size_bytes: int | None = None
    config_sha256: str | None = None
    storage_uri: str = ""


class ModelManifest(BaseModel):
    """Immutable identity for one version of a Silverwing model."""

    model_id: str
    version: str = "v1"
    revision: str = "r1"
    architecture: str = "Silverwing Decoder"
    parameter_count: int = 0
    context_length: int = 0
    vocab_size: int = 0
    tokenizer: TokenizerSpec = Field(default_factory=TokenizerSpec)
    weights: WeightsSpec = Field(default_factory=WeightsSpec)
    capabilities: list[str] = Field(default_factory=list)
    status: str = "experimental"
    created_at: str = ""
    archive_note: str | None = None
    evaluation: dict[str, Any] = Field(default_factory=dict)

    # -- identity helpers ------------------------------------------------
    @property
    def full_id(self) -> str:
        """Fully-qualified model reference, e.g. ``silverwing-120m-base-v1``."""
        return f"{self.model_id}-{self.version}"

    # -- validation -------------------------------------------------------
    def validate_manifest(self) -> list[str]:
        """Return a list of problems; empty means the manifest is sound."""
        problems: list[str] = []
        if not self.model_id:
            problems.append("model_id is empty")
        if self.status not in LIFECYCLE_STATUSES:
            problems.append(f"status {self.status!r} not in {LIFECYCLE_STATUSES}")
        if not self.tokenizer.sha256:
            problems.append("tokenizer.sha256 is missing")
        if not self.weights.sha256:
            problems.append("weights.sha256 is missing")
        if not self.weights.storage_uri:
            problems.append("weights.storage_uri is missing")
        unknown = [c for c in self.capabilities if c not in KNOWN_CAPABILITIES]
        if unknown:
            problems.append(f"unknown capabilities: {unknown}")
        if self.parameter_count <= 0:
            problems.append("parameter_count must be positive")
        return problems

    # -- (de)serialization ------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> ModelManifest:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2)


def discover_manifests(repo_root: Path) -> list[ModelManifest]:
    """Scan a model repository for every ``model_manifest.json``.

    Layout (section 42)::

        silverwing-models/
          <model_id>/v1/model_manifest.json
          <model_id>/r2000/model_manifest.json
    """
    manifests: list[ModelManifest] = []
    if not repo_root.exists():
        return manifests
    for mf in sorted(repo_root.rglob(MANIFEST_FILENAME)):
        try:
            manifests.append(ModelManifest.load(mf))
        except Exception:
            continue
    return manifests


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
