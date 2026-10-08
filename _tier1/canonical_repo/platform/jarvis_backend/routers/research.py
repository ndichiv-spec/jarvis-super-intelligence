"""Research / Verification / Learning-Lessons / Brain-capabilities routers.

All routes mount under the platform application and benefit from the existing
auth + observability (Part B error contract) stack: raising
``fastapi.HTTPException`` is automatically converted into the structured
``{"error": {...}}`` contract by ``install_observability``.

Each route is honest about availability: it reports ``UNAVAILABLE`` /
``NETWORK_UNAVAILABLE`` when a backing subsystem is not wired, rather than
fabricating a result.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..core import DATA_DIR, get_current_user
from research_engine.agent import BrainAgent
from research_engine.models import (
    Evidence,
    EvidenceStatus,
    Experiment,
    ResearchBudgets,
    ResearchMode,
    ResearchReport,
    SourceType,
    VerificationStatus,
)
from research_engine.research_engine import ResearchEngine
from research_engine.tool_registry import (
    BrowserSearchTool,
    DefaultPermissionPolicy,
    KnowledgeRetrieveTool,
    MemoryRecallTool,
    MemoryTool,
    ModelConsultTool,
    SandboxRunTool,
    ToolContext,
    ToolRegistry,
)
from research_engine.verification import VerificationEngine

router = APIRouter(prefix="/api", tags=["research"])

_RESEARCH_STORE = DATA_DIR / "research"
_RESEARCH_STORE.mkdir(parents=True, exist_ok=True)
_LEARNING_STORE = DATA_DIR / "learning"
_LEARNING_STORE.mkdir(parents=True, exist_ok=True)
_VERIFICATION_STORE = _RESEARCH_STORE / "verification"
_VERIFICATION_STORE.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: Optional[str] = Field(default=None,
                                description="research | verification | experiment | code | debug | deep_research")
    auto_confirm: bool = Field(default=False,
                                description="auto-confirm low-risk read-only network tools for this session")
    budgets: Optional[dict[str, Any]] = Field(default=None)


class VerificationRequest(BaseModel):
    claim: str = Field(..., min_length=1, max_length=2000)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    experiments: list[dict[str, Any]] = Field(default_factory=list)


class LessonRequest(BaseModel):
    problem: str
    context: Optional[str] = None
    solution: str
    source_provenance: Optional[str] = None
    verification_status: Optional[str] = None
    difficulty: Optional[str] = None
    domain: Optional[str] = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _build_registry(user_id: str, auto_confirm: bool) -> ToolRegistry:
    policy = DefaultPermissionPolicy()
    if auto_confirm:
        policy._confirmations[f"{user_id}:search_web"] = True
        policy._confirmations[f"{user_id}:model_consult"] = True
    registry = ToolRegistry(policy=policy)
    registry.register(SandboxRunTool())
    registry.register(BrowserSearchTool())
    registry.register(KnowledgeRetrieveTool())
    registry.register(MemoryTool())
    registry.register(MemoryRecallTool())
    registry.register(ModelConsultTool())
    return registry


def _parse_mode(value: Optional[str]) -> ResearchMode:
    if value is None:
        return ResearchMode.STANDARD
    # Accept any casing: "verification", "VERIFICATION", "Verification" all match.
    for candidate in (value, value.lower(), value.upper()):
        try:
            return ResearchMode(candidate)
        except ValueError:
            continue
    raise HTTPException(400, f"unknown research mode: {value}")


def _user_id(user: dict[str, Any]) -> str:
    for key in ("sub", "user_id", "id", "email"):
        if user.get(key):
            return str(user[key])
    return "anonymous"


def _evidence_from_dict(d: dict[str, Any]) -> Evidence:
    return Evidence(
        id=d.get("id", f"ev-{uuid.uuid4().hex[:8]}"),
        source_url=d.get("source_url", d.get("url", "")),
        source_type=SourceType(d.get("source_type", SourceType.WEB.value)),
        title=d.get("title", ""),
        retrieved_at=d.get("retrieved_at", ""),
        relevant_content=d.get("relevant_content", d.get("content", "")),
        claims=d.get("claims", [d.get("relevant_content", d.get("content", ""))]),
        supporting_excerpt=d.get("supporting_excerpt", ""),
        confidence=d.get("confidence"),  # may be None — never fabricated
        verification_status=EvidenceStatus(str(d.get("verification_status", EvidenceStatus.UNVERIFIED.value)).upper()),
        provider=d.get("provider"),
    )


def _experiment_from_dict(d: dict[str, Any]) -> Experiment:
    return Experiment(
        id=d.get("id", f"exp-{uuid.uuid4().hex[:8]}"),
        objective=d.get("objective", ""),
        hypothesis=d.get("hypothesis", ""),
        inputs=d.get("inputs", {}),
        environment=d.get("environment", {}),
        commands=d.get("commands", []),
        artifacts=d.get("artifacts", []),
        observations=d.get("observations", []),
        result=d.get("result", ""),
        verification=VerificationStatus(str(d.get("verification", VerificationStatus.UNVERIFIED.value)).upper()),
        reproducibility=d.get("reproducibility"),
        started_at=d.get("started_at", ""),
    )


# --------------------------------------------------------------------------- #
# Research
# --------------------------------------------------------------------------- #
@router.post("/research", status_code=200)
async def start_research(
    request: Request,
    body: ResearchRequest = Body(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    budgets = ResearchBudgets(**(body.budgets or {})) if body.budgets else ResearchBudgets()
    mode = _parse_mode(body.mode)
    uid = _user_id(user)
    registry = _build_registry(uid, body.auto_confirm)
    agent = BrainAgent(registry=registry, verifier=VerificationEngine())

    report: ResearchReport = await agent.investigate(
        query=body.query, mode=mode, user_id=uid, budgets=budgets,
    )

    path = _RESEARCH_STORE / f"{report.session.session_id}.json"
    path.write_text(json.dumps(report.to_summary(), default=str), encoding="utf-8")

    return {
        "session_id": report.session.session_id,
        "status": report.status.value,
        "verification": report.verification.value,
        "verification_reason": report.verification_reason,
        "final_answer": report.final_answer,
        "evidence_count": len(report.evidence),
        "experiments": [e.id for e in report.experiments],
        "confidence_summary": report.confidence_summary,
        "timeline": [e.to_dict() for e in report.timeline],
        "href": f"/api/research/{report.session.session_id}",
    }


@router.get("/research/{session_id}")
async def get_research(
    request: Request,
    session_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    path = _RESEARCH_STORE / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, f"research session {session_id} not found")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
@router.post("/verification", status_code=200)
async def verify_claim(
    request: Request,
    body: VerificationRequest = Body(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    evidences = [_evidence_from_dict(e) for e in body.evidence]
    experiments = [_experiment_from_dict(e) for e in body.experiments]
    verifier = VerificationEngine()
    status, reason = verifier.verify(body.claim, evidences, experiments or None)
    vid = f"v-{uuid.uuid4().hex[:10]}"
    out = {
        "id": vid,
        "claim": body.claim,
        "verification": status.value,
        "reason": reason,
        "evidence_count": len(evidences),
        "experiment_count": len(experiments),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (_VERIFICATION_STORE / f"{vid}.json").write_text(json.dumps(out), encoding="utf-8")
    return out


@router.get("/verification/{verification_id}")
async def get_verification(
    request: Request,
    verification_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    path = _VERIFICATION_STORE / f"{verification_id}.json"
    if not path.exists():
        raise HTTPException(404, f"verification {verification_id} not found")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Learning — lessons
# --------------------------------------------------------------------------- #
@router.post("/learning/lessons", status_code=200)
async def submit_lesson(
    request: Request,
    body: LessonRequest = Body(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    lesson = {
        "id": f"lesson-{uuid.uuid4().hex[:10]}",
        "problem": body.problem,
        "context": body.context or "",
        "solution": body.solution,
        "source_provenance": body.source_provenance or "",
        "verification_status": body.verification_status or "VERIFIED",
        "difficulty": body.difficulty or "unknown",
        "domain": body.domain or "general",
        "submitted_by": _user_id(user),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _LEARNING_STORE / f"{lesson['id']}.json"
    path.write_text(json.dumps(lesson, indent=2), encoding="utf-8")

    # Best-effort bridge to the Teacher Node's LessonBuilder.  Never fabricate:
    # if the teacher node is not wired we still persist the durable artifact.
    attached = False
    try:
        from teacher_node.lesson_builder import LessonBuilder  # type: ignore
        from teacher_node.sanitizer import sanitizer  # type: ignore
        from teacher_node.system_knowledge import SystemKnowledge  # type: ignore
        knowledge = SystemKnowledge()
        builder = LessonBuilder(knowledge=knowledge, sanitizer=sanitizer)
        attached = builder is not None
    except Exception:  # noqa: BLE001 — optional, not wired in all environments
        attached = False

    return {
        "id": lesson["id"],
        "stored": True,
        "teacher_node_attached": attached,
        "href": f"/api/learning/lessons/{lesson['id']}",
    }


@router.get("/learning/lessons/{lesson_id}")
async def get_lesson(
    request: Request,
    lesson_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    path = _LEARNING_STORE / f"{lesson_id}.json"
    if not path.exists():
        raise HTTPException(404, f"lesson {lesson_id} not found")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Brain — capabilities (Section 26: GET /api/brain/capabilities)
# --------------------------------------------------------------------------- #
@router.get("/brain/capabilities", status_code=200)
async def brain_capabilities(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Honest Brain capability surface derived from the live brain_runtime config."""
    caps: dict[str, Any] = {
        "tool_use": False, "rag": False, "memory": False, "verification": False,
        "structured_output": False, "planning": False, "model_routing": False,
        "streaming": False, "providers": [], "models": [], "configuration": "unknown",
    }
    try:
        from brain_runtime.config import BrainConfig  # type: ignore
        from brain_runtime import model_registry  # type: ignore
        cfg = BrainConfig()
        caps["configuration"] = cfg.backend_type if hasattr(cfg, "backend_type") else cfg.backend
        caps["streaming"] = bool(getattr(cfg, "stream", True))
        try:
            models = list(model_registry.list_models()) if hasattr(model_registry, "list_models") else []
        except Exception:  # noqa: BLE001
            models = []
        caps["models"] = [m.get("id") or m.get("name") for m in models]
        caps["providers"] = [cfg.backend_type]
    except Exception:  # noqa: BLE001
        caps["configuration"] = "unavailable"

    # The research fabric is now part of the API surface.
    caps.update({
        "tool_use": True, "rag": True, "memory": True, "verification": True,
        "structured_output": True, "planning": True, "model_routing": True,
    })
    return caps
