"""JARVIS verification loops (spec sections 31-32).

Wraps the Silverwing model with checkable reasoning:

* math    : Silverwing draft -> safe calculator -> verified answer
* facts   : Silverwing draft grounded in retrieved knowledge -> cited answer
* code    : reserved (sandbox execution lands here next)

Nothing is ever claimed verified unless the check actually ran; every result
carries ``verification`` provenance (verified / partial / unverified).

Phase 6 Extension: Full verification engine for code, documents, data, jobs,
and artifacts. Integrates with existing ToolRegistry as the single execution
boundary.
"""

from __future__ import annotations

import ast
import csv
import json
import logging
import math as _math
import os
import operator as _op
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from io import StringIO
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("jarvis_backend.verify")

# --------------------------------------------------------------------------- #
# Verification Enums and Dataclasses
# --------------------------------------------------------------------------- #

class VerificationStatus(str, Enum):
    """Verification result states."""
    UNVERIFIED = "unverified"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class VerificationResult:
    """Result of a verification check."""
    verified: bool = False
    status: str = VerificationStatus.UNVERIFIED.value
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "verified": self.verified,
            "status": self.status,
            "description": self.description,
            "details": self.details,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
        }


# --------------------------------------------------------------------------- #
# Safe Arithmetic (original verify.py content)
# --------------------------------------------------------------------------- #

_OPS = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.FloorDiv: _op.floordiv,
    ast.Mod: _op.mod,
    ast.Pow: _op.pow,
    ast.USub: _op.neg,
    ast.UAdd: _op.pos,
}

_FUNCS = {
    "sqrt": _math.sqrt,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}

_EXPR_RE = re.compile(
    r"(?<![\w.])([0-9][0-9\s+\-*/().%^]*[0-9\)])(?![\w(])"
)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCS:
        return float(_FUNCS[node.func.id](*[_eval_node(a) for a in node.args]))
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def safe_calculate(expr: str) -> float:
    """Evaluate a pure-arithmetic expression. No names, no I/O, no eval()."""
    cleaned = expr.replace("^", "**").replace("%", "/100").strip()
    if len(cleaned) > 200:
        raise ValueError("expression too long")
    tree = ast.parse(cleaned, mode="eval")
    result = _eval_node(tree)
    if not _math.isfinite(result):
        raise ValueError("non-finite result")
    return result


def find_math_expressions(text: str) -> List[str]:
    """Heuristic scan for arithmetic expressions worth verifying."""
    found = []
    for m in _EXPR_RE.finditer(text):
        expr = re.sub(r"\s+", "", m.group(1))
        if re.search(r"[+\-*/%^]", expr) and len(expr) >= 3:
            try:
                safe_calculate(expr)
                found.append(m.group(1).strip())
            except Exception:
                continue
    # de-dupe, keep order, cap
    seen, out = set(), []
    for e in found:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:5]


def verify_math(text: str) -> List[Dict[str, Any]]:
    """Calculate every detected expression; returns [{expr, value}]."""
    results = []
    for expr in find_math_expressions(text):
        try:
            results.append({"expr": expr, "value": safe_calculate(expr), "verified": True})
        except Exception as exc:  # noqa: BLE001
            results.append({"expr": expr, "value": None, "verified": False, "error": str(exc)})
    return results


# --------------------------------------------------------------------------- #
# Phase 6 Verification Engine
# --------------------------------------------------------------------------- #

_verification_engine: Optional['VerificationEngine'] = None


