"""Celery task entry points for real JARVIS backend operations."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .bio_growth_worker import BioGrowthResearchWorker
from .celery_app import celery_app
from .routers.commands import _recover_expired_commands

log = logging.getLogger("jarvis.celery_tasks")
COMMAND_LEASE_HEARTBEAT_SECONDS = 20


class CommandLeaseLostError(RuntimeError):
    """Raised when this worker no longer owns the persisted command lease."""


@celery_app.task(
    bind=True,
    name="jarvis.bio_growth.research_poll",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def research_poll(self) -> dict[str, Any]:
    """Fetch and persist due public research feeds from a supervised worker."""
    log.info(
        "Starting Bio-Growth poll task id=%s retry=%s",
        self.request.id,
        self.request.retries,
    )
    execution = asyncio.run(BioGrowthResearchWorker().run_once())
    if execution.get("status") == "failed":
        raise RuntimeError("Bio-Growth research poll failed")
    return execution


def enqueue_research_poll() -> str:
    """Queue an immediate research poll and return its broker task identifier."""
    result = research_poll.apply_async(queue="research")
    return str(result.id)


@celery_app.task(
    name="jarvis.command.recover_expired",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    ignore_result=True,
)
def recover_expired_commands() -> dict[str, int]:
    """Re-enqueue durable commands whose worker lease expired."""
    return _recover_expired_commands()


async def _execute_with_lease_heartbeat(command_id: str, worker_task_id: str, execution):
    async def maintain_lease() -> None:
        from .routers.commands import _heartbeat_command_lease

        while True:
            await asyncio.sleep(COMMAND_LEASE_HEARTBEAT_SECONDS)
            if not _heartbeat_command_lease(command_id, worker_task_id):
                raise CommandLeaseLostError(
                    f"Worker lease for command {command_id} is no longer owned."
                )

    execution_task = asyncio.create_task(execution)
    heartbeat = asyncio.create_task(maintain_lease())
    try:
        done, _ = await asyncio.wait(
            {execution_task, heartbeat},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat in done:
            error = heartbeat.exception()
            execution_task.cancel()
            await asyncio.gather(execution_task, return_exceptions=True)
            if error is not None:
                raise error
            raise CommandLeaseLostError(
                f"Worker lease for command {command_id} ended unexpectedly."
            )
        return await execution_task
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


@celery_app.task(
    bind=True,
    name="jarvis.command.execute",
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
    max_retries=3,
    time_limit=3600,
    soft_time_limit=3540,
)
def execute_command(
    self,
    command_id: str,
    user: dict[str, Any],
    goal: str | None = None,
    autonomy: str = "SUPERVISED",
    resume: bool = False,
) -> dict[str, str]:
    """Run a persisted JARVIS command in a durable worker process."""
    from .routers.commands import (
        _append_event,
        _claim_command_for_worker,
        _clear_command_lease,
        _read_command,
        _resume_command_execution,
        _run_command,
    )

    delivery = self.request.delivery_info or {}
    command = _claim_command_for_worker(
        command_id,
        str(self.request.id or ""),
        str(self.request.hostname or "unknown-worker"),
        resume=resume,
        redelivered=bool(delivery.get("redelivered")),
    )
    if command is None:
        current = _read_command(command_id)
        return {
            "command_id": command_id,
            "status": str(current.get("status", "NOT_FOUND")) if current else "NOT_FOUND",
        }
    task_id = str(self.request.id or "")
    if resume:
        execution = _resume_command_execution(command_id, user)
    else:
        if not goal:
            raise ValueError("A goal is required for a new command execution")
        execution = _run_command(command_id, user, goal, autonomy)
    asyncio.run(_execute_with_lease_heartbeat(command_id, task_id, execution))
    command = _read_command(command_id)
    if command and command.get("status") == "FAILED" and self.request.retries < self.max_retries:
        retry_resume = bool(command.get("task_id"))

        def mark_retrying(current: dict[str, Any]) -> dict[str, Any]:
            if current.get("status") == "FAILED":
                current["status"] = "RETRYING"
                current["retry_attempt"] = int(current.get("retry_attempt", 0)) + 1
                current["retry_scheduled_at"] = time.time()
            return current

        from .core import get_store

        get_store("commands").update_key(command_id, mark_retrying)
        _append_event(
            command_id,
            "command_retry_scheduled",
            retry=self.request.retries + 1,
            worker_task_id=task_id,
        )
        _clear_command_lease(command_id, task_id)
        raise self.retry(
            exc=RuntimeError("Command execution failed; retrying from persisted checkpoint."),
            kwargs={
                "command_id": command_id,
                "user": user,
                "goal": goal,
                "autonomy": autonomy,
                "resume": retry_resume,
            },
            countdown=min(300, 2 ** (self.request.retries + 1)),
        )
    _clear_command_lease(command_id, task_id)
    return {
        "command_id": command_id,
        "status": str(command.get("status", "UNKNOWN")) if command else "NOT_FOUND",
    }


def enqueue_command(
    *,
    command_id: str,
    user: dict[str, Any],
    goal: str | None = None,
    autonomy: str = "SUPERVISED",
    resume: bool = False,
) -> str:
    """Durably enqueue command work and return its broker task ID."""
    result = execute_command.apply_async(
        kwargs={
            "command_id": command_id,
            "user": user,
            "goal": goal,
            "autonomy": autonomy,
            "resume": resume,
        },
        queue="commands",
        priority=5,
    )
    return str(result.id)


__all__ = ["enqueue_command", "enqueue_research_poll", "execute_command", "research_poll"]
