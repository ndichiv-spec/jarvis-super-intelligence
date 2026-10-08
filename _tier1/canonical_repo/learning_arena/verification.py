"""Deterministic problem verification for the governed learning loop (spec §26).

Verification ordering is deliberate and cheap-first:

1. **direct answer check** — for problems with a known canonical answer
   (mathematics-style), compare numerically/token-wise first;
2. **sandbox execution** — for programming/tool problems, the proposed
   solution is executed in the hardened sandbox (no imports, no network,
   no dangerous builtins, timeout + output caps) exactly like the provider
   ``sandbox_run`` tool, so a ``REFUTED`` verdict means the code actually
   failed — never a guess.

When neither applies (open-ended essay/design/analysis), the verifier says
``UNVERIFIABLE`` honestly and the learning loop routes to a teacher critique
+ evidence instead of pretending it verified.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from research_engine.tool_registry import _sandbox_ast_violation, os_env_path


class VerificationOutcome(str, Enum):
    VERIFIED = "VERIFIED"
    REFUTED = "REFUTED"
    UNVERIFIABLE = "UNVERIFIABLE"
    ERROR = "ERROR"


#: Timeout / output caps for the sandboxed code runner (mirrors sandbox_run).
MAX_TIMEOUT_S = 20.0
MAX_OUTPUT = 5000


@dataclass
class VerificationResult:
    outcome: VerificationOutcome
    evidence: str
    method: str = "none"  # exact | numeric | sandbox | unverifiable
    stdout: str = ""
    exit_code: Optional[int] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "evidence": self.evidence,
            "method": self.method,
            "stdout": self.stdout[:MAX_OUTPUT],
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
        }

    def ok(self) -> bool:
        return self.outcome is VerificationOutcome.VERIFIED


def extract_code(text: str) -> str:
    """Pull the last Python code block (or bare snippet) from a solution."""
    lines = (text or "").splitlines()
    acc: list[str] = []
    in_block = False
    for line in lines:
        if line.strip().startswith("```"):
            if in_block:
                in_block = False
                break
            in_block = True
            continue
        if in_block:
            acc.append(line)
    if acc:
        return "\n".join(acc)
    return (text or "").strip()


def run_sandbox_code(code: str, timeout: float = 5.0) -> dict:
    """Run ``code`` in the hardened sandbox; returns result dict."""
    start = time.monotonic()
    violation = _sandbox_ast_violation(code)
    if violation:
        return {
            "ok": False,
            "error": f"violation: {violation}",
            "exit_code": None,
            "stdout": "",
            "time": time.monotonic() - start,
        }
    timeout = min(max(timeout, 1.0), MAX_TIMEOUT_S)
    env = {"PATH": os_env_path(), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=tempfile.gettempdir(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"timed out after {timeout}s",
            "exit_code": None,
            "stdout": "",
            "time": timeout,
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": f"spawn failed: {exc}",
            "exit_code": None,
            "stdout": "",
            "time": time.monotonic() - start,
        }
    return {
        "ok": proc.returncode == 0,
        "error": (proc.stderr or "")[:2000] if proc.returncode != 0 else "",
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "")[:MAX_OUTPUT],
        "time": time.monotonic() - start,
    }


def _canonical_answer(problem: Any) -> Optional[str]:
    raw_expect = getattr(problem, "canonical_answer", None) or ""
    if raw_expect:
        return str(raw_expect).strip()
    metadata = getattr(problem, "metadata", None) or {}
    if hasattr(metadata, "get"):
        expect = metadata.get("canonical_answer")
        return str(expect).strip() if expect else None
    return None


def _looks_equal(a: str, b: str, *, numeric: bool) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    if a == b:
        return True
    if numeric:
        try:
            return abs(float(a) - float(b)) < 1e-6
        except ValueError:
            return _strip_tokens(a) in _strip_tokens(b) or _strip_tokens(b) in _strip_tokens(a)
    return _strip_tokens(a) == _strip_tokens(b) or _strip_tokens(a) in _strip_tokens(b)


def _strip_tokens(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def verify_problem(problem: Any, solution: str, *, timeout: float = 5.0) -> VerificationResult:
    """Verify a ``solution`` against a curriculum ``problem``.

    Order: canonical-answer match, then sandbox execution when the solution
    looks like code, then an honest ``UNVERIFIABLE``.
    """
    canonical = _canonical_answer(problem)
    format_hint = (getattr(problem, "expected_format", "") or "").lower()
    is_code = "code" in format_hint or "program" in format_hint or solution.lstrip().startswith("```")

    if canonical:
        numeric = any(k in format_hint for k in ("number", "integer", "value"))
        if _looks_equal(canonical, extract_code(solution) or solution, numeric=numeric):
            return VerificationResult(
                outcome=VerificationOutcome.VERIFIED,
                evidence=f"matches canonical answer ({canonical[:80]})",
                method="canonical" if not numeric else "numeric",
            )
        return VerificationResult(
            outcome=VerificationOutcome.REFUTED,
            evidence=f"does not match canonical answer (expected {canonical[:80]})",
            method="canonical" if not numeric else "numeric",
        )

    code = extract_code(solution)
    if is_code and code:
        result = run_sandbox_code(code, timeout=timeout)
        if result["ok"]:
            return VerificationResult(
                outcome=VerificationOutcome.VERIFIED,
                evidence=f"sandbox executed cleanly (exit 0): {result['stdout'][:200]}",
                method="sandbox",
                stdout=result["stdout"],
                exit_code=0,
                duration_ms=float(result["time"]) * 1000,
            )
        return VerificationResult(
            outcome=VerificationOutcome.REFUTED,
            evidence=f"sandbox execution failed: {result['error'][:200]}",
            method="sandbox",
            stdout=result["stdout"],
            exit_code=result["exit_code"],
            duration_ms=float(result["time"]) * 1000,
        )

    return VerificationResult(
        outcome=VerificationOutcome.UNVERIFIABLE,
        evidence="open-ended problem with no canonical answer and no runnable "
        "artifact; route to teacher critique + research evidence",
        method="unverifiable",
    )