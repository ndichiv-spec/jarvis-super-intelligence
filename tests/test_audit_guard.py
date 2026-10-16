"""Audit regression guard.

These tests pin the audit fixes so they cannot silently regress:

* the Silverwing backends package must stay importable without torch
  (test collection must not depend on the heavy torch install);
* the authoritative ``backend`` package must resolve to the workspace copy,
  never to a ``_tier1/canonical_repo`` mirror;
* the public ``RateLimiter.consume`` contract used by callers/tests exists;
* ``diag_harvest.py`` must stay syntactically valid;
* the audit documents must exist and stay non-empty;
* the conftest stabilisers (httpx ASGITransport, duplicate-package pin) stay.

Run:  pytest tests/test_audit_guard.py -q
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parent.parent


def _run_py(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_silverwing_backends_import_without_torch():
    proc = _run_py(
        "import sys;"
        "import silverwing_runtime.backends as b;"
        "assert 'torch' not in sys.modules, 'torch imported eagerly';"
        "assert b.EchoBackend is not None;"
        "print('ok')"
    )
    assert proc.returncode == 0, proc.stderr


def test_backend_package_resolves_to_workspace():
    proc = _run_py(
        "import importlib.util;"
        "spec = importlib.util.find_spec('backend');"
        "assert spec and spec.origin, 'backend package not found';"
        "origin = spec.origin.replace(chr(92), '/');"
        "assert 'canonical_repo' not in origin, origin;"
        "print(origin)"
    )
    assert proc.returncode == 0, proc.stderr


def test_rate_limiter_consume_contract():
    proc = _run_py(
        "from backend.control_plane.rate_limiter import RateLimiter;"
        "assert hasattr(RateLimiter, 'consume'), 'RateLimiter.consume missing';"
        "print('ok')"
    )
    assert proc.returncode == 0, proc.stderr


def test_diag_harvest_compiles():
    import py_compile

    py_compile.compile(str(WORKSPACE / "diag_harvest.py"), doraise=True)


@pytest.mark.parametrize(
    "rel",
    [
        "AGENTS.md",
        "AUDIT.md",
        "docs/audits/initial-audit-report.md",
        "docs/audits/README.md",
        "docs/audits/audited-baseline.md",
    ],
)
def test_audit_documents_exist(rel):
    p = WORKSPACE / rel
    assert p.is_file(), f"missing audit document: {rel}"
    assert p.stat().st_size > 0, f"empty audit document: {rel}"


def test_conftest_stabilisers_present():
    text = (WORKSPACE / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "ASGITransport" in text, "httpx>=0.28 compatibility removed"
    assert "import providers" in text, "duplicate-package pin removed"
