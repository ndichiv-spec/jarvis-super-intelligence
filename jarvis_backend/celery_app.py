"""Celery queue for durable JARVIS background operations."""

from __future__ import annotations

import os
from datetime import timedelta

from celery import Celery
from kombu.exceptions import OperationalError

from .secret_config import load_file_secrets

load_file_secrets()

BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1"),
)
POLL_SECONDS = max(60, int(os.environ.get("JARVIS_BIO_GROWTH_POLL_SECONDS", "3600")))

celery_app = Celery(
    "jarvis",
    broker=BROKER_URL,
    include=["jarvis_backend.celery_tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    enable_utc=True,
    timezone="UTC",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    beat_schedule={
        "jarvis-bio-growth-research-poll": {
            "task": "jarvis.bio_growth.research_poll",
            "schedule": timedelta(seconds=POLL_SECONDS),
        },
        "jarvis-command-lease-recovery": {
            "task": "jarvis.command.recover_expired",
            "schedule": timedelta(seconds=30),
        },
    },
    beat_schedule_filename=os.environ.get(
        "CELERY_BEAT_SCHEDULE_FILE",
        "/app/data/celerybeat-schedule",
    ),
    task_routes={
        "jarvis.command.execute": {"queue": "commands"},
        "jarvis.command.recover_expired": {"queue": "commands"},
        "jarvis.bio_growth.research_poll": {"queue": "research"},
    },
    task_annotations={
        "jarvis.bio_growth.research_poll": {
            "rate_limit": "1/m",
            "time_limit": 900,
            "soft_time_limit": 840,
        },
    },
)


def get_queue_runtime_status() -> dict[str, object]:
    """Probe the configured broker and live workers without exposing its URL."""
    broker_reachable = False
    broker_error = None
    workers: dict[str, object] = {}
    active_jobs = 0
    reserved_jobs = 0

    try:
        with celery_app.connection_for_read() as connection:
            connection.ensure_connection(max_retries=0)
        broker_reachable = True
    except (OperationalError, OSError, TimeoutError) as exc:
        broker_error = type(exc).__name__

    worker_probe = "not_checked"
    command_queue_probe = "not_checked"
    if broker_reachable:
        try:
            inspector = celery_app.control.inspect(timeout=1.0)
            workers = inspector.ping() or {}
            worker_probe = "ok" if workers else "no_workers"
            active_queues = inspector.active_queues() or {}
            active = inspector.active() or {}
            reserved = inspector.reserved() or {}
            active_jobs = sum(len(jobs) for jobs in active.values())
            reserved_jobs = sum(len(jobs) for jobs in reserved.values())
            command_queue_probe = (
                "ok"
                if any(
                    queue.get("name") == "commands"
                    for queues in active_queues.values()
                    for queue in queues
                )
                else "no_command_queue_worker"
            )
        except Exception as exc:
            if worker_probe != "ok":
                worker_probe = type(exc).__name__
            command_queue_probe = type(exc).__name__

    return {
        "broker_configured": bool(BROKER_URL),
        "broker_reachable": broker_reachable,
        "broker_error": broker_error,
        "worker_probe": worker_probe,
        "command_queue_probe": command_queue_probe,
        "workers": sorted(workers),
        "active_jobs": active_jobs,
        "reserved_jobs": reserved_jobs,
        "queue_depth": None,
        "queue_depth_status": "not_reported_by_broker_inspector",
        "scheduler_task_registered": (
            "jarvis-bio-growth-research-poll" in celery_app.conf.beat_schedule
        ),
        "recovery_task_registered": (
            "jarvis-command-lease-recovery" in celery_app.conf.beat_schedule
        ),
        "scheduler_process_health": "not_reported",
    }


__all__ = ["celery_app"]
