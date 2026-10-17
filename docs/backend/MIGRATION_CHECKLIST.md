# Backend Migration Checklist (Phase 1)

Authoritative source of truth for reconciling the two `jarvis_backend`
trees: the **canonical, Git-tracked** backend
`_tier1/canonical_repo/platform/jarvis_backend/` (copy A) and the
**git-ignored operational superset** `Jarvis-super-intelligence-/jarvis_backend/`
(copy B, located at `F:\AI/Jarvis-super-intelligence-/jarvis_backend/` on
this machine).

This document is the **file-by-file migration plan + dependency map**. It is
companion to `BACKEND_RECONCILIATION.md` (esp. §2.2) which carries the
architectural summary. Nothing here is executable against copy B — copy B is
git-ignored and contains local secrets (`secret_config.py`, `data/`, `.env`),
so it must be secret-scrubbed into a tracked location before any file is
imported from it.

## How this was measured (reproducible)

All numbers below are reproduced with the Git for Windows `diff.exe`
(exact byte comparison, no text merge semantics):

```powershell
& 'C:\Program Files\Git\usr\bin\diff.exe' -rq --exclude=__pycache__ --exclude='*.pyc' `
  --exclude=.venv --exclude='*.egg-info' --exclude='.pytest_cache' --exclude='.ruff_cache' `
  '_tier1/canonical_repo/platform/jarvis_backend' 'Jarvis-super-intelligence-/jarvis_backend'
```

