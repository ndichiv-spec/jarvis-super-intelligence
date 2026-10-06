"""Durable command execution API for the live JARVIS runtime.

This router does not introduce a second orchestration framework. It persists a
first-class command record and executes it through the existing
``ExecutionGraph`` / ``AgentExecutor`` runtime that already lives in
``jarvis_backend.execution_fabric``. Commands therefore remain grounded in the
same real capability registry used elsewhere in the project.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from research_engine.capability_tools import build_capability_registry

from ..core import get_current_user, get_store, is_production, now_iso
from ..db import kv_get, kv_insert_if_absent, load_command_events
from ..execution_fabric import AgentExecutor, ExecutionNodeStatus, Task

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])
_command_jobs: dict[str, asyncio.Task[Any]] = {}


class CommandCreate(BaseModel):
    goal: str = Field(..., min_length=1, max_length=12_000)
    conversation_id: Optional[str] = Field(default=None)
    request_id: Optional[str] = Field(default=None)
    capabilities: Optional[list[str]] = Field(default=None)
    autonomy: str = Field(default="SUPERVISED")


class CommandAuthorization(BaseModel):
    approved: bool
    node_id: Optional[str] = None


def _owner_id(user: dict[str, Any]) -> str:
    return str(user.get("id") or user.get("email") or user.get("user_id") or "anonymous")


def _commands_store() -> Any:
    return get_store("commands")


def _read_command(command_id: str) -> Optional[dict[str, Any]]:
    store = _commands_store()
    if hasattr(store, "reload"):
        store.reload()
    command = store.load().get(command_id)
    return copy.deepcopy(command) if command is not None else None


def _read_commands() -> dict[str, Any]:
    store = _commands_store()
    if hasattr(store, "reload"):
        store.reload()
    return store.load()


def _save_command(command: dict[str, Any]) -> None:
    store = _commands_store()
    command_id = str(command["command_id"])
    if hasattr(store, "save_key"):
        current = kv_get("commands", command_id)
        if current:
            current_status = current.get("status")
            next_status = command.get("status")
            if current_status == "CANCELLED" and next_status in {
                "RECEIVED", "PLANNING", "READY", "EXECUTING",
            }:
                command["status"] = "CANCELLED"
            elif current_status == "CANCEL_REQUESTED" and next_status in {
                "RECEIVED", "PLANNING", "READY",
            }:
                command["status"] = "CANCEL_REQUESTED"
                command["cancel_requested_at"] = current.get("cancel_requested_at")
            event_map = {
                event.get("event_id"): event
                for event in [*current.get("events", []), *command.get("events", [])]
                if event.get("event_id")
            }
            command["events"] = list(event_map.values())[-200:]
            command["event_seq"] = max(
                int(current.get("event_seq", 0)),
                int(command.get("event_seq", 0)),
            )
        store.save_key(command_id, command)
        return
    store.load()[command_id] = command
    store.save()


def _insert_command(command: dict[str, Any]) -> bool:
    store = _commands_store()
    command_id = str(command["command_id"])
    if hasattr(store, "save_key"):
        inserted = kv_insert_if_absent("commands", command_id, command)
        if inserted:
            store.load()[command_id] = command
        return inserted
    commands = store.load()
    if command_id in commands:
        return False
    commands[command_id] = command
    store.save()
    return True


def _claim_command_execution(command_id: str) -> Optional[dict[str, Any]]:
    store = _commands_store()
    if hasattr(store, "update_key"):
        def claim(command: dict[str, Any]) -> dict[str, Any]:
            if command.get("status") == "READY":
                command["status"] = "EXECUTING"
                command["execution_claimed_at"] = time.time()
                command["lease_expires_at"] = time.time() + 90
            return command

        return store.update_key(command_id, claim)
    command = _read_command(command_id)
    if command and command.get("status") == "READY":
        command["status"] = "EXECUTING"
        _save_command(command)
        return command
    return command


def _claim_command_for_worker(
    command_id: str,
    worker_task_id: str,
    worker_id: str,
    *,
    resume: bool,
    redelivered: bool,
) -> Optional[dict[str, Any]]:
    store = _commands_store()
    if not hasattr(store, "update_key"):
        return _read_command(command_id)

    claimed = False

    def claim(command: dict[str, Any]) -> dict[str, Any]:
        nonlocal claimed
        status = command.get("status")
        allowed = (
            status == "QUEUED"
            or status == "RETRYING"
            or (resume and status == "READY")
            or (
                redelivered
                and status in {"RECEIVED", "PLANNING", "READY", "EXECUTING"}
            )
        )
        if allowed:
            claimed = True
            command["worker_task_id"] = worker_task_id
            command["worker_id"] = worker_id
            command["worker_attempts"] = int(command.get("worker_attempts", 0)) + 1
            command["worker_claimed_at"] = time.time()
            command["lease_expires_at"] = time.time() + 90
            command["execution_id"] = command.get("execution_id") or str(uuid.uuid4())
            if status in {"QUEUED", "RETRYING"}:
                command["status"] = "RECEIVED"
        return command

    command = store.update_key(command_id, claim)
    return command if claimed else None


def _append_event(command_id: str, event: str, **payload: Any) -> None:
    entry = {
        "event_id": str(uuid.uuid4()),
        "timestamp": now_iso(),
        "event": event,
        **payload,
    }

    store = _commands_store()
    if hasattr(store, "save_key"):
        from ..db import append_command_event

        append_command_event(command_id, entry)
        return

    def append(command: dict[str, Any]) -> dict[str, Any]:
        events = command.setdefault("events", [])
        sequence = int(command.get("event_seq", 0)) + 1
        command["event_seq"] = sequence
        events.append({**entry, "sequence": sequence, "command_id": command_id})
        command["events"] = events[-200:]
        return command

    if hasattr(store, "update_key"):
        store.update_key(command_id, append)
        return
    command = _read_command(command_id)
    if command is not None:
        _save_command(append(command))


def _heartbeat_command_lease(command_id: str, worker_task_id: str) -> bool:
    store = _commands_store()
    if not hasattr(store, "update_key"):
        return False
    owned = False

    def heartbeat(command: dict[str, Any]) -> dict[str, Any]:
        nonlocal owned
        if command.get("worker_task_id") == worker_task_id and command.get("status") in {
            "RECEIVED", "PLANNING", "READY", "EXECUTING", "RETRYING",
            "CANCEL_REQUESTED",
        }:
            owned = True
            command["lease_expires_at"] = time.time() + 90
            command["heartbeat_at"] = time.time()
        return command

    store.update_key(command_id, heartbeat)
    return owned


def _clear_command_lease(command_id: str, worker_task_id: str) -> None:
    store = _commands_store()
    if not hasattr(store, "update_key"):
        return

    def clear(command: dict[str, Any]) -> dict[str, Any]:
        if command.get("worker_task_id") == worker_task_id:
            command.pop("lease_expires_at", None)
        return command

    store.update_key(command_id, clear)


def _recover_expired_commands(now: Optional[float] = None) -> dict[str, int]:
    """Requeue commands whose worker lease expired, without replaying finished work."""
    from ..celery_tasks import enqueue_command

    current_time = now or time.time()
    store = _commands_store()
    recovered = 0
    failed_to_enqueue = 0
    for command_id, snapshot in _read_commands().items():
        status = snapshot.get("status")
        lease_expired = (
            status in {"RECEIVED", "PLANNING", "READY", "EXECUTING"}
            and float(snapshot.get("lease_expires_at") or 0) <= current_time
        )
        queued_retry_due = (
            status == "QUEUED"
            and float(
                snapshot.get("recovery_enqueued_at")
                or snapshot.get("queue_enqueued_at")
                or current_time
            )
            <= current_time - 300
        )
        if not (lease_expired or queued_retry_due) or not hasattr(store, "update_key"):
            continue

        recovered_command: dict[str, Any] = {}

        def mark_for_recovery(command: dict[str, Any]) -> dict[str, Any]:
            nonlocal recovered_command
            active_lease_expired = (
                command.get("status") in {"RECEIVED", "PLANNING", "READY", "EXECUTING"}
                and float(command.get("lease_expires_at") or 0) <= current_time
            )
            queue_stalled = (
                command.get("status") == "QUEUED"
                and float(
                    command.get("recovery_enqueued_at")
                    or command.get("queue_enqueued_at")
                    or current_time
                )
                <= current_time - 300
            )
            if active_lease_expired or queue_stalled:
                command["status"] = "QUEUED"
                command["recovery_enqueued_at"] = current_time
                command.pop("lease_expires_at", None)
                command.pop("worker_id", None)
                command.pop("worker_task_id", None)
                recovered_command = copy.deepcopy(command)
            return command

        store.update_key(command_id, mark_for_recovery)
        if not recovered_command:
            continue
        _append_event(
            command_id,
            "worker_lease_expired" if lease_expired else "queued_command_republished",
        )
        try:
            worker_task_id = enqueue_command(
                command_id=command_id,
                user={
                    "id": recovered_command["user_id"],
                    "user_id": recovered_command["user_id"],
                },
                goal=recovered_command.get("goal"),
                autonomy=recovered_command.get("autonomy", "SUPERVISED"),
                resume=bool(recovered_command.get("task_id")),
            )
            store.update_key(
                command_id,
                lambda command: {
                    **command,
                    "worker_task_id": worker_task_id,
                    "queue_enqueued_at": current_time,
                },
            )
            recovered += 1
        except Exception as exc:
            failed_to_enqueue += 1
            store.update_key(
                command_id,
                lambda command: {
                    **command,
                    "queue_error": type(exc).__name__,
                },
            )
            _append_event(
                command_id,
                "command_recovery_enqueue_failed",
                error=type(exc).__name__,
            )
    return {"recovered": recovered, "enqueue_failures": failed_to_enqueue}


def _task_status_to_command_status(task: Optional[Task]) -> str:
    if task is None:
        return "RECEIVED"
    mapping = {
        "RECEIVED": "RECEIVED",
        "UNDERSTOOD": "UNDERSTANDING",
        "PLANNED": "PLANNING",
        "AUTHORIZATION_REQUIRED": "AWAITING_AUTHORIZATION",
        "AUTHORIZED": "READY",
        "RUNNING": "EXECUTING",
        "WAITING_FOR_USER": "WAITING",
        "COMPLETED": "COMPLETED",
        "VERIFIED": "COMPLETED",
        "PARTIAL": "PARTIAL",
        "FAILED": "FAILED",
        "CANCELLED": "CANCELLED",
    }
    return mapping.get(task.status.value if hasattr(task.status, "value") else str(task.status), "RECEIVED")


async def _resume_command_execution(command_id: str, user: dict[str, Any]) -> None:
    command = _read_command(command_id)
    if command is None:
        return

    task_id = command.get("task_id")
    if not task_id:
        return
    task = Task.load(task_id)
    if task is None:
        command["status"] = "FAILED"
        command["errors"] = ["Task checkpoint was missing; execution could not be resumed."]
        _save_command(command)
        return

    executor = AgentExecutor(tool_registry=build_capability_registry())
    authorization = command.get("authorization") or {}
    approved_node_ids = set(authorization.get("approved_node_ids", []))
    for node_id in approved_node_ids:
        if (
            task.plan
            and node_id in task.plan.nodes
            and task.plan.nodes[node_id].status == ExecutionNodeStatus.WAITING_FOR_USER
        ):
            executor.approve_node(task.task_id, node_id, approved=True)

    result = await executor.execute_task(task, principal=user)
    if task.status.value == "WAITING_FOR_USER":
        pending_node_ids = [
            node_id for node_id, node in (task.plan.nodes.items() if task.plan else [])
            if node.status == ExecutionNodeStatus.WAITING_FOR_USER
        ]
        command["status"] = "AWAITING_AUTHORIZATION"
        authorization["node_ids"] = pending_node_ids
        authorization["approved_node_ids"] = sorted(approved_node_ids)
        command["authorization"] = authorization
        command["result"] = None
        command["completed_at"] = None
        _save_command(command)
        _append_event(command_id, "authorization_required", node_ids=pending_node_ids)
        return

    command["status"] = _task_status_to_command_status(task)
    command["result"] = result
    command["errors"] = [] if result.get("success") else [result.get("error") or "execution failed"]
    command["completed_at"] = time.time()
    _save_command(command)
    _append_event(command_id, "command_completed" if result.get("success") else "command_failed", result=result)


async def _run_command(command_id: str, user: dict[str, Any], goal: str, autonomy: str) -> None:
    try:
        command = _read_command(command_id)
        if command is None:
            return

        if command.get("status") in {"CANCELLED", "CANCEL_REQUESTED"}:
            command["status"] = "CANCELLED"
            command["completed_at"] = time.time()
            _save_command(command)
            _append_event(command_id, "command_cancelled_before_execution")
            return

        if command.get("task_id"):
            if Task.load(command["task_id"]) is None:
                command["status"] = "FAILED"
                command["errors"] = ["Persisted execution checkpoint is missing; refusing to replay work."]
                command["completed_at"] = time.time()
                _save_command(command)
                _append_event(command_id, "command_checkpoint_missing")
                return
            _append_event(command_id, "command_resumed", task_id=command["task_id"])
            await _resume_command_execution(command_id, user)
            return

        command["status"] = "RECEIVED"
        command["goal"] = goal
        command["started_at"] = time.time()
        _save_command(command)
        _append_event(command_id, "command_received", goal=goal, autonomy=autonomy)

        executor = AgentExecutor(tool_registry=build_capability_registry())
        requested_capabilities = command.get("requested_capabilities")
        task, graph = executor.build_execution_graph(
            goal,
            capabilities=requested_capabilities,
            user_id=_owner_id(user),
            execution_mode=autonomy.lower(),
            claim=goal,
        )
        command = _read_command(command_id) or command
        command["task_id"] = task.task_id
        command["plan"] = {
            "task_id": task.task_id,
            "capabilities": [node.capability for node in graph.nodes.values()],
        }
        command["capabilities"] = [node.capability for node in graph.nodes.values()]
        command["status"] = "PLANNING"
        _save_command(command)
        _append_event(command_id, "plan_created", task_id=task.task_id, capabilities=command["capabilities"])

        if task.plan and any(
            node.status == ExecutionNodeStatus.WAITING_FOR_USER
            for node in task.plan.nodes.values()
        ):
            command["status"] = "AWAITING_AUTHORIZATION"
            command["authorization"] = {
                "required": True,
                "requested_at": time.time(),
                "approved": None,
                "node_ids": [
                    node_id for node_id, node in task.plan.nodes.items()
                    if node.status == ExecutionNodeStatus.WAITING_FOR_USER
                ],
            }
            _save_command(command)
            _append_event(
                command_id,
                "authorization_required",
                node_ids=command["authorization"]["node_ids"],
            )
            return

        latest_command = _read_command(command_id)
        if latest_command and latest_command.get("status") in {"CANCELLED", "CANCEL_REQUESTED"}:
            latest_command["status"] = "CANCELLED"
            latest_command["completed_at"] = time.time()
            _save_command(latest_command)
            _append_event(command_id, "command_cancelled_before_execution")
            return

        command["status"] = "READY"
        _save_command(command)
        command = _claim_command_execution(command_id) or command
        if command.get("status") != "EXECUTING":
            if command.get("status") in {"CANCELLED", "CANCEL_REQUESTED"}:
                command["status"] = "CANCELLED"
                command["completed_at"] = time.time()
                _save_command(command)
                _append_event(command_id, "command_cancelled_before_execution")
            return
        result = await executor.execute_task(task, principal=user)
        command = _read_command(command_id) or command
        command["status"] = _task_status_to_command_status(task)
        command["result"] = result
        command["errors"] = [] if result.get("success") else [result.get("error") or "execution failed"]
        command["completed_at"] = time.time()
        _save_command(command)
        _append_event(command_id, "command_completed" if result.get("success") else "command_failed", result=result)
    except asyncio.CancelledError:
        command = _read_command(command_id)
        if command is not None:
            command["status"] = "CANCELLED"
            command["completed_at"] = time.time()
            _save_command(command)
            _append_event(command_id, "command_cancelled")
    except Exception as exc:  # pragma: no cover - defensive path
        command = _read_command(command_id)
        if command is not None:
            command["status"] = "FAILED"
            command["errors"] = [f"{type(exc).__name__}: {exc}"]
            command["completed_at"] = time.time()
            _save_command(command)
            _append_event(command_id, "command_failed", error=str(exc))
    finally:
        _command_jobs.pop(command_id, None)


@router.post("", status_code=202)
async def create_command(
    body: CommandCreate,
    user: dict[str, Any] = Depends(get_current_user),
):
    goal = body.goal.strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal must not be blank")

    owner_id = _owner_id(user)
    request_id = body.request_id.strip() if body.request_id else None
    if request_id == "":
        request_id = None
    if request_id and len(request_id) > 200:
        raise HTTPException(status_code=422, detail="request_id must be at most 200 characters")
    if request_id:
        request_digest = hashlib.sha256(f"{owner_id}\0{request_id}".encode()).hexdigest()
        command_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"jarvis-command:{request_digest}"))
        existing = _read_command(command_id)
        if existing is not None:
            if (
                existing.get("goal") != goal
                or existing.get("conversation_id") != body.conversation_id
                or existing.get("requested_capabilities") != list(body.capabilities or [])
                or existing.get("autonomy", "SUPERVISED") != body.autonomy
            ):
                raise HTTPException(status_code=409, detail="request_id was already used for a different command")
            return existing
    else:
        command_id = str(uuid.uuid4())
    now = time.time()
    command = {
        "command_id": command_id,
        "execution_id": str(uuid.uuid4()),
        "conversation_id": body.conversation_id,
        "request_id": request_id,
        "user_id": owner_id,
        "goal": goal,
        "requested_capabilities": list(body.capabilities or []),
        "autonomy": body.autonomy,
        "status": "QUEUED" if is_production() else "RECEIVED",
        "priority": "normal",
        "plan": {},
        "active_step": None,
        "capabilities": [],
        "agents": [],
        "models": [],
        "permissions": [],
        "authorization": None,
        "started_at": None,
        "created_at": now,
        "queue_enqueued_at": now if is_production() else None,
        "completed_at": None,
        "result": None,
        "errors": [],
        "events": [],
        "event_seq": 0,
        "task_id": None,
    }
    if not _insert_command(command):
        existing = _read_command(command_id)
        if existing is not None:
            return existing
        raise HTTPException(status_code=503, detail="Command persistence conflict; retry with the same request_id")

    _append_event(command_id, "command_queued" if is_production() else "command_received")
    if is_production():
        try:
            from ..celery_tasks import enqueue_command

            task_id = enqueue_command(
                command_id=command_id,
                user={
                    "id": owner_id,
                    "user_id": owner_id,
                    "email": user.get("email"),
                    "roles": user.get("roles", []),
                },
                goal=goal,
                autonomy=body.autonomy,
            )
            command = _read_command(command_id) or command
            command["worker_task_id"] = task_id
            _save_command(command)
        except Exception as exc:
            command["status"] = "FAILED"
            command["completed_at"] = time.time()
            command["errors"] = [f"queue unavailable: {type(exc).__name__}"]
            _save_command(command)
            _append_event(command_id, "command_enqueue_failed", error=type(exc).__name__)
            raise HTTPException(status_code=503, detail="JARVIS command queue is unavailable") from exc
    else:
        task = asyncio.create_task(_run_command(command_id, user, goal, body.autonomy))
        _command_jobs[command_id] = task
    return _read_command(command_id) or copy.deepcopy(command)


@router.get("")
async def list_commands(
    limit: int = Query(default=50, ge=1, le=200),
    user: dict[str, Any] = Depends(get_current_user),
):
    owner_id = _owner_id(user)
    items = [
        copy.deepcopy(command)
        for command in _read_commands().values()
        if command.get("user_id") == owner_id
    ]
    items.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return {"commands": items[:limit]}


@router.get("/metrics")
async def get_command_metrics(
    user: dict[str, Any] = Depends(get_current_user),
):
    owner_id = _owner_id(user)
    commands = (
        command
        for command in _read_commands().values()
        if command.get("user_id") == owner_id
    )
    counts = {status: 0 for status in [
        "QUEUED", "RECEIVED", "UNDERSTANDING", "PLANNING", "AWAITING_AUTHORIZATION",
        "READY", "EXECUTING", "WAITING", "VERIFYING", "RECOVERING",
        "REPLANNING", "COMPLETED", "PARTIAL", "FAILED", "CANCELLED",
        "CANCEL_REQUESTED",
    ]}
    for command in commands:
        status = str(command.get("status") or "RECEIVED")
        counts[status] = counts.get(status, 0) + 1
    return {
        "generated_at": now_iso(),
        "total_commands": sum(counts.values()),
        "by_status": counts,
    }


@router.get("/{command_id}")
async def get_command(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _read_command(command_id)
    if command is None or command.get("user_id") != _owner_id(user):
        raise HTTPException(status_code=404, detail="Command not found")
    return copy.deepcopy(command)


@router.get("/{command_id}/events")
async def get_command_events(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _read_command(command_id)
    if command is None or command.get("user_id") != _owner_id(user):
        raise HTTPException(status_code=404, detail="Command not found")
    store = _commands_store()
    events = (
        load_command_events(command_id)
        if hasattr(store, "save_key")
        else copy.deepcopy(command.get("events", []))
    )
    return {
        "command_id": command_id,
        "execution_id": command.get("execution_id"),
        "events": events,
    }


@router.post("/{command_id}/authorization")
async def authorize_command(
    command_id: str,
    body: CommandAuthorization,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _read_command(command_id)
    if command is None or command.get("user_id") != _owner_id(user):
        raise HTTPException(status_code=404, detail="Command not found")
    if command.get("status") != "AWAITING_AUTHORIZATION":
        raise HTTPException(status_code=409, detail="Command is not awaiting authorization")

    authorization = command.setdefault("authorization", {"required": True})
    pending_node_ids = authorization.get("node_ids", [])
    selected_node_id = body.node_id
    if selected_node_id is None and len(pending_node_ids) == 1:
        selected_node_id = pending_node_ids[0]
    if body.approved and selected_node_id not in pending_node_ids:
        raise HTTPException(
            status_code=422,
            detail="Select one pending authorization node; only pending nodes can be approved",
        )
    authorization["approved"] = body.approved
    authorization["decided_at"] = time.time()
    authorization["node_id"] = selected_node_id
    if body.approved:
        approved_node_ids = set(authorization.get("approved_node_ids", []))
        approved_node_ids.add(selected_node_id)
        authorization["approved_node_ids"] = sorted(approved_node_ids)
    command["status"] = "READY" if body.approved else "CANCELLED"
    if not body.approved:
        command["completed_at"] = time.time()
        command["errors"] = ["Authorization was rejected by the user."]
    _save_command(command)
    _append_event(command_id, "authorization_decided", approved=body.approved, node_id=selected_node_id)

    if body.approved:
        if is_production():
            from ..celery_tasks import enqueue_command

            task_id = enqueue_command(
                command_id=command_id,
                user={
                    "id": _owner_id(user),
                    "user_id": _owner_id(user),
                    "email": user.get("email"),
                    "roles": user.get("roles", []),
                },
                resume=True,
            )
            command["worker_task_id"] = task_id
            _save_command(command)
        else:
            task = asyncio.create_task(_resume_command_execution(command_id, user))
            _command_jobs[command_id] = task
    return copy.deepcopy(command)


@router.post("/{command_id}/cancel")
async def cancel_command(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _read_command(command_id)
    if command is None or command.get("user_id") != _owner_id(user):
        raise HTTPException(status_code=404, detail="Command not found")
    if command.get("status") in {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Command is already terminal")

    job = _command_jobs.get(command_id)
    if job is not None:
        job.cancel()
        command["status"] = "CANCELLED"
        command["completed_at"] = time.time()
    elif command.get("status") == "QUEUED":
        command["status"] = "CANCELLED"
        command["completed_at"] = time.time()
        if is_production() and command.get("worker_task_id"):
            from ..celery_app import celery_app

            celery_app.control.revoke(command["worker_task_id"], terminate=False)
    else:
        command["status"] = "CANCEL_REQUESTED"
        command["cancel_requested_at"] = time.time()
    _save_command(command)
    _append_event(command_id, "command_cancel_requested")
    return {
        "command_id": command_id,
        "status": command["status"],
        "cancel_requested": True,
        "cancellation": "queued_command_revoked" if command["status"] == "CANCELLED" else "will_stop_at_safe_boundary",
    }