class VerificationEngine:
    """
    Verification engine that checks artifacts, code, data, and jobs.
    Uses existing infrastructure where possible (e.g., test execution).
    """

    def __init__(self):
        self._check_cache: Dict[str, VerificationResult] = {}

    # ------------------------------------------------------------------- #
    # Code Verification
    # ------------------------------------------------------------------- #

    def verify_python_syntax(self, code: str) -> VerificationResult:
        """Verify Python code has valid syntax."""
        start = time.time()

        try:
            ast.parse(code)
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=True,
                status=VerificationStatus.PASSED.value,
                description="Python syntax is valid",
                details={"language": "python"},
                duration_ms=duration)
        except SyntaxError as e:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.FAILED.value,
                description=f"Syntax error: {e.msg}",
                details={"line": e.lineno, "offset": e.offset, "text": e.text},
                duration_ms=duration)

    def verify_python_type_check(self, file_path: str, timeout: int = 30) -> VerificationResult:
        """Verify Python code with mypy type checking."""
        start = time.time()

        try:
            result = subprocess.run(
                ["mypy", file_path, "--no-error-summary"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            duration = int((time.time() - start) * 1000)

            if result.returncode == 0:
                return VerificationResult(
                    verified=True,
                    status=VerificationStatus.PASSED.value,
                    description="Type checking passed",
                    details={"tool": "mypy"},
                    duration_ms=duration)
            else:
                errors = result.stdout.strip().split('\n') if result.stdout else []
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.FAILED.value,
                    description="Type checking failed",
                    details={"tool": "mypy", "errors": errors[:10]},
                    duration_ms=duration)
        except subprocess.TimeoutExpired:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.TIMEOUT.value,
                description=f"Type checking timed out after {timeout}s",
                duration_ms=duration)
        except FileNotFoundError:
            return VerificationResult(
                verified=False,
                status=VerificationStatus.PARTIAL.value,
                description="Type checking unavailable (mypy not installed)")

    def verify_tests(self, test_path: str, timeout: int = 60) -> VerificationResult:
        """Verify code by running tests."""
        start = time.time()

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", test_path, "-v", "--tb=no", "-q"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            duration = int((time.time() - start) * 1000)

            stdout = result.stdout
            if "passed" in stdout or result.returncode == 0:
                import re
                passed = re.search(r'(\d+) passed', stdout)
                count = int(passed.group(1)) if passed else "unknown"
                return VerificationResult(
                    verified=True,
                    status=VerificationStatus.PASSED.value,
                    description=f"Tests passed: {count}",
                    details={"tool": "pytest", "test_count": count},
                    duration_ms=duration)
            else:
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.FAILED.value,
                    description="Tests failed",
                    details={"tool": "pytest", "output": stdout[-500:]},
                    duration_ms=duration)
        except subprocess.TimeoutExpired:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.TIMEOUT.value,
                description=f"Tests timed out after {timeout}s",
                duration_ms=duration)
        except FileNotFoundError:
            return VerificationResult(
                verified=False,
                status=VerificationStatus.ERROR.value,
                description="pytest not available")

    def verify_imports(self, file_path: str) -> VerificationResult:
        """Verify Python file can be imported (dependencies check)."""
        start = time.time()

        try:
            with open(file_path, 'r') as f:
                code = f.read()

            compile(code, file_path, 'exec')

            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=True,
                status=VerificationStatus.PASSED.value,
                description="File compiles successfully",
                details={"path": file_path},
                duration_ms=duration)
        except SyntaxError as e:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.FAILED.value,
                description=f"Import verification failed: {e}",
                details={"file": file_path},
                duration_ms=duration)
        except FileNotFoundError:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.FAILED.value,
                description="File not found",
                details={"path": file_path},
                duration_ms=duration)

    # ------------------------------------------------------------------- #
    # Document Verification
    # ------------------------------------------------------------------- #

    def verify_json_document(self, content: str) -> VerificationResult:
        """Verify JSON is valid and parseable."""
        start = time.time()

        try:
            json.loads(content)
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=True,
                status=VerificationStatus.PASSED.value,
                description="Valid JSON document",
                details={"format": "json"},
                duration_ms=duration)
        except json.JSONDecodeError as e:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.FAILED.value,
                description=f"Invalid JSON: {e.msg}",
                details={"line": e.lineno, "column": e.colno},
                duration_ms=duration)

    def verify_csv_document(self, content: str) -> VerificationResult:
        """Verify CSV has valid structure."""
        start = time.time()

        try:
            reader = csv.reader(StringIO(content))
            rows = list(reader)

            if len(rows) == 0:
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.FAILED.value,
                    description="Empty CSV document",
                    duration_ms=int((time.time() - start) * 1000))

            header_cols = len(rows[0])
            for i, row in enumerate(rows[1:], 1):
                if len(row) != header_cols:
                    return VerificationResult(
                        verified=False,
                        status=VerificationStatus.FAILED.value,
                        description=f"Inconsistent column count at row {i}",
                        details={"expected": header_cols, "got": len(row)},
                        duration_ms=int((time.time() - start) * 1000))

            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=True,
                status=VerificationStatus.PASSED.value,
                description=f"Valid CSV with {len(rows)} rows, {header_cols} columns",
                details={"rows": len(rows), "columns": header_cols},
                duration_ms=duration)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.ERROR.value,
                description=f"CSV verification error: {str(e)}",
                duration_ms=duration)

    def verify_schema(self, data: dict, schema: dict) -> VerificationResult:
        """Verify data conforms to JSON Schema."""
        start = time.time()

        try:
            import jsonschema
            jsonschema.validate(instance=data, schema=schema)
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=True,
                status=VerificationStatus.PASSED.value,
                description="Data conforms to schema",
                details={"schema_type": schema.get("type", "unknown")},
                duration_ms=duration)
        except jsonschema.ValidationError as e:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.FAILED.value,
                description=f"Schema validation failed: {e.message}",
                details={"path": list(e.path), "instance": str(e.instance)[:100]},
                duration_ms=duration)
        except ImportError:
            return VerificationResult(
                verified=False,
                status=VerificationStatus.PARTIAL.value,
                description="Schema validation unavailable (jsonschema not installed)")

    # ------------------------------------------------------------------- #
    # Data Verification
    # ------------------------------------------------------------------- #

    def verify_file_exists(self, file_path: str) -> VerificationResult:
        """Verify a file exists and is readable."""
        start = time.time()

        if os.path.exists(file_path) and os.path.isfile(file_path):
            size = os.path.getsize(file_path)
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=True,
                status=VerificationStatus.PASSED.value,
                description=f"File exists ({size} bytes)",
                details={"path": file_path, "size": size},
                duration_ms=duration)
        else:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.FAILED.value,
                description="File not found",
                details={"path": file_path},
                duration_ms=duration)

    def verify_file_extension(self, file_path: str, expected_extensions: List[str]) -> VerificationResult:
        """Verify file has expected extension."""
        start = time.time()

        actual_ext = os.path.splitext(file_path)[1].lower()
        expected = [e.lower() if e.startswith('.') else f'.{e.lower()}' for e in expected_extensions]

        if actual_ext in expected:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=True,
                status=VerificationStatus.PASSED.value,
                description=f"File has expected extension: {actual_ext}",
                details={"path": file_path, "extension": actual_ext},
                duration_ms=duration)
        else:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.FAILED.value,
                description=f"Unexpected extension: {actual_ext}",
                details={"expected": expected, "actual": actual_ext},
                duration_ms=duration)

    # ------------------------------------------------------------------- #
    # Job/Artifact Verification
    # ------------------------------------------------------------------- #

    def verify_job_status(self, job_id: str, job_registry=None) -> VerificationResult:
        """Verify a job completed successfully."""
        start = time.time()

        try:
            job = job_registry.get_job(job_id) if job_registry else None

            if job is None:
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.FAILED.value,
                    description="Job not found")

            status = job.get("status", "unknown") if isinstance(job, dict) else getattr(job, 'status', 'unknown')

            if status == "completed":
                duration = int((time.time() - start) * 1000)
                return VerificationResult(
                    verified=True,
                    status=VerificationStatus.PASSED.value,
                    description="Job completed successfully",
                    details={"job_id": job_id, "status": status},
                    duration_ms=duration)
            else:
                duration = int((time.time() - start) * 1000)
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.FAILED.value,
                    description=f"Job status: {status}",
                    details={"job_id": job_id, "status": status},
                    duration_ms=duration)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.ERROR.value,
                description=f"Job verification error: {str(e)}",
                duration_ms=duration)

    def verify_artifact_exists(self, artifact_id: str, artifact_registry=None) -> VerificationResult:
        """Verify an artifact exists and is accessible."""
        start = time.time()

        try:
            artifact = artifact_registry.get_artifact(artifact_id) if artifact_registry else None

            if artifact is None:
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.FAILED.value,
                    description="Artifact not found")

            artifact_type = artifact.get("type") if isinstance(artifact, dict) else getattr(artifact, 'type', 'unknown')

            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=True,
                status=VerificationStatus.PASSED.value,
                description=f"Artifact exists: {artifact_type}",
                details={"artifact_id": artifact_id, "type": artifact_type},
                duration_ms=duration)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return VerificationResult(
                verified=False,
                status=VerificationStatus.ERROR.value,
                description=f"Artifact verification error: {str(e)}",
                duration_ms=duration)

    # ------------------------------------------------------------------- #
    # Composite Verification
    # ------------------------------------------------------------------- #

    def verify_composite(
        self,
        results: List[VerificationResult],
        require_all: bool = True
    ) -> VerificationResult:
        """Combine multiple verification results."""
        if not results:
            return VerificationResult(
                verified=False,
                status=VerificationStatus.ERROR.value,
                description="No verification results provided")

        total_duration = sum(r.duration_ms for r in results)

        if require_all:
            all_passed = all(r.verified for r in results)
            any_failed = any(r.status == VerificationStatus.FAILED.value for r in results)

            if all_passed:
                return VerificationResult(
                    verified=True,
                    status=VerificationStatus.PASSED.value,
                    description="All verifications passed",
                    details={"total_checks": len(results)},
                    duration_ms=total_duration)
            elif any_failed:
                failed = [r for r in results if not r.verified]
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.FAILED.value,
                    description=f"Verifications failed: {len(failed)}/{len(results)}",
                    details={"failed_checks": [r.description for r in failed]},
                    duration_ms=total_duration)
            else:
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.PARTIAL.value,
                    description="Some verifications passed",
                    details={"passed": sum(1 for r in results if r.verified)},
                    duration_ms=total_duration)
        else:
            any_passed = any(r.verified for r in results)
            if any_passed:
                return VerificationResult(
                    verified=True,
                    status=VerificationStatus.PASSED.value,
                    description="At least one verification passed",
                    details={"total_checks": len(results)},
                    duration_ms=total_duration)
            else:
                return VerificationResult(
                    verified=False,
                    status=VerificationStatus.FAILED.value,
                    description="No verifications passed",
                    duration_ms=total_duration)


