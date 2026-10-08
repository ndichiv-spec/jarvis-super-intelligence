"""Durable model storage abstraction.

Defines a provider-neutral :class:`ModelStorage` interface and implementations
for the providers the platform supports: local filesystem (development), Hugging
Face Hub, S3-compatible object storage, Google Cloud Storage and Azure Blob.

No provider is hard-coded anywhere in the platform.  The runtime selects a
backend by name (``SILVERWING_STORAGE_BACKEND``) or by parsing the
``storage_uri`` scheme of a manifest.

All third-party SDKs are imported lazily inside each implementation, so this
module imports cleanly with zero cloud SDKs installed (mirroring
``silverwing-backend/model_provider.py``).
"""

from __future__ import annotations

import logging
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

log = logging.getLogger("silverwing_runtime.model_storage")


def parse_storage_uri(uri: str) -> tuple[str, str]:
    """Split a ``scheme://path`` storage URI into ``(scheme, path)``.

    Examples::

        local:///F:/AI/_kout6/best  -> ("local", "F:/AI/_kout6/best")
        hf://repo/model             -> ("huggingface", "repo/model")
        s3://bucket/key             -> ("s3", "bucket/key")
        gs://bucket/key             -> ("gcs", "bucket/key")
        azblob://container/key      -> ("azure", "container/key")
    """
    if "://" not in uri:
        return "local", uri
    scheme, _, path = uri.partition("://")
    return scheme.lower(), path.lstrip("/")


class ModelStorage(ABC):
    """Provider-neutral interface to durable model storage."""

    name: str = "base"

    @abstractmethod
    def upload(self, local_path: Path, remote_key: str) -> str:
        """Upload ``local_path`` and return its storage URI."""

    @abstractmethod
    def download(self, remote_key: str, dest: Path) -> Path:
        """Download ``remote_key`` into ``dest`` (a file path)."""

    @abstractmethod
    def exists(self, remote_key: str) -> bool:
        """Return True iff ``remote_key`` exists in this storage."""

    @abstractmethod
    def get_metadata(self, remote_key: str) -> dict[str, object]:
        """Return size / bytes / created metadata for ``remote_key``."""

    @abstractmethod
    def list_versions(self, model_id: str) -> list[str]:
        """List storage keys/versions available for ``model_id``."""


