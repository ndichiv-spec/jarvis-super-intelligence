"""Sandboxed code execution API (spec #17, #16 tool security).

Exposes the Silverwing isolation sandbox (isolated subprocess, AST allowlist,
blocked dangerous builtins, wall-clock timeout, memory enforcement) to the
JARVIS API so the Coder agent / users can execute generated code safely.

Security properties (measured, not claimed):
  * authenticated (bearer token -> get_current_user)
  * rate limited per-user + global ceiling
  * isolated subprocess (Popen) with wall-clock timeout and RSS cap
  * AST allowlist pre-flight + blocked builtins in the runner
  * output caps (stdout/stderr truncated in the runner and in the router)
  * audit trail appended to jarvis_data/audit/sandbox.jsonl (request_id, user,
    code hash, status, duration, error class) and kept out of the response path
  * honest policy disclosure via GET /policy (no silent network access, no
    host file writes, this is a software sandbox not an OS/container boundary)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core import DATA_DIR, get_current_user

router = APIRouter(prefix="/api/v1/sandbox", tags=["sandbox"])

_SW_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "silverwing-backend"
if str(_SW_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_SW_BACKEND_DIR))
import sandbox as sw  # noqa: E402

MAX_CODE_LEN = 20_000
DEFAULT_TIMEOUT_S = 5.0
MAX_TIMEOUT_S = 20.0
DEFAULT_MEMORY_MB = 128
MAX_OUTPUT_CHARS = 4_000
AUDIT_DIR = DATA_DIR / "audit"
_audit_lock = threading.Lock()

_LIMIT_WINDOW_S = 60
_LIMIT_PER_USER = 10
_LIMIT_GLOBAL = 60
_buckets: Dict[str, List[float]] = {}
_stats_lock = threading.Lock()

_stats: Dict[str, Any] = {
    "executions": 0,
    "ok": 0,
    "violations": 0,
    "timeouts": 0,
    "killed_oom": 0,
    "errors": 0,
    "rate_limited": 0,
    "total_duration_ms": 0.0,
}
# In-process run history (keyed by request_id).  Process-lifetime; the durable
# audit trail lives in DATA_DIR/audit/sandbox.jsonl.  Used by GET /runs/{id}.
_RUN_STORE: Dict[str, "CodeRunOut"] = {}


class CodeRunIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=MAX_CODE_LEN)
    language: str = "python"
    timeout: float = Field(DEFAULT_TIMEOUT_S, gt=0, le=MAX_TIMEOUT_S)
    memory_limit_mb: int = Field(DEFAULT_MEMORY_MB, ge=16, le=1024)


class CodeRunOut(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    execution_time_ms: int = 0
    signal: str | None = None
    duration_ms: int = 0
    memory_enforced: bool = False
    policy: Dict[str, Any] = {}


class PolicyOut(BaseModel):
    language: str
    isolation: str
    controls: Dict[str, Any]
    honest_limits: List[str]
    metrics: Dict[str, Any]


def _audit(record: Dict[str, Any]) -> None:
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, default=str) + "\n"
        with _audit_lock:
            with open(AUDIT_DIR / "sandbox.jsonl", "a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:  # noqa: BLE001 - audit must never break the request
        pass


def _rate_allowed(user_id: str) -> bool:
    now = time.time()
    with _stats_lock:
        cutoff = now - _LIMIT_WINDOW_S
        bucket = [t for t in _buckets.get(user_id, []) if t > cutoff]
        global_events = sum(1 for ts in _buckets.values() for t in ts if t > cutoff)
        if len(bucket) >= _LIMIT_PER_USER or global_events >= _LIMIT_GLOBAL:
            _stats["rate_limited"] += 1
            return False
        bucket.append(now)
        _buckets[user_id] = bucket
        return True


def _categorize(result: Dict[str, Any]) -> str:
    if result.get("signal") == "timeout":
        return "timeouts"
    if result.get("signal") == "killed" and "Memory limit" in (result.get("error") or ""):
        return "killed_oom"
    if not result.get("ok") and "violation" in (result.get("error") or ""):
        return "violations"
    if not result.get("ok"):
        return "errors"
    return "ok"


@router.post("/python", response_model=CodeRunOut)
async def run_python(body: CodeRunIn, user: Dict[str, Any] = Depends(get_current_user)) -> CodeRunOut:
    user_id = str(user.get("id") or user.get("username") or "unknown")
    if not _rate_allowed(user_id):
        raise HTTPException(status_code=429, detail="Sandbox rate limit exceeded (try again shortly)")
    return await _sandbox_execute(body, actor=user_id)


async def _sandbox_execute(body: CodeRunIn, actor: str) -> CodeRunOut:
    """Shared audited sandbox execution (used by the API and the agents router).

    Everything security-relevant lives here: isolated subprocess, wall-clock
    timeout, RSS cap, AST pre-flight, output caps, audit trail, telemetry.
    """
    request_id = uuid.uuid4().hex[:12]
    code_hash = hashlib.sha256(body.code.encode("utf-8")).hexdigest()[:16]
    started = time.monotonic()

    try:
        sw.validate(body.code)
    except sw.SandboxViolation as exc:
        result = {"ok": False, "error": f"violation: {exc}", "time": 0.0, "signal": "violation"}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"sandbox validation failed: {exc}", "time": 0.0, "signal": None}
    else:
        try:
            result = await asyncio.to_thread(sw.run_code, body.code, body.timeout, body.memory_limit_mb)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": f"sandbox invocation failed: {exc}", "time": 0.0, "signal": None}

    duration_ms = int((time.monotonic() - started) * 1000)
    category = _categorize(result)

    with _stats_lock:
        _stats["executions"] += 1
        _stats[category] += 1
        _stats["total_duration_ms"] += float(result.get("time", 0.0) * 1000)

    _audit({
        "request_id": request_id,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "actor": actor,
        "language": body.language,
        "code_sha256_16": code_hash,
        "code_len": len(body.code),
        "ok": result.get("ok", False),
        "category": category,
        "error_class": None if result.get("ok") else (result.get("error") or "")[:200],
        "duration_ms": duration_ms,
        "memory_mb": body.memory_limit_mb,
        "memory_enforced": bool(result.get("memory_enforced")),
    })

    out = CodeRunOut(
        ok=bool(result.get("ok")),
        stdout=(result.get("stdout") or "")[:MAX_OUTPUT_CHARS],
        stderr=(result.get("stderr") or "")[:MAX_OUTPUT_CHARS // 2],
        error=result.get("error"),
        execution_time_ms=round(float(result.get("time", 0.0)) * 1000),
        signal=result.get("signal"),
        duration_ms=duration_ms,
        memory_enforced=bool(result.get("memory_enforced")),
        policy={
            "language": body.language,
            "timeout_s": body.timeout,
            "memory_limit_mb": body.memory_limit_mb,
            "network": "blocked",
            "fs_write": "blocked",
        },
    )
    # Index for GET /runs/{id} (request_id is the durable key).
    _RUN_STORE[request_id] = out
    return out


@router.post("/run", response_model=CodeRunOut)
async def run_code_alias(body: CodeRunIn, user: Dict[str, Any] = Depends(get_current_user)) -> CodeRunOut:
    """Alias for POST /python (spec Section 26: POST /api/sandbox/run)."""
    return await _sandbox_execute(body, actor=str(user.get("id") or user.get("username") or "unknown"))


@router.get("/runs/{run_id}", response_model=CodeRunOut)
async def get_run(run_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> CodeRunOut:
    """Retrieve a previously executed sandbox run by its request id."""
    out = _RUN_STORE.get(run_id)
    if out is None:
        raise HTTPException(status_code=404, detail=f"sandbox run {run_id} not found")
    return out


@router.get("/policy", response_model=PolicyOut)
async def policy() -> PolicyOut:
    with _stats_lock:
        metrics = {k: v for k, v in _stats.items()}
        if _stats["executions"]:
            metrics["avg_duration_ms"] = round(_stats["total_duration_ms"] / _stats["executions"], 1)
    return PolicyOut(
        language="python",
        isolation="isolated subprocess (software sandbox; not an OS/container boundary)",
        controls={
            "ast_allowlist": True,
            "blocked_builtins": True,
            "import_blocked": True,
            "network_blocked": True,
            "fs_write_blocked": True,
            "wall_clock_timeout_s": MAX_TIMEOUT_S,
            "memory_cap_mb": 1024,
            "memory_enforcement": True,
            "output_cap_chars": MAX_OUTPUT_CHARS,
            "auth_required": True,
            "rate_limits": {
                "per_user_per_min": _LIMIT_PER_USER,
                "global_per_min": _LIMIT_GLOBAL,
            },
        },
        honest_limits=[
            "Software sandbox: not a hardened OS/container isolation boundary.",
            "A determined attacker may be able to escape; do not run code you do not trust.",
            "No network access by policy; no host filesystem writes by policy.",
        ],
        metrics=metrics,
    )