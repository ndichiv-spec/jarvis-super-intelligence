"""Agents, tasks, scheduler, collaboration, and goal endpoints."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core import _require_auth, get_current_user, get_store, now_iso
from ..chat_service import chat_service

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_DEFAULT_AGENTS = [
    {"id": "jarvis-core", "name": "Jarvis Core", "role": "coordinator",
     "status": "active", "capabilities": ["chat", "memory", "knowledge", "voice"]},
    {"id": "researcher", "name": "Researcher", "role": "research",
     "status": "idle", "capabilities": ["web_search"]},
    {"id": "analyst", "name": "Analyst", "role": "analysis",
     "status": "idle", "capabilities": ["data_analysis"]},
    {"id": "coder", "name": "Coder", "role": "engineering",
     "status": "idle", "capabilities": ["codegen", "review", "execute", "email"]},
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


def _user_id(user: Dict[str, Any]) -> str:
    user_id = user.get("id") or user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated identity is missing")
    return str(user_id)


def _owned_task(tasks: Dict[str, Any], task_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    task = tasks.get(task_id)
    if not isinstance(task, dict) or task.get("user_id") != _user_id(user):
        raise HTTPException(status_code=404, detail="Task not found")
    return task


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
        # Idempotent capability updates for persisted registry entries.
        changed = False
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
async def list_agents(user: Dict[str, Any] = Depends(_require_auth)):
    _ensure_agents()
    return {"agents": list(get_store("agents").load().values())}


@router.get("/stats")
async def agent_stats(user: Dict[str, Any] = Depends(_require_auth)):
    _ensure_agents()
    agents = list(get_store("agents").load().values())
    return {
        "total": len(agents),
        "active": sum(1 for a in agents if a.get("status") == "active"),
        "idle": sum(1 for a in agents if a.get("status") == "idle"),
        "by_role": {r: sum(1 for a in agents if a.get("role") == r)
                    for r in set(a.get("role") for a in agents)},
    }


@router.post("/task")
async def create_agent_task(body: TaskIn, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "user_id": _user_id(user),
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
    if body.schedule_type != "manual":
        raise HTTPException(
            status_code=501,
            detail="Scheduled agent tasks are not connected to a scheduler.",
        )
    tasks = get_store("tasks").load()
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "user_id": _user_id(user),
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


@router.get("/tasks")
async def list_agent_tasks(
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(_require_auth),
):
    user_id = _user_id(user)
    tasks = get_store("tasks").load()
    owned = [
        task for task in tasks.values()
        if isinstance(task, dict) and task.get("user_id") == user_id
    ]
    owned.sort(key=lambda task: task.get("created_at") or "", reverse=True)
    return {"tasks": owned[:limit], "total": len(owned)}


@router.post("/tasks/{task_id}/toggle")
async def toggle_task(task_id: str, body: ToggleIn, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    task = _owned_task(tasks, task_id, user)
    task["enabled"] = body.enabled
    get_store("tasks").save()
    return task


@router.post("/tasks/{task_id}/run")
async def run_task(task_id: str, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    task = _owned_task(tasks, task_id, user)
    if not task.get("enabled", True):
        raise HTTPException(status_code=409, detail="Task is disabled")
    if task.get("status") == "running":
        raise HTTPException(status_code=409, detail="Task is already running")
    owner_id = _user_id(user)
    task["status"] = "running"
    task["started_at"] = now_iso()
    task["error"] = None
    task["run_count"] = int(task.get("run_count", 0)) + 1
    session_id = task.setdefault("session_id", f"agent-task-{task_id}")
    get_store("tasks").save()
    chat_service.create_session(owner_id, session_id, task.get("name") or "Agent task")
    result = await chat_service.send_message(
        owner_id,
        session_id,
        task.get("description") or task.get("name") or "Run task",
        client_message_id=f"agent-task:{task_id}:{task['run_count']}",
        principal=user,
    )
    task["status"] = "completed" if result.get("status") == "COMPLETED" else "failed"
    task["completed_at"] = now_iso()
    task["last_result"] = result.get("message") if task["status"] == "completed" else None
    task["provider"] = result.get("provider")
    task["model"] = result.get("model")
    task["error"] = result.get("error")
    task["runtime_status"] = result.get("status")
    get_store("tasks").save()
    executions = get_store("executions").load()
    executions.append({
        "id": str(uuid.uuid4()),
        "user_id": owner_id,
        "task_id": task_id,
        "task_name": task.get("name"),
        "status": task["status"],
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at"),
        "provider": task.get("provider"),
        "model": task.get("model"),
        "session_id": session_id,
    })
    get_store("executions").save()
    return task


@router.get("/executions")
async def list_executions(
    limit: int = Query(20, ge=1, le=100),
    user: Dict[str, Any] = Depends(_require_auth),
):
    executions = get_store("executions").load()
    owned = [
        entry for entry in executions
        if isinstance(entry, dict) and entry.get("user_id") == _user_id(user)
    ]
    return {"executions": owned[-limit:][::-1], "total": len(owned)}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("tasks").load()
    _owned_task(tasks, task_id, user)
    tasks.pop(task_id)
    get_store("tasks").save()
    return {"success": True}


@router.get("/scheduler/status")
async def scheduler_status(user: Dict[str, Any] = Depends(_require_auth)):
    return {"running": False, "status": "NOT_CONFIGURED", "next_run": None}


@router.post("/scheduler/toggle")
async def toggle_scheduler(body: Dict[str, Any], user: Dict[str, Any] = Depends(_require_auth)):
    raise HTTPException(
        status_code=501,
        detail="The legacy agent scheduler is not connected to a worker.",
    )


@router.get("/service-tailoring")
async def service_tailoring(user: Dict[str, Any] = Depends(_require_auth)):
    return {
        "enabled": False,
        "status": "NOT_CONFIGURED",
        "services": [],
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
    items = [
        task for task in tasks.values()
        if isinstance(task, dict) and task.get("user_id") == _user_id(user)
    ]
    if status:
        items = [t for t in items if t.get("status") == status]
    return {"tasks": items[-limit:][::-1], "total": len(items)}


@router.post("/collaboration/task/create")
async def collab_task_create(body: CollabCreateIn, user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("collab_tasks").load()
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "user_id": _user_id(user),
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
    task = _owned_task(tasks, body.task_id, user)
    if task.get("status") == "running":
        raise HTTPException(status_code=409, detail="Task is already running")
    task["status"] = "running"
    task["started_at"] = now_iso()
    session_id = task.setdefault("session_id", f"collab-task-{body.task_id}")
    owner_id = _user_id(user)
    get_store("collab_tasks").save()
    chat_service.create_session(owner_id, session_id, "Agent collaboration")
    result = await chat_service.send_message(
        owner_id,
        session_id,
        task.get("description") or "Execute the requested collaboration.",
        client_message_id=f"collab-task:{body.task_id}",
        principal=user,
    )
    task["status"] = "completed" if result.get("status") == "COMPLETED" else "failed"
    task["completed_at"] = now_iso()
    task["result"] = result.get("message") if task["status"] == "completed" else None
    task["error"] = result.get("error")
    task["provider"] = result.get("provider")
    task["model"] = result.get("model")
    get_store("collab_tasks").save()
    return task


@router.get("/collaboration/metrics")
async def collab_metrics(user: Dict[str, Any] = Depends(_require_auth)):
    tasks = get_store("collab_tasks").load()
    items = [
        task for task in tasks.values()
        if isinstance(task, dict) and task.get("user_id") == _user_id(user)
    ]
    return {
        "total_tasks": len(items),
        "completed": sum(1 for t in items if t.get("status") == "completed"),
        "running": sum(1 for t in items if t.get("status") == "running"),
        "failed": sum(1 for t in items if t.get("status") == "failed"),
    }


@router.post("/collaboration/self-organize")
async def collab_self_organize(description: str = Query(""), user: Dict[str, Any] = Depends(_require_auth)):
    raise HTTPException(
        status_code=501,
        detail="Automatic agent planning is not configured.",
    )


@router.get("/{agent_id}")
async def agent_status(
    agent_id: str,
    user: Dict[str, Any] = Depends(_require_auth),
):
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


# =============================================================================
# Phase 6: Multi-Agent Orchestration (Redis-backed agent graph)
# =============================================================================

from ..agents.graph_store import AgentGraphStore, AgentNode, AgentMessage
from ..agents.lifecycle import AgentLifecycleManager
from ..agents.specialist import create_agent, get_role_definitions, ROLE_DEFINITIONS

_graph_store: Optional[AgentGraphStore] = None
_lifecycle_manager: Optional[AgentLifecycleManager] = None


async def _get_graph_store() -> AgentGraphStore:
    global _graph_store
    if _graph_store is None:
        _graph_store = AgentGraphStore.get_shared()
        if not _graph_store._connected:
            await _graph_store.connect()
    return _graph_store


async def _get_lifecycle_manager() -> AgentLifecycleManager:
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = AgentLifecycleManager.get_shared()
        await _lifecycle_manager.ensure_store()
    return _lifecycle_manager


def _graph_owner_id(user: Dict[str, Any]) -> str:
    owner_id = user.get("id") or user.get("email")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Authenticated identity is missing")
    return str(owner_id)


def _graph_inbox_id(user: Dict[str, Any]) -> str:
    return f"orchestrator:{_graph_owner_id(user)}"


async def _get_owned_graph_agent(agent_id: str, user: Dict[str, Any]) -> AgentNode:
    store = await _get_graph_store()
    node = await store.get_agent(agent_id)
    if node is None or node.config.get("_owner_id") != _graph_owner_id(user):
        raise HTTPException(status_code=404, detail="Agent not found")
    return node


class SpawnAgentIn(BaseModel):
    name: str
    role: str = "researcher"
    config: Optional[Dict[str, Any]] = None
    capabilities: Optional[List[str]] = None
    request: Optional[Dict[str, Any]] = None


class SendMessageIn(BaseModel):
    sender_id: str
    receiver_id: str
    content: Dict[str, Any]
    message_type: str = "message"
    priority: int = 0


@router.get("/graph/status")
async def graph_status(user: Dict[str, Any] = Depends(_require_auth)):
    """Get the authenticated user's agent graph status."""
    store = await _get_graph_store()
    owner_id = _graph_owner_id(user)
    agents = [
        node for node in await store.list_agents()
        if node.config.get("_owner_id") == owner_id
    ]
    by_role: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    pending_messages: Dict[str, int] = {}
    for agent in agents:
        by_role[agent.role] = by_role.get(agent.role, 0) + 1
        by_status[agent.status] = by_status.get(agent.status, 0) + 1
        pending_messages[agent.name] = await store.get_pending_count(agent.agent_id)
    pending_messages["orchestration inbox"] = await store.get_pending_count(_graph_inbox_id(user))
    status = {
        "total_agents": len(agents),
        "by_role": by_role,
        "by_status": by_status,
        "pending_messages": pending_messages,
        "redis_connected": store._redis is not None,
    }
    manager = await _get_lifecycle_manager()
    lifecycle_status = await manager.get_status()
    owned_agent_ids = {agent.agent_id for agent in agents}
    managed_agents = {
        agent_id: details
        for agent_id, details in lifecycle_status["managed_agents"].items()
        if agent_id in owned_agent_ids
    }
    lifecycle = {"managed_agents": managed_agents, "total_managed": len(managed_agents)}
    return {"graph": status, "lifecycle": lifecycle}


