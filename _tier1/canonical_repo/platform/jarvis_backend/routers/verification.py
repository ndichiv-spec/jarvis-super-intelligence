"""
Verification endpoints for Phase 6 - Intelligent Operating Layer.

Provides API endpoints for:
- Code verification (syntax, type checking, tests)
- Document verification (JSON, CSV, schema)
- Data verification (file existence, extension)
- Job/artifact verification

These endpoints consume the verification engine and integrate with existing
ToolRegistry as the single execution boundary.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core import _require_auth, get_store, ai_service
from ..verify import (
    VerificationStatus,
    get_verification_engine,
)

router = APIRouter(prefix="/api/v1", tags=["verification"])

logger = logging.getLogger("verification_router")


# --------------------------------------------------------------------------- #
# Request/Response Models
# --------------------------------------------------------------------------- #

class VerifyCodeRequest(BaseModel):
    """Request to verify Python code."""
    code: Optional[str] = Field(None, description="Python source code to verify")
    file_path: Optional[str] = Field(None, description="Path to Python file to verify")
    check_type: str = Field(default="syntax", description="Type of check: syntax, type_check, imports, tests")
    timeout: int = Field(default=30, description="Timeout in seconds")


class VerifyDocumentRequest(BaseModel):
    """Request to verify a document."""
    content: Optional[str] = Field(None, description="Document content to verify")
    format: str = Field(..., description="Document format: json, csv, schema")
    file_path: Optional[str] = Field(None, description="Path to document file")
    json_schema: Optional[Dict] = Field(None, description="JSON Schema for validation")


class VerifyDataRequest(BaseModel):
    """Request to verify data/artifacts."""
    file_path: str = Field(..., description="Path to verify")
    expected_extensions: Optional[List[str]] = Field(None, description="Expected file extensions")
    verify_exists: bool = Field(default=True, description="Whether to verify file exists")


class VerifyJobRequest(BaseModel):
    """Request to verify a job or artifact."""
    job_id: Optional[str] = Field(None, description="Job ID to verify")
    artifact_id: Optional[str] = Field(None, description="Artifact ID to verify")
    type: str = Field(default="job", description="Type: job, artifact")


# --------------------------------------------------------------------------- #
# Verification Endpoints
# --------------------------------------------------------------------------- #

@router.post("/verify/code")
async def verify_code(
    body: VerifyCodeRequest,
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Verify Python code for syntax, type checking, imports, or test status."""
    engine = get_verification_engine()
    
    if body.check_type == "syntax":
        if not body.code:
            raise HTTPException(status_code=400, detail="code is required for syntax check")
        result = engine.verify_python_syntax(body.code)
        
    elif body.check_type == "type_check":
        if not body.file_path:
            raise HTTPException(status_code=400, detail="file_path is required for type check")
        result = engine.verify_python_type_check(body.file_path, timeout=body.timeout)
        
    elif body.check_type == "imports":
        if not body.file_path:
            raise HTTPException(status_code=400, detail="file_path is required for import check")
        result = engine.verify_imports(body.file_path)
        
    elif body.check_type == "tests":
        if not body.file_path:
            raise HTTPException(status_code=400, detail="file_path is required for test check")
        result = engine.verify_tests(body.file_path, timeout=body.timeout)
        
    else:
        raise HTTPException(status_code=400, detail=f"Unknown check type: {body.check_type}")
    
    return result.to_dict()


