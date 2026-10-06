"""Run and monitor the JARVIS API independently of any frontend process."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "jarvis_data" / "supervisor"
STATE_FILE = LOG_DIR / "backend-state.json"
HEALTH_URL = "http://127.0.0.1:8000/health/live"
POLL_SECONDS = 5
HEALTH_FAILURE_LIMIT = 3
RESTART_WINDOW_SECONDS = 15 * 60
RESTART_LIMIT = 5
MAX_BACKOFF_SECONDS = 120
COOLDOWN_SECONDS = 5 * 60
STARTUP_GRACE_SECONDS = 180

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "supervisor.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
stopping = False


def _set_stopping(_signum: int, _frame: object) -> None:
    global stopping
    stopping = True


def _write_state(status: str, **details: object) -> None:
    state = {"status": status, "updated_at": time.time(), **details}
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    temporary.replace(STATE_FILE)


def _healthy() -> bool:
    try:
        with urlopen(HEALTH_URL, timeout=2) as response:
            return response.status == 200
    except (OSError, URLError, TimeoutError):
        return False


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def supervise() -> int:
    signal.signal(signal.SIGINT, _set_stopping)
    signal.signal(signal.SIGTERM, _set_stopping)
    restarts: deque[float] = deque()
    backoff = 2
    while not stopping:
        stdout_path = LOG_DIR / "backend.stdout.log"
        stderr_path = LOG_DIR / "backend.stderr.log"
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "jarvis_api.py")],
                cwd=ROOT,
                env=os.environ.copy(),
                stdout=stdout,
                stderr=stderr,
            )
            logging.info("Backend process started pid=%s", process.pid)
            _write_state("starting", pid=process.pid, health_url=HEALTH_URL)
            failed_probes = 0
            healthy_since: float | None = None
            process_started = time.time()
            while not stopping and process.poll() is None:
                if _healthy():
                    failed_probes = 0
                    healthy_since = healthy_since or time.time()
                    _write_state("ready", pid=process.pid, health_url=HEALTH_URL)
                else:
                    if time.time() - process_started < STARTUP_GRACE_SECONDS:
                        _write_state("starting", pid=process.pid, health_url=HEALTH_URL)
                    else:
                        failed_probes += 1
                    if failed_probes >= HEALTH_FAILURE_LIMIT:
                        logging.error("Backend failed %d consecutive liveness probes", failed_probes)
                        _write_state("restarting", pid=process.pid, reason="liveness probes failed")
                        _terminate(process)
                        break
                    _write_state("degraded", pid=process.pid, reason="liveness probe failed")
                for _ in range(POLL_SECONDS):
                    if stopping or process.poll() is not None:
                        break
                    time.sleep(1)

            exit_code = process.poll()
            if stopping:
                _terminate(process)
                _write_state("stopped", exit_code=process.poll())
                return 0

        now = time.time()
        if healthy_since and now - healthy_since >= RESTART_WINDOW_SECONDS:
            restarts.clear()
            backoff = 2
        restarts.append(now)
        while restarts and now - restarts[0] > RESTART_WINDOW_SECONDS:
            restarts.popleft()
        logging.warning("Backend exited code=%s restart_count=%d", exit_code, len(restarts))

        if len(restarts) >= RESTART_LIMIT:
            _write_state(
                "failed",
                restart_count=len(restarts),
                retry_after_seconds=COOLDOWN_SECONDS,
            )
            logging.error("Restart budget exhausted; entering cooldown")
            for _ in range(COOLDOWN_SECONDS):
                if stopping:
                    _write_state("stopped", reason="shutdown during cooldown")
                    return 0
                time.sleep(1)
            restarts.clear()
            backoff = 2
            continue

        _write_state(
            "restarting",
            restart_count=len(restarts),
            retry_after_seconds=backoff,
        )
        for _ in range(backoff):
            if stopping:
                _write_state("stopped", reason="shutdown during restart backoff")
                return 0
            time.sleep(1)
        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    _write_state("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(supervise())
