#!/usr/bin/env python3
"""
start_brain.py - launcher for the JARVIS BRAIN v1 runtime (:8011).

The Brain is a *dedicated* model runtime — the Qwen3-4B inference endpoint that
sits alongside (and is distinct from) the Silverwing runtime on :8010:

    JARVIS BRAIN   -> http://127.0.0.1:8011  (serves Qwen3-4B Base / SFT)
    Silverwing     -> http://127.0.0.1:8010  (serves silverwing-120m-base-v1, unchanged)

The JARVIS platform (``start_jarvis.py``) is NOT started from here — it connects
to the Brain over HTTP at ``JARVIS_BRAIN_ENDPOINT``.  This launcher only starts
the Brain runtime process.

Because Qwen3-4B cannot load on this CPU-only PC (spec section 13), the runtime
serves the OpenAI-compatible contract with an explicitly-labeled ``stub``
backend (``JARVIS_BRAIN_BACKEND=stub``) which:

  * enforces real bearer-token auth,
  * reports ``available=false`` / ``production_health=false`` on /health (HTTP 503),
  * prefixes every reply with ``[brain-stub]``.

The stub therefore never masquerades as a real Brain: with no available Brain,
the platform gateway honestly falls back to Silverwing on :8010.  Set
``JARVIS_BRAIN_BACKEND=transformers`` (and run on a Kaggle GPU host) for real
Qwen3-4B inference.

Usage:
    python start_brain.py              # start Brain on :8011 (env-configured backend)
    python start_brain.py --stub       # start in stub mode (local API-contract testing)
    python start_brain.py --model jarvis-brain-qwen3-4b-sft-v1
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parent            # F:\AI
JARVIS_DIR = REPO_ROOT / "Jarvis-super-intelligence-"  # platform package
BRAIN_HOST = os.environ.get("JARVIS_BRAIN_HOST", "127.0.0.1")
BRAIN_PORT = int(os.environ.get("JARVIS_BRAIN_PORT", "8011"))
BRAIN_URL = f"http://{BRAIN_HOST}:{BRAIN_PORT}"
BRAIN_HEALTH = f"{BRAIN_URL}/health"
BRAIN_MODELS = f"{BRAIN_URL}/v1/models"
SILVERWING_PORT = int(os.environ.get("SILVERWING_PORT", "8010"))


def apply_env() -> None:
    """Apply the canonical integration env (endpoint + model id)."""
    try:
        import _env

        _env.apply()
    except Exception:
        os.environ.setdefault("JARVIS_BRAIN_ENDPOINT", "http://127.0.0.1:8011/v1")
        os.environ.setdefault("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1")
        os.environ.setdefault("JARVIS_BRAIN_HOST", "127.0.0.1")
        os.environ.setdefault("JARVIS_BRAIN_PORT", str(BRAIN_PORT))
    # Bind address: Brain listens on 127.0.0.1 only (never 0.0.0.0).
    os.environ.setdefault("JARVIS_BRAIN_HOST", "127.0.0.1")
    assert BRAIN_HOST == "127.0.0.1", "JARVIS BRAIN must bind 127.0.0.1 (loopback only)."


def child_env(**overrides: str) -> dict:
    """Environment inherited by the Brain subprocess."""
    apply_env()
    env = os.environ.copy()
    pythonpath_parts = [str(REPO_ROOT), str(JARVIS_DIR)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        pythonpath_parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env["PYTHONUNBUFFERED"] = "1"
    for k, v in overrides.items():
        env[k] = v
    # Never allow the API key to leak into the launcher's own stdout; the
    # subprocess reads it from the env/vault and never prints it.
    return env


def _port_in_use(host: str, port: int) -> bool:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def _http_json(url: str, headers: dict | None = None, timeout: float = 2.0):
    """GET `url`; return (status_code, json_or_None, raw_text)."""
    req_headers = headers or {}
    try:
        req = __import__("urllib.request", fromlist=["Request"]).Request(url, headers=req_headers)
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw), raw
            except ValueError:
                return r.status, None, raw
    except HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        try:
            return e.code, json.loads(raw), raw
        except ValueError:
            return e.code, None, raw
    except (URLError, OSError, ConnectionError):
        return 0, None, ""


def validate_model(model_id: str) -> str | None:
    """Confirm the configured Brain model is registered; return its repo or None."""
    apply_env()
    try:
        from brain_runtime.model_registry import BrainCatalog

        cat = BrainCatalog()
        entry = cat.lookup(model_id)
        if entry is None:
            return None
        return entry.repository
    except Exception:
        return None


def runtime_ready(timeout: float = 45.0) -> dict:
    """Poll /health until the Brain runtime answers (HTTP reachable).

    Returns a summary dict.  Note: a stub backend answers HTTP but reports
    ``available=false`` (HTTP 503) — that is the *correct* readiness signal for
    local API-contract testing; the platform will fall back to Silverwing.
    """
    deadline = time.time() + timeout
    last = {"reachable": False}
    while time.time() < deadline:
        code, data, _raw = _http_json(BRAIN_HEALTH, timeout=2.0)
        if code:
            last = {
                "reachable": True,
                "http_status": code,
                "status": (data or {}).get("status"),
                "stub": (data or {}).get("stub", False),
                "available": (data or {}).get("available", False),
                "production_health": (data or {}).get("production_health", False),
                "model": (data or {}).get("model"),
                "backend": (data or {}).get("backend"),
            }
            return last
        time.sleep(1.0)
    return last


def _stream(name: str, proc: subprocess.Popen) -> None:
    """Forward subprocess stdout/stderr to our stdout with a [name] prefix."""
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


class BrainLauncher:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._stopping = False
        self._threads: list[threading.Thread] = []

    def start(self, env: dict) -> subprocess.Popen:
        print(f"[brain-launcher] starting JARVIS BRAIN v1 on {BRAIN_URL}/v1 ...", flush=True)
        print(f"[brain-launcher] model={env.get('JARVIS_BRAIN_MODEL')} "
              f"backend={env.get('JARVIS_BRAIN_BACKEND')} device={env.get('JARVIS_BRAIN_DEVICE')} "
              f"api_key={'<set>' if env.get('JARVIS_BRAIN_API_KEY') else '<unset>'}", flush=True)
        proc = subprocess.Popen(
            [sys.executable, "-m", "brain_runtime.server"],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.proc = proc
        t = threading.Thread(target=_stream, args=("brain", proc), daemon=True)
        t.start()
        self._threads.append(t)
        return proc

    def stop(self, signum=None, frame=None) -> None:
        if self._stopping:
            return
        self._stopping = True
        print("\n[brain-launcher] shutting down Brain subprocess ...", flush=True)
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
        print("[brain-launcher] stopped.", flush=True)
        sys.exit(0)

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self.stop)
            except (ValueError, OSError, RuntimeError):
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the JARVIS BRAIN v1 runtime (:8011).")
    parser.add_argument("--stub", action="store_true",
                        help="force BRAIN_BACKEND=stub (local API-contract testing; never production-healthy)")
    parser.add_argument("--model", default=None,
                        help="override JARVIS_BRAIN_MODEL (e.g. jarvis-brain-qwen3-4b-sft-v1)")
    parser.add_argument("--backend", default=None,
                        help="override BRAIN_BACKEND (stub | transformers)")
    parser.add_argument("--port", type=int, default=None,
                        help="override BRAIN_PORT (default 8011)")
    args = parser.parse_args()

    apply_env()
    env_overrides: dict[str, str] = {}
    if args.stub:
        env_overrides["JARVIS_BRAIN_BACKEND"] = "stub"
    if args.backend:
        env_overrides["JARVIS_BRAIN_BACKEND"] = args.backend
    if args.model:
        env_overrides["JARVIS_BRAIN_MODEL"] = args.model
    if args.port:
        env_overrides["JARVIS_BRAIN_PORT"] = str(args.port)

    # ---- Port-collision safety (spec section 1) --------------------------
    port = int(env_overrides.get("JARVIS_BRAIN_PORT", str(BRAIN_PORT)))
    if _port_in_use("127.0.0.1", port):
        raise SystemExit(
            f"[brain-launcher] port 127.0.0.1:{port} is already in use by another service. "
            "JARVIS BRAIN must run on 127.0.0.1:8011 (separate from Silverwing :8010)."
        )
    sw_port = int(env_overrides.get("SILVERWING_PORT", str(SILVERWING_PORT)))
    if _port_in_use("127.0.0.1", sw_port):
        print(f"[brain-launcher] Silverwing runtime detected on 127.0.0.1:{sw_port} "
              "(preserved, unchanged; Brain runs on :8011).", flush=True)
    else:
        print(f"[brain-launcher] NOTE: Silverwing runtime was not detected on "
              f":{sw_port}; Silverwing fallback will be unavailable until start_jarvis.py "
              "is running.", flush=True)

    # ---- Model validation ------------------------------------------------
    brain_model = env_overrides.get("JARVIS_BRAIN_MODEL") or os.environ.get("JARVIS_BRAIN_MODEL", "")
    if brain_model:
        repo = validate_model(brain_model)
        if repo is None:
            print(f"[brain-launcher] WARNING: model {brain_model!r} is not registered in the "
                  "Brain catalog. A real transformers backend will attempt to resolve its "
                  "Hugging Face repository; the stub backend will use it as an opaque label.",
                  flush=True)
        else:
            print(f"[brain-launcher] model {brain_model!r} -> HF repository {repo}", flush=True)

    env = child_env(**env_overrides)
    if not env.get("JARVIS_BRAIN_API_KEY"):
        print("[brain-launcher] WARNING: JARVIS_BRAIN_API_KEY is not set in the environment; "
              "the runtime will start with auth disabled. Set the key before production use.",
              flush=True)

    launcher = BrainLauncher()
    launcher._install_signal_handlers()
    launcher.start(env)

    ready = runtime_ready(timeout=45.0)
    if not ready.get("reachable"):
        print("[brain-launcher] Brain runtime did not bind to the port in time.", flush=True)
        return 1

    is_stub = bool(env_overrides.get("JARVIS_BRAIN_BACKEND") == "stub") or ready.get("stub")
    available = bool(ready.get("available"))
    if is_stub or not available:
        print(f"[brain-launcher] Brain runtime is UP on {BRAIN_URL}/v1 (status="
              f"{ready.get('status')}, stub={ready.get('stub')}, available={ready.get('available')}, "
              f"production_health={ready.get('production_health')}).", flush=True)
        if is_stub:
            print("[brain-launcher] Running in STUB mode: the API contract is served but this is "
                  "NOT a real model. JARVIS_BRAIN_API_KEY still authenticates /v1/* routes, but "
                  "/health reports available=false so the platform will fall back to Silverwing (:8010).",
                  flush=True)
        else:
            print("[brain-launcher] Model not loaded on this hardware (offline). The runtime serves "
                  "the API contract with available=false; the platform will fall back to Silverwing.",
                  flush=True)
    else:
        print(f"[brain-launcher] Brain runtime is UP and production-healthy on {BRAIN_URL}/v1 "
              f"(model={ready.get('model')}, backend={ready.get('backend')}).", flush=True)

    print("[brain-launcher] Brain runtime is listening. Press Ctrl-C to stop.", flush=True)
    try:
        while True:
            if launcher.proc is not None and launcher.proc.poll() is not None:
                print(f"[brain-launcher] Brain process exited with code {launcher.proc.returncode}.",
                      flush=True)
                break
            time.sleep(2.0)
    except KeyboardInterrupt:
        pass
    finally:
        launcher.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