Verified result on branch `unify/backend-reconciliation` @ `4026357a3ee2055e8a809547d267c727940922b1` (local HEAD; remote origin `d7f7e5cf95` -- push blocked; PR #6 unverifiable: api.github.com unreachable, no egress):

| Relationship | Count | Meaning |
|--------------|-------|---------|
| `... differ` | **49** | present in A and B, byte-different content |
| `Only in B` (op-only) | **37** | present only in the operational superset |
| `Only in A` (tracked-only) | **12** | present only in canonical / tracked |
| identical | **89** | present in A and B, byte-identical |

> IMPORTANT — the canonical backend does **not** require copy B to *import*.
> `import jarvis_backend.main` succeeds from copy A alone in a clean venv
> (see `STARTUP.md` §"Clean-clone import proof"). The 49/37 differing/op-only
> files are **capability gaps and richer impls to merge from**, not import
> prerequisites. See `BACKEND_RECONCILIATION.md` §1 for the architectural
> rationale of each layer.

## Status of the `start_jarvis.py` import-pin (BACKEND-1)

`start_jarvis.py` (repo root, tracked) hard-codes `REPO_ROOT =
F:\AI\Jarvis-super-intelligence-` and inserts it on `sys.path` *before*
importing `jarvis_backend`. In this sandbox that resolves `jarvis_backend` to
copy B (the git-ignored operational superset), which is why the live boot is not
reproducible from a clean checkout. **Phase 2 (`STARTUP.md`) documents the
canonical, clean-checkout startup path** that does not depend on copy B.

## The 12 tracked-only (canonical) files — must NOT regress

These exist only in A (tracked) and have no operational counterpart. They are
canonical capabilities that copy B was never meant to supersede. Do not delete
or overwrite them when porting:

```
jarvis_backend/endpoint_registry.py
jarvis_backend/isolated_candidate.py
jarvis_backend/world_resolver.py
jarvis_backend/presentation_contract.py
jarvis_backend/runtime.py
jarvis_backend/mcp_runtime.py
jarvis_backend/media_storage.py
jarvis_backend/connectors/github.py
jarvis_backend/connectors/_inspect_tests.py
jarvis_backend/connectors/_read_conf_mid.py
jarvis_backend/routers/endpoints.py
jarvis_backend/gateway.py.before-silverwing-http-fix   # JUNK: committed backup artifact (see §"Backup artifacts")
```

Classification:
- `endpoint_registry.py`, `endpoints.py`, `world_resolver.py`,
  `presentation_contract.py`, `presentation_contract.py` — canonical
  registration / contract layer (API-contract alignment, verified live per
  `BACKEND_RECONCILIATION.md` tail).
- `mcp_runtime.py`, `media_storage.py`, `runtime.py` — canonical runtime
  surface consumed by `main.py`.
- `connectors/github.py` (+ `_inspect_tests.py`, `_read_conf_mid.py`) —
  canonical GitHub connector.
- `gateway.py.before-silverwing-http-fix` — **backup artifact**, not code.
  Must be `git rm --cached` (BACKEND-4 action).

## The 37 operational-only (op-only) files — capability imports, classified

Each below is a candidate for porting into the canonical tree **after
secret-scrubbing** (it lives in copy B, which contains `secret_config.py`,
`data/`, `.env`). Classified by function; migration order is the row order in
the "Safe migration sequence" (see end).

### R (routers to add to canonical `routers/` + register in `setup_routers`)
```
routers/openai_compat.py          # OpenAI-compatible /v1/* proxy (P1-6 compat surface) — HIGH priority
routers/notifications.py         # push/WebPush/email notifications (duplicates root notifications.py → reconcile)
routers/runtime_events.py        # server-sent runtime events endpoint (duplicates root runtime_events.py)
routers/bio_growth.py            # biological-growth demo/telemetry route (simulation — preserve)
```
> `routers/system.py.corrupted-backup-20261001_133146` is **JUNK** (corrupted
> backup). Do NOT port. Delete from any scrubbed staging copy.
> `routers/identity.py` already exists in A (differing) — the op `notifications`/`runtime_events`
> must be merged, not dropped.

### M (modules to port at package root, with lazy/optional guards)
```
secret_config.py                # SECURITY-SENSITIVE (P1-3). Review only. Do NOT copy verbatim.
a2a_server.py                   # A2A agent protocol server (optional; lazy)
celery_app.py / celery_tasks.py # distributed task queue (optional; celery not in core deps)
grpc_server.py                  # gRPC surface (optional; lazy import)
temporal_workflows.py           # Temporal.io workflows (optional; lazy import)
event_fabric.py                 # event fabric / runtime bus
embeddings.py                   # provider-agnostic embedding helper
langsmith_integration.py        # LangSmith tracing (optional; lazy)
phoenix_integration.py          # Arize/Phoenix tracing (optional; lazy)
qwen_agent_bridge.py            # Qwen-Agent bridge (optional; lazy)
mcp_client.py / mcp_server.py   # MCP client/server (mcp is in core deps — safe to import)
platform_identity.py            # platform-level identity helpers
ownership.py                    # ownership/authorization helpers (preserve owner-gate, see P1-2)
path_security.py                # path-traversal hardening (preserve; SECURITY)
persistence.py                  # persistence utilities
auth_mail.py                    # auth-related mailers (lazy)
automation_runners.py           # automation runners
bio_growth_worker.py            # bio-growth worker (simulation — preserve)
capability.py                   # capability helpers
sandbox.py                      # execution sandbox (preserve path_security)
schema_migrations.py            # DB schema migrations (alembic; reconcile with alembic)
interaction.py                  # interaction model
```

### D (directories to reconcile, not wholesale-copy)
```
capabilities/   # capability registry — merge with tracked endpoint_registry.py
data/           # SECURITY-SENSITIVE + generated. Scrub. (secrets, seed data)
presentation/   # presentation layer — port only non-secret config
research/       # research artifacts — port only non-sensitive, non-credential bits
agents/         # agent definitions — port; verify no embedded keys
```

## The 49 differing files — reconciliation strategy

These exist in both A and B with content differences. Treatment per group:

| Group (diff subset in A) | Strategy | Rationale |
|--------------------------|----------|-----------|
| `jarvis_backend/__init__.py` | **A wins** | A already calls `jarvis_runtime.bootstrap_runtime()`; B is the legacy no-op. Keep A. |
| `jarvis_backend/core.py` | **Merge** | A has the production-startup guard block (JARVIS_SECRET_KEY/DATABASE_URL checks); B likely has richer runtime. Port B's runtime bits into A, KEEP A's guards. |
| `jarvis_backend/main.py` | **A wins** | A is verified to build (53 routes, identity integrated) in a clean venv; B may wire the same routers but the canonical `setup_routers` is the tracked source. Port any router addition from B's main into A's `setup_routers` list. |
| `jarvis_backend/gateway.py` | **A wins** (already fixed) | `gateway.py.before-silverwing-http-fix` is the stale backup; current A is the Silverwing-HTTP-fix. Do not regress. |
| `jarvis_backend/observability.py` | **Merge (audit-safe)** | Preserve A's structure; port any extra metrics from B. Keep logging secret-free. |
| `jarvis_backend/db.py` / `brain_fabric.py` / `chat_service.py` | **Merge** | Port B's richer impl into A, keep A's connection guards. |
| `jarvis_backend/runtime_status.py` | **Merge** | B may expose more status fields; add to A. |
| `jarvis_backend/self_improvement.py` / `browser_engine.py` / `execution_fabric.py` | **Merge** | Port B enhancements into A; keep A's entry points. |
| `routers/*.py` (all 28 differing routers) | **Merge per-router** | For each of the 28 routers present in both, diff B against A, port new endpoints into A, keep A's auth/owner-gate. Register any brand-new B router in A's `setup_routers`. |

## Backup artifacts (BACKEND-4) — must be removed

- `jarvis_backend/gateway.py.before-silverwing-http-fix` (canonical, tracked) —
  stale backup of the pre-Silverwing-HTTP fix. `git rm --cached` + disk delete
  as the BACKEND-4 action. Gate: `py_compile` still passes.
- `routers/system.py.corrupted-backup-20261001_133146` — lives only in op copy B;
  it is JUNK. Exclude it from any scrubbed staging. Not in git (B is ignored),
  so no `git rm` needed — just don't port it.

## Precise blockers / why full migration is owner-supervised (NOT done this pass)

This pass does NOT execute the merge (per AGENTS.md §3: "Fix in place";
§6: "do not delete either implementation until reconciled and verified").
Reasons the merge cannot be completed autonomously in this sandbox:

1. **Copy B is git-ignored and secret-bearing.** It contains `secret_config.py`,
   `data/`, and local `.env`. Importing from B requires a human secret-scrub
   step. (P1-3.)
2. **No Postgres / no provider keys / no GPU / no network.** `start_jarvis.py`
   is not authorized to run (Phase 5). The merged backend's runtime paths
   (DB init, provider routing, embeddings) cannot be exercised here.
3. **Dependency drift (P2-4/P2-5).** B was built against the live env (68
   pip-audit vulns, 573 Dependabot alerts, langchain/openai/torch constraint
   drift). Merging B's heavy deps wholesale would widen the vuln surface. Merge
   only what is pinned-safe and importable (e.g. `mcp` is in core deps;
   langchain/torch/openai stay lazy/optional).
4. **Duplication hazard (P1-5).** `backend/`, `providers/`,
   `silverwing_runtime/`, `jarvis_brain/`, `identity/`, `research_engine/`
   exist in three divergent locations. Merging "by basename" is explicitly
   warned against (`JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md` line 9). A
   human must sign off per package before `git rm` of any divergent copy.
5. **`research_engine` is tracked (P1-4 status update).** `research_engine`
   IS present and tracked at `_tier1/canonical_repo/research_engine/` (13 files)
   and at root `research_engine/` (13 files). It is imported automatically once
   `jarvis_backend` is imported (via
   `jarvis_backend/__init__.py` → `jarvis_runtime.bootstrap_runtime()` →
   `ensure_import_paths()`, which adds `_tier1/canonical_repo` to `sys.path`).
   This closes the *import* blocker — no substitution package is needed.
   The remaining P1-4 work is **consistency** (two divergent tracked copies at
   root vs `_tier1`) and is tracked in P1-5.

## Safe migration sequence (owner-supervised, per-file)

Each step is gated by `python -m py_compile` + the relevant test, and a git
`diff` review. Do NOT bulk-copy B → A.

1. **Scrub.** Copy B into a tracked staging dir `docs/backend/_migration_staging/`
   (git-ignored) — actually: stage B's files into a temp dir OUTSIDE the repo,
   delete `secret_config.py`, `data/`, `.env*`, `*.corrupted-backup`,
   `__pycache__`, `.venv` from the staging copy, then `git add -f` only the
   scrubbed `.py`. Review with secret scan before any import.
2. **`__init__.py` / `core.py` / `main.py`.** Adopt A. Port B's router
   registrations into A's `setup_routers`; keep A's startup guard. Verify
   `import jarvis_backend.main` still builds (53 routes) in the clean venv.
3. **Module imports (lazy-first).** For each `M` module, wrap heavy optional
   deps (celery, grpc, temporal, langsmith, phoenix, qwen_agent, torch,
   langchain, openai) in `try/except ImportError` or move to function scope.
   Keep `mcp_client`/`mcp_server`/`path_security`/`ownership`/`embeddings`
   import-safe (no heavy top-level deps).
4. **Routers.** For each of the 28 differing routers, `diff` A vs B, apply B's
   new endpoints into A, keep A's owner-gate + rate limiting. Register new B
   routers (`openai_compat`, `notifications`, `runtime_events`, `bio_growth`)
   in A's `setup_routers` list.
5. **Backup artifacts.** `git rm --cached jarvis_backend/gateway.py.before-silverwing-http-fix`.
6. **Re-lock.** After merge, regenerate the pinned manifest and re-run
   `pip-audit` (Phase 4) + full backend tests.
7. **Flip the launcher.** After merge is verified, `start_jarvis.py` should
   resolve `jarvis_backend` from the canonical tree (Phase 2), not copy B.

## Evidence captured this session

- `import jarvis_backend.main` in a **clean venv** (only platform dir on
  `PYTHONPATH`, cwd ≠ repo, no `research_engine` preinstalled) → builds a
  `FastAPI` app, **53 routes**, identity router integrated,
  `research_engine` resolves from the tracked `_tier1/canonical_repo/research_engine/`
  via `jarvis_runtime.ensure_import_paths()`. No `torch`, no `langchain`, no
  `openai` required for import.
- 13 test files top-level `import jarvis_backend`/`research_engine`; in clean CI
  they collect **only** when `PYTHONPATH` includes the platform dir (so
  `jarvis_backend`/canonical tree is importable) — see Phase 3 CI.
- Diff counts reproduced with Git for Windows `diff.exe` (see command above):
  49 differ / 37 op-only / 12 tracked-only / 89 identical.