@router.post("/verify/document")
async def verify_document(
    body: VerifyDocumentRequest,
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Verify document format and structure (JSON, CSV, schema validation)."""
    engine = get_verification_engine()
    
    if body.format == "json":
        if body.content is None and not body.file_path:
            raise HTTPException(status_code=400, detail="content or file_path is required for JSON verification")
        
        content = body.content or ""
        if body.file_path:
            import os
            if os.path.exists(body.file_path):
                with open(body.file_path, 'r') as f:
                    content = f.read()
            else:
                return {
                    "verified": False,
                    "status": VerificationStatus.FAILED.value,
                    "description": "File not found",
                    "details": {"file_path": body.file_path}
                }
        
        result = engine.verify_json_document(content)
        
    elif body.format == "csv":
        if body.content is None and not body.file_path:
            raise HTTPException(status_code=400, detail="content or file_path is required for CSV verification")
        
        content = body.content or ""
        if body.file_path:
            import os
            if os.path.exists(body.file_path):
                with open(body.file_path, 'r') as f:
                    content = f.read()
            else:
                return {
                    "verified": False,
                    "status": VerificationStatus.FAILED.value,
                    "description": "File not found",
                    "details": {"file_path": body.file_path}
                }
        
        result = engine.verify_csv_document(content)
        
    elif body.format == "schema":
        if not body.content or not body.json_schema:
            raise HTTPException(status_code=400, detail="content and json_schema are required for schema validation")
        result = engine.verify_schema(body.content, body.json_schema)
        
    else:
        raise HTTPException(status_code=400, detail=f"Unknown format: {body.format}")
    
    return result.to_dict()


@router.post("/verify/data")
async def verify_data(
    body: VerifyDataRequest,
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Verify data files (existence, extension)."""
    engine = get_verification_engine()
    results = []
    
    # Verify file existence
    if body.verify_exists:
        result = engine.verify_file_exists(body.file_path)
        results.append(result)
    
    # Verify extension if specified
    if body.expected_extensions:
        result = engine.verify_file_extension(body.file_path, body.expected_extensions)
        results.append(result)
    
    # Combine results
    if len(results) == 1:
        final_result = results[0]
    else:
        final_result = engine.verify_composite(results, require_all=True)
    
    return final_result.to_dict()


@router.post("/verify")
async def verify(
    body: VerifyJobRequest,
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Verify job completion or artifact existence.
    
    This endpoint integrates with the existing job and artifact registries
    to verify that operations completed successfully.
    """
    engine = get_verification_engine()
    
    if body.type == "job" and body.job_id:
        # Try to get job from tasks store
        try:
            task_store = get_store("tasks")
            jobs = task_store.load() if task_store else {}
            job = jobs.get(body.job_id)
            
            if job is None:
                return {
                    "verified": False,
                    "status": VerificationStatus.FAILED.value,
                    "description": "Job not found",
                    "details": {"job_id": body.job_id}
                }
            
            status = job.get("status", "unknown") if isinstance(job, dict) else getattr(job, 'status', 'unknown')
            
            if status == "completed":
                return {
                    "verified": True,
                    "status": VerificationStatus.PASSED.value,
                    "description": f"Job completed successfully",
                    "details": {
                        "job_id": body.job_id,
                        "status": status,
                        "result": job.get("result") if isinstance(job, dict) else None
                    }
                }
            else:
                return {
                    "verified": False,
                    "status": VerificationStatus.FAILED.value,
                    "description": f"Job status: {status}",
                    "details": {"job_id": body.job_id, "status": status}
                }
        except Exception as e:
            return {
                "verified": False,
                "status": VerificationStatus.ERROR.value,
                "description": f"Job verification error: {str(e)}"
            }
    
    elif body.type == "artifact" and body.artifact_id:
        # Try to get artifact from artifacts store
        try:
            artifact_store = get_store("artifacts")
            artifacts = artifact_store.load() if artifact_store else {}
            artifact = artifacts.get(body.artifact_id)
            
            if artifact is None:
                return {
                    "verified": False,
                    "status": VerificationStatus.FAILED.value,
                    "description": "Artifact not found"
                }
            
            artifact_type = artifact.get("type") if isinstance(artifact, dict) else getattr(artifact, 'type', 'unknown')
            
            return {
                "verified": True,
                "status": VerificationStatus.PASSED.value,
                "description": f"Artifact exists: {artifact_type}",
                "details": {
                    "artifact_id": body.artifact_id,
                    "type": artifact_type,
                    "metadata": {k: v for k, v in artifact.items() if k not in ('content', 'data')}
                }
            }
        except Exception as e:
            return {
                "verified": False,
                "status": VerificationStatus.ERROR.value,
                "description": f"Artifact verification error: {str(e)}"
            }
    
    else:
        raise HTTPException(status_code=400, detail="Either job_id or artifact_id is required, and type must be 'job' or 'artifact'")


@router.get("/verification/status")
async def verification_status(
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Get verification engine status and capabilities."""
    engine = get_verification_engine()
    
    return {
        "verification_engine": "operational",
        "capabilities": [
            "python_syntax",
            "python_type_check",
            "python_imports",
            "python_tests",
            "json_document",
            "csv_document",
            "schema_validation",
            "file_exists",
            "file_extension",
            "job_status",
            "artifact_status",
        ],
        "supported_formats": ["json", "csv", "schema"],
        "check_types": ["syntax", "type_check", "imports", "tests"],
    }


# --------------------------------------------------------------------------- #
# Integration with existing systems
# --------------------------------------------------------------------------- #

@router.get("/verify/capabilities")
async def verify_capabilities(
    user: Dict[str, Any] = Depends(_require_auth)
):
    """Discover capabilities that require verification and verify their status.
    
    This endpoint integrates with the CapabilityRegistry to discover
    capabilities and verify their availability and health.
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from research_engine.capability_contract import build_contracts
        contracts_dict = build_contracts()
    except ImportError:
        # Fall back to built-in capabilities
        contracts_dict = {}
    
    results = {}
    
    # Process contracts from build_contracts (they are dicts)
    if contracts_dict:
        for cap_id, contract in contracts_dict.items():
            # Handle both dict and object access
            risk_level = contract.get("risk_level", "read") if isinstance(contract, dict) else getattr(contract, "risk_level", "read")
            requires_verification = risk_level in ("write", "exec")
            available = contract.get("availability", "unknown") != "unknown" if isinstance(contract, dict) else getattr(contract, "availability", "unknown") != "unknown"
            
            results[cap_id] = {
                "domain": contract.get("domain", "unknown") if isinstance(contract, dict) else getattr(contract, "domain", "unknown"),
                "risk_level": risk_level,
                "requires_verification": requires_verification,
                "available": available,
                "supports_offline": contract.get("supports_offline", True) if isinstance(contract, dict) else getattr(contract, "supports_offline", True),
                "supports_streaming": contract.get("supports_streaming", False) if isinstance(contract, dict) else getattr(contract, "supports_streaming", False),
            }
    
    # If no contracts from build_contracts, use fallback
    if not results:
        from ..core import get_store
        misc = get_store("misc").load()
        settings = misc.get("provider_settings") or {}
        ai_enabled = bool(getattr(ai_service, "enabled", False))
        
        # Use system capabilities as fallback
        from .system import _CAPABILITIES
        for cap_id, category, tool, permissions, needs_ai, provider_service in _CAPABILITIES:
            if needs_ai:
                available = ai_enabled and bool(settings.get("openai_api_key") or settings.get("google_gemini_api_key"))
                health = "ok" if available else ("degraded" if settings else "offline")
            else:
                available = True
                health = "ok"
            results[cap_id] = {
                "domain": category,
                "risk_level": "read" if not needs_ai else "ai",
                "requires_verification": needs_ai,
                "available": available,
                "supports_offline": not needs_ai,
                "supports_streaming": needs_ai,
            }
    
    # Summary
    total = len(results)
    verified = sum(1 for r in results.values() if r["requires_verification"])
    available_count = sum(1 for r in results.values() if r["available"])
    
    return {
        "total_capabilities": total,
        "requires_verification": verified,
        "available": available_count,
        "capabilities": results,
    }


@router.get("/activity/timeline")
async def activity_timeline(
    user: Dict[str, Any] = Depends(_require_auth),
    limit: int = 100,
    event_type: Optional[str] = None
):
    """Get Activity Timeline - a read model of events across the platform.
    
    Aggregates real events from:
    - Audit logs (security actions)
    - Task/job executions
    - Chat conversations
    - Provider interactions
    - Verification results
    
    This provides a single source of truth for the Activity Timeline UI.
    """
    from ..core import get_store
    
    events = []
    
    # Collect events from various stores in reverse chronological order
    try:
        # 1. Audit logs
        audit_logs = get_store("audit_logs").load()
        if isinstance(audit_logs, list):
            for entry in audit_logs[-50:]:  # Limit per source
                if isinstance(entry, dict):
                    events.append({
                        "ts": entry.get("ts", entry.get("timestamp", "")),
                        "type": "security",
                        "category": "audit",
                        "action": entry.get("action", ""),
                        "status": entry.get("status", ""),
                        "description": entry.get("detail", ""),
                        "user": entry.get("user", ""),
                        "resource": entry.get("resource", ""),
                    })
    except Exception:
        pass
    
    try:
        # 2. Task executions
        tasks = get_store("tasks").load()
        if isinstance(tasks, dict):
            for task_id, task in list(tasks.items())[-30:]:
                if isinstance(task, dict):
                    events.append({
                        "ts": task.get("created_at", ""),
                        "type": "task",
                        "category": "execution",
                        "action": f"task.{task.get('status', 'unknown')}",
                        "status": "completed" if task.get("status") == "completed" else "running",
                        "description": f"Task: {task.get('type', '')[:50]}",
                        "user": task.get("user_id", ""),
                        "resource": task_id,
                    })
    except Exception:
        pass
    
    try:
        # 3. Chat sessions
        chat_sessions = get_store("chat_sessions").load()
        if isinstance(chat_sessions, dict):
            for session_id, session in list(chat_sessions.items())[-30:]:
                if isinstance(session, dict):
                    events.append({
                        "ts": session.get("updated_at", session.get("created_at", "")),
                        "type": "conversation",
                        "category": "chat",
                        "action": "session.active",
                        "status": "active" if not session.get("archived") else "archived",
                        "description": session.get("title", "Chat session")[:50],
                        "user": session.get("user_id", ""),
                        "resource": session_id,
                    })
    except Exception:
        pass
    
    # Sort by timestamp (most recent first)
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    
    # Apply filters
    if event_type:
        events = [e for e in events if e.get("type") == event_type]
    
    # Apply limit
    events = events[:limit]
    
    return {
        "events": events,
        "total_count": len(events),
        "filtered_count": sum(1 for e in events if e.get("type") == event_type) if event_type else len(events),
    }