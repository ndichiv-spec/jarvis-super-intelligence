# NVIDIA NIM as Remote JARVIS Brain — Implementation Plan

Spec: wire **NVIDIA-hosted NIM** (`https://integrate.api.nvidia.com/v1`, OpenAI-compatible)
as the **real remote JARVIS Brain backend** using the **EXISTING** architecture.
Do NOT rebuild the platform. Do NOT add a second HTTP client. Do NOT fake health.

## 1. Architecture mapping (spec ↔ real code)

| Spec concept | Real file |
|---|---|
| Model Gateway / JARVIS Brain boundary (:8011) | `jarvis_backend/gateway.py` → `ProviderGateway` + singleton `provider_gateway`; Brain remote tier = `_chat_via_remote_brain`; probe = `probe_brain` |
| JARVIS API | `jarvis_backend/main.py` (FastAPI on :8000); `jarvis_api.py` entrypoint |
| Jarvis Frontend | `frontend/web` (Next 16.2.4 Turbopack, :3000) |
| Silverwing local fallback | `silverwing-backend/model_provider.py` (offline TorchBackend) + `SILVERWING_ENDPOINT=http://127.0.0.1:8010` |
| Existing **generic OpenAI-compatible HTTP client** (the adapter surface §6 wants reused) | `extensions.py::_openai_json_post(url, payload, key)` — Bearer+httpx, 30s, 401/403/429/5xx mapping |
| Provider catalog / status matrix | `extensions.py::_API_KEY_PROVIDERS` + `routers/provider_status.py` (`GET /api/v1/integrations/providers`) |
| `ai_enabled` flag | `core.py::AIService.enabled` (= `JARVIS_AI_ENABLED` env) + `ai.py::/ai/status` |

