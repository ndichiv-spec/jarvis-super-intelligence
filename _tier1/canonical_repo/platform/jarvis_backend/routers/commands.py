"""Authenticated command runtime endpoints.

Commands run through the existing BrainOrchestrator, PlanValidator, and
ToolRegistry. This router supplies persistence, approval hand-off, and a
pollable event snapshot without introducing another execution path.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import get_current_user, get_store
from ..runtime import (
    ACTIVE_STATES as ACTIVE_EXECUTION_STATES,
    ExecutionState,
    runtime as jarvis_runtime,
)
from research_engine.tool_registry import scrub_secrets

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])
_cancel_tokens: dict[str, asyncio.Event] = {}
_authorization_events: dict[str, asyncio.Event] = {}
_command_jobs: dict[str, asyncio.Task[None]] = {}
_execution_slots = asyncio.Semaphore(4)
_WORKER_ID = f"api-{os.getpid()}-{uuid.uuid4().hex[:10]}"
_supervisor_job: asyncio.Task[None] | None = None

_STATUS_BY_EVENT = {
    "BRAIN_PLAN_CREATED": "UNDERSTANDING",
    "BRAIN_PLAN_PROPOSED": "PLANNING",
    "BRAIN_PLAN_VALIDATED": "PLANNING",
    "PLAN_AUTHORIZED": "READY",
    "HUMAN_APPROVAL": "AWAITING_AUTHORIZATION",
    "EXECUTION_STARTED": "EXECUTING",
    "CAPABILITY_STARTED": "EXECUTING",
    "CAPABILITY_COMPLETED": "EXECUTING",
    "CAPABILITY_FAILED": "RECOVERING",
    "EXECUTION_RESULT": "VERIFYING",
    "VERIFICATION_RESULT": "VERIFYING",
    "BRAIN_REASSESSMENT": "REPLANNING",
    "PROVIDER_UNAVAILABLE": "RECOVERING",
    "TASK_COMPLETED": "COMPLETED",
    "TASK_FAILED": "FAILED",
    "TASK_CANCELLED": "CANCELLED",
    "TASK_BUDGET_EXCEEDED": "FAILED",
}


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_secrets(value)[0]
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return scrub_secrets(str(value))[0]


class CommandCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=12_000)
    conversation_id: Optional[str] = Field(default=None, max_length=128)
    request_id: Optional[str] = Field(default=None, max_length=128)
    autonomy: str = Field(default="SUPERVISED", pattern="^(ASSISTED|SUPERVISED)$")


class CommandAuthorization(BaseModel):
    approved: bool


def _commands() -> dict[str, Any]:
    return get_store("commands").load()


def _owner_id(user: dict[str, Any]) -> str:
    return str(user.get("id") or user.get("email") or "")


def _owned_command(command_id: str, user: dict[str, Any]) -> dict[str, Any]:
    command = _commands().get(command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    if command.get("user_id") != _owner_id(user):
        raise HTTPException(status_code=404, detail="Command not found")
    return command


def _append_event(command_id: str, event_type: str, **payload: Any) -> None:
    store = get_store("commands")
    commands = store.load()
    command = commands.get(command_id)
    if command is None:
        return
    safe_payload = _safe_value(payload)
    plan_id = command.get("plan_id")
    if plan_id:
        safe_payload["plan_id"] = plan_id
    event_step_id = (
        command.get("active_step_id")
        or safe_payload.get("step_id")
        or command.get("active_step")
    )
    durable_event = jarvis_runtime.append_event(
        command_id=command_id,
        event_type=event_type,
        payload=safe_payload,
        execution_id=command.get("active_execution_id"),
        step_id=event_step_id,
        status=command.get("status"),
    )
    event = {
        **safe_payload,
        "event_id": durable_event["event_id"],
        "sequence": durable_event["sequence"],
        "event": event_type,
        "timestamp": durable_event["timestamp"],
    }
    command["events"].append(event)
    if len(command["events"]) > 500:
        del command["events"][:-500]
    store.save()


def _set_status(command_id: str, status: str) -> None:
    store = get_store("commands")
    command = store.load().get(command_id)
    if command is None:
        return
    command["status"] = status
    if status in {
        "COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "RECOVERY_REQUIRED",
    }:
        command["completed_at"] = time.time()
    store.save()


def _execution_id(command_id: str) -> str | None:
    command = _commands().get(command_id)
    return command.get("active_execution_id") if command else None


def _advance_execution(command_id: str, state: ExecutionState) -> None:
    execution_id = _execution_id(command_id)
    if not execution_id:
        return
    current = jarvis_runtime.get_execution(execution_id)
    if current is None or not jarvis_runtime.can_transition(current["status"], state):
        return
    jarvis_runtime.transition(
        execution_id, state, worker_id=_WORKER_ID,
    )


def _schedule_command(
    command_id: str, user: dict[str, Any], autonomy: str,
) -> None:
    _cancel_tokens.setdefault(command_id, asyncio.Event())
    _authorization_events.setdefault(command_id, asyncio.Event())
    existing = _command_jobs.get(command_id)
    if existing is not None and not existing.done():
        return
    _command_jobs[command_id] = asyncio.create_task(
        _execute_command(command_id, user, autonomy)
    )


@router.on_event("startup")
async def recover_commands_on_startup() -> None:
    global _supervisor_job
    store = get_store("commands")
    commands = store.load()
    orphaned = jarvis_runtime.recover_orphaned(worker_id=_WORKER_ID)
    queued_ids = {
        record["execution_id"]
        for record in jarvis_runtime.list_executions(statuses={ExecutionState.QUEUED.value})
    }
    for execution_id in queued_ids:
        record = jarvis_runtime.get_execution(execution_id)
        command = commands.get(record["command_id"]) if record else None
        if not command or command.get("status") in {"COMPLETED", "CANCELLED"}:
            continue
        users = get_store("users").load()
        user = users.get(record["user_id"])
        if not user:
            jarvis_runtime.transition(
                execution_id,
                ExecutionState.FAILED,
                error="Command owner no longer exists; queued work was not resumed.",
            )
            command["status"] = "FAILED"
            command["completed_at"] = time.time()
            command.setdefault("errors", []).append(
                "Command owner no longer exists; queued work was not resumed."
            )
            store.save()
            _append_event(command["command_id"], "command_failed")
            continue
        command["active_execution_id"] = execution_id
        command.setdefault("execution_ids", [])
        if execution_id not in command["execution_ids"]:
            command["execution_ids"].append(execution_id)
        command["status"] = "RECEIVED"
        store.save()
        _append_event(command["command_id"], "command_recovered_and_queued")
        _schedule_command(command["command_id"], user, command.get("autonomy", "SUPERVISED"))

    for record in orphaned:
        command = commands.get(record["command_id"])
        if not command:
            continue
        if record["status"] == ExecutionState.RECOVERY_REQUIRED.value:
            command["status"] = "RECOVERY_REQUIRED"
            command["completed_at"] = time.time()
            command.setdefault("errors", []).append(record["error"])
            store.save()
            _append_event(
                command["command_id"], "execution_recovery_required",
                execution_id=record["execution_id"],
            )

    attached_ids = {
        record["command_id"]
        for record in jarvis_runtime.list_executions(limit=10000)
    }
    legacy_active = {
        "RECEIVED", "UNDERSTANDING", "PLANNING", "AWAITING_AUTHORIZATION",
        "READY", "EXECUTING", "WAITING", "VERIFYING", "RECOVERING",
        "REPLANNING",
    }
    for command_id, command in commands.items():
        if command.get("status") in legacy_active and command_id not in attached_ids:
            command["status"] = "FAILED"
            command["completed_at"] = time.time()
            command.setdefault("errors", []).append(
                "Interrupted command has no durable execution record; manual retry is required."
            )
            store.save()
            _append_event(command_id, "command_interrupted_without_execution_record")
    _supervisor_job = asyncio.create_task(_supervise_execution_recovery())


async def _supervise_execution_recovery() -> None:
    while True:
        await asyncio.sleep(10)
        records = jarvis_runtime.recover_orphaned(worker_id=_WORKER_ID)
        commands = _commands()
        users = get_store("users").load()
        for record in records:
            command = commands.get(record["command_id"])
            if command is None:
                continue
            if record["status"] == ExecutionState.QUEUED.value:
                user = users.get(record["user_id"])
                if user is None:
                    jarvis_runtime.transition(
                        record["execution_id"],
                        ExecutionState.FAILED,
                        error="Command owner no longer exists; queued work was not resumed.",
                    )
                    command["status"] = "FAILED"
                    command["completed_at"] = time.time()
                    command.setdefault("errors", []).append(
                        "Command owner no longer exists; queued work was not resumed."
                    )
                    get_store("commands").save()
                    _append_event(command["command_id"], "command_failed")
                    continue
                command["active_execution_id"] = record["execution_id"]
                command["status"] = "RECEIVED"
                get_store("commands").save()
                _append_event(
                    command["command_id"], "command_recovered_and_queued",
                    execution_id=record["execution_id"],
                )
                _schedule_command(
                    command["command_id"], user,
                    command.get("autonomy", "SUPERVISED"),
                )
            elif record["status"] == ExecutionState.RECOVERY_REQUIRED.value:
                command["status"] = "RECOVERY_REQUIRED"
                command["completed_at"] = time.time()
                command.setdefault("errors", []).append(record["error"])
                get_store("commands").save()
                _append_event(
                    command["command_id"], "execution_recovery_required",
                    execution_id=record["execution_id"],
                )


@router.on_event("shutdown")
async def stop_runtime_supervisor() -> None:
    global _supervisor_job
    if _supervisor_job is not None:
        _supervisor_job.cancel()
        await asyncio.gather(_supervisor_job, return_exceptions=True)
        _supervisor_job = None


def _audit_callback(command_id: str):
    def record(audit_event: Any) -> None:
        event_name = str(audit_event.event)
        command_store = get_store("commands")
        command = command_store.load().get(command_id)
        if command is None:
            return
        event_step_id = (
            command.get("active_step_id")
            or command.get("active_step")
            or audit_event.capability
            or None
        )
        status = _STATUS_BY_EVENT.get(event_name)
        if status:
            command["status"] = status
            if status == "EXECUTING":
                command["started_at"] = command["started_at"] or time.time()
            if status in {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
                command["completed_at"] = time.time()
        provenance = audit_event.provenance or {}
        if event_name == "BRAIN_PLAN_PROPOSED":
            proposed_steps = _safe_value(provenance.get("capabilities", []))
            if command.get("replan_pending"):
                command["plan_id"] = str(uuid.uuid4())
                command["replan_pending"] = False
            command["plan"] = proposed_steps
            command["plan_id"] = command.get("plan_id") or str(uuid.uuid4())
            command.setdefault("plan_ids", [])
            if command["plan_id"] not in command["plan_ids"]:
                command["plan_ids"].append(command["plan_id"])
            command["models"] = [provenance["model"]] if provenance.get("model") else []
            jarvis_runtime.create_plan(
                plan_id=command["plan_id"],
                command_id=command_id,
                user_id=command["user_id"],
                objective=_safe_value(audit_event.detail),
                steps=proposed_steps,
            )
        elif event_name == "BRAIN_PLAN_VALIDATED":
            decision = str(provenance.get("decision") or "").upper()
            plan_status = {
                "ACCEPTED": "VALIDATED",
                "HUMAN_APPROVAL": "WAITING_AUTHORIZATION",
                "DENIED": "REJECTED",
                "PLAN_REJECTED": "REJECTED",
                "PLAN_BLOCKED": "BLOCKED",
            }.get(decision, "VALIDATED")
            if command.get("plan_id"):
                jarvis_runtime.update_plan_status(command["plan_id"], plan_status)
        elif event_name == "HUMAN_APPROVAL":
            if command.get("plan_id"):
                jarvis_runtime.update_plan_status(
                    command["plan_id"], "WAITING_AUTHORIZATION",
                )
        elif event_name == "PLAN_AUTHORIZED":
            authorized = set(provenance.get("authorized", []))
            if authorized:
                command["plan"] = [
                    step for step in command["plan"]
                    if step.get("capability") in authorized
                ]
                plan = jarvis_runtime.get_plan(command.get("plan_id"))
                for step in (plan or {}).get("steps", []):
                    if step["capability"] not in authorized:
                        jarvis_runtime.update_plan_step(
                            command["plan_id"],
                            step["step_id"],
                            status="SKIPPED",
                            result={"reason": "not authorized for this execution"},
                        )
            if command.get("plan_id"):
                jarvis_runtime.update_plan_status(
                    command["plan_id"], "EXECUTING",
                )
        if event_name == "CAPABILITY_STARTED" and audit_event.capability:
            command["active_step"] = audit_event.capability
            if audit_event.capability not in command["capabilities"]:
                command["capabilities"].append(audit_event.capability)
            plan_id = command.get("plan_id")
            plan = jarvis_runtime.get_plan(plan_id) if plan_id else None
            step = next(
                (
                    item for item in (plan or {}).get("steps", [])
                    if item["capability"] == audit_event.capability
                    and item["status"] == "PENDING"
                ),
                None,
            )
            command["active_step_id"] = (
                step["step_id"] if step else audit_event.capability
            )
            if plan_id:
                jarvis_runtime.update_plan_step(
                    plan_id,
                    command["active_step_id"],
                    status="RUNNING",
                )
        elif event_name in {"CAPABILITY_COMPLETED", "CAPABILITY_FAILED"}:
            plan_id = command.get("plan_id")
            step_id = command.get("active_step_id")
            if plan_id and step_id:
                jarvis_runtime.update_plan_step(
                    plan_id,
                    step_id,
                    status=(
                        "SUCCEEDED"
                        if event_name == "CAPABILITY_COMPLETED" else "FAILED"
                    ),
                    result={
                        "success": bool(audit_event.success),
                        "detail": _safe_value(audit_event.detail),
                    },
                )
            command["active_step"] = None
            command["active_step_id"] = None
        if event_name in {"TASK_COMPLETED", "TASK_FAILED", "TASK_CANCELLED"}:
            plan_id = command.get("plan_id")
            if plan_id:
                jarvis_runtime.update_plan_status(
                    plan_id,
                    {
                        "TASK_COMPLETED": "COMPLETED",
                        "TASK_FAILED": "FAILED",
                        "TASK_CANCELLED": "CANCELLED",
                    }[event_name],
                )
        if event_name == "BRAIN_REASSESSMENT":
            plan_id = command.get("plan_id")
            if plan_id:
                jarvis_runtime.update_plan_status(plan_id, "REPLANNED")
            command["replan_pending"] = True
            command["plan"] = []
        command_store.save()
        execution_state_by_event = {
            "HUMAN_APPROVAL": ExecutionState.WAITING,
                "PLAN_AUTHORIZED": ExecutionState.RUNNING,
                "EXECUTION_STARTED": ExecutionState.RUNNING,
            "CAPABILITY_STARTED": ExecutionState.RUNNING,
            "CAPABILITY_FAILED": ExecutionState.RECOVERING,
            "EXECUTION_RESULT": ExecutionState.VERIFYING,
            "BRAIN_REASSESSMENT": ExecutionState.RECOVERING,
            "PROVIDER_UNAVAILABLE": ExecutionState.RECOVERING,
        }
        next_execution_state = execution_state_by_event.get(event_name)
        if next_execution_state:
            _advance_execution(command_id, next_execution_state)
        _append_event(
            command_id,
            event_name.lower(),
            detail=_safe_value(audit_event.detail),
            capability=audit_event.capability or None,
            step_id=event_step_id,
            success=audit_event.success,
            provenance=_safe_value(provenance),
        )

    return record


async def _execute_command(command_id: str, user: dict[str, Any], autonomy: str) -> None:
    heartbeat_task: asyncio.Task[None] | None = None
    execution_id: str | None = None
    try:
        command = _commands().get(command_id)
        if command is None:
            return
        execution_id = command.get("active_execution_id")
        if not execution_id or not jarvis_runtime.claim_execution(
            execution_id, worker_id=_WORKER_ID,
        ):
            return
        jarvis_runtime.transition(
            execution_id, ExecutionState.STARTING, worker_id=_WORKER_ID,
        )
        command["status"] = "UNDERSTANDING"
        command["started_at"] = command.get("started_at") or time.time()
        get_store("commands").save()
        _append_event(
            command_id, "execution_claimed", execution_id=execution_id,
        )
        jarvis_runtime.transition(
            execution_id, ExecutionState.RUNNING, worker_id=_WORKER_ID,
        )

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(15)
                if not jarvis_runtime.heartbeat(
                    execution_id, worker_id=_WORKER_ID,
                ):
                    return

        heartbeat_task = asyncio.create_task(heartbeat())
        from jarvis_brain import (
            BrainOrchestrator,
            PlanValidator,
            TaskBudget,
            build_brain_adapter,
        )
        from research_engine.capability_tools import build_capability_registry
        from research_engine.tool_registry import resolve_permissions

        command = _commands().get(command_id)
        if command is None:
            return
        registry = build_capability_registry()
        cancel_token = _cancel_tokens[command_id]
        authorization_event = _authorization_events[command_id]

        async def approval_gate(request: dict[str, Any], _autonomy: str) -> bool:
            store = get_store("commands")
            current = store.load()[command_id]
            current["status"] = "AWAITING_AUTHORIZATION"
            current["authorization"] = {
                "required": True,
                "capabilities": list(request.get("capabilities", [])),
                "requested_at": time.time(),
                "approved": None,
            }
            store.save()
            _advance_execution(command_id, ExecutionState.WAITING)
            _append_event(
                command_id,
                "capability_authorization_required",
                capabilities=list(request.get("capabilities", [])),
            )
            try:
                await asyncio.wait_for(authorization_event.wait(), timeout=300)
            except asyncio.TimeoutError:
                _append_event(command_id, "authorization_timed_out")
                return False
            if cancel_token.is_set():
                return False
            authorization = _commands()[command_id].get("authorization") or {}
            return authorization.get("approved") is True

        user_id = _owner_id(user)
        permissions = resolve_permissions(user_id, principal=user)
        orchestrator = BrainOrchestrator(
            build_brain_adapter(),
            registry,
            PlanValidator(registry),
            budget=TaskBudget(max_execution_time=300, max_cost=1.0),
            conversation_id=command.get("conversation_id"),
            user_id=user_id,
            permissions=permissions,
            principal=user,
            approval_gate=approval_gate,
            cancel_token=cancel_token,
            audit_callback=_audit_callback(command_id),
        )
        _append_event(command_id, "command_understood")
        async with _execution_slots:
            result = await asyncio.wait_for(
                orchestrator.run(
                    command["goal"],
                    autonomy=autonomy,
                    task_id=command_id,
                ),
                timeout=300,
            )
        store = get_store("commands")
        current = store.load()[command_id]
        verified = (
            result.status == "COMPLETED"
            and bool(result.completion_condition_met)
            and result.confidence_state.value == "SUFFICIENT_INFORMATION"
        )
        current["result"] = {
            "status": result.status,
            "summary": _safe_value(result.summary),
            "evidence": _safe_value(result.evidence),
            "confidence_state": result.confidence_state.value,
            "completion_condition_met": result.completion_condition_met,
            "cost": result.cost,
        }
        current["errors"] = (
            [_safe_value(result.summary)]
            if not verified and result.summary
            else []
        )
        terminal_status = {
            "COMPLETED": "COMPLETED" if verified else "PARTIAL",
            "CANCELLED": "CANCELLED",
            "FAILED": "FAILED",
            "BUDGET_EXCEEDED": "FAILED",
        }.get(result.status, "PARTIAL")
        execution = jarvis_runtime.get_execution(execution_id) if execution_id else None
        execution_state = (
            ExecutionState(execution["status"]) if execution else None
        )
        reconciliation_error = None
        if (
            execution_state == ExecutionState.CANCEL_REQUESTED
            and terminal_status != "CANCELLED"
        ):
            terminal_status = "RECOVERY_REQUIRED"
            reconciliation_error = (
                "Cancellation was requested, but the operation returned without "
                "confirming cancellation; reconcile possible side effects."
            )
        elif (
            terminal_status == "CANCELLED"
            and execution_state != ExecutionState.CANCEL_REQUESTED
        ):
            terminal_status = "RECOVERY_REQUIRED"
            reconciliation_error = (
                "The orchestrator reported cancellation without a persisted "
                "cancellation request; reconcile execution state."
            )
        current["status"] = terminal_status
        if reconciliation_error:
            current.setdefault("errors", []).append(reconciliation_error)
        current["completed_at"] = time.time()
        store.save()
        if execution_id:
            state = execution_state
            if state == ExecutionState.CANCEL_REQUESTED and terminal_status == "CANCELLED":
                jarvis_runtime.transition(
                    execution_id,
                    ExecutionState.CANCELLED,
                    worker_id=_WORKER_ID,
                    result=_safe_value(current["result"]),
                )
            else:
                if (
                    terminal_status == "RECOVERY_REQUIRED"
                    and state
                    and jarvis_runtime.can_transition(
                        state, ExecutionState.RECOVERY_REQUIRED,
                    )
                ):
                    jarvis_runtime.transition(
                        execution_id,
                        ExecutionState.RECOVERY_REQUIRED,
                        worker_id=_WORKER_ID,
                        result=_safe_value(current["result"]),
                        error=reconciliation_error,
                    )
                    state = ExecutionState.RECOVERY_REQUIRED
                if state and state != ExecutionState.VERIFYING and jarvis_runtime.can_transition(
                    state, ExecutionState.VERIFYING,
                ):
                    jarvis_runtime.transition(
                        execution_id, ExecutionState.VERIFYING, worker_id=_WORKER_ID,
                    )
                    state = ExecutionState.VERIFYING
                end_state = (
                    ExecutionState.SUCCEEDED
                    if terminal_status == "COMPLETED"
                    else ExecutionState.CANCELLED
                    if terminal_status == "CANCELLED"
                    else ExecutionState.RECOVERY_REQUIRED
                    if terminal_status == "RECOVERY_REQUIRED"
                    else ExecutionState.FAILED
                )
                if state and jarvis_runtime.can_transition(state, end_state):
                    jarvis_runtime.transition(
                        execution_id,
                        end_state,
                        worker_id=_WORKER_ID,
                        result=_safe_value(current["result"]),
                        error=None if verified else _safe_value(result.summary),
                    )
        completion_event = {
            "COMPLETED": "command_completed",
            "RECOVERY_REQUIRED": "execution_recovery_required",
            "CANCELLED": "command_cancelled",
        }.get(terminal_status, "command_failed")
        _append_event(
            command_id,
            completion_event,
            status=terminal_status,
            execution_id=execution_id,
        )
    except asyncio.CancelledError:
        _set_status(command_id, "RECOVERY_REQUIRED")
        if execution_id:
            current_execution = jarvis_runtime.get_execution(execution_id)
            if current_execution and jarvis_runtime.can_transition(
                current_execution["status"], ExecutionState.RECOVERY_REQUIRED,
            ):
                jarvis_runtime.transition(
                    execution_id,
                    ExecutionState.RECOVERY_REQUIRED,
                    error="Worker task was interrupted; reconciliation is required.",
                )
        _append_event(command_id, "execution_recovery_required")
    except asyncio.TimeoutError:
        message = (
            "Command exceeded its execution timeout; external side effects "
            "could not be verified and require reconciliation."
        )
        cancel_token = _cancel_tokens.get(command_id)
        if cancel_token is not None:
            cancel_token.set()
        _set_status(command_id, "RECOVERY_REQUIRED")
        if execution_id:
            current_execution = jarvis_runtime.get_execution(execution_id)
            if current_execution and jarvis_runtime.can_transition(
                current_execution["status"], ExecutionState.RECOVERY_REQUIRED,
            ):
                jarvis_runtime.transition(
                    execution_id,
                    ExecutionState.RECOVERY_REQUIRED,
                    error=message,
                )
        _append_event(
            command_id,
            "execution_timeout_recovery_required",
            error=message,
            execution_id=execution_id,
        )
    except Exception as exc:
        failure_message = _safe_value(f"{type(exc).__name__}: {exc}")
        failed_execution = (
            jarvis_runtime.get_execution(execution_id) if execution_id else None
        )
        cancellation_uncertain = bool(
            failed_execution
            and failed_execution["status"] == ExecutionState.CANCEL_REQUESTED.value
        )
        command_status = (
            "RECOVERY_REQUIRED" if cancellation_uncertain else "FAILED"
        )
        if cancellation_uncertain:
            failure_message = (
                "Execution errored after cancellation was requested; "
                "reconciliation is required to determine side effects."
            )
        _set_status(command_id, command_status)
        if execution_id:
            current_execution = failed_execution or jarvis_runtime.get_execution(execution_id)
            target_state = (
                ExecutionState.RECOVERY_REQUIRED
                if cancellation_uncertain else ExecutionState.FAILED
            )
            if current_execution and jarvis_runtime.can_transition(
                current_execution["status"], target_state,
            ):
                jarvis_runtime.transition(
                    execution_id,
                    target_state,
                    error=failure_message,
                )
        _append_event(
            command_id,
            (
                "execution_recovery_required"
                if cancellation_uncertain else "command_failed"
            ),
            error=failure_message,
            execution_id=execution_id,
        )
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
        _command_jobs.pop(command_id, None)
        _cancel_tokens.pop(command_id, None)
        _authorization_events.pop(command_id, None)


async def _create_command(body: CommandCreate, user: dict[str, Any]) -> dict[str, Any]:
    goal = scrub_secrets(body.goal.strip())[0]
    if not goal:
        raise HTTPException(status_code=400, detail="goal must not be blank")
    owner_id = _owner_id(user)
    idempotency_key = (
        hashlib.sha256(f"{owner_id}:{body.request_id}".encode("utf-8")).hexdigest()
        if body.request_id else None
    )
    existing = next(
        (
            item for item in _commands().values()
            if body.request_id
            and item.get("request_id") == body.request_id
            and item.get("user_id") == owner_id
        ),
        None,
    )
    if existing is not None:
        return copy.deepcopy(existing)
    durable_existing = (
        jarvis_runtime.get_execution_by_idempotency_key(idempotency_key)
        if idempotency_key else None
    )
    if durable_existing is not None:
        existing_command = _commands().get(durable_existing["command_id"])
        if existing_command and existing_command.get("user_id") == owner_id:
            return copy.deepcopy(existing_command)
        raise HTTPException(
            status_code=409,
            detail="This idempotency key is already associated with a command.",
        )
    command_id = str(uuid.uuid4())
    now = time.time()
    command = {
        "command_id": command_id,
        "conversation_id": body.conversation_id,
        "request_id": body.request_id,
        "user_id": _owner_id(user),
        "goal": goal,
        "status": "RECEIVED",
        "autonomy": body.autonomy,
        "plan_id": str(uuid.uuid4()),
        "plan_ids": [],
        "priority": "normal",
        "plan": [],
        "active_step": None,
        "capabilities": [],
        "agents": [],
        "models": [],
        "permissions": [],
        "authorization": None,
        "started_at": None,
        "created_at": now,
        "completed_at": None,
        "result": None,
        "execution_ids": [],
        "active_execution_id": None,
        "errors": [],
        "events": [],
    }
    store = get_store("commands")
    store.load()[command_id] = command
    store.save()
    try:
        execution = jarvis_runtime.create_execution(
            command_id=command_id,
            user_id=owner_id,
            plan_id=command["plan_id"],
            idempotency_key=idempotency_key,
        )
    except Exception:
        store.load().pop(command_id, None)
        store.save()
        raise
    command["execution_ids"] = [execution["execution_id"]]
    command["active_execution_id"] = execution["execution_id"]
    command["status"] = "RECEIVED"
    store.save()
    _append_event(command_id, "command_received")
    _schedule_command(command_id, user, body.autonomy)
    return copy.deepcopy(command)


@router.post("", status_code=202)
async def create_command(
    body: CommandCreate,
    user: dict[str, Any] = Depends(get_current_user),
):
    return await _create_command(body, user)


@router.get("")
async def list_commands(
    limit: int = Query(default=50, ge=1, le=100),
    user: dict[str, Any] = Depends(get_current_user),
):
    owner_id = _owner_id(user)
    commands = [
        item for item in _commands().values()
        if item.get("user_id") == owner_id
    ]
    commands.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return {"commands": [copy.deepcopy(item) for item in commands[:limit]]}


@router.get("/capabilities")
async def list_command_capabilities(
    user: dict[str, Any] = Depends(get_current_user),
):
    del user
    from research_engine.capability_contract import build_contracts
    from research_engine.capability_tools import build_capability_registry

    contracts = build_contracts(build_capability_registry())
    return {
        "capabilities": [
            {
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "domain": item["domain"],
                "availability": item["availability"],
                "availability_reason": item["availability_reason"],
                "risk_level": item["risk_level"],
                "authentication_required": item["authentication_required"],
            }
            for item in contracts.values()
        ]
    }


@router.get("/{command_id}")
async def get_command(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    return copy.deepcopy(_owned_command(command_id, user))


@router.get("/{command_id}/events")
async def get_command_events(
    command_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict[str, Any] = Depends(get_current_user),
):
    _owned_command(command_id, user)
    events = jarvis_runtime.replay_events(
        command_id, after_sequence=after_sequence, limit=limit,
    )
    return {
        "command_id": command_id,
        "after_sequence": after_sequence,
        "events": events,
        "next_sequence": events[-1]["sequence"] if events else after_sequence,
    }


@router.get("/{command_id}/executions")
async def get_command_executions(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _owned_command(command_id, user)
    records = [
        jarvis_runtime.get_execution(execution_id)
        for execution_id in command.get("execution_ids", [])
    ]
    return {"command_id": command_id, "executions": [r for r in records if r]}


@router.get("/{command_id}/plans")
async def get_command_plans(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _owned_command(command_id, user)
    plans = [
        jarvis_runtime.get_plan(plan_id)
        for plan_id in command.get("plan_ids", [])
    ]
    return {"command_id": command_id, "plans": [plan for plan in plans if plan]}


@router.post("/{command_id}/authorization")
async def authorize_command(
    command_id: str,
    body: CommandAuthorization,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _owned_command(command_id, user)
    if command.get("status") != "AWAITING_AUTHORIZATION":
        raise HTTPException(status_code=409, detail="Command is not awaiting authorization")
    authorization = command.get("authorization") or {}
    if authorization.get("approved") is not None:
        raise HTTPException(status_code=409, detail="Authorization was already decided")
    authorization["approved"] = body.approved
    authorization["decided_at"] = time.time()
    command["authorization"] = authorization
    get_store("commands").save()
    _append_event(
        command_id,
        "authorization_granted" if body.approved else "authorization_denied",
        capabilities=authorization.get("capabilities", []),
    )
    gate = _authorization_events.get(command_id)
    if gate is not None:
        gate.set()
    return copy.deepcopy(command)


@router.post("/{command_id}/cancel")
async def cancel_command(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _owned_command(command_id, user)
    if command.get("status") in {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Command is already terminal")
    execution_id = command.get("active_execution_id")
    execution = jarvis_runtime.get_execution(execution_id) if execution_id else None
    if execution is None:
        raise HTTPException(status_code=409, detail="Command has no active execution record")
    cancel_token = _cancel_tokens.get(command_id)
    if execution["status"] in {
        ExecutionState.QUEUED.value, ExecutionState.PAUSED.value,
    }:
        jarvis_runtime.transition(execution_id, ExecutionState.CANCELLED)
        _set_status(command_id, "CANCELLED")
    elif execution["status"] in ACTIVE_EXECUTION_STATES:
        if cancel_token is None:
            raise HTTPException(
                status_code=409,
                detail="Execution is not attached to a live worker; recovery is required.",
            )
        if execution["status"] != ExecutionState.CANCEL_REQUESTED.value:
            jarvis_runtime.transition(
                execution_id, ExecutionState.CANCEL_REQUESTED,
                worker_id=_WORKER_ID,
            )
        cancel_token.set()
    else:
        raise HTTPException(status_code=409, detail="Execution cannot be cancelled")
    authorization_event = _authorization_events.get(command_id)
    if authorization_event is not None:
        authorization_event.set()
    _append_event(
        command_id, "command_cancel_requested",
        execution_id=execution_id,
    )
    return {
        "command_id": command_id,
        "status": command.get("status"),
        "cancel_requested": execution["status"] not in {
            ExecutionState.QUEUED.value, ExecutionState.PAUSED.value,
        },
    }


@router.post("/{command_id}/pause")
async def pause_command(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _owned_command(command_id, user)
    execution_id = command.get("active_execution_id")
    execution = jarvis_runtime.get_execution(execution_id) if execution_id else None
    if not execution or execution["status"] != ExecutionState.QUEUED.value:
        raise HTTPException(
            status_code=409,
            detail="Pause is supported only before a worker claims the execution.",
        )
    jarvis_runtime.transition(execution_id, ExecutionState.PAUSED)
    command["status"] = "PAUSED"
    get_store("commands").save()
    _append_event(command_id, "command_paused", execution_id=execution_id)
    return {"command_id": command_id, "status": "PAUSED"}


@router.post("/{command_id}/resume")
async def resume_command(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _owned_command(command_id, user)
    execution_id = command.get("active_execution_id")
    execution = jarvis_runtime.get_execution(execution_id) if execution_id else None
    if not execution or execution["status"] != ExecutionState.PAUSED.value:
        raise HTTPException(status_code=409, detail="Command is not safely paused")
    jarvis_runtime.transition(execution_id, ExecutionState.QUEUED)
    command["status"] = "RECEIVED"
    get_store("commands").save()
    _append_event(command_id, "command_resumed", execution_id=execution_id)
    _schedule_command(command_id, user, command.get("autonomy", "SUPERVISED"))
    return {"command_id": command_id, "status": "RECEIVED"}


@router.post("/{command_id}/retry")
async def retry_command(
    command_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    command = _owned_command(command_id, user)
    execution_id = command.get("active_execution_id")
    execution = jarvis_runtime.get_execution(execution_id) if execution_id else None
    if (
        command.get("status") != "FAILED"
        or not execution
        or execution["status"] != ExecutionState.FAILED.value
        or execution["started_at"] is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="Retry is allowed only when execution failed before work started.",
        )
    jarvis_runtime.transition(execution_id, ExecutionState.RETRYING)
    jarvis_runtime.transition(execution_id, ExecutionState.QUEUED)
    command["status"] = "RECEIVED"
    command["completed_at"] = None
    command["errors"] = []
    get_store("commands").save()
    _append_event(
        command_id, "command_retry_queued",
        execution_id=execution_id,
        attempt=jarvis_runtime.get_execution(execution_id)["attempt"],
    )
    _schedule_command(command_id, user, command.get("autonomy", "SUPERVISED"))
    return {"command_id": command_id, "execution_id": execution_id, "status": "QUEUED"}
