"""JARVIS Brain model catalog / registry (spec sections 9, 20).

The Brain runtime serves Qwen3-4B variants.  Each variant has an immutable
identity and a durable Hugging Face repository.  The Base lineage entry is NEVER
overwritten by the SFT candidate (spec section 20):

    Kaggle (training)
      -> Hugging Face  (durable artifact repository)
           Qwen/Qwen3-4B                                   (Base)
           videlisndichi/jarvis-brain-qwen3-4b-sft-v1      (SFT candidate)
      -> Brain inference server (:8011)

Manifests live under ``model_repo/jarvis-brain-*/v1/model_manifest.json``.
The HF repository is the authority for weights; the manifest only carries the
model identity + hash metadata (weights are never committed to the source tree,
spec section 7).  Entries are keyed by ``full_id`` (e.g.
``jarvis-brain-qwen3-4b-v1``), mirroring the Silverwing registry convention.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("brain_runtime.model_registry")

# Canonical lineage for every JARVIS Brain full_id.  ``repository`` is the
# authoritative Hugging Face repo; ``training_method`` distinguishes Base vs.
# the Kaggle-trained SFT candidate so the two are never confused (spec §9/§20).
BRAIN_MODEL_LINEAGE: dict[str, dict[str, Any]] = {
    "jarvis-brain-qwen3-4b-v1": {
        "model_id": "jarvis-brain-qwen3-4b",
        "repository": "Qwen/Qwen3-4B",
        "training_method": "base",
        "hf_revision": "1cfa9a7208912126459214e8b04321603b3df60c",
        "notes": "Qwen3-4B Base (Kaggle fine-tune source). Lineage root; never overwritten by an SFT candidate.",
    },
    "jarvis-brain-qwen3-4b-sft-v1": {
        "model_id": "jarvis-brain-qwen3-4b-sft",
        "repository": "videlisndichi/jarvis-brain-qwen3-4b-sft-v1",
        "training_method": "sft",
        "hf_revision": "main",
        "notes": "Qwen3-4B SFT candidate fine-tuned on Kaggle. Distinct artifact from Base.",
    },
}


def _strip_hf(uri: str) -> str:
    """``hf://Qwen/Qwen3-4B`` -> ``Qwen/Qwen3-4B``."""
    return uri.replace("hf://", "").strip("/")


@dataclass
class BrainModel:
    """Immutable identity for one version of a JARVIS Brain model."""

    model_id: str
    full_id: str
    version: str
    repository: str
    revision: str
    architecture: str
    parameter_count: int
    context_length: int
    vocab_size: int
    capabilities: list[str] = field(default_factory=list)
    status: str = "experimental"
    training_method: str = "base"
    notes: str = ""
    manifest_path: str = ""

    @classmethod
    def from_manifest(cls, data: dict[str, Any], manifest_path: Path) -> "BrainModel":
        version = data.get("version", "v1")
        full_id = data.get("full_id", f"{data.get('model_id', '')}-{version}")
        return cls(
            model_id=data.get("model_id", full_id),
            full_id=full_id,
            version=version,
            repository=_strip_hf(data["weights"]["storage_uri"]),
            revision=data.get("revision") or data.get("commit", "") or "",
            architecture=data.get("architecture", "Qwen3ForCausalLM"),
            parameter_count=int(data.get("parameter_count", 0)),
            context_length=int(data.get("context_length", 0)),
            vocab_size=int(data.get("vocab_size", 0)),
            capabilities=list(data.get("capabilities", [])),
            status=data.get("status", "experimental"),
            training_method=data.get("training_method", "base"),
            notes=data.get("notes", ""),
            manifest_path=str(manifest_path),
        )

    def lineage(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "full_id": self.full_id,
            "repository": self.repository,
            "training_method": self.training_method,
            "revision": self.revision,
        }


