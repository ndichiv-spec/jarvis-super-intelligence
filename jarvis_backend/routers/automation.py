"""Automation workflows and task execution.

Spec §33/§50: automation is driven FROM this console. When n8n is available it
is exposed as a thin proxy here, so the developer manages workflows through the
existing Automation surface without a second admin platform. n8n executes
actions that JARVIS authorizes (via the JARVIS tool API), authenticated with
``JARVIS_OAUTH_N8N_API_KEY`` — it never holds OAuth provider tokens directly.

The local misc store keeps a lightweight mirror of automation tasks (default +
n8n synced). The n8n public API is authenticated with ``X-N8N-API-KEY``
(``N8N_API_KEY`` env — the bearer token created for the n8n owner).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import get_store, get_current_user, now_iso
from ..automation_runners import LOCAL_RUNNERS

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])

_N8N_URL = os.environ.get("N8N_URL", "http://127.0.0.1:5678").rstrip("/")
# n8n public API auth is X-N8N-API-KEY (not basic auth). Bearer token created
# via POST /rest/api-keys for the activated owner user and stored in .env.
_N8N_API_KEY = os.environ.get("N8N_API_KEY") or os.environ.get("JARVIS_OAUTH_N8N_API_KEY") or ""


async def _parse_run_response(r: httpx.Response) -> Any:
    """Best-effort JSON parse; n8n webhook triggers answer with plain text."""
    try:
        return r.json()
    except (ValueError, json.JSONDecodeError):
        return {"message": r.text[:200], "status_code": r.status_code}


def _n8n_headers() -> Dict[str, str]:
    if not _N8N_API_KEY:
        return {}
    return {"X-N8N-API-KEY": _N8N_API_KEY}


_DEFAULT_WORKFLOWS = [
    {"id": "wf-nightly-report", "name": "Nightly System Report", "enabled": True, "type": "report",
     "description": "Generates a daily system health + learning report via JARVIS"},
    {"id": "wf-knowledge-digest", "name": "Knowledge Digest", "enabled": True, "type": "digest",
     "description": "Digests new knowledge entries and refreshes the knowledge graph"},
    {"id": "wf-cleanup", "name": "Temp Cleanup", "enabled": True, "type": "cleanup",
     "description": "Removes stale temp files and expired caches"},
]


def _default_task(w: Dict[str, Any]) -> Dict[str, Any]:
    """Map a local/default workflow record to the frontend AutomationTask shape."""
    return {
        "id": w["id"],
        "name": w["name"],
        "description": w.get("description") or "",
        "trigger_type": "schedule",
        "trigger_config": {"cron": w.get("cron") or "0 3 * * *"},
        "action_type": w.get("type", "generic"),
        "action_config": {},
        "enabled": bool(w.get("enabled", True)),
        "last_run_at": w.get("last_run_at"),
        "last_run_status": w.get("last_run_status"),
        "created_at": w.get("created_at", now_iso()),
        "engine": "local" if w.get("type") in LOCAL_RUNNERS else "n8n",
    }


def _n8n_task(w: Dict[str, Any]) -> Dict[str, Any]:
    """Map an n8n workflow to the frontend AutomationTask shape."""
    active = bool(w.get("active"))
    tags = [t.get("name", "") for t in (w.get("tags") or []) if isinstance(t, dict)]
    name = w.get("name") or "Untitled workflow"
    desc = w.get("description") or (f"n8n workflow tagged: {', '.join(tags)}" if tags else "n8n workflow")
    webhook_path = _extract_webhook_path(w)
    return {
        "id": w.get("id") or w.get("publicId") or name,
        "name": name,
        "description": desc,
        "trigger_type": "webhook" if webhook_path else ("schedule" if tags and "schedule" in tags else "manual"),
        "trigger_config": {"webhook": webhook_path} if webhook_path else {},
        "action_type": f"n8n:{w.get("type", "workflow")}" if isinstance(w.get("type"), str) else "n8n",
        "action_config": {"nodes": len(w.get("nodes") or []), "connections": w.get("connections") or {}},
        "enabled": active,
        "last_run_at": w.get("updatedAt"),
        "last_run_status": None,
        "created_at": w.get("createdAt", now_iso()),
        "engine": "n8n",
        "n8n_id": str(w.get("id") or w.get("publicId") or name),
        "webhook_path": webhook_path,
    }


def _extract_webhook_path(w: Dict[str, Any]) -> Optional[str]:
    """Return the production webhook path of the first webhook node, if any."""
    for n in (w.get("nodes") or []):
        if isinstance(n, dict) and n.get("type") == "n8n-nodes-base.webhook":
            p = n.get("parameters", {}).get("path")
            if isinstance(p, str) and p:
                return p
    return None


def _load_local_workflows() -> Dict[str, Any]:
    misc = get_store("misc").load()
    workflows = misc.setdefault("workflows", {})
    if not workflows:
        for w in _DEFAULT_WORKFLOWS:
            workflows[w["id"]] = w
        get_store("misc").save()
    return workflows


async def _n8n_list_workflows() -> List[Dict[str, Any]]:
    """Fetch active workflow summaries from the n8n public API (best-effort)."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{_N8N_URL}/api/v1/workflows?limit=100",
                                 headers=_n8n_headers())
        if r.status_code != 200:
            return []
        return r.json().get("data", [])
    except httpx.HTTPError:
        return []