@router.get("/graph/roles")
async def list_agent_roles():
    """List all available agent roles and their definitions."""
    return {"roles": get_role_definitions()}


@router.get("/graph/agents")
async def list_graph_agents(user: Dict[str, Any] = Depends(_require_auth)):
    """List agents owned by the authenticated user."""
    store = await _get_graph_store()
    owner_id = _graph_owner_id(user)
    agents = [
        node for node in await store.list_agents()
        if node.config.get("_owner_id") == owner_id
    ]
    return {"agents": [a.to_dict() for a in agents], "count": len(agents)}


@router.post("/graph/agent")
async def spawn_graph_agent(body: SpawnAgentIn, user: Dict[str, Any] = Depends(_require_auth)):
    """Spawn a new multi-agent instance."""
    if body.role not in ROLE_DEFINITIONS:
        raise HTTPException(status_code=422, detail="Unknown agent role")
    request = dict(body.request or {})
    request["sender_id"] = _graph_inbox_id(user)
    manager = await _get_lifecycle_manager()
    agent_id = await manager.spawn(
        name=body.name,
        role=body.role,
        config={**(body.config or {}), "_owner_id": _graph_owner_id(user)},
        capabilities=body.capabilities or [],
        request=request,
    )
    return {"agent_id": agent_id, "status": "spawned"}


