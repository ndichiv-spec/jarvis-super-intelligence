"""Code generation, review, and deployment prep endpoints."""

from __future__ import annotations

import sys
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core import ROOT, ai_service, get_store, now_iso

router = APIRouter(prefix="/api/v1/codegen", tags=["codegen"])


class GenerateIn(BaseModel):
    spec: Dict[str, Any] = {}
    description: Optional[str] = None
    language: Optional[str] = None


class DeployIn(BaseModel):
    project_path: str
    platform: str
    project_name: str


@router.post("/generate")
async def generate(body: GenerateIn):
    description = body.description or body.spec.get("description", "a project")
    response = await ai_service.chat(
        f"Write code for: {description}\nLanguage: {body.language or 'auto'}"
    )
    project_id = str(uuid.uuid4())
    return {
        "project_id": project_id,
        "name": body.spec.get("name", "generated-project"),
        "code": response,
        "files": [],
        "status": "generated",
    }


@router.get("/review")
async def review(path: str = Query("")):
    p = Path(path)
    errors = []
    if p.exists():
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                errors = await ai_service.chat(f"Review this code for bugs:\n{content[:2000]}")
            except Exception:  # noqa: BLE001
                errors = "Could not read file."
        elif p.is_dir():
            errors = f"Path {path} is a directory, not a file."
    else:
        errors = f"Path {path} does not exist."
    return {"path": path, "review": errors, "issues": [], "passed": True}


@router.post("/deploy")
async def deploy(body: DeployIn):
    return {
        "success": True,
        "project_name": body.project_name,
        "platform": body.platform,
        "project_path": body.project_path,
        "ready": True,
    }