@router.get("")
async def list_automation():
    """Merge local default tasks + live n8n workflows into the frontend shape.

    n8n workflows are mirrored into the misc store so offline mode still lists
    what was last seen (state may be stale while n8n is down — ``engine``
    distinguishes the source).
    """
    local = _load_local_workflows()
    n8n = await _n8n_list_workflows()

    local_ids = set(local.keys())
    n8n_webhook_to_task = {}
    n8n_records = []
    if n8n:
        mirrored = get_store("misc").load().setdefault("n8n_workflows", {})
        for w in n8n:
            tid = str(w.get("id") or w.get("publicId"))
            if tid:
                mirrored[tid] = w
            for l_id in local_ids:
                if _extract_webhook_path(w) == l_id or (w.get("name") or "").lower() == (local.get(l_id, {}).get("name") or "").lower():
                    n8n_webhook_to_task[l_id] = w
                    break
            else:
                n8n_records.append(_n8n_task(w))
        get_store("misc").save()

    tasks = []
    for l_id in sorted(local_ids):
        if l_id in n8n_webhook_to_task:
            tasks.append(_n8n_task(n8n_webhook_to_task[l_id]))
        else:
            tasks.append(_default_task(local[l_id]))
    tasks.extend(n8n_records)

    return {"tasks": tasks, "engine": "n8n" if n8n else "local"}


class RunTaskIn(BaseModel):
    body: Dict[str, Any] = Field(default_factory=dict)


