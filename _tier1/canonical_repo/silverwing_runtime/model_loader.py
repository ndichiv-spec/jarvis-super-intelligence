"""Model loading pipeline.

Flow (specification section 10):

    model requested -> registry lookup -> storage lookup
    -> download/cache if necessary -> verify SHA-256 -> load model
    -> health check -> serve requests

The loader hands a backend a *materialized asset directory*: the verified
weights file plus tokenizer/config are cached on the inference machine only.
"""

from __future__ import annotations

import logging
from pathlib import Path

from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.model_cache import ModelCache
from silverwing_runtime.model_manifest import ModelManifest
from silverwing_runtime.model_registry import RegistryEntry, SilverwingRegistry

log = logging.getLogger("silverwing_runtime.model_loader")


class LoadedModel:
    """A verified, cached model ready for the inference backend."""

    def __init__(self, entry: RegistryEntry, weights_path: Path):
        self.entry = entry
        self.weights_path = weights_path
        # Asset directory on the inference machine (cache).
        self.asset_dir = weights_path.parent

    @property
    def full_id(self) -> str:
        return self.entry.full_id

    @property
    def sha256_verified(self) -> bool:
        return True  # ModelCache only returns hash-verified paths

    @property
    def sha256_verified_str(self) -> str:
        """Honest label: the cache verifies SHA-256 before exposing a path."""
        return "verified" if self.sha256_verified else "unverified"


class ModelLoader:
    """Resolve a model id to a verified, cached asset path."""

    def __init__(
        self,
        registry: SilverwingRegistry,
        cache: ModelCache | None = None,
        config: RuntimeConfig | None = None,
    ):
        self.registry = registry
        self.cache = cache or ModelCache((config or RuntimeConfig()).model_cache_dir)
        self.config = config or RuntimeConfig()

    def resolve(self, model_ref: str) -> RegistryEntry | None:
        """Registry lookup for ``model_ref`` (full id or base id)."""
        return self.registry.lookup(model_ref)

    def load(self, model_ref: str) -> LoadedModel:
        """Download (if necessary), verify, and materialize a model."""
        entry = self.resolve(model_ref)
        if entry is None:
            raise KeyError(f"model not found in registry: {model_ref!r}")

        manifest = self._load_manifest(entry)
        cached_hit = self.cache.hit(manifest)
        if cached_hit is not None:
            log.info("cache hit for %s (%s)", entry.full_id, cached_hit)
            return LoadedModel(entry, cached_hit)
        weights = self.cache.acquire(manifest)
        return LoadedModel(entry, weights)

    def _load_manifest(self, entry: RegistryEntry) -> ModelManifest:
        from silverwing_runtime.model_manifest import ModelManifest

        return ModelManifest(
            model_id=entry.model_id,
            version=entry.version,
            revision=entry.revision,
            architecture=entry.architecture,
            parameter_count=entry.parameter_count,
            context_length=entry.context_length,
            vocab_size=entry.vocab_size or 0,
            tokenizer={
                "version": entry.tokenizer_version,
                "sha256": entry.tokenizer_sha256,
            },
            weights={
                "sha256": entry.model_sha256,
                "config_sha256": entry.config_sha256,
                "storage_uri": entry.storage_uri,
            },
            capabilities=list(entry.capabilities),
            status=entry.status,
            created_at=entry.created_at,
        )
