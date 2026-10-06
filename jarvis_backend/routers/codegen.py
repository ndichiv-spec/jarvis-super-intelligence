"""Code generation, review, and deployment prep endpoints."""

from __future__ import annotations

import os
import stat
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core import ROOT, _require_admin, ai_service, get_current_user

router = APIRouter(prefix="/api/v1/codegen", tags=["codegen"])
_REVIEW_SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".jsx",
    ".kt", ".php", ".py", ".rb", ".rs", ".scala", ".sh", ".sql", ".swift",
    ".ts", ".tsx", ".vue",
}


class GenerateIn(BaseModel):
    spec: dict[str, Any] = {}
    description: str | None = None
    language: str | None = None


@router.post("/generate")
async def generate(
    body: GenerateIn,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
):
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
async def review(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    path: Annotated[str, Query(min_length=1, max_length=500)],
):
    root = ROOT.resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical_path = Path(os.path.abspath(candidate))
    try:
        relative_path = lexical_path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Review source not found")

    current = root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise HTTPException(status_code=404, detail="Review source not found")

    try:
        resolved = lexical_path.resolve(strict=True)
        relative_path = resolved.relative_to(root)
        source_stat = resolved.stat()
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=404, detail="Review source not found")
    if not stat.S_ISREG(source_stat.st_mode) or resolved.suffix.lower() not in _REVIEW_SOURCE_SUFFIXES:
        raise HTTPException(status_code=404, detail="Review source not found")

    try:
        with resolved.open("r", encoding="utf-8", errors="replace") as source_file:
            content = source_file.read(2000)
    except OSError:
        raise HTTPException(status_code=404, detail="Review source not found")
    review_result = await ai_service.chat(f"Review this code for bugs:\n{content}")
    return {
        "path": relative_path.as_posix(),
        "review": review_result,
        "issues": None,
        "passed": None,
        "validation": "not_run",
    }


@router.post("/deploy")
async def deploy(_user: Annotated[dict[str, Any], Depends(_require_admin)]):
    raise HTTPException(status_code=501, detail="Deployment is not implemented")
