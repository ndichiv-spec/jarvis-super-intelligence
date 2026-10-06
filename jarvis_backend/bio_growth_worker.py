"""Active backend worker for polling configured Bio-Growth research feeds."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from .core import get_store

log = logging.getLogger("jarvis.bio_growth_worker")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat().replace("+00:00", "Z")


class BioGrowthResearchWorker:
    """Poll due research feeds, persist outcomes, and expose its live state."""

    def __init__(self, interval_seconds: int = 3600):
        self.interval_seconds = max(60, interval_seconds)
        self._task: asyncio.Task | None = None
        self._cycle_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._run_loop(), name="jarvis-bio-growth")
        self._write_state(status="running", started_at=_iso())
        log.info("Bio-Growth research polling worker started")

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        self._task = None
        self._write_state(status="stopped", stopped_at=_iso())
        log.info("Bio-Growth research polling worker stopped")

    async def run_once(self) -> dict[str, Any]:
        """Run a real due-feed ingestion cycle and persist its execution record."""
        async with self._cycle_lock:
            started_at = _iso()
            started_clock = time.perf_counter()
            run_id = f"bio-growth-{uuid.uuid4().hex}"
            self._write_state(status="running_cycle", current_run_id=run_id)
            try:
                from .research.autonomous_research import SEED_FEEDS, AutonomousResearchCortex

                cortex = AutonomousResearchCortex()
                await asyncio.to_thread(cortex.initialize)
                from .research.technology_watch import refresh_watch

                try:
                    technology_watch = await refresh_watch()
                except Exception as exc:
                    log.exception("Technology watch refresh failed")
                    technology_watch = {
                        "status": "unavailable",
                        "new_items": 0,
                        "error": type(exc).__name__,
                    }
                allowed_urls = {feed["url"] for feed in SEED_FEEDS}
                due_feed_ids = [
                    feed_id
                    for feed_id in cortex.get_due_feeds()
                    if cortex._feeds[feed_id].get("url") in allowed_urls
                ]
                results = []
                for feed_id in due_feed_ids:
                    feed = cortex._feeds[feed_id]
                    try:
                        result = await cortex.ingest_feed(feed_id)
                        if not result.get("success"):
                            raise RuntimeError(result.get("error") or "Feed ingestion failed")
                        results.append({
                            "feed_id": feed_id,
                            "feed_name": feed["name"],
                            "items_discovered": result.get("items_discovered", 0),
                            "items_new": result.get("items_new", 0),
                            "status": "completed",
                        })
                    except Exception as exc:
                        log.warning("Research feed %s failed: %s", feed_id, exc)
                        results.append({
                            "feed_id": feed_id,
                            "feed_name": feed.get("name", feed_id),
                            "status": "failed",
                            "error": type(exc).__name__,
                        })

                succeeded = sum(item["status"] == "completed" for item in results)
                failed = len(results) - succeeded
                watch_status = technology_watch.get("status")
                watch_failed = watch_status == "unavailable"
                watch_partial = watch_status == "partial"
                watch_errors = len(technology_watch.get("last_errors", []))
                if watch_failed and not watch_errors:
                    watch_errors = 1
                status = (
                    "failed" if failed and not succeeded and watch_failed
                    else "partial" if failed or watch_failed or watch_partial
                    else "completed"
                )
                execution = {
                    "id": run_id,
                    "task_id": "wf-bio-growth-research",
                    "task_name": "Bio-Growth Research Poll",
                    "status": status,
                    "engine": "local",
                    "started_at": started_at,
                    "completed_at": _iso(),
                    "duration_ms": round((time.perf_counter() - started_clock) * 1000),
                    "result": {
                        "feeds_due": len(due_feed_ids),
                        "feeds_succeeded": succeeded,
                        "feeds_failed": failed,
                        "items_discovered": sum(item.get("items_discovered", 0) for item in results),
                        "items_new": sum(item.get("items_new", 0) for item in results),
                        "feeds": results,
                        "technology_watch": {
                            "status": watch_status,
                            "new_items": technology_watch.get("new_items", 0),
                            "source_errors": len(technology_watch.get("last_errors", [])),
                            **(
                                {"error": technology_watch["error"]}
                                if technology_watch.get("error")
                                else {}
                            ),
                        },
                    },
                }
                self._record_execution(execution)
                self._write_state(
                    status="running" if self.running else "idle",
                    last_run_at=execution["completed_at"],
                    last_run_status=status,
                    last_run_id=run_id,
                    last_error_count=failed + watch_errors,
                    next_run_at=_iso(_utc_now() + timedelta(seconds=self.interval_seconds)),
                )
                return execution
            except Exception as exc:
                execution = {
                    "id": run_id,
                    "task_id": "wf-bio-growth-research",
                    "task_name": "Bio-Growth Research Poll",
                    "status": "failed",
                    "engine": "local",
                    "started_at": started_at,
                    "completed_at": _iso(),
                    "duration_ms": round((time.perf_counter() - started_clock) * 1000),
                    "error": type(exc).__name__,
                }
                self._record_execution(execution)
                self._write_state(
                    status="running" if self.running else "error",
                    last_run_at=execution["completed_at"],
                    last_run_status="failed",
                    last_run_id=run_id,
                    last_error=type(exc).__name__,
                )
                log.exception("Bio-Growth research cycle failed")
                raise

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # One source/database failure must not permanently stop polling.
                pass
            await asyncio.sleep(self.interval_seconds)

    @staticmethod
    def _write_state(**updates: Any) -> None:
        store = get_store("misc")
        data = store.load()
        state = data.setdefault("bio_growth_worker", {})
        state.update(updates)
        store.save()

    @staticmethod
    def _record_execution(execution: dict[str, Any]) -> None:
        store = get_store("executions")
        records = store.load()
        records.append({**execution, "user_id": "system"})
        del records[:-5000]
        store.save()

    def get_status(self) -> dict[str, Any]:
        stored = get_store("misc").load().get("bio_growth_worker", {})
        return {
            **stored,
            "worker_running": self.running,
            "execution_mode": os.environ.get(
                "JARVIS_BIO_GROWTH_WORKER_MODE",
                "embedded",
            ).strip().lower(),
            "poll_interval_seconds": self.interval_seconds,
            "persistence": "jarvis_kv",
        }


_worker: BioGrowthResearchWorker | None = None


def get_bio_growth_worker() -> BioGrowthResearchWorker:
    global _worker
    if _worker is None:
        interval = int(os.environ.get("JARVIS_BIO_GROWTH_POLL_SECONDS", "3600"))
        _worker = BioGrowthResearchWorker(interval)
    return _worker


async def start_bio_growth_worker() -> None:
    if os.environ.get("JARVIS_TEST_MODE") == "1":
        return
    enabled = os.environ.get("JARVIS_BIO_GROWTH_WORKER_ENABLED", "true").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return
    mode = os.environ.get("JARVIS_BIO_GROWTH_WORKER_MODE", "embedded").strip().lower()
    if mode == "celery":
        log.info("Bio-Growth polling is delegated to the Celery worker and scheduler")
        return
    if mode != "embedded":
        raise ValueError("JARVIS_BIO_GROWTH_WORKER_MODE must be 'embedded' or 'celery'")
    await get_bio_growth_worker().start()


async def stop_bio_growth_worker() -> None:
    if _worker is not None:
        await _worker.stop()
