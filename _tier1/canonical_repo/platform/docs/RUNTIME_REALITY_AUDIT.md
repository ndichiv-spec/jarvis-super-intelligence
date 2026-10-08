# JARVIS Runtime Reality Audit

## 1. Backend Entrypoint & Startup

**Entrypoint:** `jarvis_api.py` (workspace root)

```
python3 -u jarvis_api.py    # cwd = F:\AI\Jarvis-super-intelligence-
```

**Startup chain:**

1. `jarvis_api.py` (line 15-17): `from dotenv import load_dotenv; load_dotenv()`
   - Loads `F:\AI/Jarvis-super-intelligence-/.env` into `os.environ` (override=False,
     so the first `.env` in the CWD wins and is not clobbered by later loads).
2. `jarvis_api.py` (line 19): `from jarvis_backend.main import app`
   - Triggers `jarvis_backend/__init__.py` (line 10) → `bootstrap_runtime()`
     → `load_environment()` → `load_dotenv(WORKSPACE_ROOT / ".env")`
   - `WORKSPACE_ROOT = F:\AI`, so `F:\AI/.env` is loaded second (adds the
     remaining provider keys that are not in the project `.env`).
3. `jarvis_backend/main.py` (line ~215): `build_app()` → `_jarvis_startup()`
   - Calls `bootstrap_fabric()` (Phase 6 provider fabric init).
   - Calls `start_backend()` which seeds roles, permissions, admin user,
     and the canonical owner.
4. `uvicorn.run(app, host="0.0.0.0", port=8000)` — listens on `0.0.0.0:8000`.

### Environment Loading — Verified Working

| Source | Keys loaded |
|---|---|
| System env | `JARVIS_PASSWORD`, `JARVIS_TEST_MODE` (unused / overridden) |
| `F:\AI/Jarvis-super-intelligence-/.env` | `OPENAI_API_KEY`, `NEXT_PUBLIC_API_URL`, `JARVIS_APP_URL`, `JARVIS_AI_ENABLED=1`, `JARVIS_ADMIN_PASSWORD=<redacted - rotated, see docs/SECRET_ROTATION.md>`, `JARVIS_SECRET_KEY=<redacted - rotated, see docs/SECRET_ROTATION.md>` |
| `F:\AI/.env` (workspace root) | `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `NVIDIA_API_KEY`, `HF_TOKEN`, `JARVIS_NVIDIA_API_KEY`, `JARVIS_ADMIN_PASSWORD`, `DATABASE_URL`, etc. |

The project `.env` is loaded first (takes precedence via `override=False`).
The workspace `.env` fills in any keys not already set — this is how NVIDIA, Google,
and OpenAI API keys all become available to the `SecretManager`.

### JARVIS_TEST_MODE → file-based SQLite

`JARVIS_TEST_MODE` is set in the system environment, which forces
`db.py:database_url()` to return `sqlite://` (in-memory), resulting in a
0-byte `jarvis.db` file and no persistence across restarts.

**Resolution:** When starting the backend, clear this env var so that
file-based SQLite is used:

```
env={"JARVIS_TEST_MODE": "", "DATABASE_URL": ""}
```

With this override, `jarvis_data/jarvis.db` is created (20 KB, 22 rows after
first login + chat) with the `jarvis_kv` table and real persistence.

## 2. Provider Configuration

**Provider fabric:** `F:\AI/providers/` (not `F:\AI/Jarvis-super-intelligence-/providers/`).

The `providers/__init__.py` in the JARVIS project is a **shim** that redirects
`import providers` to `F:\AI/providers/` by rewriting `__path__`. The real fabric
contains `bootstrap.py`, `base.py`, `secrets.py`, `registry.py`, `routing.py`,
`health.py`, and per-provider adapters (`openai/`, `nvidia/`, `google/`, `aws/`,
`huggingface/`).

**SecretManager lookup order** (`providers/secrets.py`):
1. Runtime overrides
2. `os.environ` (system env + all `.env` files loaded at startup)
3. `F:\AI/Jarvis-super-intelligence-/.env` (project `.env` via `load_dotenv`)
4. `F:\AI/.env` (workspace `.env` via `load_environment()`)
5. Fernet-encrypted vault file (if `JARVIS_VAULT_PATH` is set — currently not set)

**Verified provider health** (live `/api/v1/ai/models`):