@router.get("/graph/agent/{agent_id}")
async def get_graph_agent(agent_id: str, user: Dict[str, Any] = Depends(_require_auth)):
    """Get a single agent's status when owned by the authenticated user."""
    node = await _get_owned_graph_agent(agent_id, user)
    return node.to_dict()


@router.post("/graph/agent/{agent_id}/pause")
async def pause_agent(agent_id: str, user: Dict[str, Any] = Depends(_require_auth)):
    await _get_owned_graph_agent(agent_id, user)
    manager = await _get_lifecycle_manager()
    return {"success": await manager.pause(agent_id)}


@router.post("/graph/agent/{agent_id}/resume")
async def resume_agent(agent_id: str, user: Dict[str, Any] = Depends(_require_auth)):
    await _get_owned_graph_agent(agent_id, user)
    manager = await _get_lifecycle_manager()
    return {"success": await manager.resume(agent_id, owner_id=_graph_owner_id(user))}


@router.post("/graph/agent/{agent_id}/terminate")
async def terminate_agent(agent_id: str, user: Dict[str, Any] = Depends(_require_auth)):
    await _get_owned_graph_agent(agent_id, user)
    manager = await _get_lifecycle_manager()
    return {"success": await manager.terminate(agent_id)}


@router.post("/graph/agent/{agent_id}/message")
async def send_agent_message(agent_id: str, body: SendMessageIn, user: Dict[str, Any] = Depends(_require_auth)):
    """Send a message to a specific agent's message board."""
    await _get_owned_graph_agent(agent_id, user)
    if body.sender_id != _graph_inbox_id(user):
        await _get_owned_graph_agent(body.sender_id, user)
    store = await _get_graph_store()
    msg_id = await store.send_message(
        sender_id=body.sender_id,
        receiver_id=agent_id,
        content=body.content,
        message_type=body.message_type,
        priority=body.priority,
    )
    return {"message_id": msg_id}


