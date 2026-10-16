# JARVIS Backend Reconciliation

**Status:** Phase 1–4 evidence + canonical selection (non-destructive).
**Branch:** `unify/backend-reconciliation` (parent `feat/frontend-modernization` @ `041978e`, which stacks on audit PR #4 @ `b8c47c7`).
**Scope rule this pass:** **Inspect, classify, recommend.** No runtime execution, no deletion of the operational reference, no secret scrub-and-commit, no mass rewrite. (Per mandate Phase 3: "If the operational reference cannot safely be inspected or imported, record the precise blocker and continue with non-destructive work.")

This document records **verified repository evidence**. Where a behavior could not be executed in this environment, it is classified `BLOCKED` with the exact command and the missing requirement — never claimed as working.

---

## 0. Executive decisions (from the mandate)

1. Next.js web app is the **PRIMARY UI** (path: `_tier1/canonical_repo/platform/frontend/web/`).
2. One **canonical FastAPI backend** — selected by evidence (see §3).
3. Mobile, desktop, and other interfaces **may remain** but must consume shared backend services, not duplicate core logic.
4. File-by-file reconciliation is authorized **with safeguards** (do not change runtime behavior until mapped; do not mass-replace; preserve existing implementation).
5. `start_jarvis.py` is **NOT** authorized to run in this pass → no admin init, no `_token.txt`, no credential use, no prod DB mutation.
6. No production deployment.
7. Vitest (unit-test) regression guard is authorized to be **added** to the Next.js project (`package-lock.json` may change; no unrelated dependency churn).

---

## 1. Repository topology (tracked vs ignored vs external)

Authoritative git tree = this checkout (`F:\AI`), **not** the git-ignored `Jarvis-super-intelligence-/` siblings. `git ls-files` was used for all counts so git-ignored duplicates are excluded by definition.

| Layer | Tracked path | Role |
|---|---|---|
| **Primary frontend** | `_tier1/canonical_repo/platform/frontend/web/` | Next.js 16 / React 19 / TS (ChatGPT-quality chat+SSE, voice, dashboard, JARVIS theme) |
| **Secondary frontends** | `…/platform/frontend/{jarvis-remix, mobile, jarvis-native}` | Remix / RN-Capacitor / native modules |
| **Python-served holographic UI** | `…/platform/frontend/static/`, `templates/index.html`, + the `unified_backend.py` stub (generated at runtime, **never committed**) | Served by the stub launchers (see §4) |
| **PyQt5 desktop** | `_tier1/canonical_repo/platform/frontend/jarvis_desktop_app.py` | Desktop GUI (`QWebEngineView` embeds a web view) |
| **Canonical backend (reproducible)** | `_tier1/canonical_repo/platform/jarvis_backend/` | FastAPI app (`main.py` wires 44 routers) |
| Backend package A | `_tier1/canonical_repo/backend/` | `model_gateway/` (routing/llm gateway) + `control_plane/` (reconciler, executor, supervisor, auth_runtime, rate_limiter, etc.) |
| Brain runtime | `_tier1/canonical_repo/brain_runtime/` | `backends/{huggingface,nvidia,remote,stub,transformers}`, `server.py` (OpenAI-compat `/v1/*` on :8010) |
| Identity / auth | `_tier1/canonical_repo/identity/` | sessions, models, provider_center (OIDC) |
| Infra / config | `_tier1/canonical_repo/platform/infrastructure/` | settings, provider_registry, model_registry, resilience/ai_provider, migrations |
| Persistence | `_tier1/canonical_repo/platform/memory/` | database.py, migrate_to_postgres.py, `migrations/001_initial_schema.sql` |
| **Operational reference (GIT-IGNORED)** | `Jarvis-super-intelligence-/` + `Jarvis-super-intelligence-/jarvis_backend/` | Live/richer superset; **not in git** (see §2) |
| Root launchers | `_tier1/.../platform/frontend/start_jarvis_unified.py`, `start_unified_jarvis.py`; root `start_jarvis.py`, `start_backend.py`, `start_backend2.py`, `start_silverwing.py` | Orchestrate backend+frontend |
| Tests | root `tests/`, `_tier1/.../platform/tests/`, `e2e_*.py`, `phase6_*.py`, `trace_*.py`, `pytest.ini` | Collected 868 items (Phase 1) |
| CI | `.github/workflows/audit-guard.yml` (Python pytest only) | No backend CI; no frontend CI |
| Env config | `.env.example`, `…/platform/.env.example`, `…/configs/.env.example`, `web/.env.example`, `…/production/.env.example` | Tracked examples; **no secret values** |

**Git-ignore rules (why the operational copy is ignored):** `.gitignore:231` = `/Jarvis-super-intelligence-` (ignored with the literal comment `Jarvis-super-intelligence-`). Env files `.env`, `.env.bak*`, `.env.backup`, `.env.old`, `.env.*.bak` are ignored; only `.env.example` is force-tracked (`!.env.example`). `.venv/`, `venv/` ignored. `.jarvis_uploads/` ignored. **No `.gitattributes`** → tracked files are CRLF (Windows) with no normalization.

**Reproducibility blocker (clean checkout):** The operational `jarvis_backend` is git-ignored, and `start_jarvis.py`/`start_backend.py` hard-code `REPO_ROOT = F:\AI\Jarvis-super-intelligence-`. A clean clone of the repo **cannot** boot the live backend — the canonical FastAPI app that actually runs is *outside* the authoritative tree. See §7.

---

## 2. Backend inventory

### 2.1 Two `jarvis_backend` packages

| | Tracked A: `_tier1/.../jarvis_backend/` | Operational B: `Jarvis-super-intelligence-/jarvis_backend/` |
|---|---|---|
| In git? | ✅ Tracked | ❌ Git-ignored |
| `app` definition | `core.py:837 app = FastAPI(...)`, wired by `main.py` (`setup_routers` includes 44 routers; `legacy`, `auth`, `ai`, `voice`, …) | Same shape; richer (longer files) |
| `start` entry | Bootstrapped indirectly via root `start_jarvis.py` → `from jarvis_backend.main import app` | Bootstrapped by `Jarvis-super-intelligence-/jarvis_api.py` (39 lines: `from jarvis_backend.main import app; uvicorn.run(app, 0.0.0.0, 8000)`) |
| Routers (22 unique files + 42 shared) | 44 routers | 47 routers (shared 42 + `bio_growth`, `notifications`, `openai_compat`, `runtime_events`) |
| `legacy.py` (chat/stream SSE) | ✅ present, wired | ✅ present |
| OpenAI-compat `/v1/chat/completions` | ❌ absent | ✅ `openai_compat.py` |

**Boot path (verified by reading `start_jarvis.py` + `jarvis_api.py`):**
`start_jarvis.py` (root, tracked) sets `REPO_ROOT=r"F:\AI\Jarvis-super-intelligence-"`, inserts it on `sys.path`, then `from jarvis_backend.core import (start_backend, get_store, create_token, is_admin, hash_password, now_iso)` and `from jarvis_backend.main import app`. → **it imports from git-ignored B, not from tracked A.** So the *running* backend is B. A is the reproducible (git-stored) skeleton.

### 2.2 Reconciliation matrix (file-by-file, `diff -rq`, excluding `__pycache__`/`.pyc`/`.venv`)

Source-of-truth: `/tmp/jb_diff.txt` generated by `diff -rq A B`.

| Metric | Tracked (A) | Operational (B) |
|---|---|---|
| Files that **differ** | 49 | — (same 49 pairs) |
| Files **only in tracked** | 12 | — |
| Files **only in operational** | — | 37 |

**Files differing (the reconciliation surface; sample by size):**
| File | tracked L | op L | delta (±) | Notes |
|---|---|---|---|---|
| `core.py` | 1176 | 1417 | +251 (op) | op adds identity/secret helpers, richer start_backend |
| `main.py` | 271 | 376 | +105 (op) | op main.py richer (A2A/MCP/etc. wiring) |
| `gateway.py` | 1308 | 1456 | +296 (op) | Silverwing brain-gateway HTTP client |
| `chat_service.py` | 1714 | 2495 | +781 (op) | Much richer chat orchestration (op) |
| `db.py` | 453 | 835 | +382 (op) | DB layer (op) |
| `brain_fabric.py` | 1410 | 1437 | +65 | |
| `execution_fabric.py` | 1255 | 1281 | +42 | |
| `connectors/registry.py` | 114 | 142 | +62 | |
| `connectors/dispatch.py` | 263 | 335 | +150 | |
| `connectors/mail/connector.py` | 176 | 183 | +13 | |
| `connectors/oauth.py` | 324 | 325 | +17 | |

**Files only in tracked A (12):**
- `gateway.py.before-silverwing-http-fix` → **committed backup artifact** (cleanup candidate; regenerable, not source of truth)
- `endpoint_registry.py` (vs B's `endpoint_gateway.py`)
- `isolated_candidate.py`, `world_resolver.py`, `presentation_contract.py`, `runtime.py`, `mcp_runtime.py` (MCP runtime), `media_storage.py`, `connectors/github.py`, `connectors/_inspect_tests.py`, `connectors/_read_conf_mid.py`, `routers/endpoints.py`

> `mcp_runtime.py` (tracked-only) provides MCP runtime + `mount_mcp`; `main.py` (tracked) imports `from .mcp_runtime import router as mcp_runtime_router, mount_mcp`. Operational replaces this with `mcp_server.py`/`mcp_client.py`, so the MCP *pattern* differs but both exist. Reconcile to one.

**Files only in operational B (37):**
- Routers: `bio_growth.py`, `notifications.py`, `openai_compat.py` (`/v1/chat/completions`), `runtime_events.py`
- Modules: `a2a_server.py`, `celery_app.py`, `celery_tasks.py`, `embeddings.py`, `event_fabric.py`, `grpc_server.py`, `interactions.py`, `langsmith_integration.py`, `mcp_server.py`, `mcp_client.py`, `notifications.py`, `ownership.py`, `path_security.py`, `persistence.py`, `phoenix_integration.py`, `qwen_agent_bridge.py`, `secret_config.py`, `temporal_workflows.py`, `auth_mail.py`, `automation_runners.py`, `bio_growth_worker.py`, `capability.py`, `capabilities/`, `data/`, `platform_identity.py`, `presentation/`, `research/`
- Artifact: `routers/system.py.corrupted-backup-20261001_133146` → **corrupted backup file** (cleanup candidate; do not commit/import)

**Classification of operational-only modules (reconciliation guidance):**
- **OpenAI-compat / multi-provider:** `openai_compat.py` → **useful, migrate to tracked** (OpenAI-format clients, tools).
- **Prod infra (env-dependent, optional):** `celery_app.py`/`celery_tasks.py`, `grpc_server.py`, `a2a_server.py`, `temporal_workflows.py`, `event_fabric.py`, `embeddings.py` → **keep as optional plugins**; they require Redis/Postgres/Celery/gRPC and must not become hard runtime deps of the canonical app.
- **Observability (secrets/env-dependent):** `langsmith_integration.py`, `phoenix_integration.py`, `qwen_agent_bridge.py` → **optional plugins** (need external endpoints/keys).
- **Auth/security (evaluate):** `secret_config.py`, `path_security.py`, `ownership.py`, `auth_mail.py` → **candidate imports** (security-sensitive; review before adopting).
- **Local-only junk:** `system.py.corrupted-backup-20261001_133146` → **exclude** (do not import).

---

## 3. Canonical backend (Phase 2 selection)

**Selected:** the **tracked `_tier1/canonical_repo/platform/jarvis_backend/`** as the canonical, *reproducible* backend.

Rationale (evidence, not filename):
- It is the **only** `jarvis_backend` in git → a clean checkout can build it. B (operational) is git-ignored → not reproducible from source.
- `main.py` (`setup_routers`) wires the **44 routers** including `legacy.py` (the chat/SSE routes) and `auth`, `ai`, `voice`, `agents`, `browser`, `monitoring`, etc. — i.e. it is the real app, not a stub.
- `core.py` defines `app = FastAPI(...)` (837) plus the bootstrap helpers (`start_backend`, `get_store`, `create_token`, `is_admin`, `hash_password`, `now_iso`, `_read_secret_setting`); `runtime_status.py` provides `build_canonical_runtime_status` (called by A's `main.py:unified_status`); `mcp_runtime.py` provides `mount_mcp`. So tracked A is internally consistent and complete for the API contract.
- B is richer (longer `core.py`/`gateway.py`/`chat_service.py`/`db.py`) but carries local secrets, a corrupted-backup file, and prod-infra integrations that must not be hard deps. It is the **local superset to merge FROM, not to copy wholesale.**

**Therefore: do NOT replace A with B.** The safe plan is the reverse: *augment* A with B's missing, generally-useful, non-secret capabilities (§6), one file at a time, each change statically verified.

---

## 4. Startup architecture (Phase 4)

**Authoritative boot (recommended):** `python start_jarvis.py` (root, tracked)
- sets `JARVIS_TEST_MODE=1`, `JARVIS_ENV=dev`;
- `sys.path` → `Jarvis-super-intelligence-` (git-ignored operational ref);
- `from jarvis_backend.core import start_backend` → seeds admin `admin@jarvis.local` idempotently;
- mints admin JWT → writes **`_token.txt`** (plaintext token on disk — see §8 security);
- `from jarvis_backend.main import app` → `uvicorn.run(app, 127.0.0.1:8000)`.
- Documented endpoints: `/api/v1/system/{status,identity,capabilities,dashboard,diagnose,processes,files,provider-settings,models,services}`.

Alternate direct entry: `python jarvis_api.py` (git-ignored operational root) → `uvicorn jarvis_backend.main:app 0.0.0.0:8000` (no admin seeding).

**The two competing stub launchers (to reconcile/decrecate):**
- `start_jarvis_unified.py` and `start_unified_jarvis.py` do **NOT** run the real app. Each **writes a synthetic `unified_backend.py`** (a 7-route FastAPI: `/`, `/api/v1/status`, `/components`, `/metrics`, `/control/{action}`, `/drive/status`, `/ai/status`, `/monitoring/dashboard` backed only by `drive_engine`), then spawns it + `npm run dev`.
- **Conflict:** both stubs define `GET /api/v1/status` and `GET /` — same paths as the real `jarvis_backend/main.py:unified_status`. If both ran, the stub would shadow/collide.
- Neither stub serves `/api/v1/chat/stream`, `/api/v1/auth/*`, `/api/v1/voice/*`, etc. → a Next.js frontend pointed at a stub would 404 on chat/auth/voice.

**Recommendation (not yet applied — non-destructive this pass):** declare `start_jarvis.py` (+ `jarvis_api.py` once imported) the single authoritative backend entry; **deprecate** `start_jarvis_unified.py` and `start_unified_jarvis.py` (mark deprecated + delete only after confirming nothing depends on the stub). Do not delete yet (preserve per mandate §3).

**Model gateway (separate, correct):** `brain_runtime/server.py` is an OpenAI-compatible server (`/v1/models`, `/v1/chat/completions`) launched by `start_silverwing.py` on :8010; integrated into the main app as the mounted sub-app `app.mount("/silverwing", ...)`. ✅ Not a duplicate; keep.

---

## 5. API contract alignment (Phase 3)

Next.js contract (`_tier1/.../frontend/web/src/config/api.ts`) vs tracked backend:

| Frontend expectation (`config/api.ts` / `api-client.ts`) | Tracked `jarvis_backend` route | Status |
|---|---|---|
| `POST /api/v1/auth/{login,register,logout,refresh,me,forgot-password,reset-password,change-password,sessions,api-keys}` | `routers/auth.py` (`/login`,`/register`,`/logout`,`/refresh`,`/me`,`/forgot-password`,`/reset-password`,`/change-password`,`/sessions`,`/sessions/{id}`,`/api-keys`,…api-key rotate, `/verify-email`,`/resend-verification`) | ✅ Live |
| `POST /api/v1/chat` ; `POST /api/v1/chat/stream` (SSE) | `routers/legacy.py` `/api/chat`, `/api/v1/chat`, `/api/chat/stream`, `/api/v1/chat/stream` (wired in `main.py` `setup_routers`) | ✅ Live |
| `GET/POST /api/v1/chat/sessions`, `/…/export`, `/…/history/{id}` | `routers/legacy.py` `/api/chat/sessions`, `/…/export`, `/api/chat/history/{session_id}` | ✅ Live |
| `…/regenerate`, `…/resend`, `…/feedback`, `/switch` | `routers/legacy.py` `/api/chat/messages/{sid}/{mid}/regenerate|resend|feedback`, `/api/chat/switch` | ✅ Live |
| `GET /api/v1/llm` | `routers/ai.py` `/llm/chat`, `/llm/status` | ✅ Live |
| `GET /api/v1/models` (catalog) | `routers/models.py`, `routers/provider_status.py` | ✅ Live |
| `GET/POST /api/v1/agents/...` + collaboration | `routers/agents.py` (task/run/scheduler/collaboration) | ✅ Live |
| `GET /api/v1/monitoring/{metrics,health-report}` | `routers/monitoring.py` | ✅ Live |
| `GET /api/v1/system/...` | `routers/system.py` + `runtime_status.py` | ✅ Live |
| `POST/GET /api/v1/voice/{speak,listen,transcribe,profile,voices,status}` | `routers/voice.py` | ✅ Live (server-side STT) |
| `GET /api/v1/memory/...` | `routers/memory.py` | ✅ Live |
| `GET /api/v1/knowledge/...`, `/api/v1/search` | `routers/knowledge.py`, `routers/search.py` | ✅ Live |
| `/api/v1/stark/...`, `/api/v1/rbac/...`, `/api/v1/automation/...` | `routers/stark.py`, `routers/rbac.py`, `routers/automation.py` (incl `/n8n/*`) | ✅ Live |
| `GET /api/v1/status` (dashboard health) | `main.py:unified_status` + `routers/health.py` | ✅ Live |
| `ws://…/ws/{chat,health,agents}` + `…/voice/ws/chat` + `…/stark/ws/chat` | `routers/websocket.py` (MCP runtime) | ⚠️ Native SSE is the chat transport; WS is MCP/events — label correctly |
| OpenAI-format `/v1/chat/completions` (non-Next.js clients) | `routers/openai_compat.py` | ⚠️ **Operational-only** — candidate to merge into tracked (§6) |
| `GET /api/v1/control/{action}` etc. | stub `unified_backend.py` only | ⚠️ **Stub-only** — not in real `jarvis_backend` (confirms stubs are dev convenience, not canonical) |

**Bottom line:** the Next.js frontend's API contract is **fully implemented by the tracked canonical backend** (via `legacy.py` + the router table). The frontend↔backend link is real, not simulated.

---

## 6. Real-service connections & configuration (Phase 4) — status per service

Environment variables come from `platform/frontend/web/.env.example` (frontend) and the root `…/.env.example` (backend, ~100 keys). Provider keys are **server-side only** (`api-client.ts` Bearer token; no keys in the Next.js bundle).

| Service | Tracked impl | Config | Status (this env) |
|---|---|---|---|
| **AI providers** (OpenAI/Anthropic/Google/NVIDIA/HF/Ollama/AWS/Azure/Vertex) | `brain_runtime/backends/*`, `platform/providers/`, `platform/infrastructure/provider_registry.py`, `platform/silverwing-backend/model_provider.py`, `backend/model_gateway/routing.py`; env `JARVIS_PROVIDER_PRIORITY`, `JARVIS_*_API_KEY`, `JARVIS_*_MODEL` | `.env.example` | ⚠️ Implemented & env-driven; **BLOCKED** — no provider creds/GPU/network here. Exact run: `python start_jarvis.py` then `curl -H "Authorization: Bearer $(cat _token.txt)" http://127.0.0.1:8000/api/v1/ai/status` |
| **Silverwing local model** (Qwen3-4B/SFT) | `silverwing_runtime/`, `silverwing-backend/`; `gateway.py` calls `/v1/chat/completions` on the brain runtime (:8010) | `JARVIS_BRAIN_ENDPOINT`, `SILVERWING_ENDPOINT` | ⚠️ Implemented; **BLOCKED** — needs PyTorch + local model weights (no GPU/model here) |
| **Postgres / Supabase** | `platform/memory/` (`database.py`, `migrate_to_postgres.py`, `migrations/001_initial_schema.sql`, `002_data_migration.py`), `jarvis_backend/db.py` | `DATABASE_URL` / `DATABASE_URL_FILE` (production `.env.example`) | ⚠️ Schema exists; **BLOCKED** — no Postgres here. `start_backend()` runs `create_db_and_tables()`; in `JARVIS_TEST_MODE=1` it uses an in-memory/test schema |
| **Redis** (Celery/broker) | `celery_app.py` (operational-only, optional) | `REDIS_URL` | ⚠️ Optional plugin; **not required** for the core API |
| **n8n / integrations** | `routers/automation.py` (`/n8n/status`, `/n8n/workflows`, `/n8n/workflows/run`), `test_automation_n8n.py` | `N8N_API_KEY`, `N8N_HOST`, `N8N_PORT`, `N8N_ENCRYPTION_KEY`, `N8N_BASIC_AUTH_USER` | ⚠️ Wired; **BLOCKED** — no n8n instance reachable here |
| **Supabase client** | none found in tracked imports | (only mentioned in audit docs) | ❌ Not a tracked code dependency — intended, not wired. **UNKNOWN** whether planned |
| **OAuth identity** (Google/Microsoft/GitHub/GitLab/Slack) | `identity/router.py` (OIDC + Provider Connection Center), `jarvis_backend/routers/auth.py`, `connectors/oauth.py` | `JARVIS_OAUTH_*_CLIENT_ID/SECRET`, `JARVIS_GITHUB_OIDC_*`, `JARVIS_MICROSOFT_OIDC_*` | ⚠️ Implemented; **BLOCKED** — no live OAuth tenant/redirect here |
| **Observability** (LangSmith/Phoenix) | operational-only `langsmith_integration.py`/`phoenix_integration.py` | (env-driven) | ⚠️ Optional plugins; **not required** for core; would need external endpoints |

**Reproducibility blockers (clean checkout):**
1. `start_jarvis.py`/`start_backend.py` import the **git-ignored** `Jarvis-super-intelligence-/jarvis_backend` (hard-coded `REPO_ROOT`). Tracked A is importable but is a *diverged* snapshot — running tracked A directly may not match live behavior.
2. `start_jarvis.py` does `from jarvis_runtime import SILVERWING_BACKEND_ROOT` and `from jarvis_backend.core import …` — both resolve into the git-ignored tree → a clean clone cannot resolve these without bringing operational code into git (secret-scrubbed merge — see §6 merge guidance below).
3. `.env` is git-ignored; secrets via env or `DATABASE_URL_FILE`/`*_FILE_SOURCE` (production reads secrets from files, not env vars — good).

---

## 7. Security-sensitive differences (Phase 5)

| Finding | Location | Risk | Action |
|---|---|---|---|
| **Hard-coded CORS origins** | `start_jarvis_unified.py:35` `allow_origins=["http://localhost:3000"]`; `start_unified_jarvis.py:219` `["http://localhost:3000","http://127.0.0.1:3000"]` | Dev-only CORS, but **not env-driven**; if a stub ever ran in prod → origin lock-in / misconfiguration | Recommend env-driven `ALLOWED_ORIGINS` (comma list). Stub launchers are being deprecated anyway. |
| **Plaintext admin JWT on disk** | `start_jarvis.py:75-78` writes `_token.txt` | Credential-at-rest; `_token.txt` must be git-ignored (it is, via `*.txt`? **not verified** — flag for confirmation) and never committed | Confirm `_token.txt`/token files are ignored; prefer env/`--token`-in-memory for automation. |
| **`JARVIS_TEST_MODE`/dev admin** | `start_jarvis.py:25-26` defaults `JARVIS_TEST_MODE=1`, `JARVIS_ENV=dev`, seeds `admin@jarvis.local`, password `test-password-for-testing` | Dev-only; must never reach production. `_jarvis_persist_test_session.txt` is git-ignored (line 29). | Keep dev-only; never default in prod. |
| **Secrets in operational tree** | `Jarvis-super-intelligence-/jarvis_backend/secret_config.py`, `.env`, `_token.txt`, `data/` | Git-ignored → not committed. But any merge must scrub these. | Any reconciliation must exclude `*.bak`, `secret_config.py`, `data/`, `.env`, token files. |
| **No `.gitattributes`** | repo root | CRLF everywhere; no normalization. New docs written LF (per audit P2-6). | Leave; do not mass-normalize tracked files. |
| **Committed backup artifacts** | `jarvis_backend/gateway.py.before-silverwing-http-fix` (tracked), `routers/system.py.corrupted-backup-20261001_133146` (git-ignored) | Source tree pollution; `.before-*` / `.backup` files should not be tracked. | Recommend `git rm --cached` cleanup of the tracked backup (safe, regenerable) — **deferred** (non-destructive pass). |
| **Supply-chain** | GitHub reports 573 Dependabot alerts on default branch (33 critical / 293 high / 196 moderate / 51 low) | Dependency risk | Out of frontend scope; flagged for owner triage. |

**Authn/authz model (preserved):** bearer JWT (`/api/v1/auth/refresh` single silent refresh; refresh token not rotated — backend limitation), `jarvis-auth-storage` key, `is_admin` gate, OAuth Provider Connection Center, `rbac.py`. Frontend `api-client.ts` enforces 401→refresh once. **Do not weaken.**

---

## 8. Reconciliation guidance (the safe, owner-supervised plan)

The mandate does **not** authorize a blind bulk merge (it cannot be runtime-verified here — no DB/creds/GPU, `start_jarvis.py` not run). The safe, verifiable, non-destructive work performed **this pass**:

- ✅ Phase 1: topology + ignore-rule + reproducibility-blocker evidence (§1, §2).
- ✅ Phase 2: canonical selection — **tracked `jarvis_backend` = canonical reproducible; operational = richer local superset to merge FROM** (§3).
- ✅ Phase 3: API-contract alignment verified against routes (§5).
- ✅ Phase 4: startup conflict identified (`start_jarvis_unified.py`/`start_unified_jarvis.py` stubs collide on `/api/v1/status`); authoritative entry = `start_jarvis.py`.
- ✅ Phase 5: security-sensitive differences enumerated (§7).
- ⏭️ Phase 6 (merge) and startup-path changes are **deferred** to an owner-supervised follow-up because they are runtime-verified changes and `start_jarvis.py` is not authorized this pass.

**Recommended owner-supervised merge steps (not executed here):**
1. Scrub-and-import operational B → a tracked location (exclude `data/`, `.env`, `secret_config.py`, `*.corrupted-backup`, `__pycache__`, `.venv`); bring the non-secret capability modules in.
2. For each of the **49 differing files**: take B's version where B is richer (core.py, gateway.py, chat_service.py, db.py, …) BUT re-apply any tracked-only features (endpoint_registry, mcp_runtime, media_storage, presentation_contract) — **file-by-file**, with `tsc`/`py_compile`/tests on each.
3. Migrate `openai_compat`, `notifications`, `runtime_events` routers into tracked A.
4. Reconcile `endpoint_registry.py` (A) vs `endpoint_gateway.py` (B) → one implementation.
5. `git rm --cached` the committed `gateway.py.before-silverwing-http-fix`; delete the corrupted backup.
6. Replace the two stub launchers with one authoritative `start_jarvis.py`-based entry; delete stubs **after** confirming no consumer.
7. Env-drive CORS in any launcher that keeps `allow_origins`.

**If the operational reference cannot safely be inspected or imported** (e.g., it contains secrets that cannot be separated, or importing it breaks the tracked app in ways not verifiable here): **the precise blocker is recorded above (§1 reproducibility + §7 secrets).** Non-destructive work continues: API-contract mapping, the Vitest regression guard, and documentation.

---

## 9. Verification performed this pass (static only)

| Check | Command | Result |
|---|---|---|
| Audit guard (Python) | `python -m pytest tests/test_audit_guard.py -q` | **10 passed** ✅ (green baseline; untouched) |
| Frontend type-check | `node_modules/.bin/tsc --noEmit` (in `web/`) | **exit 0** ✅ |
| Frontend lint (touched file) | `eslint src/lib/websocket.ts` | refs error gone (PR #5) ✅ |
| Route inventory (tracked) | `git ls-files ... \| grep @router/@app` | 44 routers wired in `main.py` ✅ |
| API-contract alignment | `legacy.py` routes vs `config/api.ts` | chat/stream + sessions/history/regen/resend/feedback/switch all present ✅ |
| `next dev` / backend boot | `python start_jarvis.py` / `next dev` | **NOT run** — (i) `start_jarvis.py` not authorized (seeds admin + writes `_token.txt`); (ii) no Postgres/provider keys/GPU/network here. Exact expected command + missing req recorded in §6. |

Static analysis is **not** proof of runtime integration. No backend was booted this pass; no credentials were read or displayed.
