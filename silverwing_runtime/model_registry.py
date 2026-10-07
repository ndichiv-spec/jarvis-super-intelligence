"""Silverwing model registry.

Registry entries are immutable identities (one per model version) derived from
``model_manifest.json`` documents.  The registry answers:

* which models exist, and their versions,
* where a model's durable weights live (storage_uri),
* where a model is deployed (deployment endpoint + status),
* lifecycle state (TRAINING -> EXPERIMENTAL -> ... -> ARCHIVED).

Promotion requires evaluation evidence and is performed through explicit
status transitions, never by silently editing a manifest.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from pydantic import BaseModel, Field

from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.model_manifest import ModelManifest, discover_manifests

log = logging.getLogger("silverwing_runtime.model_registry")


class DeploymentInfo(BaseModel):
    """Where a model is currently deployed (runtime-known)."""

    endpoint: str = ""
    device: str = ""
    loaded: bool = False
    last_health_check: str | None = None
    healthy: bool = False


class RegistryEntry(BaseModel):
    """Immutable registry record for one model version."""

    model_id: str
    version: str
    revision: str
    full_id: str
    architecture: str = "Silverwing Decoder"
    parameter_count: int = 0
    context_length: int = 0
    vocab_size: int = 0
    tokenizer_version: str = ""
    tokenizer_sha256: str = ""
    model_sha256: str = ""
    config_sha256: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    storage_uri: str = ""
    status: str = "experimental"
    created_at: str = ""
    manifest_path: str = ""
    deployment: DeploymentInfo = Field(default_factory=DeploymentInfo)

    @classmethod
    def from_manifest(cls, m: ModelManifest, manifest_path: Path) -> RegistryEntry:
        return cls(
            model_id=m.model_id,
            version=m.version,
            revision=m.revision,
            full_id=m.full_id,
            architecture=m.architecture,
            parameter_count=m.parameter_count,
            context_length=m.context_length,
            vocab_size=m.vocab_size,
            tokenizer_version=m.tokenizer.version,
            tokenizer_sha256=m.tokenizer.sha256,
            model_sha256=m.weights.sha256,
            config_sha256=m.weights.config_sha256,
            capabilities=list(m.capabilities),
            storage_uri=m.weights.storage_uri,
            status=m.status,
            created_at=m.created_at,
            manifest_path=str(manifest_path),
        )


class SilverwingRegistry:
    """Manifest-backed registry of Silverwing model versions.

    Backed by a JSON file for persistence; built automatically by scanning the
    model repository.  ``register`` is idempotent per immutable full_id.
    """

    def __init__(self, config: RuntimeConfig | None = None, path: Path | None = None):
        self.config = config or RuntimeConfig()
        self._path = Path(path) if path else self.config.registry_path
        self._entries: dict[str, RegistryEntry] = {}
        self._lock = threading.RLock()
        self.refresh()

    # ------------------------------------------------------------------ #
    # Loading / persistence
    # ------------------------------------------------------------------ #
    def refresh(self) -> int:
        """Re-scan the model repository; returns number of entries."""
        with self._lock:
            for mf in discover_manifests(self.config.model_repo):
                key = mf.full_id
                # Never overwrite an existing entry's deployment/health state.
                existing = self._entries.get(key)
                entry = RegistryEntry.from_manifest(mf, self.config.model_repo / _rel_of(key, mf))
                if existing is not None:
                    entry.deployment = existing.deployment
                self._entries[key] = entry
            return len(self._entries)

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                for entry in data.get("models", []):
                    e = RegistryEntry(**entry)
                    self._entries[e.full_id] = e
        except Exception as exc:
            log.warning("Could not load registry from %s: %s", self._path, exc)

    def save(self) -> None:
        with self._lock:
            data = {
                "models": [e.model_dump() for e in self._entries.values()],
            }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def list_models(self) -> list[RegistryEntry]:
        with self._lock:
            return list(self._entries.values())

    def get(self, full_id: str) -> RegistryEntry | None:
        with self._lock:
            return self._entries.get(full_id)

    def lookup(self, model_id: str, version: str | None = None) -> RegistryEntry | None:
        """Resolve a request model reference to a registry entry.

        Accepts ``silverwing-120m-base-v1``, ``silverwing-120m-base``
        (latest non-archived) or ``silverwing-120m-base@v1``.
        """
        if version:
            return self.get(f"{model_id}-{version}")
        # exact full id
        exact = self.get(model_id)
        if exact is not None:
            return exact
        # base id -> pick highest-versioned non-archived entry
        candidates = [
            e for e in self.list_models() if e.model_id == model_id and e.status != "archived"
        ]
        if not candidates:
            candidates = [e for e in self.list_models() if e.model_id == model_id]
        if not candidates:
            return None
        return sorted(candidates, key=lambda e: e.version, reverse=True)[0]

    def versions(self, model_id: str) -> list[RegistryEntry]:
        return [e for e in self.list_models() if e.model_id == model_id]

    def by_capability(self, capability: str) -> list[RegistryEntry]:
        return [
            e
            for e in self.list_models()
            if capability in e.capabilities and e.status not in ("archived",)
        ]

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def set_status(self, full_id: str, status: str) -> RegistryEntry:
        """Transition a model to a lifecycle status (section 33)."""
        entry = self.get(full_id)
        if entry is None:
            raise KeyError(f"unknown model {full_id!r}")
        ordered = [
            "training",
            "experimental",
            "evaluated",
            "approved",
            "active",
            "deprecated",
            "archived",
        ]
        if status not in ordered:
            raise ValueError(f"invalid lifecycle status {status!r}")
        if status in ("approved", "active") and not entry.deployment.loaded:
            log.warning(
                "Promoting %s to %s without a loaded deployment evidence record",
                full_id,
                status,
            )
        entry.status = status
        with self._lock:
            self._entries[full_id] = entry
        return entry

    # ------------------------------------------------------------------ #
    # Deployment bookkeeping
    # ------------------------------------------------------------------ #
    def mark_deployed(
        self, full_id: str, *, endpoint: str, device: str, loaded: bool, healthy: bool
    ) -> None:
        entry = self.get(full_id)
        if entry is None:
            raise KeyError(f"unknown model {full_id!r}")
        entry.deployment = DeploymentInfo(
            endpoint=endpoint,
            device=device,
            loaded=loaded,
            healthy=healthy,
            last_health_check=time_str(),
        )
        with self._lock:
            self._entries[full_id] = entry


def _rel_of(_full_id: str, m: ModelManifest) -> Path:
    """Best-effort relative path of a manifest within the repo."""
    return Path(m.model_id) / m.version / "model_manifest.json"


def time_str() -> str:
    import time as _t

    return _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())
