# Canonical backend (selection + startup)

## 1. Selection

The **canonical, reproducible** backend is the **tracked** FastAPI package:

```
_tier1/canonical_repo/platform/jarvis_backend/
```

- `main.py` wires 44 routers — including `routers/legacy.py`, which serves the Next.js chat SSE
  contract (`/api/v1/chat/stream`, `/api/chat/sessions`, `/api/chat/history/{id}`,
  `/api/chat/switch`, …) — and mounts the Silverwing brain runtime at `/silverwing`.
- `core.py` defines `app = FastAPI(...)` plus `start_backend`, `create_token`, `get_store`,
  `is_admin`, `hash_password`, `now_iso`.
- It is the **only** `jarvis_backend` copy in git, so a clean checkout can build and run it.

The git-ignored `Jarvis-super-intelligence-/jarvis_backend/` is a richer **local superset**
(celery / grpc / a2a / temporal / langsmith / phoenix / `openai_compat` + `secret_config.py` +
`data/`). It is **not** committed and is **not** reproducible from a clean clone; `start_jarvis.py`
imports it. Treat it as a **merge-from** source (secret-scrubbed, file-by-file), never as the
canonical source of truth. Full evidence: `BACKEND_RECONCILIATION.md`.

## 2. Authoritative startup (dev)

```
python start_jarvis.py        # repo root, tracked
```

What it does:
- Sets `JARVIS_TEST_MODE=1`, `JARVIS_ENV=dev`.
- Inserts `Jarvis-super-intelligence-/` on `sys.path` and imports
  `from jarvis_backend.core import (start_backend, get_store, create_token, is_admin, hash_password, now_iso)`
  and `from jarvis_backend.main import app`.
- Seeds `admin@jarvis.local` idempotently.
- Mints an admin JWT -> writes **`_token.txt`** (gitignored; do not commit; never print).
- `uvicorn.run(app, host="127.0.0.1", port=8000)`.
- Serves the documented endpoints:
  `/api/v1/system/{status,identity,capabilities,dashboard,diagnose,processes,files,provider-settings,models,services}`
  plus the 44-router table (`/api/v1/auth/*`, `/api/v1/chat`, `/api/v1/chat/stream`, `/api/v1/voice/*`,
  `/api/v1/agents/*`, `/api/v1/monitoring/*`, `/api/v1/stark/*`, `/api/v1/browser/*`, …).

Equivalent direct entry (git-ignored operational bootstrap):
`python jarvis_api.py` -> `uvicorn jarvis_backend.main:app 0.0.0.0:8000` (no admin seeding).

## 3. Do NOT use

- `start_jarvis_unified.py` and `start_unified_jarvis.py` — these generate a synthetic
  `unified_backend.py` with 7 stub routes (`/`, `/api/v1/status`, `/components`, `/metrics`,
  `/control/{action}`, `/drive/status`, `/ai/status`, `/monitoring/dashboard`) that **collide** with
  the real app on `/` and `/api/v1/status` and serve **none** of chat/auth/voice. **Preserve**
  (do not delete); **deprecate** once consumers are reviewed.

## 4. Pre-requisites / blockers

This sandbox is not authorized to run the backend and cannot satisfy its pre-requisites, so no
runtime claim is made here:

- **PostgreSQL** + `DATABASE_URL` (or the in-memory/test schema used when `JARVIS_TEST_MODE=1`).
- **Provider API keys** (`OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`/Claude,
  `NVIDIA_API_KEY`, `HF_TOKEN`, …) and **OAuth** client secrets (`JARVIS_OAUTH_*_CLIENT_ID/SECRET`).
- A **brain runtime / local Silverwing** model (PyTorch + Qwen3-4B-SFT weights; no GPU/model here).
- `JARVIS_SECRET_KEY` >= 32 chars in production (enforced by `start_jarvis.py`).

See `AGENTS.md` §10 (Backend area) and `BACKEND_RECONCILIATION.md` §6 for the per-service status
table.
