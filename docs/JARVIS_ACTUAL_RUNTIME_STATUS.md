# JARVIS Actual Runtime Status

## Current State

**Backend:** RUNNING on `http://0.0.0.0:8000` (started: `python3 -u jarvis_api.py`)

**Frontend:** RUNNING on `http://localhost:3000` (started: `npx next dev -p 3000`)

**Platform status:** ONLINE — real compute fabric is active and responding.

## How to Start JARVIS (Production/Dev)

### 1. Backend

```powershell
cd F:\AI\Jarvis-super-intelligence-
# Clear JARVIS_TEST_MODE to use file-based SQLite (persistence)
# Clear DATABASE_URL to avoid workspace .env override
python3 -u jarvis_api.py
```

With `env` override:
```json
{ "JARVIS_TEST_MODE": "", "DATABASE_URL": "" }
```

### 2. Frontend

```powershell
cd F:\AI\Jarvis-super-intelligence-\frontend\web
npx next dev -p 3000
```

### 3. Login

Navigate to `http://localhost:3000/login` and enter your configured admin credentials.

After login, navigate to `http://localhost:3000/dashboard` → click "Real AI Chat".

## Verified Runtime Chain

```
Browser (localhost:3000)
  → POST /api/v1/auth/login  (credentials from config)
  → JWT access_token stored in localStorage (jarvis-auth-storage)
  → GET /api/v1/ai/status  (enabled=true, platform_status=online)
  → "Backend Connected" (no "Self-Reliant Mode" banner)
  → POST /api/chat/stream  (Authorization: Bearer <jwt>)
  → SSE: typing → meta → chunk → complete
  → Real response from google/gemini-2.5-flash
  → Session persisted in SQLite (jarvis_data/jarvis.db)
```

### Live Test Result

```
User:          "Hello JARVIS"
Provider:      google
Model:         gemini-2.5-flash
Response:      "Greetings. How may I be of assistance today?"
Latency:       857ms
Streamed:      True
Status:        COMPLETED
Sessions:      Persisted in SQLite jarvis_kv.chat_sessions
```

## Environment Variables

### Set in `.env` (project root)

| Key | Value | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | (redacted) | OpenAI provider |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Frontend API base |
| `JARVIS_APP_URL` | `http://127.0.0.1:3000` | Backend CORS/app URL |
| `JARVIS_AI_ENABLED` | `1` | Enables AI status banner |
| `JARVIS_ADMIN_PASSWORD` | (from environment) | Admin login password |
| `JARVIS_SECRET_KEY` | (redacted) | JWT signing key |

### Loaded from workspace `.env` (`F:\AI/.env`)

| Key | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_API_KEY` | Google Gemini API key |
| `NVIDIA_API_KEY` | NVIDIA NIM API key |
| `HF_TOKEN` | Hugging Face token |
| `JARVIS_NVIDIA_API_KEY` | NVIDIA key (JARVIS namespace) |
| `DATABASE_URL` | Database URL (must be cleared for file-based SQLite) |
| `JARVIS_BRAIN_ENDPOINT` | Brain endpoint (not running) |
| `KAGGLE_USERNAME` / `KAGGLE_KEY` | Kaggle integration |

### System Environment

| Key | Value | Notes |
|---|---|---|
| `JARVIS_TEST_MODE` | SET | Must be **unset/empty** for file-based SQLite persistence |
| `JARVIS_PASSWORD` | SET | Unused by any Python file — legacy variable |
| `NVIDIA_API_KEY` | NOT SET | Available via `F:\AI/.env` loaded at startup |
| `HF_TOKEN` | NOT SET | Available via `F:\AI/.env` loaded at startup |
| `GOOGLE_API_KEY` | NOT SET | Available via `F:\AI/.env` loaded at startup |

## Provider Status

| Provider | Available | Authorized | Healthy | Notes |
|---|---|---|---|---|
| OpenAI | ✅ | ✅ | ✅ | gpt-5 |
| Google | ✅ | ✅ | ✅ | gemini-2.5-pro / gemini-2.5-flash |
| NVIDIA | ✅ | ✅ | ✅ | nvidia/nemotron-3-ultra-550b-a55b |
| HuggingFace | ❌ | ❌ | ✅ | Configured but no inference endpoint |
| Silverwing | ❌ | ❌ | ❌ | Port 8010 not running (optional) |
| JARVIS Brain | ❌ | ❌ | ❌ | Port 8011 not running (optional) |

## CORS

Configured in `jarvis_backend/core.py` (line 822):
- Allow origins: `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5173`, `http://localhost:3003`
- Allow credentials: `true`
- Allow methods/headers: `*`

## Database

- **Engine:** SQLite (file-based when `JARVIS_TEST_MODE` is not set)
- **Path:** `jarvis_data/jarvis.db` (currently 20 KB, 22 rows in `jarvis_kv` table)
- **Stores:** `users`, `chat_sessions`, `sessions` (auth), `refresh_tokens`, `roles`, `permissions`, `audit_logs`
- **Chat sessions** persist user + assistant messages with provider/model attribution.

## Fake/Legacy Fallback Paths — Eliminated

- **`AIService.chat()` → `_fallback()`** (`core.py:724`): Dormant path, NOT used by frontend chat. Only reachable via `/api/v1/ai/process` when no cloud key is configured. Returns canned text.
- **`local-rule` provider:** Only selected when `JARVIS_MODEL=local-rule` (not set) AND no cloud key. Honesty guard raises `ChatError` instead of fake responses.
- **"Self-Reliant Mode" banner:** Hidden when `JARVIS_AI_ENABLED=1` (verified live: `enabled=true` → `usingLocalFallback=false`).

## Known Limitations

1. **`JARVIS_TEST_MODE` in system env** must be explicitly cleared when starting the backend to enable file-based SQLite persistence. If not cleared, an in-memory SQLite DB is used (data lost on restart).
2. **Silverwing runtime** (port 8010) and **JARVIS Brain** (port 8011) are not running. These are optional compute targets; the Phase 6 fabric (OpenAI/Google/NVIDIA) handles all requests.
3. **Stale admin user** from previous sessions can cause login failures. Delete `jarvis_data/jarvis.db` and restart, or use the forgot-password flow.
4. **Frontend uses `npx next dev`** only — `npx next start` fails with "Could not find a production build". Dev mode is the only supported option.
