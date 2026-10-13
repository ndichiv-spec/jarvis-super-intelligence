"""Owner-scoped storage and expiring delivery references for generated media."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.exc import SQLAlchemyError

from .connectors.crypto import decrypt_secret, encrypt_secret
from .core import UPLOADS_DIR, _signing_key, get_store

MEDIA_REFERENCE_TTL_SECONDS = 15 * 60
MAX_MEDIA_BYTES = 20 * 1024 * 1024
_PROVIDER_HOST_SUFFIXES = ("replicate.delivery",)


class MediaReferenceError(ValueError):
    """Raised when provider output cannot safely become an authorized reference."""


def register_generated_image(
    *,
    owner_id: str,
    image: dict[str, Any],
    provider: str,
    model: str,
    prompt: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Persist provider output privately and return a short-lived media URL."""
    asset_id = str(uuid.uuid4())
    content_type = "image/png"
    record: dict[str, Any] = {
        "owner_id": owner_id,
        "provider": provider,
        "model": model,
        "prompt": prompt,
        "created_at": time.time(),
        "content_type": content_type,
        "width": width,
        "height": height,
    }
    stored_path: Path | None = None
    encoded = image.get("base64")
    if isinstance(encoded, str) and encoded:
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise MediaReferenceError("provider returned invalid image data") from exc
        if not content or len(content) > MAX_MEDIA_BYTES:
            raise MediaReferenceError("provider image exceeded the storage limit")
        if content.startswith(b"\xff\xd8\xff"):
            content_type = "image/jpeg"
            extension = "jpg"
        elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            content_type = "image/webp"
            extension = "webp"
        elif content.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = "png"
        else:
            raise MediaReferenceError("provider returned an unsupported image format")
        media_dir = UPLOADS_DIR / "generated"
        media_dir.mkdir(parents=True, exist_ok=True)
        stored_path = media_dir / f"{asset_id}.{extension}"
        stored_path.write_bytes(content)
        record["relative_path"] = str(stored_path.relative_to(UPLOADS_DIR))
        record["content_type"] = content_type
    else:
        source_url = image.get("url")
        if not isinstance(source_url, str) or not _is_allowed_provider_url(source_url):
            raise MediaReferenceError(
                "provider returned no safely storable image output"
            )
        record["encrypted_source_url"] = encrypt_secret(source_url)

    try:
        assets = get_store("media_assets").load()
        assets[asset_id] = record
        get_store("media_assets").save()
    except (OSError, SQLAlchemyError):
        if stored_path is not None:
            stored_path.unlink(missing_ok=True)
        raise

    expires = int(time.time()) + MEDIA_REFERENCE_TTL_SECONDS
    signature = _signature(asset_id, owner_id, expires)
    return {
        "media_ref": asset_id,
        "url": f"/api/v1/media/{asset_id}?expires={expires}&signature={signature}",
        "expires_at": expires,
        "prompt": prompt,
        "model": model,
        "provider": provider,
        "content_type": content_type,
        "width": width,
        "height": height,
        "created_at": record["created_at"],
        "provenance": {
            "provider": provider,
            "model": model,
            "generated_at": record["created_at"],
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        },
    }


def load_authorized_media(
    *,
    asset_id: str,
    expires: int,
    signature: str,
) -> dict[str, Any] | None:
    """Resolve a valid, unexpired bearer reference without exposing its owner."""
    assets = get_store("media_assets").load()
    record = assets.get(asset_id)
    if not isinstance(record, dict):
        return None
    owner_id = record.get("owner_id")
    now = int(time.time())
    if (
        not isinstance(owner_id, str)
        or expires < now
        or expires > now + MEDIA_REFERENCE_TTL_SECONDS
        or not hmac.compare_digest(signature, _signature(asset_id, owner_id, expires))
    ):
        return None
    return dict(record)


def issue_generated_image_reference(
    *,
    asset_id: str,
    owner_id: str,
) -> dict[str, Any] | None:
    """Issue a fresh short-lived URL only when the stored asset belongs to owner."""
    assets = get_store("media_assets").load()
    record = assets.get(asset_id)
    if not isinstance(record, dict) or record.get("owner_id") != owner_id:
        return None
    expires = int(time.time()) + MEDIA_REFERENCE_TTL_SECONDS
    signature = _signature(asset_id, owner_id, expires)
    return {
        "media_ref": asset_id,
        "url": f"/api/v1/media/{asset_id}?expires={expires}&signature={signature}",
        "expires_at": expires,
        "prompt": record.get("prompt"),
        "provider": record.get("provider"),
        "model": record.get("model"),
        "content_type": record.get("content_type"),
        "width": record.get("width"),
        "height": record.get("height"),
        "created_at": record.get("created_at"),
        "provenance": {
            "provider": record.get("provider"),
            "model": record.get("model"),
            "generated_at": record.get("created_at"),
            "prompt_sha256": hashlib.sha256(
                str(record.get("prompt") or "").encode("utf-8")
            ).hexdigest(),
        },
    }


def revoke_media(*, asset_id: str, owner_id: str) -> bool:
    """Remove a media reference and its private local copy for its owner."""
    assets = get_store("media_assets").load()
    record = assets.get(asset_id)
    if not isinstance(record, dict) or record.get("owner_id") != owner_id:
        return False
    relative_path = record.get("relative_path")
    if isinstance(relative_path, str):
        path = (UPLOADS_DIR / relative_path).resolve()
        root = UPLOADS_DIR.resolve()
        if root not in path.parents:
            raise MediaReferenceError("stored media path is outside its storage root")
        path.unlink(missing_ok=True)
    del assets[asset_id]
    get_store("media_assets").save()
    return True


def is_allowed_provider_url(value: str) -> bool:
    return _is_allowed_provider_url(value)


def _is_allowed_provider_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            parsed.scheme == "https"
            and bool(host)
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and any(host == suffix or host.endswith(f".{suffix}")
                    for suffix in _PROVIDER_HOST_SUFFIXES)
        )
    except ValueError:
        return False


def _signature(asset_id: str, owner_id: str, expires: int) -> str:
    message = f"{asset_id}:{owner_id}:{expires}".encode("utf-8")
    return hmac.new(
        _signing_key().encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def media_path(record: dict[str, Any]) -> Path | None:
    relative_path = record.get("relative_path")
    if not isinstance(relative_path, str):
        return None
    path = (UPLOADS_DIR / relative_path).resolve()
    if UPLOADS_DIR.resolve() not in path.parents:
        raise MediaReferenceError("stored media path is outside its storage root")
    return path


def decrypt_source_url(record: dict[str, Any]) -> str | None:
    value = record.get("encrypted_source_url")
    if not isinstance(value, str):
        return None
    source_url = decrypt_secret(value)
    if not _is_allowed_provider_url(source_url):
        raise MediaReferenceError("stored provider media URL is not allowed")
    return source_url