### Decisive findings
- **`backend` package is MISSING** (`importlib.util.find_spec('backend')` → ModuleNotFoundError) and **`providers` Phase‑6 fabric is NOT importable**. So `gateway.py`'s `_chat_via_remote_brain` (lazy `from backend.model_gateway.n import n`) and the Phase‑6 tier are **dead code**. Both tiers currently raise/return-None → AI is offline even though `OPENAI_API_KEY` is in `.env`.
- **The only WORKING OpenAI-compatible HTTP call** is `extensions.py::_invoke_openai` → `_openai_json_post`. NVIDIA NIM speaks the identical `/v1/chat/completions` + `GET /v1/models` + Bearer shape → **reuse `_openai_json_post`, do not duplicate**.
- **Vault credential resolution** (`infrastructure/vault/manager.py`): backends = `[EnvBackend(prefix="JARVIS_"), DotenvBackend()]`. `get_or_none("brain_api_key")` → env `JARVIS_BRAIN_API_KEY` or `.env` key `brain_api_key`. `NVIDIA_API_KEY` (no `JARVIS_` prefix) is therefore NOT resolved by `EnvBackend` → resolve NVIDIA via direct `os.environ.get("NVIDIA_API_KEY")` (the spec's canonical name) with vault fallback.

## 2. GATING BLOCKER (honest — NOT faked)

`NVIDIA_API_KEY` is **ABSENT**:
- `os.environ` provider-key scan = `[]` (openai/claude/gemini/anthropic/hf/azure/microsoft/copilot all absent)
- vault `get_or_none("nvidia_api_key")` = `None`; `get_secrets_manager().get_or_none('NVIDIA_API_KEY')` = False
- `.env` has `OPENAI_API_KEY` only (no NVIDIA line)
- `list_secrets` → empty

**Consequence per §21/§37:** the §4 live credential test and §23 minimal‑inference test MUST report **"API key missing"** and CANNOT produce a healthy/real reply. The implementation must be correct‑by‑construction with **mocked primary tests** + a **separate gated live test** that `skipif(no key)`. No stub success for the primary path. The user must inject the key (see §9) for live verification.

## 3. Implementation (reuse existing surfaces)

### 3a. `jarvis_backend/routers/extensions.py` — NVIDIA adapter (PRIMARY, §6)
Add `nvidia` as a sibling of `openai` (NOT a new fabric):
- `_API_KEY_PROVIDERS["nvidia"]` = `{key_env:["NVIDIA_API_KEY","JARVIS_API_KEY_NVIDIA"], console_url:"https://catalog.ngc.nvidia.com/models", validator:"_validate_nvidia_key"}`.
- `_validate_nvidia_key(key)` — mirrors `_validate_openai_key`: `GET https://integrate.api.nvidia.com/v1/models` w/ `Authorization: Bearer {key}` → `(verified, err)` `(True, None)| (False, "invalid NVIDIA API key") | (None, None)`.
- `_discover_nvidia_models(key)` (NVIDIAModelDiscovery, §5): `GET /v1/models` → list of `{model_id, provider:"nvidia", capabilities, availability}`. Honour `JARVIS_NVIDIA_MODEL` override **only as a selection hint** (never hard‑code before discovery).
- `_invoke_nvidia(ext_id, capability, params, key)` (NVIDIAClient, §6): reuses `_openai_json_post("https://integrate.api.nvidia.com/v1/chat/completions", payload, key)` — OpenAI‑compatible shape. Capability `nvidia.chat` (and `nvidia.generate` for embeddings if offered). Returns `{provider:"nvidia", content, model, usage}`.
- Register `"nvidia": _invoke_nvidia` in `_PROVIDER_INVOKE_HANDLERS`; `"_validate_nvidia_key"` in `_VALIDATORS`.
- `model` resolution: `params.model` → `JARVIS_NVIDIA_MODEL` env → discovered default.

### 3b. `jarvis_backend/gateway.py` — repair the Brain remote path (§1/§7/§8)
`_chat_via_remote_brain` currently lazy‑imports the missing `backend.model_gateway.n` (dead). Replace with a **self‑contained OpenAI‑compatible call reusing `_openai_json_post`** (imported from `jarvis_backend.routers.extensions`), so the Brain boundary actually works for NVIDIA. This is the §1 "RemoteBrainBackend → NVIDIA NIM" hop and uses the **existing** generic POST (no new HTTP client).
- New `_brain_upstream_key(endpoint)` (§33 — keep `JARVIS_BRAIN_API_KEY`/`brain_api_key` ≠ `NVIDIA_API_KEY`): if `integrate.api.nvidia.com` in endpoint → resolve `NVIDIA_API_KEY` (env then vault `nvidia_api_key` — never logged); else → vault `brain_api_key` (existing local Brain boundary key).
- `_chat_via_remote_brain` posts to `f"{endpoint.rstrip('/')}/chat/completions"` with the resolved upstream key + `JARVIS_BRAIN_MODEL`/`JARVIS_NVIDIA_MODEL`.
- `probe_brain` already calls `_chat_via_remote_brain` → immediately becomes the §15 Brain‑:8011 health probe (reports `backend=remote, provider=nvidia, model=<discovered>`).
- Inject point `self._n`/`brain_client` already exists for tests — keep it; add a `_brain_post` seam to allow httpx mocking.

### 3c. `jarvis_backend/routers/provider_status.py` — NVIDIA in the honest matrix
Already composes `_env_api_key` + validator + `_NOT_IMPLEMENTED` generically over `_API_KEY_PROVIDERS`. Adding `nvidia` to the dict makes NVIDIA appear **automatically** in `GET /api/v1/integrations/providers` with honest states: `NOT_CONFIGURED` (no key) → `CONFIGURED` (key in env) → `HEALTHY`/`INVALID_KEY` (validator). Add model discovery to the `probe=true` path. No false `NOT_IMPLEMENTED` — NVIDIA is a real adapter.

### 3d. `core.py::AIService` + `ai.py::/ai/status` — §16 remove false "AI disabled"
`AIService.enabled` is purely `JARVIS_AI_ENABLED`. Make `ai_status`/`enabled` additionally report `True` when the Brain remote path is **live‑probed healthy** (NVIDIA configured+healthy) OR an extensions adapter (nvidia/openai/gemini) returns HEALTHY — never assume. With no key (current), `enabled=False` stays **honest**. Expose `ai/brain = {backend:"remote", provider:"nvidia", model:"<resolved-or-not-configured>", healthy:<probe>}`.

### 3e. `routers/health.py` — §15 Brain health endpoint
Augment `GET /health` and `GET /api/v1/health/status` with `brain` block (`backend`, `provider`, `model`, `healthy`, `latency_ms`, `detail`) derived from `provider_gateway.probe_brain()` (cached, ~30s). Never fakes healthy.

### 3f. Config (§7) `.env.example` + `.env`
Append canonical placeholders only (NOT real keys):
`NVIDIA_API_KEY`, `NVIDIA_NIM_ENDPOINT=https://integrate.api.nvidia.com/v1`, `JARVIS_NVIDIA_MODEL`, `JARVIS_BRAIN_BACKEND=remote`, `JARVIS_BRAIN_ENDPOINT`, `JARVIS_BRAIN_MODEL`, `JARVIS_BRAIN_REMOTE_API_KEY` (reference: "vault:nvidia_api_key"), `JARVIS_BRAIN_API_KEY` (local boundary, distinct).

### 3g. Frontend (§20) — surface NVIDIA honestly, key NEVER sent to client
- `features/system/api.ts` / `store.ts`: read `/api/v1/integrations/providers`; add `nvidia` entry to the provider list UI (NOT_CONFIGURED badge + link to NGC console + "set NVIDIA_API_KEY in server env"). No value shipped to client (status is a boolean/availability enum).
- `dashboard/system/page.tsx` / ai-status: replace the false "AI disabled" with an honest "AI: standby (NVIDIA NOT_CONFIGURED)" until a key verifies.

### 3h. Settings page key‑name reconciliation (ADV‑14/15 already‑in‑flight)
Leave Gemini/Browser settings reconciliation as‑is (out of scope for THIS task); NVIDIA only needs the provider matrix + the ai-status toggle above.

## 4. Tests (§36/§37)

### 4a. `tests/test_nvidia.py` (mocked — primary path, NEVER a stub success)
- `test_nvidia_invoke_chat_reuses_openai_compatible_shape`: mock `httpx.post` → 200 OpenAI JSON; `_invoke_nvidia("nvidia","nvidia.chat", params, key)` returns `{provider:"nvidia", content, model, usage}` and posts to `https://integrate.api.nvidia.com/v1/chat/completions` with `Authorization: Bearer <key>`. Asserts the adapter reuses `_openai_json_post` (no duplicate client).
- `test_validate_nvidia_key`: 200→`(True,None)`, 401→`(False,"invalid NVIDIA API key")`, network→`(None,None)`.
- `test_discover_nvidia_models`: mock `/v1/models` → parses `data[].id` + capabilities; `JARVIS_NVIDIA_MODEL` honored as selection, not hard‑code.
- `test_brain_remote_path_uses_nvidia_key_when_endpoint_is_nvidia`: `ProviderGateway` with injected fake brain_post; `JARVIS_BRAIN_ENDPOINT=https://integrate.api.nvidia.com/v1` + `NVIDIA_API_KEY` set → `_chat_via_remote_brain` posts to NVIDIA `/chat/completions` with the NVIDIA key (NOT `brain_api_key`). 401→`PROVIDER_UNAVAILABLE`.
- Honesty: bad key → error, not a fake reply.

### 4b. `tests/test_nvidia_live.py` (gated LIVE — §4 §23)
`@pytest.mark.skipif(not _nvidia_key_present())`. When run with `NVIDIA_API_KEY` set:
- §4: `GET https://integrate.api.nvidia.com/v1/models` w/ `Authorization: Bearer <key>` → assert 200, parse real model IDs.
- §23: minimal `POST /v1/chat/completions` (`"Reply with the single word: ok"`, 1 token) via `_chat_via_remote_brain`; assert real `content`.
- When key absent: **skips** (never a fake pass).

### 4c. Regression
Keep existing suite green: `pytest tests/test_sec1_security.py tests/test_auth.py tests/test_security_regression.py tests/test_platform_identity.py tests/test_provider_status.py tests/test_browser_model_route.py tests/test_nvidia.py -q` → all pass; `tsc --noEmit` → 0; `jarvis:8000/health`→200; `jarvis:3000`→200; `POST /api/v1/system/launch {"app":"shutdown"}`→403.

## 5. Execution order
1. Implement 3a (extensions adapter) + 3c (matrix auto‑surfaces) — lowest risk (no runtime path change), tests 4a.
2. Implement 3b (repair Brain remote path) — higher risk; run full regression + live health after.
3. 3d/3e (AIService + health honesty).
4. 3f (`.env.example`) + 3g (frontend). NEVER put a key in `.env`/frontend.
5. §4 live test (will report "missing key" honestly until user injects). §23 gated.
6. Final gate (§34): full pytest + tsc + health + launch/shutdown 403.

## 6. Credential handoff (the one thing only the user can do)
Per §3/§21, the agent must NOT fabricate `NVIDIA_API_KEY`. To activate live inference:
```
echo. >> .env  & echo NVIDIA_API_KEY=<paste-your-key>
```
or export in the backend shell, then **restart `jarvis-back`**. Then re‑run `tests/test_nvidia_live.py` (un‑skips) + `GET /api/v1/integrations/providers?probe=true` → `nvidia: HEALTHY`. Until then the system stays honestly `NOT_CONFIGURED`/`ai_enabled=False`.

## 7. Files
**Edit (existing):** `jarvis_backend/routers/extensions.py`, `jarvis_backend/gateway.py`, `jarvis_backend/core.py`, `jarvis_backend/routers/health.py`, `jarvis_backend/routers/ai.py` (settings only), `jarvis_backend/main.py` (env defaults), `.env.example`, frontend `features/system/*`, `dashboard/system/page.tsx`, `dashboard/ai-status*` (as exist).
**Create:** `tests/test_nvidia.py`, `tests/test_nvidia_live.py`, this plan file.

## 8. Risks
- `gateway.py` Brain‑path edit blocks all chat on regression → must keep `SILVERWING_ENDPOINT`/Silverwing fallback path intact; tests inject fakes. Backend/frontend are LIVE (pid 9248/:3000) — restart backend after edits via `taskkill /PID 9248 /F` + `python jarvis_api.py`.
- `backend`/`providers` packages still missing — do NOT depend on them; the NVIDIA adapter lives entirely in `extensions.py` + `gateway.py` self‑contained call. If `silverbwing-backend/model_provider.py` import is fragile, the honesty guard already handles it (502, no fake).