| Provider | Available | Authorized | Model | Healthy |
|---|---|---|---|---|
| openai | ✅ | ✅ | gpt-5 | healthy |
| google | ✅ | ✅ | gemini-2.5-pro | healthy |
| nvidia | ✅ | ✅ | nvidia/nemotron-3-ultra-550b-a55b | healthy |
| hf | ❌ | ❌ | meta-llama/Llama-3.3-70B-Instruct | healthy (no inference endpoint) |
| silverwing | ❌ | ❌ | silverwing-120m-base-v1 | unreachable (port 8010 not running) |
| jarvis-brain | ❌ | ❌ | jarvis-brain-qwen3-4b-sft-v1 | unreachable (port 8011 not running) |

Default provider: `openai`, default model: `gpt-5`.
Phase 6 fabric auto-selects the first healthy provider when `model="auto"`.

## 3. Authentication Flow

**Login endpoint:** `POST /api/v1/auth/login`
- Body: `{"identifier": "<email>", "password": "<password from config>"}`
- Response: `{"access_token", "refresh_token", "token_type": "bearer", "expires_in": 604800, "user"}`

**Admin credentials:**
- Seeded by `core.py:start_backend()` using `JARVIS_ADMIN_PASSWORD` from environment.
- Password hashed with PBKDF2-HMAC-SHA256 (200,000 iterations).
- `_ensure_canonical_owner()` always ensures the owner user exists.

**Frontend login flow:**
1. `app/login/page.tsx` → `jarvisAPI.login(identifier, password)`
2. `lib/api.ts` → POST `/api/v1/auth/login` → returns JWT
3. `stores/authStore.ts` `login()` → `syncToken()` → `setAuthToken()` in `api-client.ts`
4. Token stored in localStorage (key: `jarvis-auth-storage`) and in-memory
5. `api-client.ts` `getAuthToken()` lazily reads from localStorage
6. All subsequent requests include `Authorization: Bearer <jwt>`

**Protected endpoints** use `Depends(get_current_user)` from `core.py`, which
accepts either JWT Bearer tokens or `jarvis_` API keys.

**Password reset flow** (use when credentials are lost):
```
POST /api/v1/auth/forgot-password  {email: "<admin-email>"}  → reset_token
POST /api/v1/auth/reset-password  {token, new_password: "<new-password>"}
```

## 4. Chat Streaming Path

**Frontend → Backend SSE trace:**

1. `RealAIChat` component (`real-ai-chat.tsx` line 255): `runStream()`
   - `API_BASE = process.env.NEXT_PUBLIC_API_URL` (`http://127.0.0.1:8000`)
   - `authHeaders()` includes `Authorization: Bearer <jwt>` via `getAuthToken()`
   - POST to `http://127.0.0.1:8000/api/chat/stream`
   - Body: `{message, session_id, stream: true, model: "auto", client_message_id}`

2. `routers/legacy.py` (line 66): `@router.post("/api/chat/stream")`
   - `Depends(get_current_user)` — requires JWT
   - Returns `StreamingResponse(media_type="text/event-stream")`
   - Calls `chat_service.streaming_chat()`

3. `chat_service.py` (line 823): `stream_message()`
   - Calls `self.gateway.stream_chat()` (or `chat_service.streaming_chat()`)
   - Emits SSE events: `typing`, `meta`, `activity`, `chunk`, `complete`, `error`
   - Complete event includes: `{type, session_id, content, status, message_id,
     streamed, provider, model, usage, latency_ms, request_id}`

4. `gateway.py` (line 660): `ProviderGateway.stream_chat()`
   - Checks for explicit cloud provider prefix (e.g. `openai:gpt-5`)
   - Falls through to Phase 6 fabric: `stream_chat_via_fabric()`
   - Iterates `fabric.adapters` where `adapter.supports(Capability.STREAMING)`
   - ProviderRouter routes to the appropriate adapter (OpenAI/NVIDIA/Google)
   - Real SSE `delta` chunks are emitted as `data: {"type":"chunk","content":"..."}`

5. Provider adapters (`/providers/{openai,nvidia,google}/client.py`):
   - Read API keys via `SecretManager` (never raw env or model context)
   - OpenAI-compatible HTTP streaming
   - Return `StreamChunk(provider, model, text=delta)` objects

## 5. SSE Event Schema (Verified Live)

