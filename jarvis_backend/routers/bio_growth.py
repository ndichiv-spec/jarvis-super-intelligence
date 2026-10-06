"""REST endpoints for the bio-growth intelligence layer.

Exposes the four bio-growth capabilities through the existing JARVIS API
surface.  Every request flows through the Orchestrator (which wraps the
execution in an OpenTelemetry span and emits correlation-traced events),
so the new endpoints get full observability for free.

All endpoints are authenticated and use the same ``get_current_user``
dependency as the rest of the platform.

Routes (mount prefix /api/v1):
  - /research/ingest           → research.cortex.ingest_url
  - /research/ingest-content   → research.cortex.ingest_content
  - /research/knowledge-graph  → research.cortex.get_knowledge_graph
  - /research/status           → research.cortex.get_status
  - /science/solve             → science.engine.solve
  - /science/status            → science.engine health
  - /learning/study            → bio.learner.study_concept
  - /learning/consolidate      → bio.learner.consolidate
  - /learning/path             → bio.learner.get_learning_path
  - /learning/due              → bio.learner.review_due
  - /learning/review           → bio.learner.perform_review
  - /learning/status           → bio.learner.get_status
  - /tech/discover             → tech.evolution.discover
  - /tech/radar                → tech.evolution.get_tech_radar
  - /tech/frontiers            → tech.evolution.get_frontiers
  - /tech/lifecycle            → tech.evolution.model_lifecycle
  - /tech/status               → tech.evolution.get_status
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..core import get_current_user, now_iso
from ..capability import get_orchestrator, ExecutionContext


router = APIRouter(prefix="/api/v1", tags=["bio-growth"])


def _make_context(user: dict[str, Any], session_id: str = "default") -> ExecutionContext:
    """Build an ExecutionContext from the authenticated user."""
    uid = ""
    for key in ("sub", "user_id", "id", "email"):
        if user.get(key):
            uid = str(user[key])
            break
    return ExecutionContext(
        user_id=uid or "anonymous",
        session_id=session_id,
        correlation_id=f"rest-{__import__('uuid').uuid4().hex[:12]}",
        permissions=list(user.get("permissions", [])),
    )


# --------------------------------------------------------------------------- #
# Pydantic request bodies
# --------------------------------------------------------------------------- #
class ScienceSolveBody(BaseModel):
    operation: str = Field(..., description="Science operation to perform")
    problem: Optional[str] = None
    variable: str = "x"
    matrix: Optional[list[list[float]]] = None
    data: Optional[list[float]] = None
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    mc_operation: Optional[str] = None
    n_samples: Optional[int] = None


class ConceptBody(BaseModel):
    domain: str = Field(..., min_length=1, max_length=255)
    concept: str = Field(..., min_length=1, max_length=500)


class ReviewBody(BaseModel):
    item_key: str = Field(..., min_length=1, max_length=500)
    quality: int = Field(3, ge=0, le=5)


class LifecycleBody(BaseModel):
    tech_id: str = Field(..., min_length=1, max_length=255)


class IngestUrlBody(BaseModel):
    url: str = Field(..., min_length=5, max_length=2000)
    title: Optional[str] = None
    source_type: str = "web_crawl"


class IngestContentBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    source: str = "user"
    source_type: str = "web_crawl"


def _require_operator(user: dict[str, Any]) -> None:
    roles = user.get("roles") or []
    if not any(role in {"admin", "owner", "developer"} for role in roles if isinstance(role, str)):
        raise HTTPException(status_code=403, detail="Admin or Developer role required")


# --------------------------------------------------------------------------- #
# Research Cortex  (research.cortex)
# --------------------------------------------------------------------------- #
@router.get("/research/workflow/status")
async def research_workflow_status(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Report the active backend research workflow's scheduler and last run."""
    _require_operator(user)
    from ..bio_growth_worker import get_bio_growth_worker

    workflow = get_bio_growth_worker().get_status()
    if workflow["execution_mode"] == "celery":
        from ..celery_app import get_queue_runtime_status

        workflow["queue"] = await asyncio.to_thread(get_queue_runtime_status)
    return {"workflow": workflow}


