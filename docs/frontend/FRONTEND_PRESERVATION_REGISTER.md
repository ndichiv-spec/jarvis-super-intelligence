# Frontend Preservation Register

> **Purpose:** A guardrail for the JARVIS frontend modernization. Before any file is modified or
> deleted, consult this register. It lists (a) what **must be preserved** because it is real,
> working, and valuable; (b) what **uses simulations/mock data** (so improvements are honest about
> what is backed by a live backend vs. client-side); and (c) **security-sensitive surfaces** that
> must not be weakened.
>
> **Authoritative source:** `_tier1/canonical_repo/platform/frontend/web/` (Git-trackable).
> See `FRONTEND_REALITY_AUDIT.md` §2 for scope & trackability, and the list of directories that
> must **not** be touched.

---

## 1. Do-not-destroy surface (real, working functionality)

These files implement **live** backend-driven behavior. Replacement, refactoring, or "polish"
must preserve the wire contract (`@types`, API endpoints, store method names) and behavior.

### 1.1 Core conversation workspace
| File | What it does | Preserve because |
| --- | --- | --- |
| `src/features/chat/store.ts` | Streaming state machine, session CRUD, drafts, browser-bridge, edit-and-resend | Real SSE state machine; the single source of truth for chat UX |
| `src/features/chat/api.ts` | `send`/`sendStreamingMessage` (SSE w/ 120s abort), sessions/history/export/regen/feedback/switchModel | Real backend contract |
| `src/features/chat/types.ts` | `ChatMessage`, `ChatStreamChunk`, `ChatRequest`, `SemanticPresentationContract`, `ProviderInfo`, `ModelCatalog`, `CHAT_MODELS` | Public type contract; consumers depend on it |
| `src/components/chat/chat-window.tsx` | Session sidebar, provider/model selector, streaming bubble + scroll, error boundary w/ retry | ChatGPT-quality UX, live |
| `src/components/chat/chat-input.tsx` | Auto-resize, Enter/Shift+Enter, attach, stop, voice Mic | Live input surface |
| `src/components/chat/chat-message.tsx` | Message rendering incl. tool_calls, sources, presentation, feedback | Live renderer |
| `src/components/chat/session-list.tsx` | Session history list | Live, real data |

### 1.2 Auth & security
| File | What it does | Preserve because |
| --- | --- | --- |
| `src/lib/api-client.ts` | Typed HTTP client: retry/backoff, `AbortController` timeouts, Bearer auth, 401→refresh, `AuthError` | Security-critical request pipeline |
| `src/stores/authStore.ts` | Zustand persist (`jarvis-auth-storage`), login/logout/loadUser | Auth state of record |
| `src/features/auth/{api,store,types}.ts` | Newer auth layer | Part of the auth contract |
| `src/lib/api.ts` | Legacy `jarvisAPI` (LoginResponse, ProviderSettings field names, Stark types) | Used by `/login`, type field names must stay stable |
| `src/app/login/page.tsx`, `register/page.tsx`, `forgot-password/page.tsx`, `oauth/callback/...` | Auth flows | Live, real endpoints |
| `src/components/layout/authenticated-shell.tsx`, `dashboard-shell.tsx` | Route protection | Auth-gating |
| `.env.example` | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, app name/version | Only tracked env sample; **no secrets** (keep clean) |

### 1.3 Voice
| File | What it does | Preserve because |
| --- | --- | --- |
| `src/features/voice/api.ts` | `speak`/`listen`/`transcribe`/`getVoices`/`getStatus` → `/api/v1/voice/*` | Backend TTS/STT contract |
| `src/features/voice/store.ts`, `src/components/voice/voice-interface.tsx` | Voice UI state machine | Live voice surface |
| `src/features/voice/realtime/` | Real-time voice (present) | Live directory; inspect before editing |

### 1.4 Dashboard, monitoring, control center, widgets (live polled data)
| File | What it does | Preserve because |
| --- | --- | --- |
| `src/app/dashboard/page.tsx` | Operator workbench: polls `/api/v1/status` (30s) + embeds chat + capability list | Live dashboard; real polling w/ cleanup |
| `src/stores/platform-store.ts`, `system-store.ts`, `monitoring-store.ts` | Runtime/platform/system/monitoring state | Store contracts |
| `src/features/monitoring/{api,store,types}.ts` | `metrics`/`healthReport`/`recoveryHistory`/`triggerRecovery` → `/api/v1/monitoring/*` | Live monitoring contract |
| `src/components/widgets/system-metrics-widget.tsx` | Polls `/api/v1/dashboard/widgets/data/system-metrics` | Real CPU/mem/disk widget |
| `src/components/widgets/*` (ai-status, health-monitor, memory-consciousness, agent-status) | Live widget pattern | Preserve polling contract |
| `src/components/control-center/*` (10 tabs) | Control-center surfaces | Live surfaces |
| `src/lib/control-center-api.ts` | Control-center API | Live contract |

