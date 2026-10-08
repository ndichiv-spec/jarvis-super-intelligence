"""Multimodal file upload, listing, deletion, and status."""

from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..core import UPLOADS_DIR, get_store, now_iso

router = APIRouter(prefix="/api/v1/multimodal", tags=["multimodal"])


async def _save_upload(file: UploadFile, subdir: str) -> dict:
    safe_name = os.path.basename(file.filename or "file")
    target_dir = UPLOADS_DIR / subdir
    target_dir.mkdir(exist_ok=True)
    name = f"{uuid.uuid4()}-{safe_name}"
    path = target_dir / name
    with path.open("wb") as fh:
        fh.write(await file.read())
    files = get_store("multimodal_files").load()
    record = {
        "id": str(uuid.uuid4()),
        "filename": name,
        "original_name": safe_name,
        "path": str(path),
        "category": subdir,
        "size": path.stat().st_size,
        "created_at": now_iso(),
    }
    files[record["id"]] = record
    get_store("multimodal_files").save()
    return record


@router.post("/upload/image")
async def upload_image(file: UploadFile = File(...), description: Optional[str] = None):
    record = await _save_upload(file, "images")
    record["description"] = description
    return record


@router.post("/upload/document")
async def upload_document(file: UploadFile = File(...), category: Optional[str] = None):
    record = await _save_upload(file, "documents")
    record["category"] = category or "document"
    return record


@router.get("/files")
async def list_files():
    files = list(get_store("multimodal_files").load().values())
    return {"files": files[::-1], "total": len(files)}


@router.delete("/files/{filename}")
async def delete_file(filename: str):
    files = get_store("multimodal_files").load()
    for fid, record in list(files.items()):
        if record.get("filename") == filename or record.get("id") == filename:
            try:
                os.remove(record["path"])
            except OSError:
                pass
            files.pop(fid, None)
            get_store("multimodal_files").save()
            return {"success": True}
    raise HTTPException(status_code=404, detail="File not found")


@router.get("/status")
async def multimodal_status():
    return {
        "status": "ready",
        "uploads_supported": True,
        "upload_dir": str(UPLOADS_DIR),
    }
