# Canonical backend startup (Phase 2)

This document defines **one authoritative startup path** for the canonical
backend that is reproducible from a clean checkout of branch
`unify/backend-reconciliation`, and explains how the stub launchers
(`start_jarvis_unified.py`, `start_unified_jarvis.py`) are reconciled so they
can no longer shadow the real application.

## 1. What is the canonical backend application?

| Name | Location | Tracked? | Notes |
|------|----------|----------|-------|
| **Canonical FastAPI app** | `_tier1/canonical_repo/platform/jarvis_backend/main.py` → `app = build_app()` | ✅ Git-tracked | Authoritative, reproducible backend. Imports `jarvis_backend.core` (production-startup guard), mounts Silverwing, includes 43 routers (41 in the `setup_routers` loop tuple + `identity_internal` + the external `identity` router; 53 route entries in `app.routes`). |
| Operational superset | `Jarvis-super-intelligence-/jarvis_backend/` (git-ignored) | ❌ Git-ignored | Richer (celery/grpc/a2a/temporal/langsmith + `secret_config.py` + `data/`). Import target is **migration-from**, not canonical. |

- **ASGI target:** `jarvis_backend.main:app`.
- **Module bootstrap:** importing `jarvis_backend` runs
  `jarvis_backend/__init__.py` → `jarvis_runtime.bootstrap_runtime()` →
  `ensure_import_paths()`, which inserts `_tier1/canonical_repo/platform`
  (PROJECT_ROOT) and its parent `_tier1/canonical_repo` (WORKSPACE_ROOT) onto
  `sys.path`. This is why `import jarvis_backend.main` is reproducible from a
  clean checkout with only `PYTHONPATH` pointing at the platform dir
  (see §3).

## 2. Authoritative startup path (clean checkout)

> **Do not run `start_jarvis.py` for the canonical clean-clone boot.** The root
> `start_jarvis.py` is the *authoritative operational* launcher, but it
> hard-codes `REPO_ROOT = F:\AI\Jarvis-super-intelligence-` (the git-ignored
> operational superset) via `sys.path.insert(0, REPO_ROOT)` (lines 37-38), with a guarded `os.chdir` (lines 39-40), and seeds an admin user +
> writes a JWT to `_token.txt`. It is **not** clean-checkout-reproducible and is
> **not authorized to execute in this sandbox** (Phase 5). Use the canonical
> boot below to obtain a reproducible import + route registration from the
> tracked tree alone.

### Disposable test configuration (never touches production)

```dotenv
# All of these are OPTIONAL in dev/test; no production secrets required.
JARVIS_TEST_MODE=1            # dev/test: is_production() is False (JARVIS_ENV not 'production'), so _jarvis_startup skips the SECRET_KEY/ADMIN_PASSWORD/DATABASE_URL/CORS production checks; db falls back to in-memory sqlite://
JARVIS_ENV=dev
DATABASE_URL=sqlite:///./.test_jarvis.db   # sync SQLite (core uses a SYNC engine; sqlite+aiosqlite:// triggers sqlalchemy.exc.MissingGreenlet)
JARVIS_SECRET_KEY=dev-only-not-secret-0123456789abcdef0123456789abcdef  # 64 chars (dev only)
JARVIS_ADMIN_PASSWORD=test-password-for-testing   # 16+ chars (dev only)
JARVIS_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
# Do NOT set live provider keys. Providers that are unconfigured report
# out-of-service; results are never fabricated.
```

These map onto the production guard `is_production()` (`jarvis_backend/core.py:178`),
invoked from the `startup` event `_jarvis_startup` (`jarvis_backend/main.py:458`):
in `JARVIS_TEST_MODE=1` the environment is `dev`/test (not `production`), so
`is_production()` returns False and `_jarvis_startup` skips the
32-char `JARVIS_SECRET_KEY` / 16-char `JARVIS_ADMIN_PASSWORD` / `postgresql://`
`DATABASE_URL` / `JDBC_ORIGINS`-style CORS checks; when `JARVIS_ENV` is
`production`/`prod`, `is_production()` is True and `_jarvis_startup` enforces all
four. There is **no** `require_production_env()` in the tracked source - the guard
is `is_production()` plus `_jarvis_startup` (main.py:458-476).

### Clean-checkout boot command

From a clean checkout of this repo (`F:\AI`), with the canonical platform tree
on the import path:

```powershell
# PowerShell (Windows); use ';' not '&&'
$env:PYTHONPATH = 'F:\AI\_tier1\canonical_repo\platform'
$env:JARVIS_TEST_MODE = '1'
$env:JARVIS_ENV = 'dev'
$env:DATABASE_URL = 'sqlite:///C:/Windows/Temp/jarvis_clean.db'   # sync SQLite (NOT +aiosqlite - core.py/db.py use a SYNC engine)
$env:JARVIS_SECRET_KEY = 'dev-only-not-secret-0123456789abcdef0123456789abcdef'
$env:JARVIS_ADMIN_PASSWORD = 'test-password-for-testing'
$env:JARVIS_CORS_ORIGINS = 'http://localhost:3000'
python -m uvicorn jarvis_backend.main:app --host 127.0.0.1 --port 8000
```

> On POSIX the equivalent is `PYTHONPATH=_tier1/canonical_repo/platform \
> JARVIS_TEST_MODE=1 ... uvicorn jarvis_backend.main:app`.
> **Production deployment** uses `Jarvis-super-intelligence-/jarvis_api.py`
> (operational, git-ignored, owner only) and is out of scope here; do **not**
> deploy or rotate real credentials without owner authorization (AGENTS.md §8).

### Verification (run without executing the server)

The import + route-registration gate does not require the server to bind:

```powershell
$env:PYTHONPATH = 'F:\AI\_tier1\canonical_repo\platform'
python -c "import jarvis_backend.main as m; \
print('routes', len([r for r in m.app.routes]))"
# Expected: a FastAPI app prints, then "routes 53" (canonical route count
# including mounts /api/status /api/v1/status /api/runtime/status /silverwing
# /mcp + the 43 routers' endpoints aggregated under mounts).
```

**Verified this session** in an isolated venv
(`C:\tmp\jarvis_clean_venv`) with only the platform core (non-ML) dependencies
installed — `torch`, `langchain`, `openai`, `transformers` etc. **not**
installed. `import jarvis_backend.main` succeeded, the FastAPI app built, the
identity router integrated (`OIDC + Provider Connection Center`), and
`research_engine` resolved from the **tracked** `_tier1/canonical_repo/research_engine/`
via `ensure_import_paths()`. This closes the P1-4 clean-clone import blocker.

## 3. Stub launchers — deprecation, not deletion

`start_jarvis_unified.py` and `start_unified_jarvis.py` (both at
`_tier1/canonical_repo/platform/frontend/`) are **stub generators**: each
writes a synthetic `unified_backend.py` defining `GET /` and `GET /api/v1/status`
(and a handful of others) and runs *that* instead of `jarvis_backend.main:app`.
The synthetic routes **collide** with the real `jarvis_backend.main`
`unified_status` (BACKEND-2). The stubs serve none of chat/auth/voice.

Per AGENTS.md §3 ("do not remove … entry points until deployment references are
reviewed") the stubs are **preserved** but **deprecated** this pass with a
non-blocking warning banner at the top of each file that (a) states they are
stubs, (b) names the collision, and (c) redirects operators to the canonical
boot in §2 above. The banner does **not** alter the stubs' behavior (so existing
callers are not broken); it makes the collision unmistakable at runtime.

> `unified_jarvis_api.py` (at `...platform/`) is the **compatibility adapter**
> (`unified_jarvis_api:app`), NOT a stub — it is preserved and documented as
> per BACKEND-1/BACKEND-4. It is not deprecated here.

The single-authoritative-entry recommendation (replace the two stubs with one
launcher) is left as the owner action in `MIGRATION_CHECKLIST.md` §"Safe
migration sequence" step 7, gated on the owner-reviewed merge of the operational
capabilities.

## 4. Competing-root launcher hygiene

The repo root also carries `start_backend.py`, `start_backend2.py`, and
`start_silverwing.py` (all tracked, per AGENTS.md §1 root list). These are
**preserved** and are **not** made canonical:
- `start_backend.py` / `start_backend2.py` — legacy alternate backends; not
  referenced by the canonical boot; left as-is.
- `start_silverwing.py` — Silverwing runtime entry; preserved (not the full app).

No root launcher is removed or renamed without a verified grep of its callers;
the canonical full-platform boot is the `uvicorn jarvis_backend.main:app`
invocation in §2.
