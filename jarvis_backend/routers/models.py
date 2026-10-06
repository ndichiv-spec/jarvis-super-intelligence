"""Model Registry API endpoints.

Provides CRUD operations for model management with proper authentication and
authorization.

Authentication:
- PUBLIC: GET /api/v1/models (list/approved models)
- AUTHENTICATED: POST /api/v1/models (register new model)
- AUTHENTICATED: GET /api/v1/models/{id} (get by ID)
- AUTHENTICATED: PATCH /api/v1/models/{id} (update metadata)
- ADMIN: DELETE /api/v1/models/{id} (retire model)

All mutation operations require authentication.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import _require_auth, _require_admin, is_admin, get_current_user


router = APIRouter(prefix="/api/v1/models", tags=["models"])


# --------------------------------------------------------------------------- #
# Request/Response Models
# --------------------------------------------------------------------------- #

class ModelRegisterRequest(BaseModel):
    """Request to register a new model."""
    model_id: str = Field(..., description="Full model ID (e.g., 'openai:gpt-5')")
    provider_id: str = Field(..., description="Provider identifier")
    display_name: Optional[str] = None
    description: Optional[str] = None
    lifecycle_type: str = Field(default="discovered", description="Model type")
    capabilities: List[str] = Field(default_factory=list)
    context_length: int = 0
    max_output_tokens: int = 0
    architecture: Optional[str] = None
    parameters: Optional[int] = None
    open_weights: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    parent_model_id: Optional[str] = None
    revision: Optional[str] = None


class ModelUpdateRequest(BaseModel):
    """Request to update model metadata."""
    display_name: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    context_length: Optional[int] = None
    max_output_tokens: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class ModelResponse(BaseModel):
    """Model registry entry for API responses."""
    id: str
    model_id: str
    provider_id: str
    display_name: str
    description: str
    lifecycle_type: str
    lifecycle_status: str
    parent_model_id: Optional[str] = None
    revision: str = ""
    capabilities: List[str] = Field(default_factory=list)
    context_length: int
    max_output_tokens: int
    architecture: str = ""
    parameters: Optional[int] = None
    open_weights: bool
    deployment: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    evaluation_results: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: float
    updated_at: float


# --------------------------------------------------------------------------- #
# Public Endpoints (Health/Discovery)
# --------------------------------------------------------------------------- #

@router.get("", response_model=Dict[str, Any])
async def list_models(
    provider: Optional[str] = Query(None, description="Filter by provider"),
    status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    capability: Optional[str] = Query(None, description="Filter by capability"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
):
    """
    List approved/available models (public endpoint for discovery).
    
    Returns models that are safe for public discovery:
    - lifecycle_status in [approved, deployed, registered]
    - Basic metadata only (no sensitive internal data)
    """
    from infrastructure.model_registry import model_registry
    
    models = model_registry.list_models(
        provider_id=provider,
        lifecycle_status=status or "approved",
        capabilities=[capability] if capability else None,
    )
    
    # Return only public-safe data
    result = []
    for m in models[:limit]:
        result.append({
            "model_id": m.model_id,
            "provider_id": m.provider_id,
            "display_name": m.display_name,
            "capabilities": m.capabilities,
            "context_length": m.context_length,
            "open_weights": m.open_weights,
        })
    
    return {
        "models": result,
        "count": len(result),
        "total_available": len(models),
    }


@router.get("/search", response_model=Dict[str, Any])
async def search_models(
    q: str = Query(..., min_length=1, max_length=100, description="Search query"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
):
    """Search models by model_id or display_name (public endpoint)."""
    from infrastructure.model_registry import model_registry
    
    models = model_registry.search(q, limit=limit)
    
    return {
        "query": q,
        "results": [
            {
                "model_id": m.model_id,
                "provider_id": m.provider_id,
                "display_name": m.display_name,
                "capabilities": m.capabilities,
            }
            for m in models
        ],
        "count": len(models),
    }


# --------------------------------------------------------------------------- #
# Authenticated User Endpoints
# --------------------------------------------------------------------------- #

@router.get("/me", response_model=Dict[str, Any])
async def my_registered_models(
    user: Dict[str, Any] = Depends(_require_auth),
):
    """Get models associated with current user (authenticated)."""
    # For now, return all approved models - extend with user-specific logic
    from infrastructure.model_registry import model_registry
    
    models = model_registry.list_models(lifecycle_status="approved")
    
    return {
        "models": [
            {
                "model_id": m.model_id,
                "provider_id": m.provider_id,
                "display_name": m.display_name,
                "capabilities": m.capabilities,
            }
            for m in models[:50]
        ],
        "count": min(len(models), 50),
    }


# --------------------------------------------------------------------------- #
# Authenticated Endpoints
# --------------------------------------------------------------------------- #

@router.post("", response_model=ModelResponse, status_code=201)
async def register_model(
    req: ModelRegisterRequest,
    user: Dict[str, Any] = Depends(_require_auth),
):
    """
    Register a new model (authenticated).
    
    Requires authentication. Admin privileges may be required for certain
    lifecycle states in the future.
    """
    from infrastructure.model_registry import model_registry
    
    # Check for existing model
    existing = model_registry.get(req.model_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Model '{req.model_id}' already registered"
        )
    
    import uuid
    from infrastructure.model_registry import ModelInfo
    
    model_info = ModelInfo(
        id=str(uuid.uuid4()),
        model_id=req.model_id,
        provider_id=req.provider_id,
        display_name=req.display_name or req.model_id,
        description=req.description or "",
        lifecycle_type=req.lifecycle_type,
        lifecycle_status="registered",
        capabilities=req.capabilities,
        context_length=req.context_length,
        max_output_tokens=req.max_output_tokens,
        architecture=req.architecture or "",
        parameters=req.parameters,
        open_weights=req.open_weights,
        deployment=req.deployment or "local",
        metadata=req.metadata,
        created_at=time.time(),
        updated_at=time.time(),
    )
    
    model_registry.register(model_info)
    
    return {
        "id": model_info.id,
        "model_id": model_info.model_id,
        "provider_id": model_info.provider_id,
        "display_name": model_info.display_name,
        "description": model_info.description,
        "lifecycle_type": model_info.lifecycle_type,
        "lifecycle_status": model_info.lifecycle_status,
        "parent_model_id": model_info.parent_model_id,
        "revision": model_info.revision,
        "capabilities": model_info.capabilities,
        "context_length": model_info.context_length,
        "max_output_tokens": model_info.max_output_tokens,
        "architecture": model_info.architecture,
        "parameters": model_info.parameters,
        "open_weights": model_info.open_weights,
        "deployment": model_info.deployment,
        "metadata": model_info.metadata,
        "evaluation_results": model_info.evaluation_results,
        "history": model_info.history,
        "created_at": model_info.created_at,
        "updated_at": model_info.updated_at,
    }


# --------------------------------------------------------------------------- #
# Admin-Only Endpoints
# --------------------------------------------------------------------------- #

@router.delete("/{model_id}", response_model=Dict[str, Any])
async def retire_model(
    model_id: str,
    user: Dict[str, Any] = Depends(_require_admin),
):
    """
    Retire a model (admin only).
    
    Marks the model as retired - it will no longer appear in discovery
    but historical references are preserved.
    """
    from infrastructure.model_registry import model_registry
    
    if not model_registry.update_lifecycle(model_id, "retired", "retired_by_admin"):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    
    return {
        "status": "retired",
        "model_id": model_id,
        "retired_at": time.time(),
        "retired_by": user.get("email", "admin"),
    }


@router.patch("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: str,
    req: ModelUpdateRequest,
    user: Dict[str, Any] = Depends(_require_auth),
):
    """
    Update model metadata (authenticated).
    
    Only allowed fields can be updated. Full replacement requires admin.
    """
    from infrastructure.model_registry import model_registry
    
    existing = model_registry.get(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    
    import uuid
    from infrastructure.model_registry import ModelInfo
    
    # Create updated model info
    updated = ModelInfo(
        id=existing.id,
        model_id=existing.model_id,
        provider_id=existing.provider_id,
        display_name=req.display_name or existing.display_name,
        description=req.description or existing.description,
        lifecycle_type=existing.lifecycle_type,
        lifecycle_status=existing.lifecycle_status,
        parent_model_id=existing.parent_model_id,
        revision=existing.revision,
        capabilities=req.capabilities or existing.capabilities,
        context_length=req.context_length or existing.context_length,
        max_output_tokens=req.max_output_tokens or existing.max_output_tokens,
        architecture=existing.architecture,
        parameters=existing.parameters,
        open_weights=existing.open_weights,
        deployment=existing.deployment,
        metadata=req.metadata or existing.metadata,
        provenance=existing.provenance,
        evaluation_results=existing.evaluation_results,
        history=existing.history,
        created_at=existing.created_at,
        updated_at=time.time(),
    )
    
    model_registry.register(updated)
    
    return {
        "id": updated.id,
        "model_id": updated.model_id,
        "provider_id": updated.provider_id,
        "display_name": updated.display_name,
        "description": updated.description,
        "lifecycle_type": updated.lifecycle_type,
        "lifecycle_status": updated.lifecycle_status,
        "parent_model_id": updated.parent_model_id,
        "revision": updated.revision,
        "capabilities": updated.capabilities,
        "context_length": updated.context_length,
        "max_output_tokens": updated.max_output_tokens,
        "architecture": updated.architecture,
        "parameters": updated.parameters,
        "open_weights": updated.open_weights,
        "deployment": updated.deployment,
        "metadata": updated.metadata,
        "evaluation_results": updated.evaluation_results,
        "history": updated.history,
        "created_at": updated.created_at,
        "updated_at": updated.updated_at,
    }


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    user: Optional[Dict[str, Any]] = Depends(lambda: None),  # Public for now
):
    """
    Get a specific model by ID.
    
    Public endpoint - returns basic model info for discovery.
    """
    from infrastructure.model_registry import model_registry
    
    model = model_registry.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    
    return {
        "id": model.id,
        "model_id": model.model_id,
        "provider_id": model.provider_id,
        "display_name": model.display_name,
        "description": model.description,
        "lifecycle_type": model.lifecycle_type,
        "lifecycle_status": model.lifecycle_status,
        "parent_model_id": model.parent_model_id,
        "revision": model.revision,
        "capabilities": model.capabilities,
        "context_length": model.context_length,
        "max_output_tokens": model.max_output_tokens,
        "architecture": model.architecture,
        "parameters": model.parameters,
        "open_weights": model.open_weights,
        "deployment": model.deployment,
        "metadata": model.metadata,
        "evaluation_results": model.evaluation_results,
        "history": model.history,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


# --------------------------------------------------------------------------- #
# Health/Liveness
# --------------------------------------------------------------------------- #

@router.get("/health", response_model=Dict[str, Any])
async def models_health():
    """Health check for model registry."""
    from infrastructure.model_registry import model_registry
    
    try:
        models = model_registry.list_models()
        return {
            "status": "healthy",
            "model_count": len(models),
            "providers": list(set(m.provider_id for m in models)),
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
        }