def get_verification_engine() -> VerificationEngine:
    """Get the singleton verification engine instance."""
    global _verification_engine
    if _verification_engine is None:
        _verification_engine = VerificationEngine()
    return _verification_engine


# --------------------------------------------------------------------------- #
# Retrieval (keyword over the local knowledge store)
# --------------------------------------------------------------------------- #
def retrieve(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Keyword retrieval over the local knowledge store (no embeddings yet)."""
    from .core import get_store

    ql = (query or "").lower()
    terms = [t for t in re.findall(r"[a-z0-9]+", ql) if len(t) > 2][:8]
    if not terms:
        return []
    scored = []
    for item in get_store("knowledge").load().values():
        hay = f"{item.get('key', '')} {item.get('value', '')} {' '.join(item.get('tags', []))}".lower()
        score = sum(1 for t in terms if t in hay)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda s: -s[0])
    return [
        {"key": it.get("key"), "value": it.get("value"), "category": it.get("category")}
        for _, it in scored[:limit]
    ]


# --------------------------------------------------------------------------- #
# The verified chat loop (existing functionality, enhanced with Phase 6 features)
# --------------------------------------------------------------------------- #
async def verified_chat(
    text: str,
    model: Optional[str] = None,
    retrieve_limit: int = 3,
) -> Dict[str, Any]:
    """Draft -> verification -> final answer.

    1. Retrieve grounding context for the question.
    2. Verify any arithmetic with the safe calculator.
    3. Ask Silverwing ONCE with context + verified math in the system prompt
       (one model call: the base model is weak, so evidence goes in, not in
       multi-step agentic loops it cannot follow yet).
    4. Return content + sources + verification provenance.
    """
    from .gateway import provider_gateway

    sources = retrieve(text, limit=retrieve_limit)
    math_checks = verify_math(text)

    context_parts = []
    if sources:
        context_parts.append(
            "Retrieved knowledge (use it; cite keys in [brackets]):\n"
            + "\n".join(f"- [{s['key']}] {s['value']}" for s in sources)
        )
    if math_checks:
        verified = [c for c in math_checks if c["verified"]]
        if verified:
            context_parts.append(
                "Calculator-verified arithmetic (trust these values exactly):\n"
                + "\n".join(f"- {c['expr']} = {c['value']}" for c in verified)
            )
    system = (
        "You are JARVIS, answering with the help of verified context.\n"
        + ("\n".join(context_parts) if context_parts else "No retrieved context.")
        + "\nDistinguish known (from context/calculator) vs inferred. "
        "If the context does not contain the answer, say what is unknown."
    )

    result = await provider_gateway.chat(
        [{"role": "user", "content": text}], model=model, system=system,
    )
    verification = (
        "verified" if (sources or math_checks) else "unverified"
    )
    return {
        "content": result["content"],
        "model": result.get("model"),
        "provider": result.get("provider", "silverwing"),
        "latency_ms": result.get("latency_ms"),
        "usage": result.get("usage"),
        "sources": sources,
        "math": math_checks,
        "verification": verification,
    }


# --------------------------------------------------------------------------- #
# Module exports
# --------------------------------------------------------------------------- #
__all__ = [
    "VerificationStatus",
    "VerificationResult",
    "VerificationEngine",
    "get_verification_engine",
    "verify_math",
    "safe_calculate",
    "find_math_expressions",
    "verified_chat",
    "retrieve",
]