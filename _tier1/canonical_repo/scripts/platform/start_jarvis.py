#!/usr/bin/env python3
"""
start_jarvis.py - automatic launcher for the JARVIS platform + trained Silverwing runtime.

This is the single entry point that wires the two cooperating services together so
that JARVIS always talks to the *trained* Silverwing 120M model:

    * Silverwing runtime  -> http://127.0.0.1:8010  (serves silverwing-120m-base-v1)
    * JARVIS platform      -> http://127.0.0.1:8000  (FastAPI, auto-wired to :8010)

The platform subprocess is launched with SILVERWING_ENDPOINT=http://127.0.0.1:8010
and SILVERWING_MODEL=silverwing-120m-base-v1 (provided by the canonical _env module),
so chat requests flow automatically:

    client -> JARVIS :8000 -> ProviderGateway -> ModelGateway
        -> SilverwingClient -> POST :8010/v1/chat/completions -> TorchBackend

The launcher starts the runtime first, waits for its /v1/health to report
"healthy" (incl. model warmup), and only then starts the platform. Both
processes are kept alive for the lifetime of this launcher; Ctrl-C / SIGTERM
tears both down.

Usage:
    python start_jarvis.py               # start both, block, forward Ctrl-C to stop both
    python start_jarvis.py --no-runtime   # platform only (runtime already running on 8010)
    python start_jarvis.py --runtime-only # runtime only (no platform)
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

REPO_ROOT = Path(__file__).resolve().parent            # F:\AI
JARVIS_DIR = REPO_ROOT / "Jarvis-super-intelligence-"  # platform package lives here

# Make this file importable as a script and ensure _env / silverwing_runtime are
# importable when run directly (e.g. `python start_jarvis.py` from F:\AI).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RUNTIME_HOST = os.environ.get("SILVERWING_HOST", "127.0.0.1")
RUNTIME_PORT = int(os.environ.get("SILVERWING_PORT", "8010"))
RUNTIME_URL = f"http://{RUNTIME_HOST}:{RUNTIME_PORT}"
RUNTIME_HEALTH = f"{RUNTIME_URL}/v1/health"

PLATFORM_HOST = os.environ.get("JARVIS_HOST", "127.0.0.1")
PLATFORM_PORT = int(os.environ.get("JARVIS_PORT", "8000"))
PLATFORM_URL = f"http://{PLATFORM_HOST}:{PLATFORM_PORT}"


def apply_env() -> None:
    """Apply the canonical integration env (endpoint + trained model id)."""
    try:
        import _env  # canonical env module at repo root
        _env.apply()
    except Exception:
        # Minimal fallback if _env is unavailable in the environment.
        for k, v in {
            "SILVERWING_ENDPOINT": RUNTIME_URL,
            "SILVERWING_MODEL": "silverwing-120m-base-v1",
            "SILVERWING_TIMEOUT": "300",
            "SILVERWING_BACKEND": "torch",
            "SILVERWING_PORT": str(RUNTIME_PORT),
        }.items():
            os.environ.setdefault(k, v)


def child_env() -> dict:
    """Build the environment inherited by both subprocesses (with PYTHONPATH)."""
    apply_env()
    env = os.environ.copy()
    pythonpath_parts = [str(REPO_ROOT), str(JARVIS_DIR)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        pythonpath_parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env["PYTHONUNBUFFERED"] = "1"
    # CPU-safe operating point for the 120M model:
    #   * 64-token generations finish in ~15 s on CPU (vs the old 256 -> ~70 s),
    #     which keeps the runtime healthy across back-to-back requests (no 504 ->
    #     503 degradation cascade that previously broke multi-turn chat).
    #   * 300 s request-timeout gives headroom past the runtime's 120 s default.
    # Both are overridable via the environment.
    env.setdefault("SILVERWING_MAX_TOKENS", "64")
    env.setdefault("SILVERWING_REQUEST_TIMEOUT", "300")
    return env


def http_ok(url: str, timeout: float = 2.0) -> bool:
    """True if `url` returns any HTTP response (i.e. a server is bound)."""
    try:
        with urlopen(url, timeout=timeout):
            return True
    except HTTPError:
        # Any HTTP status means the server is up and answering.
        return True
    except (URLError, OSError, ConnectionError):
        return False


def runtime_healthy(timeout: float = 120.0) -> bool:
    """Poll /v1/health until the runtime reports healthy (includes warmup)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(RUNTIME_HEALTH, timeout=2.0) as r:
                if r.status == 200:
                    body = r.read().decode("utf-8", "replace")
                    if '"healthy"' in body.lower() or "healthy" in body.lower():
                        return True
        except (HTTPError, URLError, OSError, ConnectionError):
            pass
        time.sleep(1.0)
    return False


def platform_up(timeout: float = 60.0) -> bool:
    """Poll the platform until it answers any HTTP request on :8000."""
    deadline = time.time() + timeout
    candidates = [f"{PLATFORM_URL}/health", f"{PLATFORM_URL}/docs", f"{PLATFORM_URL}/"]
    while time.time() < deadline:
        for url in candidates:
            if http_ok(url, timeout=2.0):
                return True
        time.sleep(1.0)
    return False


