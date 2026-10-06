# JARVIS Recovery Baseline

## Repository State

- **Current Branch**: main
- **HEAD Commit**: b0a8835f6d5fb674b04757a4900279e6c9a7f804
- **Commit Message**: Document GitHub publishing fallback
- **Modified Files Count**: 78
- **Staged Changes**: 2 (1 deleted, 1 new)
- **Untracked Files**: 300+

## Staged Changes
- Deleted: `frontend/web/src/components/chat/chat-message.tsx`
- New: `tests/test_browser_adversarial.py`

## Modified Files (Not Staged)
- drive_engine/project_initializer.py
- frontend/dashboard/main_dashboard.py
- frontend/dashboard/web_dashboard.py
- frontend/static/holographic.css
- frontend/static/script.js
- frontend/templates/index.html
- frontend/web/next.config.mjs
- frontend/web/src/app/billing/page.tsx
- frontend/web/src/app/dashboard/** (multiple files)
- jarvis_backend/core.py
- jarvis_backend/main.py
- jarvis_backend/routers/misc.py
- tests/test_auth.py
- tests/conftest.py
- tests/test_server.py
- And 50+ more frontend files

## Process Status

- **Running Python Processes**: None detected
- **Port 8000**: Not in use
- **Port 3000**: Not in use

## Entry Points

### Backend Entrypoint
- **Primary**: `jarvis_api.py` (root directory)
- **Alternative**: `start_all.py` (unified launcher)
- **App Factory**: `jarvis_backend.main:build_app()`

### Frontend Entrypoint
- **Dev**: `frontend/web/package.json` → `npm run dev`
- **Build**: `frontend/web/package.json` → `npm run build`
- **Next Config**: `frontend/web/next.config.mjs`

## Environment

- **Python**: 3.13.14
- **Node**: v20.20.2
- **Package Manager**: npm

## Database Configuration

- **Type**: SQLite (default) / PostgreSQL (optional)
- **Default Location**: `jarvis_data/jarvis.db` (SQLite)
- **Production Override**: `DATABASE_URL` environment variable
- **Test Database**: `tests/_test_jarvis.db`

## Environment Variables (Names Only)

### Backend Vars
- OPENAI_API_KEY
- JARVIS_OPENAI_API_KEY
- JARVIS_NVIDIA_API_KEY
- JARVIS_NVIDIA_ENDPOINT
- JARVIS_NVIDIA_MODEL
- JARVIS_ADMIN_EMAIL
- JARVIS_ADMIN_PASSWORD
- SMTP_HOST
- SMTP_PORT
- SMTP_USER
- SMTP_PASSWORD
- KAGGLE_USERNAME
- KAGGLE_KEY
- KAGGLE_API_TOKEN
- HF_TOKEN
- JARVIS_SECRET_KEY

### Frontend Vars
- NEXT_PUBLIC_API_URL
- NEXT_PUBLIC_WS_URL
- NEXT_PUBLIC_SOCKET_URL
- NEXT_PUBLIC_APP_NAME
- NEXT_PUBLIC_APP_VERSION

## Ports
- **Backend API**: 8000
- **Frontend**: 3000

## Key Files for Recovery

1. `/.env` - Environment variables (secrets redacted)
2. `/jarvis_api.py` - Backend entry point
3. `/frontend/web/next.config.mjs` - Frontend routing
4. `/frontend/web/.env.local` - Frontend environment
5. `/jarvis_backend/main.py` - FastAPI app wiring
6. `/jarvis_backend/core.py` - Core application logic
7. `/jarvis_backend/routers/auth.py` - Authentication routes
8. `/jarvis_backend/runtime_status.py` - Runtime status routes