@router.post("/task/{task_id}/run")
async def run_workflow(
    task_id: str,
    body: RunTaskIn | None = None,
    user=Depends(get_current_user),
):
    _require_admin_or_dev(user)
    local = _load_local_workflows()
    payload = (body.body if body else {}) or {}
    started = now_iso()
    run_id = f"{task_id}-{uuid.uuid4().hex[:8]}"

    if task_id in local:
        wf = local[task_id]
        if not wf.get("enabled", True):
            raise HTTPException(status_code=409, detail="Automation task is disabled")

        webhook_path = wf.get("webhook_path")
        if not webhook_path:
            mirrored = get_store("misc").load().get("n8n_workflows", {})
            for w in mirrored.values():
                wp = _extract_webhook_path(w)
                if str(w.get("id")) == task_id or str(w.get("publicId")) == task_id or wp == task_id:
                    webhook_path = wp
                    break

        runner = LOCAL_RUNNERS.get(str(wf.get("type")))
        if not webhook_path and runner:
            started_clock = time.perf_counter()
            try:
                result = await asyncio.to_thread(
                    runner,
                    str(user.get("id") or ""),
                    payload,
                )
            except Exception as exc:
                completed = now_iso()
                execution = {
                    "id": run_id,
                    "task_id": task_id,
                    "task_name": wf.get("name", task_id),
                    "status": "failed",
                    "started_at": started,
                    "completed_at": completed,
                    "duration_ms": round((time.perf_counter() - started_clock) * 1000),
                    "engine": "local",
                    "error": "Local automation failed",
                }
                _record_execution(execution, str(user.get("id") or ""))
                _record_run_result(task_id, user, "failed", "local")
                raise HTTPException(status_code=500, detail="Local automation failed") from exc

            completed = now_iso()
            execution = {
                "id": run_id,
                "task_id": task_id,
                "task_name": wf.get("name", task_id),
                "status": "completed",
                "started_at": started,
                "completed_at": completed,
                "duration_ms": round((time.perf_counter() - started_clock) * 1000),
                "engine": "local",
                "result": result,
            }
            _record_execution(execution, str(user.get("id") or ""))
            _record_run_result(task_id, user, "completed", "local")
            return {"success": True, "execution": execution}

        try:
            if webhook_path:
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.post(
                        f"{_N8N_URL}/webhook/{webhook_path}",
                        json=payload,
                    )
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.post(
                        f"{_N8N_URL}/api/v1/workflows/{task_id}/run",
                        json={"data": payload} if payload else {},
                        headers=_n8n_headers(),
                    )
        except httpx.HTTPError as exc:
            _record_execution({
                "id": run_id,
                "task_id": task_id,
                "task_name": wf.get("name", task_id),
                "status": "failed",
                "started_at": started,
                "completed_at": now_iso(),
                "duration_ms": 0,
                "engine": "n8n",
                "error": "n8n unavailable",
            }, str(user.get("id") or ""))
            _record_run_result(task_id, user, "failed", "n8n")
            raise HTTPException(status_code=502, detail="n8n is unavailable; task was not run") from exc

        if r.status_code not in (200, 202):
            _record_execution({
                "id": run_id,
                "task_id": task_id,
                "task_name": wf.get("name", task_id),
                "status": "failed",
                "started_at": started,
                "completed_at": now_iso(),
                "duration_ms": 0,
                "engine": "n8n",
                "error": f"n8n rejected task run: HTTP {r.status_code}",
            }, str(user.get("id") or ""))
            _record_run_result(task_id, user, "failed", "n8n")
            raise HTTPException(status_code=502, detail=f"n8n rejected task run: HTTP {r.status_code}")

        execution = {
            "id": run_id,
            "task_id": task_id,
            "task_name": wf.get("name", task_id),
            "status": "accepted",
            "started_at": started,
            "duration_ms": 0,
            "engine": "n8n",
            "run": await _parse_run_response(r),
        }
        _record_execution(execution, str(user.get("id") or ""))
        _record_run_result(task_id, user, "accepted", "n8n")
        return {"success": True, "execution": execution}

    # Not local — try a raw n8n workflow id, then its webhook path.
    try:
        mirrored = get_store("misc").load().get("n8n_workflows", {})
        w = mirrored.get(task_id)
        if not w:
            for _w in mirrored.values():
                if _extract_webhook_path(_w) == task_id:
                    w = _w
                    break
        if w and not w.get("active", False):
            raise HTTPException(status_code=409, detail="n8n workflow is inactive")
        webhook_path = _extract_webhook_path(w) if w else None
        async with httpx.AsyncClient(timeout=20) as client:
            if webhook_path:
                r = await client.post(f"{_N8N_URL}/webhook/{webhook_path}", json=payload)
            else:
                r = await client.post(f"{_N8N_URL}/api/v1/workflows/{task_id}/run",
                                      json={"data": payload} if payload else {},
                                      headers=_n8n_headers())
        if r.status_code not in (200, 202):
            _record_execution({
                "id": run_id,
                "task_id": task_id,
                "task_name": (w or {}).get("name", task_id),
                "status": "failed",
                "started_at": started,
                "completed_at": now_iso(),
                "duration_ms": 0,
                "engine": "n8n",
                "error": f"n8n rejected task run: HTTP {r.status_code}",
            }, str(user.get("id") or ""))
            _record_run_result(task_id, user, "failed", "n8n")
            raise HTTPException(status_code=502, detail=f"n8n rejected task run: HTTP {r.status_code}")

        execution = {
            "id": run_id,
            "task_id": task_id,
            "task_name": (w or {}).get("name", task_id),
            "status": "accepted",
            "started_at": started,
            "duration_ms": 0,
            "engine": "n8n",
            "run": await _parse_run_response(r),
        }
        _record_execution(execution, str(user.get("id") or ""))
        _record_run_result(task_id, user, "accepted", "n8n")
        return {"success": True, "execution": execution}
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        _record_execution({
            "id": run_id,
            "task_id": task_id,
            "task_name": task_id,
            "status": "failed",
            "started_at": started,
            "completed_at": now_iso(),
            "duration_ms": 0,
            "engine": "n8n",
            "error": "n8n unavailable",
        }, str(user.get("id") or ""))
        _record_run_result(task_id, user, "failed", "n8n")
        raise HTTPException(status_code=502, detail="n8n is unavailable; task was not run") from exc