def _stream(name: str, proc: subprocess.Popen) -> None:
    """Forward a subprocess's stdout/stderr to our stdout with a [name] prefix."""
    if proc.stdout is None:
        return
    try:
        for raw in iter(proc.stdout.readline, b""):
            try:
                line = raw.decode("utf-8", "replace").rstrip("\n")
            except Exception:
                line = str(raw)
            if line:
                print(f"[{name}] {line}", flush=True)
    except (ValueError, OSError):
        pass


class Launcher:
    def __init__(self) -> None:
        self.runtime_proc: subprocess.Popen | None = None
        self.platform_proc: subprocess.Popen | None = None
        self._stopping = False
        self._threads: list[threading.Thread] = []

    # -- process lifecycle -------------------------------------------------
    def start_runtime(self) -> subprocess.Popen:
        apply_env()
        env = child_env()
        print(f"[launcher] starting Silverwing runtime on {RUNTIME_URL} ...", flush=True)
        proc = subprocess.Popen(
            [sys.executable, "-m", "silverwing_runtime.server"],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.runtime_proc = proc
        t = threading.Thread(target=_stream, args=("runtime", proc), daemon=True)
        t.start()
        self._threads.append(t)
        return proc

    def start_platform(self) -> subprocess.Popen:
        apply_env()
        env = child_env()
        print(f"[launcher] starting JARVIS platform on {PLATFORM_URL} "
              f"(SILVERWING_ENDPOINT={os.environ.get('SILVERWING_ENDPOINT')}) ...", flush=True)
        proc = subprocess.Popen(
            [sys.executable, "jarvis_api.py"],
            cwd=str(JARVIS_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.platform_proc = proc
        t = threading.Thread(target=_stream, args=("platform", proc), daemon=True)
        t.start()
        self._threads.append(t)
        return proc

    # -- shutdown ----------------------------------------------------------
    def stop(self, signum=None, frame=None) -> None:
        if self._stopping:
            return
        self._stopping = True
        print("\n[launcher] shutting down subprocesses ...", flush=True)
        for proc in (self.platform_proc, self.runtime_proc):
            if proc is None or proc.poll() is not None:
                continue
            try:
                proc.terminate()
            except OSError:
                pass
        for proc in (self.platform_proc, self.runtime_proc):
            if proc is None:
                continue
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
        print("[launcher] stopped.", flush=True)
        sys.exit(0)

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self.stop)
            except (ValueError, OSError, RuntimeError):
                pass

    # -- main orchestration ------------------------------------------------
    def run(self, no_runtime: bool, runtime_only: bool) -> int:
        self._install_signal_handlers()

        if not runtime_only:
            if not no_runtime:
                # If a runtime is already answering :8010, reuse it; else start one.
                if http_ok(RUNTIME_HEALTH, timeout=1.0):
                    print("[launcher] runtime already healthy on :8010; reusing.", flush=True)
                else:
                    self.start_runtime()
                    if not runtime_healthy(timeout=180.0):
                        print("[launcher] WARNING: runtime did not become healthy in time; "
                              "starting platform anyway (it will report MODEL_UNAVAILABLE "
                              "until the runtime is reachable).", flush=True)
                print(f"[launcher] runtime : {RUNTIME_URL}  ready={http_ok(RUNTIME_HEALTH)}",
                      flush=True)
            self.start_platform()
            if not platform_up(timeout=90.0):
                print("[launcher] WARNING: platform did not answer on :8000 within timeout. "
                      "Check the [platform] lines above for import/startup errors.",
                      flush=True)
                return 1
            print(f"[launcher] platform : {PLATFORM_URL}  ready={http_ok(PLATFORM_URL + '/docs')}",
                  flush=True)
        else:
            # runtime only
            self.start_runtime()
            if not runtime_healthy(timeout=180.0):
                print("[launcher] WARNING: runtime did not become healthy in time.",
                      flush=True)
                return 1
            print(f"[launcher] runtime : {RUNTIME_URL}  ready", flush=True)

        print("[launcher] both services are up. Press Ctrl-C to stop.", flush=True)
        try:
            while True:
                # Reap-exit detection: if either child dies, log and wait a bit
                # so the user can see the streamed error before the shell returns.
                rp = self.runtime_proc and self.runtime_proc.poll()
                pp = self.platform_proc and self.platform_proc.poll()
                if rp is not None and not no_runtime:
                    print(f"[launcher] runtime process exited with code {rp}.", flush=True)
                if pp is not None and not runtime_only:
                    print(f"[launcher] platform process exited with code {pp}.",
                          flush=True)
                if (rp is not None and not no_runtime) or (pp is not None and not runtime_only):
                    break
                time.sleep(2.0)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-runtime", action="store_true",
                        help="do not start the Silverwing runtime (assume :8010 is already up)")
    parser.add_argument("--runtime-only", action="store_true",
                        help="start only the Silverwing runtime (no platform)")
    args = parser.parse_args()
    return Launcher().run(no_runtime=args.no_runtime, runtime_only=args.runtime_only)


if __name__ == "__main__":
    sys.exit(main())