### 1.5 Design system (identity, not a mock)
| File | What it does | Preserve because |
| --- | --- | --- |
| `src/lib/design-tokens.ts` | Full JARVIS token set (colors, voice states, audio geometry, motion) | Defines brand identity; **do not** make it look like ChatGPT |
| `src/app/globals.css` | Wires tokens to HSL CSS vars; holographic theme; markdown `prose`; scrollbars; animations | Theme backbone |
| `src/components/ui/*` | shadcn-style primitives (Radix-backed) | Component foundation |
| `src/components/theme-provider.tsx` | Theme provider | Theme plumbing |
| `src/lib/design-system.ts` | Design-system utilities | Shared helpers |

### 1.6 API surface / contracts (must stay stable)
| File | Preserve because |
| --- | --- |
| `src/config/api.ts` | Canonical endpoint map; many `features/*/api.ts` and `lib/*` import `API_ENDPOINTS` |
| `src/config/env.ts` | `NEXT_PUBLIC_*` env contract consumed app-wide |
| `src/lib/api-client.ts` exports (`apiClient`, `getAuthToken`, `setAuthToken`, `clearAuthToken`, `onAuthError`, `ApiClientError`, `AuthError`) | Imported across chat/voice/agents/etc. |
| `src/lib/websocket.ts` (`useWebSocket`, `useHealthWebSocket`, `useAgentWebSocket`) | WebSocket hooks used by real components |
| `src/hooks/useApi.ts`, `useWebSocket.ts`, `useNavigationContext.ts` | Hook contracts |
| `src/stores/index.ts` | Store barrel |

## 2. Simulations & mock data (improvements must label honestly)

Per the task: *"do not fabricate capabilities or live-service connections — label simulations
honestly."* The following were inspected and classified. **None** of the inspected core surfaces
generate fake data; the `Math.random()`/`setTimeout`/`setInterval` hits are for client IDs, polling
timers, and the autonomous agent libs — not fake renders.

| Component | Data source | Classification |
| --- | --- | --- |
| Chat messages | `/api/v1/chat` + `/api/v1/chat/stream` (SSE) | **LIVE** |
| Model provider list | `POST /api/chat/switch` + `/api/v1/ai/models` (`modelCatalog`) | **LIVE** |
| Sessions/history | `/api/chat/sessions`, `/api/chat/history/:id` | **LIVE** |
| Auth | `/api/v1/auth/login` + `/api/v1/auth/refresh` | **LIVE** |
| Voice | `/api/v1/voice/speak`, `/voice/listen`, `/voice/status` | **LIVE** (server-side STT/TTS) |
| Dashboard runtime health | `/api/v1/status` (30s poll) | **LIVE** |
| System metrics widget | `/api/v1/dashboard/widgets/data/system-metrics` (poll) | **LIVE** |
| Platform capabilities | `usePlatformStore.refreshCommands` (backend) | **LIVE** |
| Voice orb / 48-bar visualizer | `design-tokens.ts` `voice.*` / `audio.*` only | **TOKEN-ONLY / NOT RENDERED** — the animated orb/visualizer is a *design-system capability not yet implemented* by `voice-interface.tsx` (do **not** claim it exists at runtime) |

> Dashboard sub-routes (`dashboard/*`, 20+) and `desktop`/`holographic`/`embedded-browser`/
> `knowledge-hub`/`locations`/`image-generation` were **not sampled line-by-line** in this pass.
> Treat them as **PRESENT, classification pending** until individually inspected — do not assume
> they are live or mock without checking each one.

## 3. Security-sensitive surfaces (do not weaken)

| Surface | Current control | Constraint |
| --- | --- | --- |
| Auth token | In-memory + `localStorage` (`jarvis-auth-storage`); auto refresh on 401 | Do **not** introduce logging/serialization of the token; prefer migrating to HttpOnly cookies (requires backend change) — out of frontend-only scope here |
| Provider settings | `ProviderSettings` field names (e.g. `openai_api_key`) are type-only; values come from backend env | Do **not** add provider keys to any tracked/env-sample file; do **not** fetch keys into the client |
| Redirect on 401 | `api-client.ts` calls `_onAuthError()` + `clearAuthToken()` → `/login` | Preserve redirect path; `AuthError` must remain suppressible at page level |
| Env samples | `.env.example` only; `.env*` git-ignored (§1) | Never commit secrets; do not change lockfiles unnecessarily |
| Headers | `Authorization: Bearer`, `Content-Type: application/json`, `X-Browser-Error-Category` read | Preserve auth header injection path |

## 4. Things explicitly excluded from modernization

Per protection rules, **do not** modify:
- `_worktrees/jarvis-world-workspace/` (submodule gitlink `86cd845`; pre-existing local dirt — leave untouched).
- `Jarvis-super-intelligence-/frontend/` and `_worktrees/jarvis-world-workspace/frontend/` (git-ignored dev copies with `.next`).
- `frontend/web/.tmp-jarvis-transformation/` (empty scratch — nothing to preserve).
- Root `package-lock.json` (81-byte stub) — do not regenerate unless a genuine root dependency is added.
- Any `package-lock.json`/`pnpm-lock.yaml`/`yarn.lock` unless a real dependency change is required.
- Git history (no reset/clean/force-push on `main`).
- `.github/workflows/audit-guard.yml` + `tests/test_audit_guard.py` (already passing; the Python guard is intact).