class BrainCatalog:
    """In-process catalog of JARVIS Brain models.

    Seeded from the canonical lineage table (so every variant is resolvable even
    without a local manifest) and then enriched with any ``model_manifest.json``
    found on disk under ``model_repo/jarvis-brain-*/`` (authoritative
    hash/geometry metadata).  Lineage identity (repository / training_method) is
    never clobbered by a manifest.  Entries are keyed by ``full_id``.
    """

    def __init__(self, model_repo: str | Path | None = None):
        self.model_repo = Path(model_repo) if model_repo else Path("F:/AI/silverwing-models")
        self._entries: dict[str, BrainModel] = {}
        self._lock = threading.RLock()
        self.refresh()

    # -- loading -----------------------------------------------------------
    def refresh(self) -> int:
        """(Re)build the catalog from lineage + on-disk manifests."""
        with self._lock:
            for full_id, lin in BRAIN_MODEL_LINEAGE.items():
                self._entries[full_id] = BrainModel(
                    model_id=lin["model_id"],
                    full_id=full_id,
                    version="v1",
                    repository=lin["repository"],
                    revision=lin["hf_revision"],
                    architecture="Qwen3ForCausalLM",
                    parameter_count=0,
                    context_length=40960,
                    vocab_size=151936,
                    capabilities=["text-generation", "chat", "reasoning"],
                    status="experimental",
                    training_method=lin["training_method"],
                    notes=lin["notes"],
                    manifest_path="",
                )
            # Overlay authoritative hash/geometry from on-disk manifests.
            for data, mf_path in self._discover_manifests():
                try:
                    m = BrainModel.from_manifest(data, mf_path)
                except Exception as exc:  # pragma: no cover - malformed manifest
                    log.warning("skipping brain manifest %s: %s", mf_path, exc)
                    continue
                key = m.full_id if m.full_id in self._entries else m.model_id
                entry = self._entries.get(key)
                if entry is None:
                    # An unknown-but-discovered brain model; register it.
                    self._entries[m.full_id] = m
                    continue
                entry.repository = m.repository or entry.repository
                entry.revision = m.revision or entry.revision
                entry.architecture = m.architecture or entry.architecture
                entry.parameter_count = m.parameter_count or entry.parameter_count
                entry.context_length = m.context_length or entry.context_length
                entry.vocab_size = m.vocab_size or entry.vocab_size
                entry.capabilities = m.capabilities or entry.capabilities
                entry.status = m.status or entry.status
                entry.notes = m.notes or entry.notes
                entry.manifest_path = str(mf_path)
            return len(self._entries)

    def _discover_manifests(self) -> list[tuple[dict[str, Any], Path]]:
        """Return ``(manifest_dict, path)`` for every ``jarvis-brain-*`` manifest."""
        results: list[tuple[dict[str, Any], Path]] = []
        if not self.model_repo.exists():
            return results
        for path in sorted(self.model_repo.rglob("model_manifest.json")):
            rel = path.relative_to(self.model_repo).as_posix()
            if not rel.startswith("jarvis-brain-"):
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            if not data.get("model_id"):
                continue
            results.append((data, path))
        return results

    # -- queries -----------------------------------------------------------
    def list_models(self) -> list[BrainModel]:
        with self._lock:
            return list(self._entries.values())

    def lookup(self, model_id: str | None) -> BrainModel | None:
        """Resolve a Brain model reference to its catalog entry.

        Accepts the full id (``jarvis-brain-qwen3-4b-v1``), a base id
        (``jarvis-brain-qwen3-4b``) or the SFT qualifier.
        """
        with self._lock:
            if not model_id:
                return None
            if model_id in self._entries:
                return self._entries[model_id]
            # exact base-id match
            for entry in self._entries.values():
                if entry.model_id == model_id:
                    return entry
            # strip a trailing -sft to fall back to the Base candidate
            base = model_id.removesuffix("-sft")
            if base in self._entries:
                return self._entries[base]
            for entry in self._entries.values():
                if entry.model_id == base:
                    return entry
            # lenient prefix match on the short name
            short = model_id.removesuffix("-v1").removesuffix("-sft-v1")
            for entry in self._entries.values():
                if entry.model_id.startswith(short):
                    return entry
            return None

    def repository_for(self, model_id: str) -> str:
        """Return the Hugging Face repository for a Brain model id."""
        entry = self.lookup(model_id)
        if entry is None:
            return BRAIN_MODEL_LINEAGE.get(model_id, {}).get("repository", "")
        return entry.repository
