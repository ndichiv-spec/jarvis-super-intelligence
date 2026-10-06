# JARVIS Recovery Failure Matrix

| Component | Source | Runtime | Browser | Status |
|-----------|--------|---------|---------|--------|
| **Auth** | auth.py:login() | PASS (code correct) | NOT RUN | FAIL |
| Admin seeding | core.py:start_backend() | PASS (code correct) | NOT RUN | FAIL |
| Email verification bypass | auth.py:require_email_verified() | PASS (exists) | NOT RUN | INFO |
| **Database** | db.py:kv_load/save() | SQL/SQLite | NOT RUN | INFO |
| **Runtime Status** | runtime_status.py | routes mounted | NOT RUN | INFO |
| **Chat** | routers/chat.py | NOT RUN | NOT RUN | NOT RUN |
| **Streaming** | SSE endpoints | NOT RUN | NOT RUN | NOT RUN |
| **NVIDIA** | providers/ | DEGRADED | NOT RUN | INFO |
| **Google** | providers/ | DEGRADED | NOT RUN | INFO |
| **OpenAI** | providers/ | DEGRADED | NOT RUN | INFO |
| **Brain** | silverwing/ | UNREACHABLE | NOT RUN | INFO |
| **Silverwing** | silverwing/ | UNREACHABLE | NOT RUN | INFO |
| **Kaggle** | providers/ | CONFIGURED | NOT RUN | INFO |
| **HuggingFace** | providers/ | CONFIGURED | NOT RUN | INFO |
| **Holographic UI** | frontend/ | NOT RUN | NOT RUN | NOT RUN |
| **Dashboard** | frontend/ | NOT RUN | NOT RUN | NOT RUN |

## Status Legend
- **PASS**: Code/surface verified working
- **FAIL**: Actual defect found
- **INFO**: Configuration exists but unverified at runtime
- **NOT RUN**: Component not executed/tested
- **STALE**: Unclear if matches running code

## Critical Root Causes

### 1. Authentication Failure (401)
**Cause**: Admin account not properly seeded due to:
- Missing `JARVIS_ADMIN_PASSWORD` environment variable, OR
- Database clearing between runs, OR
- Role assignment not persisting

**Fix**: Ensure `JARVIS_ADMIN_PASSWORD` is set in .env before starting

### 2. Runtime Status Routing
**Status**: PASS in source, but routes must be in correct order
- `runtime_status_router` MUST come before `misc.router`
- This is already correct in `main.py`

### 3. Process Lifecycle
**Cause**: Background shell sessions in agent environment may timeout
**Fix**: Use `scripts/dev-start.ps1` and `scripts/dev-stop.ps1` for stable process management

### 4. Frontend Build Broken
**Cause**: `prerender-manifest.json` missing for `output: 'standalone'`
**Fix**: Use `next dev` (development mode) which doesn't require this file

## Database Configuration
- **Type**: SQLite (default at `jarvis_data/jarvis.db`)
- **Test DB**: `tests/_test_jarvis.db`
- **Production**: Requires `DATABASE_URL` environment variable

## Environment Variables (Names Recorded)
- `JARVIS_ADMIN_EMAIL` → `ndichiv@gmail.com`
- `JARVIS_ADMIN_PASSWORD` → `<HIDDEN>`
- `SMTP_HOST` → `smtp.gmail.com`
- `SMTP_USER` → `ndichiv@gmail.com`
- `SMTP_PASSWORD` → `<HIDDEN>`
- `KAGGLE_USERNAME` → `videlisndichi`
- `KAGGLE_KEY` → `<HIDDEN>`
- `KAGGLE_API_TOKEN` → `<HIDDEN>`
- `HF_TOKEN` → `<HIDDEN>`
- `NVIDIA_API_KEY` → `<HIDDEN>`

## Files Changed During Development
**Do NOT modify if not directly related to recovery:**
- `drive_engine/project_initializer.py` - Grafana config
- `.env` - SMTP/Admin credentials (updated)
- `frontend/web/src/app/login/page.tsx` - Removed credential disclosure
- `jarvis_backend/runtime_status.py` - Added CONFIGURED state
- `jarvis_backend/routers/misc.py` - Reordered routes