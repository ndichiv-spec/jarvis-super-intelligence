"""Model weight cache.

The inference runtime is the ONLY component that downloads model artifacts.
This cache:

* resolves cache hits and cache misses per (model_id, revision),
* downloads from the storage URI in the manifest,
* verifies SHA-256 before reporting a cached artifact usable,
* supports eviction and version pinning.

Weights are never copied into the application repository.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

from silverwing_runtime.hashutil import HashVerificationError, sha256_file, verify_sha256
from silverwing_runtime.model_manifest import ModelManifest
from silverwing_runtime.model_storage import ModelStorage, get_storage_for_uri

log = logging.getLogger("silverwing_runtime.model_cache")

_MARKER = ".sw_cache_entry.json"


class ModelCacheEntry:
    """One cached model version directory."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    @property
    def marker(self) -> Path:
        return self.directory / _MARKER

    @property
    def weights_path(self) -> Path:
        return self.directory / "model.safetensors"

    @property
    def config_path(self) -> Path:
        return self.directory / "config.json"

    @property
    def tokenizer_path(self) -> Path:
        return self.directory / "tokenizer.json"

    def read_marker(self) -> dict[str, object] | None:
        if not self.marker.exists():
            return None
        try:
            with open(self.marker, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def is_valid(self, manifest: ModelManifest, require_hash: bool = True) -> bool:
        """True iff this cache entry matches the manifest SHA-256 exactly."""
        if not self.weights_path.exists():
            return False
        expected = manifest.weights.sha256
        if expected and require_hash:
            try:
                actual = sha256_file(self.weights_path)
            except OSError:
                return False
            if actual.lower() != expected.lower():
                log.warning("cache entry hash mismatch in %s", self.directory)
                return False
        marker = self.read_marker()
        if marker is None:
            return True
        return (
            marker.get("model_id") == manifest.model_id
            and marker.get("revision") == manifest.revision
        )

    def write_marker(self, manifest: ModelManifest) -> None:
        entry = {
            "model_id": manifest.model_id,
            "version": manifest.version,
            "revision": manifest.revision,
            "weights_sha256": manifest.weights.sha256,
            "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(self.marker, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2)


class ModelCache:
    """Directory-backed cache keyed by ``model_id/revision``."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _dir_for(self, model_id: str, revision: str) -> Path:
        # revision is pinned from the manifest; slash is not allowed in ids.
        safe_id = model_id.replace("/", "--")
        return self.base_dir / safe_id / revision

    def hit(self, manifest: ModelManifest, require_hash: bool = True) -> Path | None:
        """Return the cached weights path on a verified cache hit."""
        entry = ModelCacheEntry(self._dir_for(manifest.model_id, manifest.revision))
        if entry.is_valid(manifest, require_hash=require_hash):
            return entry.weights_path
        return None

    def acquire(self, manifest: ModelManifest, storage: ModelStorage | None = None) -> Path:
        """Return a verified weights path, downloading to the cache on miss.

        Downloads only happen on cache miss; check :meth:`hit` before calling.
        """
        entry = ModelCacheEntry(self._dir_for(manifest.model_id, manifest.revision))
        if entry.is_valid(manifest, require_hash=True):
            return entry.weights_path

        entry.directory.mkdir(parents=True, exist_ok=True)
        tmp = entry.directory / "model.safetensors.part"
        storage = storage or get_storage_for_uri(manifest.weights.storage_uri)
        log.info(
            "cache miss: downloading %s -> %s",
            manifest.weights.storage_uri,
            entry.directory,
        )

        if manifest.weights.storage_uri.startswith("local:///"):
            # Local dev path: the storage_uri IS the durable source, and it
            # may point to a directory containing model.safetensors + friends.
            import re as _re

            m = _re.match(r"local:///(.+)", manifest.weights.storage_uri)
            src = Path(m.group(1) if m else manifest.weights.storage_uri)
            if not src.exists():
                raise FileNotFoundError(f"local model source missing: {src}")
            _copy_local_source(src, entry.directory)
        else:
            _, key = _split_for_download(manifest.weights.storage_uri)
            storage.download(key, tmp)
            tmp.rename(entry.weights_path)

        # Verify the acquired weights against the manifest hash (both paths).
        if not verify_sha256(entry.weights_path, manifest.weights.sha256):
            shutil.rmtree(entry.directory, ignore_errors=True)
            raise HashVerificationError(
                f"downloaded weights for {manifest.full_id} failed SHA-256 "
                f"verification (expected {manifest.weights.sha256})"
            )
        entry.write_marker(manifest)
        return entry.weights_path

    def evict(self, model_id: str | None = None, revision: str | None = None) -> int:
        """Remove cached entries.  Returns the number of entries removed."""
        removed = 0
        root = self.base_dir.resolve()
        if model_id is None:
            targets = [self.base_dir]
        else:
            safe_id = model_id.replace("/", "--")
            base = self.base_dir / safe_id
            targets = [base / revision] if revision else [base]
        for target in targets:
            try:
                resolved = target.resolve()
            except OSError:
                resolved = target
            if not resolved.is_relative_to(root):
                continue
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                removed += 1
        return removed

    def list_cached(self) -> dict[str, str]:
        """Return ``{model_id: [revision...]}`` map of cached versions."""
        result: dict[str, str] = {}
        for marker in self.base_dir.rglob(_MARKER):
            try:
                with open(marker, encoding="utf-8") as f:
                    data = json.load(f)
                result[data.get("model_id", marker.parent.parent.name)] = marker.parent.name
            except Exception:
                continue
        return result

    def clear(self) -> int:
        return self.evict()


def _split_for_download(uri: str) -> tuple[str, str]:
    """Split a non-local storage URI into ``(scheme, key)``."""
    scheme, _, rest = uri.partition("://")
    # For s3/gs we keep everything after '://' as the key; for hf we use
    # 'repo_id/filename'.
    return scheme.lower(), rest.lstrip("/")


def _copy_local_source(src: Path, dest_dir: Path) -> None:
    """Copy ``model.safetensors`` (+ config/tokenizer if present) from a local
    source that may be a single file or a directory."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        for name in (
            "model.safetensors",
            "config.json",
            "tokenizer.json",
            "tokenizer_manifest.json",
            "metadata.json",
        ):
            s = src / name
            if s.is_file():
                shutil.copy2(s, dest_dir / name)
    else:
        shutil.copy2(src, dest_dir / "model.safetensors")