def _record_run_result(task_id: str, user: Dict[str, Any], status: str, engine: str) -> None:
    """Persist truthful task state and an audit event without storing run data."""
    misc_store = get_store("misc")
    misc = misc_store.load()
    workflow = misc.get("workflows", {}).get(task_id)
    if workflow is not None:
        workflow["last_run_at"] = now_iso()
        workflow["last_run_status"] = status
        misc_store.save()

    audit_store = get_store("audit_logs")
    audit = audit_store.load()
    audit.append({
        "ts": now_iso(),
        "actor": user.get("username") or user.get("email") or "automation",
        "kind": "automation",
        "operation": "task_run",
        "ok": status != "failed",
        "meta": {"task_id": task_id, "engine": engine, "status": status},
    })
    audit_store.save()


def _record_execution(execution: Dict[str, Any], user_id: str) -> None:
    """Persist bounded run metadata without retaining upstream response bodies."""
    store = get_store("executions")
    history = store.load()
    history.append({
        key: value
        for key, value in {**execution, "user_id": user_id}.items()
        if key != "run"
    })
    del history[:-5000]
    store.save()


@router.get("/executions")
async def list_automation_executions(
    task_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    user=Depends(get_current_user),
):
    """Return persisted automation outcomes, newest first (admin/developer only)."""
    _require_admin_or_dev(user)
    history = get_store("executions").load()
    matching = [
        entry for entry in history
        if isinstance(entry, dict)
        and entry.get("engine") in {"local", "n8n"}
        and (task_id is None or entry.get("task_id") == task_id)
    ]
    return {"executions": list(reversed(matching[-limit:])), "count": len(matching)}


# --------------------------------------------------------------------------- #
# n8n automation engine (§33/§50). Thin proxy so the existing Automation
# console surface manages n8n workflows; n8n only *executes* actions JARVIS
# authorizes and calls back into the JARVIS tool API.
# --------------------------------------------------------------------------- #
@router.get("/n8n/status")
async def n8n_status(user=Depends(get_current_user)):
    _require_admin_or_dev(user)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{_N8N_URL}/healthz", headers=_n8n_headers())
        if r.status_code == 200:
            return {"engine": "n8n", "status": "UP", "url": _N8N_URL,
                    "version": r.json().get("version")}
        return {"engine": "n8n", "status": "DOWN", "http": r.status_code, "url": _N8N_URL}
    except httpx.HTTPError as exc:
        return {"engine": "n8n", "status": "DOWN", "error": str(exc), "url": _N8N_URL}


@router.get("/n8n/workflows")
async def n8n_workflows(user=Depends(get_current_user)):
    _require_admin_or_dev(user)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{_N8N_URL}/api/v1/workflows?limit=100",
                             headers=_n8n_headers())
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"n8n error: {r.status_code}")
    return {"engine": "n8n", "workflows": r.json().get("data", [])}


class RunWorkflowIn(BaseModel):
    workflow_id: str
    body: Dict[str, Any] = Field(default_factory=dict)


@router.post("/n8n/workflows/run")
async def n8n_run_workflow(body: RunWorkflowIn, user=Depends(get_current_user)):
    _require_admin_or_dev(user)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{_N8N_URL}/api/v1/workflows/{body.workflow_id}/run",
                              json=body.body, headers=_n8n_headers())
    if r.status_code not in (200, 202):
        raise HTTPException(status_code=502, detail=f"n8n error: {r.status_code}")
    run = await _parse_run_response(r)
    # Audit the automation trigger (spec §27) — no secrets echoed.
    get_store("audit_logs").load().append({
        "ts": now_iso(), "actor": user.get("username") or "automation",
        "kind": "n8n", "operation": "workflow_run", "ok": True,
        "meta": {"workflow_id": body.workflow_id},
    })
    get_store("audit_logs").save()
    return {"engine": "n8n", "workflow_id": body.workflow_id, "run": run}


def _require_admin_or_dev(user):
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or "owner" in names or "developer" in names:
        return user
    raise HTTPException(status_code=403, detail="Admin or Developer role required for automation control")