"""Durable command execution state shared by the JARVIS API and workers.

The command orchestrator and provider gateway remain the existing owners of
planning and execution. This module owns their durable execution records,
leases, validated state transitions, and replayable runtime events.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import (
    ensure_schema,
    get_engine,
    presentation_revisions,
    runtime_event_sequences,
    runtime_events,
    runtime_executions,
    runtime_plan_steps,
    runtime_plans,
)


class ExecutionState(StrEnum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


ACTIVE_STATES = {
    ExecutionState.CLAIMED.value,
    ExecutionState.STARTING.value,
    ExecutionState.RUNNING.value,
    ExecutionState.WAITING.value,
    ExecutionState.VERIFYING.value,
    ExecutionState.CANCEL_REQUESTED.value,
    ExecutionState.RECOVERING.value,
}
TERMINAL_STATES = {
    ExecutionState.SUCCEEDED.value,
    ExecutionState.FAILED.value,
    ExecutionState.CANCELLED.value,
    ExecutionState.RECOVERY_REQUIRED.value,
}

_TRANSITIONS = {
    ExecutionState.QUEUED: {
        ExecutionState.CLAIMED, ExecutionState.PAUSED, ExecutionState.CANCELLED,
        ExecutionState.FAILED,
    },
    ExecutionState.CLAIMED: {
        ExecutionState.STARTING, ExecutionState.QUEUED, ExecutionState.FAILED,
        ExecutionState.RECOVERY_REQUIRED, ExecutionState.CANCEL_REQUESTED,
    },
    ExecutionState.STARTING: {
        ExecutionState.RUNNING, ExecutionState.FAILED,
        ExecutionState.RECOVERY_REQUIRED, ExecutionState.CANCEL_REQUESTED,
    },
    ExecutionState.RUNNING: {
        ExecutionState.WAITING, ExecutionState.VERIFYING, ExecutionState.FAILED,
        ExecutionState.CANCEL_REQUESTED, ExecutionState.RECOVERING,
        ExecutionState.RECOVERY_REQUIRED,
    },
    ExecutionState.WAITING: {
        ExecutionState.RUNNING, ExecutionState.FAILED,
        ExecutionState.CANCEL_REQUESTED, ExecutionState.RECOVERY_REQUIRED,
    },
    ExecutionState.VERIFYING: {
        ExecutionState.SUCCEEDED, ExecutionState.FAILED,
        ExecutionState.RECOVERING, ExecutionState.CANCEL_REQUESTED,
        ExecutionState.RECOVERY_REQUIRED,
    },
    ExecutionState.FAILED: {
        ExecutionState.RETRYING, ExecutionState.RECOVERY_REQUIRED,
    },
    ExecutionState.RETRYING: {ExecutionState.QUEUED, ExecutionState.FAILED},
    ExecutionState.CANCEL_REQUESTED: {
        ExecutionState.CANCELLED, ExecutionState.FAILED,
        ExecutionState.RECOVERY_REQUIRED,
    },
    ExecutionState.PAUSED: {ExecutionState.QUEUED, ExecutionState.CANCELLED},
    ExecutionState.RECOVERING: {
        ExecutionState.QUEUED, ExecutionState.RUNNING, ExecutionState.FAILED,
        ExecutionState.RECOVERY_REQUIRED,
    },
    ExecutionState.RECOVERY_REQUIRED: {ExecutionState.RECOVERING, ExecutionState.FAILED},
    ExecutionState.SUCCEEDED: set(),
    ExecutionState.CANCELLED: set(),
}

_PLAN_TRANSITIONS = {
    "PROPOSED": {
        "VALIDATED", "WAITING_AUTHORIZATION", "REJECTED", "BLOCKED", "FAILED",
    },
    "VALIDATED": {
        "WAITING_AUTHORIZATION", "EXECUTING", "REJECTED", "BLOCKED", "FAILED",
    },
    "WAITING_AUTHORIZATION": {
        "EXECUTING", "REJECTED", "CANCELLED", "FAILED",
    },
    "EXECUTING": {
        "REPLANNED", "COMPLETED", "PARTIAL", "FAILED", "CANCELLED",
    },
    "REPLANNED": set(),
    "COMPLETED": set(),
    "PARTIAL": set(),
    "FAILED": set(),
    "REJECTED": set(),
    "BLOCKED": set(),
    "CANCELLED": set(),
}
_PLAN_STEP_TRANSITIONS = {
    "PENDING": {"RUNNING", "SKIPPED", "FAILED"},
    "RUNNING": {"SUCCEEDED", "FAILED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "SKIPPED": set(),
}


class InvalidExecutionTransitionError(ValueError):
    pass


class InvalidPlanTransitionError(ValueError):
    pass


class InvalidPlanStepTransitionError(ValueError):
    pass


class PresentationRevisionConflictError(ValueError):
    pass


class JarvisRuntime:
    """Authoritative persistence boundary for execution lifecycle state."""

    @staticmethod
    def can_transition(current: str | ExecutionState, target: ExecutionState) -> bool:
        state = current if isinstance(current, ExecutionState) else ExecutionState(current)
        return target in _TRANSITIONS[state]

    def create_execution(
        self,
        *,
        command_id: str,
        user_id: str,
        plan_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        ensure_schema()
        now = time.time()
        execution_id = str(uuid.uuid4())
        values = {
            "execution_id": execution_id,
            "command_id": command_id,
            "user_id": user_id,
            "plan_id": plan_id,
            "step_id": None,
            "attempt": 1,
            "worker_id": None,
            "status": ExecutionState.QUEUED.value,
            "idempotency_key": idempotency_key,
            "lease_started": None,
            "lease_expires": None,
            "heartbeat_at": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "metadata": "{}",
        }
        with get_engine().begin() as connection:
            connection.execute(insert(runtime_executions).values(**values))
        return values

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        ensure_schema()
        with get_engine().connect() as connection:
            row = connection.execute(
                select(runtime_executions).where(
                    runtime_executions.c.execution_id == execution_id
                )
            ).mappings().first()
        return self._decode_execution(dict(row)) if row else None

    def create_presentation_revision(
        self,
        *,
        task_id: str,
        owner_id: str,
        request_id: str,
        presentation: dict[str, Any],
        expected_revision: int,
        idempotency_key: str,
        conversation_id: str | None = None,
        command_id: str | None = None,
        execution_id: str | None = None,
        endpoint_id: str | None = None,
        compatibility: dict[str, Any] | None = None,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        """Persist one owner-bound, idempotent presentation revision."""
        ensure_schema()
        if not task_id or not owner_id or not request_id:
            raise ValueError("task_id, owner_id, and request_id are required")
        if not idempotency_key or len(idempotency_key) > 255:
            raise ValueError("a valid idempotency_key is required")
        if not isinstance(presentation, dict):
            raise ValueError("presentation must be an object")
        contract_version = presentation.get("contract_version")
        if contract_version not in {"1.0", "1.1"}:
            raise ValueError("unsupported presentation contract version")
        now = time.time()
        revision_id = str(uuid.uuid4())
        created = None
        try:
            with get_engine().begin() as connection:
                repeated = connection.execute(
                    select(presentation_revisions).where(
                        presentation_revisions.c.idempotency_key
                        == idempotency_key
                    )
                ).mappings().first()
                if repeated:
                    if repeated["owner_id"] != owner_id or repeated["task_id"] != task_id:
                        raise PermissionError("idempotency key belongs to another task")
                    return self._decode_presentation_revision(repeated)

                task_rows = connection.execute(
                    select(
                        presentation_revisions.c.owner_id,
                        presentation_revisions.c.revision,
                    ).where(presentation_revisions.c.task_id == task_id)
                ).all()
                if any(row.owner_id != owner_id for row in task_rows):
                    raise PermissionError("task does not belong to the authenticated owner")
                current_revision = max(
                    (row.revision for row in task_rows),
                    default=0,
                )
                if current_revision != expected_revision:
                    raise PresentationRevisionConflictError(
                        f"expected revision {expected_revision}, found {current_revision}"
                    )
                values = {
                    "revision_id": revision_id,
                    "task_id": task_id,
                    "revision": current_revision + 1,
                    "owner_id": owner_id,
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "command_id": command_id,
                    "execution_id": execution_id,
                    "endpoint_id": endpoint_id,
                    "contract_version": contract_version,
                    "presentation": json.dumps(
                        presentation, ensure_ascii=False, default=str,
                    ),
                    "compatibility": json.dumps(
                        compatibility or {}, ensure_ascii=False, default=str,
                    ),
                    "fallback_reason": fallback_reason,
                    "idempotency_key": idempotency_key,
                    "created_at": now,
                }
                connection.execute(
                    insert(presentation_revisions).values(**values)
                )
                created = {
                    **values,
                    "presentation": presentation,
                    "compatibility": compatibility or {},
                }
                if command_id:
                    self._append_event_in_transaction(
                        connection,
                        command_id=command_id,
                        event_type="presentation.revision.created",
                        payload={
                            "task_id": task_id,
                            "revision_id": revision_id,
                            "revision": current_revision + 1,
                            "endpoint_id": endpoint_id,
                            "contract_version": contract_version,
                            "fallback_reason": fallback_reason,
                        },
                        execution_id=execution_id,
                    )
        except IntegrityError as exc:
            raise PresentationRevisionConflictError(
                "presentation revision changed concurrently; reload and retry"
            ) from exc

        return created

    def get_presentation_revision(
        self, revision_id: str, *, owner_id: str,
    ) -> dict[str, Any] | None:
        ensure_schema()
        with get_engine().connect() as connection:
            row = connection.execute(
                select(presentation_revisions).where(
                    presentation_revisions.c.revision_id == revision_id,
                    presentation_revisions.c.owner_id == owner_id,
                )
            ).mappings().first()
        return self._decode_presentation_revision(row) if row else None

    def list_presentation_revisions(
        self, task_id: str, *, owner_id: str,
    ) -> list[dict[str, Any]]:
        ensure_schema()
        with get_engine().connect() as connection:
            rows = connection.execute(
                select(presentation_revisions)
                .where(
                    presentation_revisions.c.task_id == task_id,
                    presentation_revisions.c.owner_id == owner_id,
                )
                .order_by(presentation_revisions.c.revision)
            ).mappings()
            return [self._decode_presentation_revision(row) for row in rows]

    @staticmethod
    def _decode_presentation_revision(row: Any) -> dict[str, Any]:
        revision = dict(row)
        revision["presentation"] = json.loads(revision["presentation"])
        revision["compatibility"] = json.loads(revision["compatibility"])
        return revision

    def get_execution_by_idempotency_key(
        self, idempotency_key: str,
    ) -> dict[str, Any] | None:
        ensure_schema()
        with get_engine().connect() as connection:
            row = connection.execute(
                select(runtime_executions).where(
                    runtime_executions.c.idempotency_key == idempotency_key
                )
            ).mappings().first()
        return self._decode_execution(dict(row)) if row else None

    def create_plan(
        self,
        *,
        plan_id: str,
        command_id: str,
        user_id: str,
        objective: str,
        steps: list[dict[str, Any]],
        required_permissions: list[str] | None = None,
        estimated_complexity: str = "unknown",
    ) -> dict[str, Any]:
        """Persist the validated planner's structured proposal and its steps."""
        ensure_schema()
        now = time.time()
        plan_values = {
            "plan_id": plan_id,
            "command_id": command_id,
            "user_id": user_id,
            "objective": objective,
            "required_capabilities": json.dumps(
                sorted({
                    str(step.get("capability"))
                    for step in steps
                    if step.get("capability")
                })
            ),
            "required_permissions": json.dumps(required_permissions),
            "estimated_complexity": estimated_complexity,
            "status": "PROPOSED",
            "created_at": now,
            "updated_at": now,
        }
        step_values = []
        for step in steps:
            capability = str(step.get("capability") or "")
            step_id = str(step.get("step_id") or capability)
            if not step_id or not capability:
                continue
            step_values.append({
                "plan_id": plan_id,
                "step_id": step_id,
                "objective": str(step.get("summary") or capability),
                "capability": capability,
                "input": json.dumps(step.get("input") or {}, ensure_ascii=False, default=str),
                "dependencies": json.dumps(
                    step.get("depends_on") or [], ensure_ascii=False,
                ),
                "timeout": step.get("timeout"),
                "retry_policy": json.dumps(
                    step.get("retry_policy") or {}, ensure_ascii=False,
                ),
                "authorization": json.dumps(
                    step.get("authorization") or {}, ensure_ascii=False,
                ),
                "verification": json.dumps(
                    step.get("verification") or {}, ensure_ascii=False,
                ),
                "status": "PENDING",
                "result": None,
            })

        with get_engine().begin() as connection:
            current = connection.execute(
                select(runtime_plans.c.plan_id).where(
                    runtime_plans.c.plan_id == plan_id
                )
            ).first()
            if current:
                plan_values.pop("created_at")
                connection.execute(
                    update(runtime_plans)
                    .where(runtime_plans.c.plan_id == plan_id)
                    .values(**plan_values)
                )
                connection.execute(
                    delete(runtime_plan_steps).where(
                        runtime_plan_steps.c.plan_id == plan_id
                    )
                )
            else:
                connection.execute(insert(runtime_plans).values(**plan_values))
            if step_values:
                connection.execute(insert(runtime_plan_steps), step_values)
            connection.execute(
                update(runtime_executions)
                .where(
                    runtime_executions.c.command_id == command_id,
                    runtime_executions.c.status.in_(
                        ACTIVE_STATES | {
                            ExecutionState.QUEUED.value,
                            ExecutionState.PAUSED.value,
                        }
                    ),
                )
                .values(plan_id=plan_id)
            )
        return self.get_plan(plan_id) or {}

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        ensure_schema()
        with get_engine().connect() as connection:
            plan_row = connection.execute(
                select(runtime_plans).where(runtime_plans.c.plan_id == plan_id)
            ).mappings().first()
            if plan_row is None:
                return None
            steps = connection.execute(
                select(runtime_plan_steps)
                .where(runtime_plan_steps.c.plan_id == plan_id)
                .order_by(runtime_plan_steps.c.step_id)
            ).mappings()
            plan = dict(plan_row)
            for field in ("required_capabilities", "required_permissions"):
                plan[field] = json.loads(plan[field])
            plan["steps"] = []
            for row in steps:
                step = dict(row)
                for field in (
                    "input", "dependencies", "retry_policy", "authorization",
                    "verification",
                ):
                    step[field] = json.loads(step[field])
                if step["result"] is not None:
                    step["result"] = json.loads(step["result"])
                plan["steps"].append(step)
            return plan

    def update_plan_status(self, plan_id: str, status: str) -> bool:
        ensure_schema()
        with get_engine().begin() as connection:
            current = connection.execute(
                select(runtime_plans.c.status).where(
                    runtime_plans.c.plan_id == plan_id
                )
            ).scalar_one_or_none()
            if current is None:
                return False
            if current != status and status not in _PLAN_TRANSITIONS.get(current, set()):
                raise InvalidPlanTransitionError(
                    f"Plan transition {current} -> {status} is not allowed"
                )
            changed = connection.execute(
                update(runtime_plans)
                .where(runtime_plans.c.plan_id == plan_id)
                .values(status=status, updated_at=time.time())
            )
        return changed.rowcount == 1

    def update_plan_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        status: str,
        result: Any = None,
    ) -> bool:
        ensure_schema()
        values: dict[str, Any] = {"status": status}
        if result is not None:
            values["result"] = json.dumps(result, ensure_ascii=False, default=str)
        with get_engine().begin() as connection:
            current = connection.execute(
                select(runtime_plan_steps.c.status).where(
                    runtime_plan_steps.c.plan_id == plan_id,
                    runtime_plan_steps.c.step_id == step_id,
                )
            ).scalar_one_or_none()
            if current is None:
                return False
            if current != status and status not in _PLAN_STEP_TRANSITIONS.get(current, set()):
                raise InvalidPlanStepTransitionError(
                    f"Plan step transition {current} -> {status} is not allowed"
                )
            changed = connection.execute(
                update(runtime_plan_steps)
                .where(
                    runtime_plan_steps.c.plan_id == plan_id,
                    runtime_plan_steps.c.step_id == step_id,
                )
                .values(**values)
            )
        return changed.rowcount == 1

    def list_executions(
        self, *, user_id: str | None = None, statuses: set[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        ensure_schema()
        query = select(runtime_executions).order_by(
            runtime_executions.c.created_at.desc()
        ).limit(limit)
        if user_id is not None:
            query = query.where(runtime_executions.c.user_id == user_id)
        if statuses:
            query = query.where(runtime_executions.c.status.in_(statuses))
        with get_engine().connect() as connection:
            return [
                self._decode_execution(dict(row))
                for row in connection.execute(query).mappings()
            ]

    @staticmethod
    def _decode_execution(record: dict[str, Any]) -> dict[str, Any]:
        for name in ("result", "metadata"):
            if record.get(name) is not None:
                record[name] = json.loads(record[name])
        return record

    def claim_execution(
        self, execution_id: str, *, worker_id: str, lease_seconds: float = 60.0,
    ) -> bool:
        ensure_schema()
        now = time.time()
        with get_engine().begin() as connection:
            result = connection.execute(
                update(runtime_executions)
                .where(
                    runtime_executions.c.execution_id == execution_id,
                    runtime_executions.c.status == ExecutionState.QUEUED.value,
                )
                .values(
                    status=ExecutionState.CLAIMED.value,
                    worker_id=worker_id,
                    lease_started=now,
                    lease_expires=now + lease_seconds,
                    heartbeat_at=now,
                )
            )
        return result.rowcount == 1

    def transition(
        self,
        execution_id: str,
        state: ExecutionState,
        *,
        worker_id: str | None = None,
        lease_seconds: float = 60.0,
        result: Any = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ensure_schema()
        current = self.get_execution(execution_id)
        if current is None:
            raise KeyError(f"Unknown execution {execution_id}")
        previous = ExecutionState(current["status"])
        if state not in _TRANSITIONS[previous]:
            raise InvalidExecutionTransitionError(
                f"Execution transition {previous.value} -> {state.value} is not allowed"
            )

        now = time.time()
        values: dict[str, Any] = {"status": state.value}
        if worker_id is not None:
            values["worker_id"] = worker_id
        if state == ExecutionState.STARTING and current["started_at"] is None:
            values["started_at"] = now
        if state in TERMINAL_STATES:
            values["completed_at"] = now
        if state == ExecutionState.RETRYING:
            values["attempt"] = current["attempt"] + 1
        if state == ExecutionState.QUEUED and previous == ExecutionState.RETRYING:
            values.update(
                worker_id=None,
                lease_started=None,
                lease_expires=None,
                heartbeat_at=None,
                error=None,
                completed_at=None,
            )
        if state in ACTIVE_STATES:
            values.update(
                heartbeat_at=now,
                lease_expires=now + lease_seconds,
            )
        if result is not None:
            values["result"] = json.dumps(result, ensure_ascii=False, default=str)
        if error is not None:
            values["error"] = error
        if metadata is not None:
            values["metadata"] = json.dumps(metadata, ensure_ascii=False, default=str)

        with get_engine().begin() as connection:
            changed = connection.execute(
                update(runtime_executions)
                .where(
                    runtime_executions.c.execution_id == execution_id,
                    runtime_executions.c.status == previous.value,
                )
                .values(**values)
            )
            if changed.rowcount != 1:
                raise InvalidExecutionTransitionError(
                    "Execution state changed concurrently; transition was not applied"
                )
        return self.get_execution(execution_id) or {}

    def heartbeat(
        self, execution_id: str, *, worker_id: str, lease_seconds: float = 60.0,
    ) -> bool:
        ensure_schema()
        now = time.time()
        with get_engine().begin() as connection:
            result = connection.execute(
                update(runtime_executions)
                .where(
                    runtime_executions.c.execution_id == execution_id,
                    runtime_executions.c.worker_id == worker_id,
                    runtime_executions.c.status.in_(ACTIVE_STATES),
                )
                .values(heartbeat_at=now, lease_expires=now + lease_seconds)
            )
        return result.rowcount == 1

    def recover_expired(self, *, now: float | None = None) -> list[dict[str, Any]]:
        """Classify stale leases without retrying potentially destructive work."""
        ensure_schema()
        now = now or time.time()
        with get_engine().begin() as connection:
            stale = [
                dict(row) for row in connection.execute(
                    select(runtime_executions).where(
                        runtime_executions.c.status.in_(ACTIVE_STATES),
                        runtime_executions.c.lease_expires < now,
                    )
                ).mappings()
            ]
            for record in stale:
                state = (
                    ExecutionState.QUEUED
                    if record["status"] == ExecutionState.CLAIMED.value
                    and record["started_at"] is None
                    else ExecutionState.RECOVERY_REQUIRED
                )
                values = {
                    "status": state.value,
                    "worker_id": None,
                    "lease_started": None,
                    "lease_expires": None,
                    "heartbeat_at": now,
                    "error": (
                        "Worker lease expired before execution began; safe to requeue."
                        if state == ExecutionState.QUEUED else
                        "Worker lease expired after execution may have started; reconciliation required."
                    ),
                }
                changed = connection.execute(
                    update(runtime_executions)
                    .where(
                        runtime_executions.c.execution_id == record["execution_id"],
                        runtime_executions.c.status == record["status"],
                        runtime_executions.c.lease_expires < now,
                    )
                    .values(**values)
                )
                if changed.rowcount == 1:
                    record.update(values)
                else:
                    record["recovered"] = False
            stale = [record for record in stale if record.get("recovered") is not False]
        return stale

    def recover_orphaned(self, *, worker_id: str) -> list[dict[str, Any]]:
        """Recover queued-before-start work; quarantine possibly executed work."""
        ensure_schema()
        now = time.time()
        with get_engine().begin() as connection:
            orphaned = [
                dict(row) for row in connection.execute(
                    select(runtime_executions).where(
                        runtime_executions.c.status.in_(ACTIVE_STATES),
                        or_(
                            runtime_executions.c.worker_id != worker_id,
                            runtime_executions.c.worker_id.is_(None),
                        ),
                        or_(
                            runtime_executions.c.lease_expires.is_(None),
                            runtime_executions.c.lease_expires <= now,
                        ),
                    )
                ).mappings()
            ]
            for record in orphaned:
                safe_to_requeue = (
                    record["status"] == ExecutionState.CLAIMED.value
                    and record["started_at"] is None
                )
                state = (
                    ExecutionState.QUEUED
                    if safe_to_requeue else ExecutionState.RECOVERY_REQUIRED
                )
                values = {
                    "status": state.value,
                    "worker_id": None,
                    "lease_started": None,
                    "lease_expires": None,
                    "heartbeat_at": now,
                    "error": (
                        "Previous worker exited before execution began; requeued."
                        if safe_to_requeue else
                        "Previous worker exited after execution may have begun; reconciliation required."
                    ),
                }
                changed = connection.execute(
                    update(runtime_executions)
                    .where(
                        runtime_executions.c.execution_id == record["execution_id"],
                        runtime_executions.c.status == record["status"],
                        or_(
                            runtime_executions.c.worker_id != worker_id,
                            runtime_executions.c.worker_id.is_(None),
                        ),
                        or_(
                            runtime_executions.c.lease_expires.is_(None),
                            runtime_executions.c.lease_expires <= now,
                        ),
                    )
                    .values(**values)
                )
                if changed.rowcount == 1:
                    record.update(values)
                else:
                    record["recovered"] = False
            orphaned = [
                record for record in orphaned
                if record.get("recovered") is not False
            ]
        return orphaned

    def append_event(
        self,
        *,
        command_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        execution_id: str | None = None,
        step_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        ensure_schema()
        with get_engine().begin() as connection:
            return self._append_event_in_transaction(
                connection,
                command_id=command_id,
                event_type=event_type,
                payload=payload,
                execution_id=execution_id,
                step_id=step_id,
                status=status,
            )

    @staticmethod
    def _append_event_in_transaction(
        connection: Any,
        *,
        command_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        execution_id: str | None = None,
        step_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        now = time.time()
        dialect = connection.dialect.name
        sequence_insert = (
            sqlite_insert(runtime_event_sequences)
            if dialect == "sqlite"
            else pg_insert(runtime_event_sequences)
        )
        sequence_statement = sequence_insert.values(
            command_id=command_id, last_sequence=1
        ).on_conflict_do_update(
            index_elements=[runtime_event_sequences.c.command_id],
            set_={
                "last_sequence": runtime_event_sequences.c.last_sequence + 1
            },
        ).returning(runtime_event_sequences.c.last_sequence)
        sequence = connection.execute(sequence_statement).scalar_one()
        safe_payload = payload or {}
        connection.execute(
            insert(runtime_events).values(
                event_id=event_id,
                command_id=command_id,
                execution_id=execution_id,
                step_id=step_id,
                sequence=sequence,
                timestamp=now,
                type=event_type,
                status=status,
                payload=json.dumps(safe_payload, ensure_ascii=False, default=str),
            )
        )
        return {
            "event_id": event_id,
            "command_id": command_id,
            "execution_id": execution_id,
            "step_id": step_id,
            "sequence": sequence,
            "timestamp": now,
            "type": event_type,
            "status": status,
            "payload": safe_payload,
        }

    def replay_events(
        self, command_id: str, *, after_sequence: int = 0, limit: int = 100,
    ) -> list[dict[str, Any]]:
        ensure_schema()
        query = (
            select(runtime_events)
            .where(
                runtime_events.c.command_id == command_id,
                runtime_events.c.sequence > after_sequence,
            )
            .order_by(runtime_events.c.sequence)
            .limit(limit)
        )
        with get_engine().connect() as connection:
            rows = connection.execute(query).mappings()
            events = []
            for row in rows:
                event = dict(row)
                event["payload"] = json.loads(event["payload"])
                events.append(event)
            return events


runtime = JarvisRuntime()
