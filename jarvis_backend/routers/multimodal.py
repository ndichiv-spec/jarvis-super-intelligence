"""Owner-scoped image/document uploads with bounded, content-checked storage."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..core import UPLOADS_DIR, get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/multimodal", tags=["multimodal"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_ALLOWED = {
    "images": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
    "documents": {".pdf", ".txt", ".csv"},
}
_CLAIMED_TYPES = {
    ".png": {"image/png", "application/octet-stream"},
    ".jpg": {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".gif": {"image/gif", "application/octet-stream"},
    ".webp": {"image/webp", "application/octet-stream"},
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".csv": {"text/csv", "text/plain", "application/octet-stream"},
}


def _safe_original_name(value: str | None) -> str:
    name = (value or "file").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    return name


def _validate_content(subdir: str, extension: str, content: bytes) -> None:
    if extension not in _ALLOWED[subdir]:
        raise HTTPException(status_code=415, detail="Unsupported upload file type")
    if subdir == "images":
        signatures = {
            ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            ".jpg": content.startswith(b"\xff\xd8\xff"),
            ".jpeg": content.startswith(b"\xff\xd8\xff"),
            ".gif": content.startswith((b"GIF87a", b"GIF89a")),
            ".webp": (
                len(content) >= 12
                and content.startswith(b"RIFF")
                and content[8:12] == b"WEBP"
            ),
        }
        valid = signatures[extension]
    elif extension == ".pdf":
        valid = content.startswith(b"%PDF-")
    else:
        try:
            content.decode("utf-8")
            valid = b"\x00" not in content
        except UnicodeDecodeError:
            valid = False
    if not valid:
        raise HTTPException(status_code=415, detail="Upload content does not match its file type")


def _public_file(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in ("id", "filename", "original_name", "category", "size", "created_at")
        if key in record
    }


async def _save_upload(file: UploadFile, subdir: str, user_id: str) -> dict[str, Any]:
    original_name = _safe_original_name(file.filename)
    extension = Path(original_name).suffix.lower()
    claimed_type = (file.content_type or "application/octet-stream").lower()
    if extension not in _ALLOWED[subdir] or claimed_type not in _CLAIMED_TYPES[extension]:
        raise HTTPException(status_code=415, detail="Unsupported upload file type")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the size limit")
    _validate_content(subdir, extension, content)

    upload_root = UPLOADS_DIR.resolve()
    target_dir = UPLOADS_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir = target_dir.resolve()
    if not target_dir.is_relative_to(upload_root):
        raise HTTPException(status_code=500, detail="Upload storage path is invalid")
    name = f"{uuid.uuid4().hex}{extension}"
    path = target_dir / name
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "filename": name,
        "original_name": original_name,
        "path": str(path),
        "category": subdir,
        "size": len(content),
        "created_at": now_iso(),
    }
    try:
        with path.open("xb") as output:
            output.write(content)
        files = get_store("multimodal_files").load()
        files[record["id"]] = record
        get_store("multimodal_files").save()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return _public_file(record)


@router.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    description: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
):
    record = await _save_upload(file, "images", user["id"])
    if description:
        record["description"] = description[:1000]
    return record


@router.post("/upload/document")
async def upload_document(
    file: UploadFile = File(...),
    category: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
):
    record = await _save_upload(file, "documents", user["id"])
    record["category"] = category[:100] if category else "document"
    return record


@router.get("/files")
async def list_files(user: dict[str, Any] = Depends(get_current_user)):
    files = get_store("multimodal_files").load()
    mine = [_public_file(item) for item in files.values() if item.get("user_id") == user["id"]]
    mine.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"files": mine, "total": len(mine)}


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    files = get_store("multimodal_files").load()
    record_id = next(
        (
            key
            for key, item in files.items()
            if item.get("user_id") == user["id"]
            and (item.get("id") == file_id or item.get("filename") == file_id)
        ),
        None,
    )
    if record_id is None:
        raise HTTPException(status_code=404, detail="File not found")

    record = files[record_id]
    upload_root = UPLOADS_DIR.resolve()
    path = Path(record.get("path", "")).resolve()
    if not path.is_relative_to(upload_root):
        raise HTTPException(status_code=500, detail="Stored upload path is invalid")
    path.unlink(missing_ok=True)
    files.pop(record_id)
    get_store("multimodal_files").save()
    return {"success": True}


@router.get("/status")
async def multimodal_status():
    return {
        "status": "available",
        "uploads_supported": True,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "authentication_required": True,
    }