class LocalStorage(ModelStorage):
    """Filesystem storage for development and single-machine deployments."""

    name = "local"

    def __init__(self, root: Path):
        self.root = Path(root)

    def _full(self, key: str) -> Path:
        # Keys are scoped to the configured root; never traverse outside it.
        p = (self.root / key).resolve()
        root = self.root.resolve()
        if not p.is_relative_to(root):
            raise ValueError(f"storage key escapes root: {key!r}")
        return p

    def upload(self, local_path: Path, remote_key: str) -> str:
        dest = self._full(remote_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        return f"local:///{dest.as_posix()}"

    def download(self, remote_key: str, dest: Path) -> Path:
        src = self._full(remote_key)
        if not src.exists():
            raise FileNotFoundError(f"local storage missing {remote_key}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def exists(self, remote_key: str) -> bool:
        try:
            return self._full(remote_key).exists()
        except ValueError:
            return False

    def get_metadata(self, remote_key: str) -> dict[str, object]:
        p = self._full(remote_key)
        if not p.exists():
            raise FileNotFoundError(f"local storage missing {remote_key}")
        stat = p.stat()
        return {"size_bytes": stat.st_size, "mtime": stat.st_mtime, "key": remote_key}

    def list_versions(self, model_id: str) -> list[str]:
        base = self._full(model_id)
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir() or p.is_file())


class HuggingFaceStorage(ModelStorage):
    """Hugging Face Hub storage (repo_id / revision)."""

    name = "huggingface"

    def __init__(self, hf_token: str | None = None):
        try:
            from huggingface_hub import HfApi  # type: ignore[import-not-found]

            self._api = HfApi(token=hf_token or os.environ.get("HF_TOKEN"))
            self._available = True
        except Exception as exc:
            self._api = None
            self._available = False
            self._init_err = str(exc)

    def _require(self):
        if not self._available:
            raise RuntimeError(
                f"huggingface_hub is not available: {getattr(self, '_init_err', '?')}"
            )

    def upload(self, local_path: Path, remote_key: str) -> str:
        self._require()
        repo_id, _, path_in_repo = remote_key.partition("/")
        self._api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=path_in_repo or local_path.name,
            repo_id=repo_id,
        )
        return f"hf://{remote_key}"

    def download(self, remote_key: str, dest: Path) -> Path:
        self._require()
        from huggingface_hub import hf_hub_download  # type: ignore[import-not-found]

        repo_id, _, filename = remote_key.partition("/")
        path = hf_hub_download(repo_id=repo_id, filename=filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        return dest

    def exists(self, remote_key: str) -> bool:
        self._require()
        repo_id, _, filename = remote_key.partition("/")
        try:
            return bool(self._api.file_exists(repo_id=repo_id, filename=filename))
        except Exception:
            return False

    def get_metadata(self, remote_key: str) -> dict[str, object]:
        self._require()
        repo_id, _, filename = remote_key.partition("/")
        try:
            info = self._api.get_paths_info(repo_id=repo_id, paths=[filename])[0]
        except Exception:
            return {"key": remote_key}
        return {"size_bytes": getattr(info, "size", None), "key": remote_key}

    def list_versions(self, model_id: str) -> list[str]:
        self._require()
        try:
            return [r.revision for r in self._api.list_repo_refs(model_id).branches]
        except Exception:
            return []


class S3Storage(ModelStorage):
    """S3-compatible object storage via ``boto3`` (lazy import)."""

    name = "s3"

    def __init__(self, endpoint_url: str | None = None):
        try:
            import boto3  # type: ignore[import-not-found]

            self._client = boto3.client("s3", endpoint_url=endpoint_url)
            self._available = True
        except Exception as exc:
            self._client = None
            self._available = False
            self._init_err = str(exc)

    def _require(self):
        if not self._available:
            raise RuntimeError(f"boto3 is not available: {getattr(self, '_init_err', '?')}")

    @staticmethod
    def _split(key: str) -> tuple[str, str]:
        bucket, _, obj = key.partition("/")
        return bucket, obj

    def upload(self, local_path: Path, remote_key: str) -> str:
        self._require()
        bucket, obj = self._split(remote_key)
        self._client.upload_file(str(local_path), bucket, obj)
        return f"s3://{remote_key}"

    def download(self, remote_key: str, dest: Path) -> Path:
        self._require()
        bucket, obj = self._split(remote_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(bucket, obj, str(dest))
        return dest

    def exists(self, remote_key: str) -> bool:
        self._require()
        bucket, obj = self._split(remote_key)
        try:
            self._client.head_object(Bucket=bucket, Key=obj)
            return True
        except Exception:
            return False

    def get_metadata(self, remote_key: str) -> dict[str, object]:
        self._require()
        bucket, obj = self._split(remote_key)
        head = self._client.head_object(Bucket=bucket, Key=obj)
        return {"size_bytes": head.get("ContentLength"), "key": remote_key}

    def list_versions(self, model_id: str) -> list[str]:
        self._require()
        bucket, prefix = self._split(model_id)
        try:
            resp = self._client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            return [c["Key"] for c in resp.get("Contents", [])]
        except Exception:
            return []


class GCSStorage(ModelStorage):
    """Google Cloud Storage via ``google-cloud-storage`` (lazy import)."""

    name = "gcs"

    def __init__(self):
        try:
            from google.cloud import storage  # type: ignore[import-not-found]

            self._client = storage.Client()
            self._available = True
        except Exception as exc:
            self._client = None
            self._available = False
            self._init_err = str(exc)

    def _require(self):
        if not self._available:
            raise RuntimeError(
                f"google-cloud-storage is not available: {getattr(self, '_init_err', '?')}"
            )

    @staticmethod
    def _split(key: str) -> tuple[str, str]:
        bucket, _, obj = key.partition("/")
        return bucket, obj

    def upload(self, local_path: Path, remote_key: str) -> str:
        self._require()
        bucket, obj = self._split(remote_key)
        blob = self._client.bucket(bucket).blob(obj)
        blob.upload_from_filename(str(local_path))
        return f"gs://{remote_key}"

    def download(self, remote_key: str, dest: Path) -> Path:
        self._require()
        bucket, obj = self._split(remote_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._client.bucket(bucket).blob(obj).download_to_filename(str(dest))
        return dest

    def exists(self, remote_key: str) -> bool:
        self._require()
        bucket, obj = self._split(remote_key)
        return self._client.bucket(bucket).blob(obj).exists()

    def get_metadata(self, remote_key: str) -> dict[str, object]:
        self._require()
        bucket, obj = self._split(remote_key)
        blob = self._client.bucket(bucket).get_blob(obj)
        if blob is None:
            raise FileNotFoundError(remote_key)
        return {"size_bytes": blob.size, "key": remote_key, "updated": str(blob.updated)}

    def list_versions(self, model_id: str) -> list[str]:
        self._require()
        bucket, prefix = self._split(model_id)
        return [b.name for b in self._client.bucket(bucket).list_blobs(prefix=prefix)]


class AzureStorage(ModelStorage):
    """Azure Blob Storage via ``azure-storage-blob`` (lazy import)."""

    name = "azure"

    def __init__(self, conn_str: str | None = None, container: str | None = None):
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore[import-not-found]

            self._client = BlobServiceClient.from_connection_string(
                conn_str
                or os.environ.get(
                    "AZURE_STORAGE_CONNECTION_STRING",
                    "DefaultEndpointsProtocol=https;AccountName=local;AccountKey=EMU;EndpointSuffix=core.windows.net",
                )
            )
            self._container = container or os.environ.get(
                "AZURE_STORAGE_CONTAINER", "silverwing-models"
            )
            self._available = True
        except Exception as exc:
            self._client = None
            self._available = False
            self._init_err = str(exc)

    def _require(self):
        if not self._available:
            raise RuntimeError(
                f"azure-storage-blob is not available: {getattr(self, '_init_err', '?')}"
            )

    def upload(self, local_path: Path, remote_key: str) -> str:
        self._require()
        blob = self._client.get_blob_client(self._container, remote_key)
        with open(local_path, "rb") as f:
            blob.upload_blob(f, overwrite=True)
        return f"azblob://{self._container}/{remote_key}"

    def download(self, remote_key: str, dest: Path) -> Path:
        self._require()
        blob = self._client.get_blob_client(self._container, remote_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            blob.download_blob().readinto(f)
        return dest

    def exists(self, remote_key: str) -> bool:
        self._require()
        return self._client.get_blob_client(self._container, remote_key).exists()

    def get_metadata(self, remote_key: str) -> dict[str, object]:
        self._require()
        props = self._client.get_blob_client(self._container, remote_key).get_blob_properties()
        return {"size_bytes": props.size, "key": remote_key}

    def list_versions(self, model_id: str) -> list[str]:
        self._require()
        container = self._client.get_container_client(self._container)
        return [b.name for b in container.list_blobs(name_starts_with=model_id)]


_STORAGE_BY_NAME: dict[str, type] = {
    "local": LocalStorage,
    "huggingface": HuggingFaceStorage,
    "hf": HuggingFaceStorage,
    "s3": S3Storage,
    "gcs": GCSStorage,
    "gs": GCSStorage,
    "azure": AzureStorage,
    "azblob": AzureStorage,
}


def get_storage(backend: str | None = None, *, root: Path | None = None) -> ModelStorage:
    """Instantiate a storage backend by name (default ``local``).

    ``root`` only applies to :class:`LocalStorage` (cache download root).
    """
    name = (backend or "local").lower()
    cls = _STORAGE_BY_NAME.get(name)
    if cls is None:
        raise ValueError(
            f"unknown storage backend {backend!r}; "
            f"expected one of {sorted({c.name for c in _STORAGE_BY_NAME.values()})}"
        )
    if cls is LocalStorage:
        return cls(root or Path("."))
    if cls is HuggingFaceStorage:
        return cls()
    if cls is S3Storage:
        return cls()
    if cls is GCSStorage:
        return cls()
    if cls is AzureStorage:
        return cls()
    raise TypeError(f"unhandled storage class {cls!r}")


def get_storage_for_uri(uri: str, *, root: Path | None = None) -> ModelStorage:
    """Select a storage backend from a manifest ``storage_uri`` scheme."""
    scheme, _ = parse_storage_uri(uri)
    return get_storage(scheme, root=root)
