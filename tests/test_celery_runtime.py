from __future__ import annotations

import asyncio
from datetime import timedelta

from jarvis_backend import celery_app, celery_tasks


def test_celery_uses_durable_queue_settings_and_scheduled_task():
    config = celery_app.celery_app.conf

    assert config.task_acks_late is True
    assert config.task_reject_on_worker_lost is True
    assert config.worker_prefetch_multiplier == 1
    assert config.task_ignore_result is True
    assert config.broker_transport_options["visibility_timeout"] >= 3600
    schedule = config.beat_schedule["jarvis-bio-growth-research-poll"]
    assert schedule["task"] == "jarvis.bio_growth.research_poll"
    assert isinstance(schedule["schedule"], timedelta)
    recovery = config.beat_schedule["jarvis-command-lease-recovery"]
    assert recovery["task"] == "jarvis.command.recover_expired"
    assert isinstance(recovery["schedule"], timedelta)


def test_celery_task_runs_real_worker_cycle(monkeypatch):
    expected = {"id": "run-1", "status": "completed", "result": {"items_new": 3}}

    class FakeWorker:
        async def run_once(self):
            return expected

    monkeypatch.setattr(celery_tasks, "BioGrowthResearchWorker", FakeWorker)

    assert celery_tasks.research_poll.run() == expected


def test_celery_task_surfaces_failed_worker_cycle_for_retry(monkeypatch):
    class FakeWorker:
        async def run_once(self):
            return {"id": "run-2", "status": "failed"}

    monkeypatch.setattr(celery_tasks, "BioGrowthResearchWorker", FakeWorker)

    try:
        celery_tasks.research_poll.run()
    except RuntimeError as exc:
        assert str(exc) == "Bio-Growth research poll failed"
    else:
        raise AssertionError("A failed worker cycle must be retried, not acknowledged")


def test_command_dispatch_routes_to_durable_commands_queue(monkeypatch):
    captured = {}

    class Queued:
        id = "command-task-1"

    def apply_async(**kwargs):
        captured.update(kwargs)
        return Queued()

    monkeypatch.setattr(celery_tasks.execute_command, "apply_async", apply_async)
    task_id = celery_tasks.enqueue_command(
        command_id="command-1",
        user={"id": "user-1", "roles": ["user"]},
        goal="Inspect provider status",
    )

    assert task_id == "command-task-1"
    assert captured["queue"] == "commands"
    assert captured["kwargs"]["command_id"] == "command-1"
    assert captured["kwargs"]["goal"] == "Inspect provider status"


def test_queue_runtime_requires_worker_to_consume_command_queue(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def ensure_connection(self, max_retries):
            assert max_retries == 0

    class Inspector:
        def ping(self):
            return {"worker-1": {"ok": "pong"}}

        def active_queues(self):
            return {"worker-1": [{"name": "research"}]}

        def active(self):
            return {}

        def reserved(self):
            return {}

    monkeypatch.setattr(
        celery_app.celery_app,
        "connection_for_read",
        lambda: Connection(),
    )
    monkeypatch.setattr(celery_app.celery_app.control, "inspect", lambda **_kwargs: Inspector())

    status = celery_app.get_queue_runtime_status()

    assert status["worker_probe"] == "ok"
    assert status["command_queue_probe"] == "no_command_queue_worker"


def test_api_does_not_start_embedded_worker_in_celery_mode(monkeypatch):
    from jarvis_backend import bio_growth_worker

    class FakeWorker:
        started = False

        async def start(self):
            self.started = True

    worker = FakeWorker()
    monkeypatch.setenv("JARVIS_TEST_MODE", "0")
    monkeypatch.setenv("JARVIS_BIO_GROWTH_WORKER_ENABLED", "true")
    monkeypatch.setenv("JARVIS_BIO_GROWTH_WORKER_MODE", "celery")
    monkeypatch.setattr(bio_growth_worker, "get_bio_growth_worker", lambda: worker)

    asyncio.run(bio_growth_worker.start_bio_growth_worker())

    assert worker.started is False


def test_lost_command_lease_cancels_execution(monkeypatch):
    cancelled = asyncio.Event()

    async def execution():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(celery_tasks, "COMMAND_LEASE_HEARTBEAT_SECONDS", 0)
    monkeypatch.setattr(
        "jarvis_backend.routers.commands._heartbeat_command_lease",
        lambda _command_id, _task_id: False,
    )

    try:
        asyncio.run(
            celery_tasks._execute_with_lease_heartbeat(
                "command-lost-lease", "worker-task-1", execution()
            )
        )
    except celery_tasks.CommandLeaseLostError as exc:
        assert "no longer owned" in str(exc)
    else:
        raise AssertionError("A worker must stop when it loses its command lease.")

    assert cancelled.is_set()
