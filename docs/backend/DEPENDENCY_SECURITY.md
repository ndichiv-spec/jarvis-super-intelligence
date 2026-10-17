# Phase 4 — Dependency Security

**Scope.** This report covers the Phase-4 dependency-security inspection for the
`jarvis-super-intelligence` repository (branch `unify/backend-reconciliation`,
commit `4026357a3ee2055e8a809547d267c727940922b1` (local HEAD; remote origin `d7f7e5cf95` -- push blocked; PR #6 unverifiable: api.github.com unreachable, no egress). It records (a) the vulnerable-dependency findings, (b) the
targeted remediation applied to `_tier1/canonical_repo/platform/requirements.txt`,
and (c) an isolated `pip-audit` before/after proof.

Two distinct environments are referenced below:

- **Live sandbox env** — the agent's full Python 3.13.14 environment (kitchen-sink
  install), scanned by the prior agent: **68 known vulnerabilities / 15
  packages**, `pip-audit` exit 1. This includes transitive and *editable* installs
  from a separate local PyCharm project (`C:\Users\Administrator\PyCharmProjects\Jarvis\packages\*`)
  that are **not** this repo's tracked source.
- **Isolated audit venv** (`C:\tmp\jarvis_audit_venv`) — created in this session
  with **only** the 7 in-scope packages installed (no ML runtime), to produce a
  reproducible before/after proof for the Phase-4 pin bumps.

## Remediation applied

The following directly-pinned entries in
`_tier1/canonical_repo/platform/requirements.txt` (the `SECURITY FIXES` and
`AUTHENTICATION` blocks) were hardened. No major-version jumps were taken on
auth-critical runtime packages; only within-major bumps to fixed releases.

| Package | Before | After | Advisory IDs | Fixed in |
|---------|--------|-------|--------------|----------|
| `gitpython` | `3.1.50` | `3.1.60` | PYSEC-2026-3783, -3784, -3785, -3786, -3787, -3788, -3836, -3837, -3838, -3839, -3840, -3841, -3842, -3843, -3947, -3948, -3950, -3951, -3952, -3953, -3981, -3982, -3984, -3995 | 3.1.60 |
| `urllib3` | `2.7.0` | `2.8.0` | PYSEC-2026-4175, -4176, -4177 | 2.8.0 |
| `PyJWT` | `>=2.9.0` (2.13.0) | `>=2.15.0` | PYSEC-2026-4140, -4141, -4142, -4143, -4144, -4145, -4146, -4147, -4148, -4149, -4150, -4151, -4152, -4183 | 2.15.0 |
| `mcp` | `>=2.1.1,<3` (2.1.1) | `>=2.2.0,<3` | CVE-2026-59951 | 2.2.0 |
| `multidict` | *(unpinned; 6.7.1 via aiohttp)* | `>=6.9.1` (added) | PYSEC-2026-4244 | 6.9.1 |
| `pip` (build tool) | `>=26.1` (26.1.2) | `>=26.2` (26.2.1) | PYSEC-2026-3721 | 26.2 |

### Usage notes (is the vulnerable package used in production?)

- **`mcp` — USED IN PRODUCTION.** `jarvis_backend/mcp_runtime.py` imports
  `mcp.server.mcpserver.MCPServer`, `mcp.server.transport_security.TransportSecuritySettings`,
  and `mcp.types`; it is consumed by `jarvis_backend/routers/health.py`
  (`mcp_status`) and `jarvis_backend/runtime_status.py`. The CVE-2026-59951
  remediation (2.1.1 -> 2.2.0) therefore closes a **high-priority** surface on a
  live MCP server path. Regression coverage: canonical-import clean-venv gate (`import jarvis_backend.main`, 53 routes, MCP/runtime integrated); `tests/test_mcp_runtime.py` is **not present** in this checkout.
- **`gitpython`** — declared in `requirements.txt`'s `SECURITY FIXES` block, but
  **not imported by the audited F:\AI tree modules** (no `import git` / `from git`
  in tracked source). It is consumed by build/workspace tooling that is not part
  of this checkout's runtime import graph. Still hardened because the manifest
  pins it.
- **`PyJWT` / `ecdsa` / `python-jose`** — declared in `requirements.txt` (AUTHENTICATION block);
  the tracked source does **NOT** use `python-jose`. `jarvis_backend/core.py` implements the JWT layer directly with the Python standard library (`create_token`/`decode_token`, HMAC-SHA256, HS256 algorithm) - grep confirms no `import jose` / `from jose` under `_tier1/canonical_repo/platform`. `python-jose[cryptography]>=3.3.0` and `ecdsa>=0.19.2` are declared in `requirements.txt` but are **not** on the production JWT code path.
- **`urllib3` / `multidict`** — transitive (via `requests`/`aiohttp`/`pip`); not
  imported directly by tracked source. Hardened at the manifest level to close
  the advisories for dependents.
- **`pip`** — build/install tool, not a runtime import.

## Before / after proof (isolated pip-audit)

Performed in a fresh venv (`C:\tmp\jarvis_audit_venv`) with **only** these packages
installed (no ML runtime), using system `pip-audit`.

```
# BEFORE (vulnerable pins)
gitpython==3.1.50  urllib3==2.7.0  PyJWT==2.13.0  mcp==2.1.1  multidict==6.7.1  pip==26.1.2
-> python -m pip_audit
Found 55 known vulnerabilities in 7 packages    (exit 1)
#   gitpython 3.1.50   : 32 PYSEC-2026-* rows (3783..3995 series)
#   pyjwt     2.13.0   : 14 rows (PYSEC-2026-4140..4183)
#   urllib3   2.7.0    :  3 rows (PYSEC-2026-4175/4176/4177)
#   pip       26.1.2   :  2 rows (PYSEC-2026-3721)
#   ecdsa     0.19.2   :  2 rows (PYSEC-2026-1325)
#   mcp       2.1.1    :  1 row  (CVE-2026-59951)
#   multidict 6.7.1    :  1 row  (PYSEC-2026-4244)

# AFTER (hardened pins)
gitpython==3.1.60  urllib3==2.8.0  PyJWT==2.15.0  mcp==2.2.0  multidict==6.9.1  pip==26.2.1
-> python -m pip_audit
Found 2 known vulnerabilities in 1 package       (exit 1)
#   ecdsa 0.19.2   :  2 rows (PYSEC-2026-1325)   <- NO upstream fixed version exists
```

**Conclusion.** All six hardened-package advisories are **CLEARED** by the pin
bumps. The only residual is `ecdsa`/`PYSEC-2026-1325`, which has **no fixed
version upstream** (0.19.2 is the current PyPI latest; `ecdsa==0.21.5` does not
exist on PyPI — attempting it aborts the install). `ecdsa` is therefore pinned to
`>=0.19.2` (latest) and its advisory stays **OPEN** pending an upstream release.

## Findings still OPEN (not remediated this pass)

These are out of scope for the within-major, low-risk-bump policy. Several are
env/transitive only and are **not** pinned in this repo's manifest.

| Package | Installed | Advisory | Severity (PyPI) | In repo manifest? | Action |
|---------|-----------|----------|-----------------|-------------------|--------|
| `ecdsa` | 0.19.2 | PYSEC-2026-1325 | medium | yes (`ecdsa>=0.19.2` direct in AUTHENTICATION block; not on JWT path - stdlib HS256) | ⚠️ OPEN — no upstream fix; pin to latest, monitor |
| `python-jose` | 3.5.0 | PYSEC-2026-4298 | medium | yes (`python-jose[cryptography]>=3.3.0` direct; **not imported** by JWT path - stdlib HS256) | ⚠️ OPEN — no upstream fix; not on JWT path (stdlib HS256); medium, low residual |
| `oauthlib` | 3.3.1 | PYSEC-2026-4257 (and others) | high | no — env/transitive only | ⚠️ OPEN — major bump 3->4 deferred (P2 risk) |
| `litellm` | 1.95.0 | (Dependabot, multiple) | — | no — env/transitive only | ⚠️ OPEN — requires major/ecosystem review |
| `pydantic-ai` | 2.32.1 | (Dependabot) | — | no — env/transitive only | ⚠️ OPEN |
| `langgraph-sdk` | 0.4.2 | (Dependabot) | — | no (transitive via `langgraph==1.0.10rc1`) | ⚠️ OPEN — rc/major review |
| `pymongo` | 4.17.0 | (Dependabot) | — | no — transitive (weaviate/pinecone) | ⚠️ OPEN |
| `virtualenv` | 21.7.1 | (Dependabot) | — | no — env only | ⚠️ OPEN |
| `setuptools` | 78.1.0 | (Dependabot) | — | no — env only | ⚠️ OPEN |

The full GitHub Dependabot count on the default branch is **573 open alerts**
(33 critical, 293 high, 196 medium, 51 low) — per `AUDIT.md` P2-5. These are
owner-triage items; the within-scope fix here is the six directly-pinned packages
above plus the documented `ecdsa`/`python-jose` no-fix hold.

## Compatibility risk

- `gitpython` 3.1.50 -> 3.1.60, `urllib3` 2.7.0 -> 2.8.0, `PyJWT` 2.13.0 ->
  2.15.0, `mcp` 2.1.1 -> 2.2.0, `multidict` 6.7.1 -> 6.9.1, `pip` 26.1.x ->
  26.2.x: all **within-major** bumps to stable releases. Backward-compatible;
  `mcp` 2.2.0 is API-compatible with 2.1.x for the `mcp.server.mcpserver` /
  `mcp.types` surface imported by `jarvis_backend/mcp_runtime.py`.
- `ecdsa` left at latest (0.19.2); no API change.
- No major-version jumps introduced (oauthlib 3->4, langgraph-sdk, pydantic-ai,
  litellm explicitly deferred to owner review).

## Regression tests (post-remediation)

The dependency changes are validated by the Phase-3 backend CI gate, all green
from a clean-checkout venv with **no** `torch`/`langchain`/`openai`:

| Check | Command | Result |
|-------|---------|--------|
| Compile (touched files) | `python -W error::SyntaxWarning -m py_compile .../backend-ci.yml` (touched .py) | exit 0 |
| Canonical backend import (clean venv) | `PYTHONPATH=platform JARVIS_TEST_MODE=1 python -c "import jarvis_backend.main"` | `IMPORT_OK`, FastAPI, **53 routes**, identity + MCP runtime integrated; `research_engine` from `_tier1` |
| Clean-CI gated backend suite | `PYTHONPATH=platform pytest tests/test_audit_guard.py tests/test_silverwing_runtime.py tests/test_silverwing_gateway.py tests/test_silverwing_evaluation.py tests/test_provider_fabric.py -q -m "not integration"` (clean venv, no torch/langchain/openai) | **125 passed, 4 skipped, 0 deselected, 0 failed** (129 items; 4 skipped = torch-perplexity in silverwing_evaluation) |
| Collection integrity (full) | `PYTHONPATH=platform pytest --collect-only -q -m "not integration" --continue-on-collection-errors` | **886 collected (875 selected, 11 deselected), 0 import errors** |
| Audit regression guard | `python -m pytest tests/test_audit_guard.py -q` | 10 passed |
| Startup safety regression | `python -m pytest tests/test_startup_safety.py -q` | 7 passed |
| MCP import safety | `mcp_runtime.py` import-safe in clean venv (mcp 2.2.0); `tests/test_mcp_runtime.py` is **not present** in this checkout (no MCP unit test exercised; covered by canonical-import gate + runtime `mcp_status`) | passed (import gate) |

`tests/test_security_gate.py` now **runs under the celery-skipif guard** when invoked directly (**30 passed / 2 skipped** in the clean venv; the 2 skips are the celery-dependent `test_health_ready_public` / `test_api_status_no_auth` status rows). It remains **excluded from the 5-file backend-CI gate** - its `/api/v1/status` / `/health` / `/ready` assertions exercise the **operational** runtime (`Jarvis-super-intelligence-/jarvis_backend/runtime_status.py:700` -> `celery_app.py:8` -> `ModuleNotFoundError: No module named celery`), which the canonical clean-clone backend does not ship; that is op-B-only, not a dependency-version failure.
`/api/v1/status` / `/health` / `/ready` routes import `celery` and call into
monitoring aggregation at request time (BACKEND-1 / operational runtime). It is
not a dependency-version failure and is documented as out-of-clean-CI-scope.

## Evidence artifacts (outside the repo, not committed)

- `C:\tmp\jarvis_audit_venv` — isolated audit venv (not in git).
- `C:\Windows\Temp\pipaudit_old.txt` / `pipaudit_new.txt` — pip-audit before/after
  output captured this session.

## CI enforcement

`.github/workflows/backend-ci.yml` pins the six hardened versions explicitly in
the install step (`gitpython==3.1.60`, `urllib3==2.8.0`, `PyJWT>=2.15.0`,
`mcp>=2.2.0,<3`, `ecdsa>=0.19.2`, `multidict>=6.9.1`) and upgrades pip to
`>=26.2`, then runs a non-gating `pip-audit` step (continue-on-check-failure).
`ecdsa` is pinned to `>=0.19.2` everywhere (0.19.2 is the current PyPI latest;
`0.21.5` does not exist, so `>=0.21.5` is unsatisfiable and is NOT used). No
unsatisfiable pins are shipped.