@router.post("/research/workflow/run")
async def run_research_workflow_now(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Run one due-feed research cycle now and return its persisted outcome."""
    _require_operator(user)
    from ..bio_growth_worker import get_bio_growth_worker

    worker = get_bio_growth_worker()
    if worker.get_status()["execution_mode"] == "celery":
        from ..celery_app import get_queue_runtime_status
        from ..celery_tasks import enqueue_research_poll

        queue_status = await asyncio.to_thread(get_queue_runtime_status)
        if not queue_status["broker_reachable"]:
            raise HTTPException(
                status_code=503,
                detail="Research queue broker is unavailable; task was not submitted",
            )
        if queue_status["worker_probe"] != "ok":
            raise HTTPException(
                status_code=503,
                detail="No research worker is responding; task was not submitted",
            )
        try:
            task_id = await asyncio.to_thread(enqueue_research_poll)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Research task submission failed ({type(exc).__name__})",
            ) from exc
        return {
            "success": True,
            "status": "queued",
            "task_id": task_id,
            "queue": "research",
        }

    execution = await worker.run_once()
    if execution["status"] == "failed":
        raise HTTPException(status_code=502, detail="Bio-Growth research workflow failed")
    return {"success": True, "execution": execution}


@router.post("/research/ingest")
async def research_ingest(
    request: Request,
    body: IngestUrlBody = Body(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Ingest a URL into the research cortex knowledge graph."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "research.cortex",
        {"action": "ingest_url", "params": {"url": body.url, "title": body.title, "source_type": body.source_type}},
        ctx,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "Research ingestion failed")
    return {"success": True, "data": result.data, "correlation_id": result.correlation_id}


@router.post("/research/ingest-content")
async def research_ingest_content(
    request: Request,
    body: IngestContentBody = Body(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Ingest raw text content into the research cortex knowledge graph."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "research.cortex",
        {"action": "ingest_content", "params": {
            "title": body.title, "content": body.content,
            "source": body.source, "source_type": body.source_type,
        }},
        ctx,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "Content ingestion failed")
    return {"success": True, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/research/knowledge-graph")
async def research_knowledge_graph(
    request: Request,
    limit: int = 100,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the research knowledge graph."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "research.cortex",
        {"action": "get_knowledge_graph", "params": {"limit": limit}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/research/status")
async def research_status(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get research cortex status (feed health, item counts, knowledge graph size)."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "research.cortex",
        {"action": "get_status", "params": {}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/research/search/{query}")
async def research_semantic_search(
    request: Request,
    query: str,
    limit: int = 10,
    source: str = "knowledge_graph",
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Semantic vector search across ingested research content.

    Uses pgvector-style embeddings (TF-IDF hash fallback when sentence-transformers unavailable).
    """
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "research.cortex",
        {"action": "semantic_search", "params": {"query": query, "limit": limit, "source": source}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


# --------------------------------------------------------------------------- #
# Science Engine  (science.engine)
# --------------------------------------------------------------------------- #
@router.post("/science/solve")
async def science_solve(
    request: Request,
    body: ScienceSolveBody = Body(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Solve a symbolic/numerical math problem via the Science Engine."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    params: dict[str, Any] = {"operation": body.operation}
    if body.problem is not None:
        params["problem"] = body.problem
    if body.variable:
        params["variable"] = body.variable
    if body.matrix is not None:
        params["matrix"] = body.matrix
    if body.data is not None:
        params["data"] = body.data
    if body.x_min is not None:
        params["x_min"] = body.x_min
    if body.x_max is not None:
        params["x_max"] = body.x_max
    if body.mc_operation:
        params["mc_operation"] = body.mc_operation
    if body.n_samples is not None:
        params["n_samples"] = body.n_samples

    result = await orch.execute_capability(
        "science.engine",
        {"action": "solve", "params": params},
        ctx,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "Science computation failed")
    return {"success": True, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/science/status")
async def science_status(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get science engine status (library availability)."""
    orch = get_orchestrator()
    caps = orch.registry.get_status()
    sci = caps.get("science.engine", {})
    return {
        "status": "ok",
        "timestamp": now_iso(),
        "science_engine": sci,
    }


# --------------------------------------------------------------------------- #
# Bio Learner  (bio.learner)
# --------------------------------------------------------------------------- #
@router.post("/learning/study")
async def learning_study(
    request: Request,
    body: ConceptBody = Body(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Study a concept within a learning domain."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "bio.learner",
        {"action": "study_concept", "params": {"domain": body.domain, "concept": body.concept}},
        ctx,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "Study failed")
    return {"success": True, "data": result.data, "correlation_id": result.correlation_id}


@router.post("/learning/consolidate")
async def learning_consolidate(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Run hippocampal replay + cross-domain synthesis."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "bio.learner",
        {"action": "consolidate", "params": {}},
        ctx,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "Consolidation failed")
    return {"success": True, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/learning/path/{domain}")
async def learning_path(
    request: Request,
    domain: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the curriculum learning path for a domain."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "bio.learner",
        {"action": "get_learning_path", "params": {"domain": domain}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/learning/due")
async def learning_due(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get due reviews (SM-2 spaced repetition)."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "bio.learner",
        {"action": "review_due", "params": {}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


@router.post("/learning/review")
async def learning_review(
    request: Request,
    body: ReviewBody = Body(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Perform a spaced-repetition review."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "bio.learner",
        {"action": "perform_review", "params": {
            "item_key": body.item_key,
            "quality": body.quality,
        }},
        ctx,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "Review failed")
    return {"success": True, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/learning/status")
async def learning_status(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get bio-learner status (domains, maturity, growth stage)."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "bio.learner",
        {"action": "get_status", "params": {}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


# --------------------------------------------------------------------------- #
# Tech Evolution Tracker  (tech.evolution)
# --------------------------------------------------------------------------- #
@router.post("/tech/discover")
async def tech_discover(
    request: Request,
    limit: int = 50,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Discover new technologies from research ingestion."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "tech.evolution",
        {"action": "discover", "params": {"limit": limit}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/tech/radar")
async def tech_radar(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the ThoughtWorks-style tech radar."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "tech.evolution",
        {"action": "get_tech_radar", "params": {}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/tech/frontiers")
async def tech_frontiers(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get mapped research frontiers with cross-domain synthesis."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "tech.evolution",
        {"action": "get_frontiers", "params": {}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


@router.post("/tech/lifecycle")
async def tech_lifecycle(
    request: Request,
    body: LifecycleBody = Body(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Model a technology's adoption lifecycle (S-curve)."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "tech.evolution",
        {"action": "model_lifecycle", "params": {"tech_id": body.tech_id}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


@router.get("/tech/status")
async def tech_status(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get tech evolution tracker status."""
    orch = get_orchestrator()
    ctx = _make_context(user)
    result = await orch.execute_capability(
        "tech.evolution",
        {"action": "get_status", "params": {}},
        ctx,
    )
    return {"success": result.success, "data": result.data, "correlation_id": result.correlation_id}


# --------------------------------------------------------------------------- #
# Observability status  (LangSmith + Qwen-Agent integration)
# --------------------------------------------------------------------------- #
@router.get("/observability/status")
async def observability_status(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Check observability integration status (LangSmith tracing + OTel)."""
    from jarvis_backend.langsmith_integration import (
        get_langsmith_tracer, langsmith_available, MODEL_PRICING
    )
    from jarvis_backend.phoenix_integration import get_phoenix_status
    ls = get_langsmith_tracer()
    traces = ls.get_in_memory_traces()
    return {
        "langsmith": {
            "available": langsmith_available(),
            "client_active": ls.available,
            "in_memory_traces": len(traces),
            "pricing_models": len(MODEL_PRICING),
        },
        "phoenix": get_phoenix_status(),
    }


@router.get("/orchestration/status")
async def orchestration_status(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Check Qwen-Agent multi-agent orchestration status."""
    from jarvis_backend.qwen_agent_bridge import get_qwen_agent_status
    return {"qwen_agent": get_qwen_agent_status()}


@router.get("/temporal/status")
async def temporal_status(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Check Temporal.io workflow orchestration status."""
    from jarvis_backend.temporal_workflows import get_temporal_status
    return {"temporal": get_temporal_status()}


@router.get("/a2a/status")
async def a2a_status(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Check A2A (Agent2Agent) protocol server status."""
    from jarvis_backend.a2a_server import a2a_available, CAPABILITY_SKILLS
    return {
        "a2a_sdk_available": a2a_available(),
        "agent_card_url": "/.well-known/agent-card.json",
        "jsonrpc_endpoint": "/a2a",
        "skills_exposed": [s["id"] for s in CAPABILITY_SKILLS],
        "skill_count": len(CAPABILITY_SKILLS),
    }