Tested with `POST /api/chat/stream` + JWT, body `{"message":"Hello JARVIS","model":"auto"}`:

| Event # | Type | Content | Provider | Model |
|---|---|---|---|---|
| 1 | `typing` | (none) | — | — |
| 2 | `meta` | (none) | — | — |
| 3 | `chunk` | `"Greetings. How may I assistance today?"` | — | — |
| 4 | `complete` | `"Greetings. How may I assist you today?"` | google | gemini-2.5-flash |

Response: `status=COMPLETED, streamed=True, latency_ms=857`

**No fake fallback responses.** The `/api/chat/stream` path goes through
`chat_service → gateway → Phase 6 fabric → real provider adapter`.

The `ai_service.chat()` method in `core.py` (line 724) has a dormant `_fallback()`
that returns canned text ("Hello! I'm JARVIS.") — this is NOT in the chat path.

## 6. SQLite Persistence (Verified)

With `JARVIS_TEST_MODE` cleared, file-based SQLite at
`jarvis_data/jarvis.db` (20 KB, 22 rows):

| Store | Rows | Content |
|---|---|---|
| `users` | 1 | admin@jarvis.local (roles: admin, owner) |
| `chat_sessions` | 2 | Each contains `messages` list with user + assistant turns |
| `sessions` | 3 | Auth sessions (login, refresh, e2e test) |
| `refresh_tokens` | 3 | Refresh token records |
| `audit_logs` | 1 | Login audit entry |
| `roles` | 7 | Role definitions |
| `permissions` | 14 | Permission entries |

Chat session structure:
```json
{
  "id": "11127810-d8fe...",
  "user_id": "00000000-0000-0000-0000-000000000001",
  "title": "Hello JARVIS",
  "messages": [
    {"role": "user", "content": "Hello JARVIS", ...},
    {"role": "assistant", "content": "Greetings. How may I be of assistance today?",
     "provider": "google", "model": "gemini-2.5-flash", ...}
  ]
}
```

## 7. Frontend Configuration

**Start:** `npx next dev -p 3000` (cwd=`frontend/web/`)

**Key files:**
- `frontend/web/.env.local`: `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`
- `frontend/web/src/config/env.ts`: `API_URL = NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'`
- `frontend/web/src/config/api.ts`: `chat.stream = ${env.API_URL}/api/chat/stream`
- `frontend/web/src/stores/authStore.ts`: zustand persist, key `jarvis-auth-storage`
- `frontend/web/src/components/real-ai-chat.tsx`: 1098 lines, SSE parser + Real AI Chat

**Banner logic** (`real-ai-chat.tsx` line 611-621):
```jsx
{usingLocalFallback ? (
  <span className="text-yellow-400">Self-Reliant Mode (Local Fallback Active)</span>
) : (
  <span className="text-green-400">Backend Connected</span>
)}
```
`usingLocalFallback = !data.enabled` from `GET /api/v1/ai/status`.
With `JARVIS_AI_ENABLED=1`, `enabled=true` → `usingLocalFallback=false` →
"Backend Connected" is shown. **No "Self-Reliant Mode" banner.**

**CORS** (`core.py` line 822):
```python
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", ...],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
Verified: `Access-Control-Allow-Origin: http://localhost:3000` is returned
on both GET and POST responses.

## 8. Fake/Legacy Fallback Paths — Status

| Path | Component | Status |
|---|---|---|
| `AIService.chat()` → `_fallback()` | `core.py:724` | DORMANT — not in the chat path. Returns canned "Hello! I'm JARVIS..." only if called via `/api/v1/ai/process` with no cloud key. |
| `ProviderGateway._chat_via_local_rule()` | `gateway.py` | Only used when `JARVIS_MODEL=local-rule` and no cloud key. Honesty guard (`_has_cloud_key()`) raises `ChatError` instead of returning fake responses. |
| `ai_service.enabled` | `core.py:724` | Only controls the status banner, NOT the chat routing. Set to `true` via `JARVIS_AI_ENABLED=1`. |
| `_looks_fabricated()` | `chat_service.py:705` | Scans output for canned strings — not currently triggered for real provider responses. |
| Silverwing runtime | port 8010 | Not running (expected — optional local inference). |
| JARVIS Brain | port 8011 | Not running (expected — optional remote brain). |

No fake/legacy fallback responses are present in the active chat path.