@router.get("/graph/agent/{agent_id}/messages")
async def get_agent_messages(
    agent_id: str,
    limit: int = Query(100, ge=1, le=500),
    unread_only: bool = Query(False),
    user: Dict[str, Any] = Depends(_require_auth),
):
    """Retrieve messages from an owned agent or the user's orchestration inbox."""
    if agent_id != _graph_inbox_id(user):
        await _get_owned_graph_agent(agent_id, user)
    store = await _get_graph_store()
    messages = await store.get_messages(agent_id, limit, unread_only)
    return {"messages": [asdict(m) for m in messages], "count": len(messages)}


@router.get("/graph/inbox/messages")
async def get_orchestration_inbox(
    limit: int = Query(100, ge=1, le=500),
    user: Dict[str, Any] = Depends(_require_auth),
):
    """Retrieve results delivered to the authenticated user's orchestration inbox."""
    store = await _get_graph_store()
    messages = await store.get_messages(_graph_inbox_id(user), limit)
    return {"messages": [asdict(m) for m in messages], "count": len(messages)}


@router.get("/graph/edges")
async def list_edges(agent_id: str = Query(None), user: Dict[str, Any] = Depends(_require_auth)):
    """List graph edges, optionally filtered to one agent."""
    store = await _get_graph_store()
    if agent_id:
        await _get_owned_graph_agent(agent_id, user)
        candidates = await store.get_edges(agent_id)
        edges = []
        for edge in candidates:
            source = await store.get_agent(edge.source_agent_id)
            target = await store.get_agent(edge.target_agent_id)
            if (
                source and target
                and source.config.get("_owner_id") == _graph_owner_id(user)
                and target.config.get("_owner_id") == _graph_owner_id(user)
            ):
                edges.append(edge)
    else:
        edges = []
    return {"edges": [asdict(e) for e in edges]}
