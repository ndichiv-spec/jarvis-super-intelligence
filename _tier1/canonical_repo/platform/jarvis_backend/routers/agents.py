"""Agents, tasks, scheduler, collaboration, and goal endpoints."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core import _require_auth, ai_service, get_current_user, get_store, now_iso

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_DEFAULT_AGENTS = [
    {"id": "jarvis-core", "name": "Jarvis Core", "role": "coordinator",
     "status": "REGISTERED", "capabilities": ["chat", "memory", "knowledge", "voice"]},
    {"id": "researcher", "name": "Researcher", "role": "research",
     "status": "REGISTERED", "capabilities": ["web_search"]},
    {"id": "analyst", "name": "Analyst", "role": "analysis",
     "status": "REGISTERED", "capabilities": ["data_analysis"]},
    {"id": "coder", "name": "Coder", "role": "engineering",
     "status": "REGISTERED", "capabilities": ["codegen", "review", "execute", "email"]},
]


class TaskIn(BaseModel):
    name: str
    description: str
    priority: str = "medium"


class RegisterTaskIn(BaseModel):
    name: str
    description: str
    schedule_type: str = "manual"
    schedule_value: Optional[str] = None
    priority: str = "medium"
    timeout: int = 300
    max_retries: int = 3


class ToggleIn(BaseModel):
    enabled: bool


class CollabCreateIn(BaseModel):
    description: str
    agents_needed: List[str] = []
    collaboration_pattern: str = "sequential"


class CollabExecuteIn(BaseModel):
    task_id: str


class AgentActIn(BaseModel):
    action: str = "run_code"
    code: str = ""
    language: str = "python"
    timeout: float = 5.0
    memory_limit_mb: int = 128
    params: Dict[str, Any] = {}
    target_kind: str = "email"


def _ensure_agents() -> None:
    store = get_store("agents")
    agents = store.load()
    if not agents:
        for a in _DEFAULT_AGENTS:
            agents[a["id"]] = {
                **a,
                "created_at": now_iso(),
                "last_activity": None,
            }
        store.save()
    else:
        # Existing status labels do not prove that an agent has an execution.
        changed = False
        for agent in agents.values():
            if agent.get("status") in {"active", "idle", "ACTIVE", "IDLE"}:
                agent["status"] = "REGISTERED"
                changed = True
        coder = agents.get("coder")
        if coder:
            caps = coder.get("capabilities") or []
            merged = caps[:]
            for cap in ("execute", "email"):
                if cap not in merged:
                    merged.append(cap)
            if merged != caps:
                coder["capabilities"] = merged
                changed = True
        if changed:
            store.save()


@router.get("")
async def list_agents():
    _ensure_agents()
    registered = get_store("agents").load().values()
    return {
        "agents": [
            {**agent, "status": "REGISTERED"}
            for agent in registered
        ]
    }


@router.get("/stats")
async def agent_stats():
    _ensure_agents()
    agents = list(get_store("agents").load().values())
    return {
        "total": len(agents),
        "active": 0,
        "idle": 0,
        "registered": len(agents),
        "busy": 0,
        "by_role": {r: sum(1 for a in agents if a.get("role") == r)
                    for r in set(a.get("role") for a in agents)},
    }


@router.post("/task")
async def create_agent_task(body: TaskIn, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "name": body.name,
        "description": body.description,
        "priority": body.priority,
        "status": "pending",
        "enabled": True,
        "schedule_type": "manual",
        "schedule_value": None,
        "timeout": 300,
        "max_retries": 0,
        "created_at": now_iso(),
    }
    get_store("tasks").save()
    return tasks[task_id]


@router.post("/tasks")
async def register_task(body: RegisterTaskIn, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "name": body.name,
        "description": body.description,
        "priority": body.priority,
        "status": "pending",
        "enabled": True,
        "schedule_type": body.schedule_type,
        "schedule_value": body.schedule_value,
        "timeout": body.timeout,
        "max_retries": body.max_retries,
        "created_at": now_iso(),
    }
    get_store("tasks").save()
    return tasks[task_id]


@router.post("/tasks/{task_id}/toggle")
async def toggle_task(task_id: str, body: ToggleIn, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks[task_id]["enabled"] = body.enabled
    get_store("tasks").save()
    return tasks[task_id]


@router.post("/tasks/{task_id}/run")
async def run_task(task_id: str, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    task["status"] = "running"
    task["started_at"] = now_iso()
    task["last_result"] = await ai_service.chat(task.get("description") or task.get("name") or "run")
    task["status"] = "completed"
    task["completed_at"] = now_iso()
    get_store("tasks").save()
    executions = get_store("executions").load()
    executions.append({
        "id": str(uuid.uuid4()),
        "task_id": task_id,
        "task_name": task.get("name"),
        "status": "completed",
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at"),
    })
    get_store("executions").save()
    return task


@router.get("/executions")
async def list_executions(limit: int = Query(20), user: Dict[str, Any] = Depends(_require_auth)):
    executions = get_store("executions").load()
    return {"executions": executions[-limit:][::-1], "total": len(executions)}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    tasks.pop(task_id, None)
    get_store("tasks").save()
    return {"success": True}


@router.get("/scheduler/status")
async def scheduler_status(user: Dict[str, Any] = Depends(_require_auth)):
    del user
    return {
        "running": False,
        "status": "NOT_IMPLEMENTED",
        "detail": "No durable agent scheduler is running.",
    }


@router.post("/scheduler/toggle")
async def toggle_scheduler(body: Dict[str, Any], user: Dict[str, Any] = Depends(_require_auth)):
    del body, user
    raise HTTPException(
        status_code=501,
        detail="No durable agent scheduler is implemented.",
    )


@router.get("/service-tailoring")
async def service_tailoring():
    return {
        "enabled": True,
        "services": ["ai", "agents", "memory", "knowledge", "voice", "monitoring"],
    }


@router.get("/goals")
async def agent_goals(user: Dict[str, Any] = Depends(_require_auth)):
    return {"goals": get_store("misc").load().get("cognitive_goals", [])}


# ---- collaboration ----


@router.get("/collaboration/agents/list")
async def collab_agents_list(user: Dict[str, Any] = Depends(_require_auth)):
    _ensure_agents()
    agents = get_store("agents").load()
    return {
        "agents": [
            {"id": a["id"], "name": a.get("name"), "role": a.get("role"),
             "status": a.get("status")}
            for a in agents.values()
        ]
    }


@router.get("/collaboration/tasks/list")
async def collab_tasks_list(status: Optional[str] = None, limit: int = Query(20), user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("collab_tasks").load()
    items = list(tasks.values())
    if status:
        items = [t for t in items if t.get("status") == status]
    return {"tasks": items[-limit:][::-1], "total": len(items)}


@router.post("/collaboration/task/create")
async def collab_task_create(body: CollabCreateIn, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("collab_tasks").load()
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "description": body.description,
        "agents_needed": body.agents_needed,
        "collaboration_pattern": body.collaboration_pattern,
        "status": "pending",
        "created_at": now_iso(),
    }
    get_store("collab_tasks").save()
    return tasks[task_id]


@router.post("/collaboration/task/execute")
async def collab_task_execute(body: CollabExecuteIn, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("collab_tasks").load()
    task = tasks.get(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["status"] = "completed"
    task["completed_at"] = now_iso()
    task["result"] = await ai_service.chat(task.get("description") or "collaboration")
    get_store("collab_tasks").save()
    return task


@router.get("/collaboration/metrics")
async def collab_metrics(user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("collab_tasks").load()
    items = list(tasks.values())
    return {
        "total_tasks": len(items),
        "completed": sum(1 for t in items if t.get("status") == "completed"),
        "agents_utilization": 0.0,
    }


@router.post("/collaboration/self-organize")
async def collab_self_organize(description: str = Query(""), user: Dict[str, Any] = Depends(_require_auth)):
    _ensure_agents()
    agents = list(get_store("agents").load().values())
    return {
        "plan": description,
        "assigned_agents": [a["id"] for a in agents],
        "status": "planned",
    }


@router.get("/{agent_id}")
async def agent_status(agent_id: str):
    _ensure_agents()
    agents = get_store("agents").load()
    agent = agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/act")
async def agent_act(agent_id: str, body: AgentActIn, user: Dict[str, Any] = Depends(get_current_user)):
    """Let an agent execute a controlled tool action (spec #16/#17).

    Only the Coder agent has execution wired for now. Generated code runs in the
    audited Silverwing sandbox -- never directly on the host -- so it is isolated
    by an AST allowlist, blocked dangerous builtins, wall-clock timeout, RSS cap,
    and an audit-trail record (jarvis_data/audit/sandbox.jsonl).
    """
    _ensure_agents()
    agents = get_store("agents").load()
    agent = agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if body.action not in ("run_code", "email"):
        raise HTTPException(status_code=400, detail=f"Unsupported action for {agent_id}: {body.action}")

    if body.action == "email":
        if "email" not in (agent.get("capabilities") or []):
            raise HTTPException(status_code=400, detail=f"Agent '{agent_id}' is not enabled for email actions (email capability missing)")
        from ..connectors.dispatch import execute_connector_action

        result = await execute_connector_action(
            kind=body.target_kind,
            action=body.params.pop("email_action", "email.folders"),
            params=body.params,
            actor=f"agent:{agent_id}",
            user_id=user.get("id"),
        )
        ok = bool(result.get("ok"))
    else:
        if body.language != "python":
            raise HTTPException(status_code=400, detail="Only python execution is wired for agents")
        from ..routers.sandbox import CodeRunIn, _sandbox_execute
        _sandbox_result = await _sandbox_execute(
            CodeRunIn(code=body.code, language="python", timeout=body.timeout, memory_limit_mb=body.memory_limit_mb),
            actor=f"agent:{agent_id}",
        )
        ok = _sandbox_result.ok
        result = _sandbox_result
    executions = get_store("executions").load()
    error = getattr(result, "error", None) if not isinstance(result, dict) else result.get("error")
    executions.append({
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "action": body.action,
        "status": "completed" if ok else "failed",
        "error": error,
        "started_at": now_iso(),
        "completed_at": now_iso(),
    })
    get_store("executions").save()

    if body.action == "email":
        return {
            "agent_id": agent_id,
            "ok": ok,
            "action": body.action,
            "connector": body.target_kind,
            "result": result,
        }

    return {
        "agent_id": agent_id,
        "ok": result.ok,
        "language": body.language,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error": result.error,
        "execution_time_ms": result.execution_time_ms,
        "signal": result.signal,
        "memory_enforced": result.memory_enforced,
    }
