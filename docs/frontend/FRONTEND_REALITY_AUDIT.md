# Frontend Reality Audit — JARVIS Super Intelligence

> **Status:** `VERIFIED` by direct file inspection (see [Evidence index](#evidence-index)) and
> runnable toolchain checks. This audit was produced by reading the **actual repository files**
> in `_tier1/canonical_repo/platform/frontend/web/`, *not* from prior session reports.
> (A prior report referenced `docs/FRONTEND_CAPABILITY_CENSUS.md`; **that file does not exist on
> disk** — see [Findings that were disverified](#findings-that-were-disverified).)

**Scope:** The canonical, Git-trackable frontend. See [Scope & trackability](#scope--trackability).
**Branch:** `feat/frontend-modernization` (forked from `docs/jarvis-audit-integration` @ `b8c47c7`,
which already merged the Phase-1 audit integration).
**Last inspected:** session timestamp below; files read listed in the evidence index.

---

## 1. Executive summary

The canonical frontend is a **real, production-structured Next.js 16 application** with a live
backend integration across **auth, chat, voice, dashboard, monitoring, and system widgets**. It is
**not** a demo, mockup, or disconnected prototype: every core user flow calls the JARVIS backend
(`jarvis_backend` at `NEXT_PUBLIC_API_URL`, defaulting to `http://127.0.0.1:8000`) through a typed
API client with retry/timeout and 401-refresh handling.

The application already possesses a **distinctive JARVIS identity** (holographic cyan/teal/amethyst
dark theme, "Operator workbench" dashboard, semantic presentation contracts) — it is **not** a
ChatGPT clone. The work ahead is therefore **refinement, consistency, and closing verified gaps**,
not a ground-up rebuild. This matches the task's primary constraint: *do not destroy existing
functionality; do not turn working features into static mockups.*

### Verdict by area

| Area | Classification | Summary |
| --- | --- | --- |
| Framework / build / toolchain | **LIVE** | Next.js 16.2.4, React 19, TS 6, Tailwind 3.4, Radix, Zustand, shadcn/ui. `tsc --noEmit` clean. `eslint` broken-by-config (see [Linting](#7-linting--type-checking)). |
| Routes | **LIVE** | ~30 App Router routes (root, chat, dashboard/*, voice, knowledge-hub, locations, image-generation, embedded-browser, voice, workflows, stark-control, omega, login/register/billing/oauth). |
| Auth | **LIVE, WEAK** | Real JWT login/refresh/logout against `/api/v1/auth/*` via Zustand persist. **Known weaknesses:** Bearer token in `localStorage`, no refresh-token rotation (backend limitation), two parallel auth layers (legacy `lib/api.ts` + newer `features/auth`). See [Auth](#6-authentication) + AUDIT.md P1-2. |
| Conversation (chat) | **LIVE** | ChatGPT-quality workspace: SSE streaming with placeholder + auto-scroll, model/provider selector (openai/claude/gemini/bedrock/ollama/jarvis-brain/silverwing/…), session history, drafts persisted to `localStorage`, edit-and-resend, feedback, export, error boundary w/ retry. **Gaps:** streaming cancel only flips a flag (doesn't abort `fetch`); voice Mic is not wired into the `/chat` route. |
| Voice | **LIVE** | Backend-driven TTS/STT via `/api/v1/voice/*`. Browser UI uses `features/voice/store`. **Gap:** STT (`listen`) is server-side (no inline browser `SpeechRecognition`); voice orb/visualizer present as design tokens but not yet rendered in the voice route. |
| Dashboard & monitoring | **LIVE** | Operator workbench polls `/api/v1/status` (30s) + real widgets poll `/api/v1/dashboard/widgets/data/system-metrics`, `/api/v1/monitoring/metrics`, `/api/v1/system/processes`, etc. |
| Control center | **LIVE** | 10 tab components (overview, connections, credentials, providers, security, diagnostics, developer, extensions, permissions). |
| Design system / theme | **LIVE** | `design-tokens.ts` (263 lines) wired to `globals.css` (~1.5k lines) as HSL CSS custom properties. Distinctive holographic JARVIS theme. |
| Tests | **NONE CONFIGURED** | No Jest/Vitest, no `test` script. Only `features/chat/presentation-adapter.test.mjs` (1 orphaned JS test, not runnable by `npm`). |
| Responsive | **PARTIAL** | Chat uses `dvh`/`min`/`max-w` + `sm:`/`lg:`/`xl:` breakpoints + mobile session drawer. Dashboard uses `sm:`/`md:`/`xl:` grids. Login page is responsive but **theme-inconsistent**. Many dashboard sub-pages not yet inspected. |

---

## 2. Scope & trackability

- **Authoritative frontend:** `_tier1/canonical_repo/platform/frontend/web/` — a Next.js 16 app.
- **Git-trackable in `F:\AI`:** **YES** — 208 files under `…/frontend/web/src/` are tracked by the
  `F:\AI` repository (verified via `git ls-files`). Edits here are part of the PR diff.
- **Do NOT touch (git-ignored / out-of-scope duplicates):**
  - `Jarvis-super-intelligence-/frontend/` (git-ignored §`Jarvis-super-intelligence-/`; contains
    `.next` builds — a personal/dev copy, **not** a source of truth).
  - `_worktrees/jarvis-world-workspace/frontend/` (submodule gitlink at `86cd845`; working-tree
    dirty at `789de27` — pre-existing, left untouched per the no-destructive rule).
  - Top-level `./frontend/web/.tmp-jarvis-transformation/` (empty scratch dir — no prior
    transformation content to preserve).
- **Root:** `package-lock.json` is an 81-byte stub; there is **no** root `package.json`. Node
  tooling must run from `frontend/web/`.

## 3. Environment & toolchain (verified)

| Tool | Value |
| --- | --- |
| Host | Windows amd64, Git Bash `C:\Program Files\Git\bin\bash.exe` |
| node | v20.20.2 |
| npm | 10.8.2 |
| `next` (local bin) | 16.2.4 |
| `tsc` (local bin) | TS 6.0.3 |
| `eslint` (local bin) | v9.39.4 (flat config `eslint.config.mjs`) |
| `npx eslint .` (without `--no-install`) | resolves to ESLint **10.12.0** → fails "no config" |
| Python | 3.13.14 (system), pytest 9.1.1 |
| Backend at `127.0.0.1:8000` | **NOT available** in this environment (`_tier1/canonical_repo` backend is git-ignored). App cannot be runtime-verified here. |
| Provider credentials / GPU / Postgres | **None.** Live provider endpoints cannot be exercised. |

> **Operational note (not a defect):** the local `npx eslint .` is shadowed by a globally-resolvable
> ESLint 10 in this sandbox; the project's own `node_modules/.bin/eslint` (v9) is the correct
> binary and is what `npm run lint` resolves. Always invoke lint via the local binary.

## 4. Framework, dependencies & scripts

`web/package.json` (2025-10-06 snapshot) declares:

```json5
{
  "name": "jarvis-web", "version": "3.0.0", "private": true,
  "scripts": { "dev": "next dev -p 3000", "build": "next build", "start": "next start -p 3000",
                 "lint": "eslint .", "lint:fix": "eslint . --fix" },
  "dependencies": { "@radix-ui/*", "next": "16.2.4", "react": "^19.2.5", "tailwindcss": "^3.4.0",
    "zustand": "^4.5.0", "socket.io-client": "^4.7.0", "react-markdown": "^9.0.0", "remark-gfm": "^4.0.0",
    "framer-motion": "^11.1.0", "lucide-react": "^0.468.0", "recharts": "^2.12.0", "maplibre-gl": "^6.12.0",
    "sonner": "^1.4.0", "clsx": "^2.1.0", "class-variance-authority": "^0.7.0", "date-fns": "^3.6.0",
    "uuid": "^13.0.0", "next-themes": "^0.4.0", cmdk, tailwind-merge, tailwindcss-animate, autoprefixer, postcss },
  "devDependencies": { "@tailwindcss/typography", "eslint": "^9.39.4", "eslint-config-next": "^16.2.4" }
}
```

Notable: **no `test` script, no Jest/Vitest/nx**. `next.config.mjs` sets `output: 'standalone'` and
**rewrites** `/api/v1/:path*`, `/api/chat/:path*`, `/health`, `/api/health`, `/api/ping`,
`/api/version` → the backend origin (see [API wiring](#5-api-wiring--contract)).

## 5. API wiring & contract

`src/config/api.ts` (261 lines) defines a comprehensive endpoint map backed by
`NEXT_PUBLIC_API_URL` (see `src/config/env.ts`, 22 lines):

- **auth**: login/register/logout/me/forgot-password/reset-password/change-password/sessions/api-keys
- **chat**: `send` (`POST /api/v1/chat`), `stream` (`POST /api/v1/chat/stream`, SSE), sessions/history/export/regenerate/feedback/editAndResend/switchModel
- **llm / models**: `/api/v1/llm/chat`, `/api/v1/ai/models` (model catalog), `/api/v1/ai/status`
- **agents**: list/task/tasks/stats/scheduler/collaboration/service-tailoring
- **monitoring**: health-report/metrics/optimization-report/optimize/diagnostics/recovery-history/trigger-recovery
- **system**: status/capabilities/processes/provider-settings/files
- **voice**: speak/listen/transcribe/profile/voices/status
- **browser**: a large surface (sessions/tabs/navigate/extract/search/security/evidence/missions/actions/observe-act/page-state/tasks/workspaces/telemetry/sourceGraph/timeline/modelRoute/remote-browser/summon/artifacts/resourceUsage/network diagnostics/…)
- **memory/cognitive**: store/recall/stats/consolidate/consciousness/emotion/knowledge-graph
- **search**: global/domains/suggest/status/inspect → toBrowser/toResearch/toKnowledge
- **rbac**: users/roles/permissions/audit-logs/tenant-settings
- **ws**: `/ws/chat`, `/ws/health`, `/ws/agents`, `/api/v1/voice/ws/chat`, `/api/v1/stark/ws/chat`, `/ws/monitoring` (WebSocket)

`src/lib/api-client.ts` (291 lines, `ApiClient` class) is the primary typed client: per-request
`AbortController` timeout (`env.REQUEST_TIMEOUT` = 30000ms), retry w/ exponential backoff (2
retries), `Authorization: Bearer <token>`, 401→silent refresh via `POST /api/v1/auth/refresh`,
`AuthError`/`ApiClientError` classes, `FormData` upload support. **This is production-grade, not
toy code.**

## 6. Authentication (LIVE, with known weaknesses)

- **Login:** `app/login/page.tsx` posts to `jarvisAPI.login` (`src/lib/api.ts`, legacy 1509-line
  client), receives `{access_token, refresh_token, user}`, persists via
  `stores/authStore.ts` (Zustand + `persist`, storage key `jarvis-auth-storage`), redirects to
  `/chat`. Includes password visibility toggle, error display, loading spinner, forgot-password
  link.
- **Token handling:** `lib/api-client.ts` hydrates from `localStorage` lazily on each request,
  refreshes silently on 401, clears on hard 401. **Weaknesses (match AUDIT.md P1-2):**
  1. Access token lives in `localStorage` (XSS-exfiltrable) rather than an HttpOnly cookie —
     no `HttpOnly`/`Secure`/`SameSite` cookie path is configured in the audited surface.
  2. Backend does **not** rotate/revoke refresh tokens on refresh (see inline comment in
     `_tryRefresh()`), so a stolen refresh token is long-lived.
  3. **Two auth layers coexist:** legacy `jarvisAPI` (`lib/api.ts`) used by `/login` and a
     newer `authApi` (`features/auth/api.ts` + `api-client.ts`). Both persist to the same
     `jarvis-auth-storage` key. This is live code-duplication (AUDIT.md P2-1) that should be
     reconciled, but is **not** broken.
- **Auth-gated routes:** `components/layout/authenticated-shell.tsx` + `components/layout/dashboard-shell.tsx`
  + `components/layout/sidebar.tsx`/`header.tsx`.

## 7. Conversation experience (LIVE — ChatGPT-quality feature set)

- **Route:** `app/chat/page.tsx` → `<ChatWindow>` in a responsive `dvh` section.
- **Store:** `features/chat/store.ts` (606 lines) — full state machine: messages, sessions,
  `modelCatalog`, `activeModel`, `isStreaming`, `streamingContent`, draft persistence
  (`jarvis-chat-drafts` in `localStorage` keyed by session), browser-context bridge
  (`publishBrowserEvent`/`subscribeToBrowserEvents`), edit-and-resend, restore.
- **Streaming:** `features/chat/api.ts` `sendStreamingMessage` uses raw `fetch` to
  `/api/v1/chat/stream`, parses SSE-style `data:` lines, `AbortController` 120s timeout,
  handles chunk/meta/complete/done/error/STREAM_INTERRUPTED/THINKING statuses.
- **Rendering:** `components/chat/chat-window.tsx` (359 lines) — session sidebar (collapsible on
  mobile), provider/model selector w/ status icons, streaming placeholder bubble + smooth
  scroll-to-bottom, empty state, error boundary with Retry (targets last user message) and
  Dismiss. A11y: aria-labels, `role="status"`, `aria-live`.
- **Input:** `components/chat/chat-input.tsx` (148 lines) — auto-resize textarea, Enter-to-send,
  Shift+Enter newline, file attach, streaming stop button, voice Mic (conditional).
- **Identity:** "JARVIS may produce inaccurate information. Verify critical facts." footer.

### Verified gaps (do not fabricate fixes)

1. **Streaming cancel is incomplete.** In `chat-window.tsx`, `onStopStreaming` calls
   `useChatStore.setState({ isStreaming: false })` — it flips a flag but does **not** abort the
   in-flight `fetch` (the `AbortController` is created and discarded inside `sendStreamingMessage`).
   Backend keeps generating until its 120s timeout. Fix target → expose the abort controller from
   the streaming call (see [Transformation plan — Phase C](#phase-c-core-conversation-workspace)).
2. **Voice Mic not wired into `/chat`.** `ChatWindow` receives `onVoiceClick?` but
   `app/chat/page.tsx` renders `<ChatWindow className="…" />` **without** `onVoiceClick`, so the
   Mic button never renders on the main chat route. Voice input only exists on `/voice`.
3. **No frontend tests** for the chat flow (would catch the cancel bug above).

## 8. Voice interaction (LIVE backend-driven)

- `features/voice/api.ts`: `speak`→`POST /api/v1/voice/speak`, `listen`→`POST /api/v1/voice/listen`
  (server-side STT — there is **no** browser `SpeechRecognition`/`getUserMedia` path), `transcribe`
  (file upload), `getVoices`/`getStatus` (poll). All go through the typed `apiClient`.
- `features/voice/store.ts` (97 lines) + `components/voice/voice-interface.tsx` (129 lines):
  state machine, `loadStatus` polled every 5s, BETA badge, mic/speaker availability, transcript
  display, available-voices list.
- `features/voice/realtime/` directory present (not yet inspected in detail).
- **Design tokens** for a voice orb + 48-bar audio visualizer (`design-tokens.ts`
  `voice.*` + `audio.*`) exist but are **not rendered** by the current `voice-interface.tsx` —
  the visualizer is a documented capability that lives only in tokens. (Honest gap: don't claim an
  animated visualizer exists at runtime.)

## 9. Dashboard & control center (LIVE, real backend polling)

- `app/dashboard/page.tsx` (499 lines): "Operator workbench" — polls `/api/v1/status` every 30s
  with `AbortController` cancellation (proper cleanup), shows Runtime health states
  (operational/degraded/unavailable/checking/unknown), renders capability list from
  `usePlatformStore` (`system-store.ts`), embeds `<ChatWindow>`, and links to
  browser/locations/image-generation/voice workspaces.
- **Widgets** (`components/widgets/`): `system-metrics-widget.tsx` (213 lines) polls
  `/api/v1/dashboard/widgets/data/system-metrics` every `pollInterval` (real CPU/mem/disk
  metrics); `ai-status-widget`, `health-monitor-widget`, `memory-consciousness-widget`,
  `agent-status-widget` follow the same real-poll pattern.
- **Control center** (`components/control-center/`): 10 tabs — overview, connections, credentials,
  providers, security, diagnostics, developer, extensions, permissions — backed by
  `lib/control-center-api.ts` and the RBAC/browser/system endpoints.
- **Sub-routes** (20+ under `dashboard/`): admin, advanced, agents, api-keys, cognitive,
  commands, connections, developer, embedded-browser, extensions, knowledge, memory, monitoring,
  operational, phase3, search, security, self-reliant, sessions, settings, system, system-status,
  tier4. Most are structurally present; several not sampled in detail (classification pending).

## 10. Design system / theme (LIVE, distinctive JARVIS identity)

- `src/lib/design-tokens.ts` (263 lines, `as const`): colors (hsl + hex), gradients, shadows,
  typography, spacing, radius, voice state colors (idle/connecting/listening/thinking/speaking/
  processing/error), audio visualizer geometry, status chip triples, charts palette, generative-UI
  tokens, motion tokens. **Distinctive palette:** `#00d4ff` (cyan), `#00e5a0` (teal), `#0078d4`
  (blue), `#f59e0b` (amber), `#a78bfa` (violet).
- `src/app/globals.css` (~1.5k lines): wires the tokens as HSL CSS custom properties (`--background`,
  `--primary`, `--ring`, `--radius`, `--gradient-*`, `--shadow-*`, `--mansion-wall*`, etc.),
  holographic glass/glass-morphism components, scrollbars, scanlines, waveform bars, blob animation,
  radar sweep, `prose` markdown styling. Dark-first, no light theme toggle wired in globals.
- `components/ui/*` (shadcn-style): avatar, badge, button, card, command, dialog, dropdown-menu,
  input, label, popover, progress, scroll-area, select, separator, slider, sonner, switch, table,
  tabs, textarea, tooltip.
- **Inconsistency:** `app/login/page.tsx` uses Tailwind `gray-{}`/`purple-{}` utility classes + an
  inline `<style jsx>` blob animation instead of the project's `--holo-*`/`designTokens` theme — it
  visually clashes with the rest of the app. Migration target in the plan.

## 11. Responsive behavior

- Chat: `dvh`-based heights, `min-w-0` flex children, `sm:`/`lg:`/`xl:` breakpoints, a mobile
  session drawer toggled via `aria-expanded`.
- Dashboard: grid `sm:grid-cols-2` → `sm:grid-cols-4`, `xl:` two-pane layout, `md:` typography.
- **Coverage not yet verified** across all 20+ dashboard sub-routes and the `desktop`/`holographic`/
  `embedded-browser` pages. Classification = PARTIAL until sampled.

## 12. Testing (NONE configured)

- `package.json` has **no `test` script**; no `jest`/`vitest`/`@playwright/test` in dependencies.
- Only test artifact: `src/features/chat/presentation-adapter.test.mjs` (JS ESM) — **orphaned**;
  `npm run lint`/`build` do not execute it and there is no runner configured.
- `docs/audits/JARVIS_INTEGRATION_TEST_AND_RELEASE_EVIDENCE.md` (Phase-1 audit baseline) is the
  relevant context; the audited baseline notes frontend tests are "sparse" and the chat
  `presentation-adapter.test.mjs` exists but is not wired to a harness.
- **No way to add a regression guard that runs in CI for the frontend** unless a runner is added
  to `package.json` + GitHub Actions (see Phase B / recommendations). This differs from the Python
  `tests/test_audit_guard.py` which already runs in `.github/workflows/audit-guard.yml`.

## 13. Linting & type-checking (runnable, real signals)

Commands run from `web/` with the local toolchain:

| Check | Command | Result |
| --- | --- | --- |
| Type-check | `npx --no-install tsc --noEmit` | **PASS** (exit 0) — no type errors |
| Lint (local v9) | `node_modules/.bin/eslint .` | **FAIL** (exit 1): `937 problems (450 errors, 487 warnings)` |
| Lint (npx, no pin) | `npx eslint .` | **FAIL** (exit 2): resolves to ESLint 10, "no eslint.config.*" — misleading |

Top lint signals (local v9):
- `@typescript-eslint/no-explicit-any` — dominant error (54+ instances), e.g.
  `stores/chat-store.ts:61/65/71`, `stores/monitoring-store.ts:15/16/22/23`,
  `stores/system-store.ts:14/20/21`.
- `@typescript-eslint/no-unused-vars` — e.g. `chat-store.ts:61` `data` unused.
- `react-hooks/refs` **ERROR** (1): `src/lib/websocket.ts:133` `isConnected: isConnected.current`
  reads a ref during render — a real React defect (see [Fix target](#phase-c-core-conversation-workspace)).
- `@typescript-eslint/no-require-imports` (2): `tailwind.config.js:80`.
- Only **2 of 937** problems are `--fix` auto-fixable. Do **not** blind-mass-apply.

> **Do not** blindly upgrade ESLint or add strict new lint rules pre-fix — that would surface
> hundreds of errors and block the build. Lint hygiene is improved incrementally per touched file.

## 14. Findings that were disverified

- **`docs/FRONTEND_CAPABILITY_CENSUS.md` exists / is tracked:** **FALSE.** `find` returns nothing;
  only `JARVIS_COMPLETE_STATUS.md` (repo root) and `CONTROL_CENTER_ARCHITECTURE.md` (repo root)
  exist. The reality audit is written from live inspection instead.
- **"Frontend is a static mockup":** **FALSE.** Auth, chat (SSE), voice, dashboard/polling, and
  control-center all call real backend endpoints through `ApiClient`.

## 15. Verification artifacts (this session)

```
tsc:   npx --no-install tsc --noEmit            -> TSC_EXIT=0
eslint: node_modules/.bin/eslint .             -> 937 problems (450 errors / 487 warnings), ESLINT_EXIT=1
```
`next build`/`next dev` were **not** run to completion — they require the backend at
`127.0.0.1:8000` (git-ignored, not launched) and provider credentials. Attempting `next build`
without the backend is expected to fail at prerender for backend-dependent pages; that failure is
**environmental**, not a code defect. (See [Risks/unblocked work](#risks--unblocked-work).)

## 16. Risks & unblocked work

- The backend (`jarvis_backend`) is **not runnable** in this environment (git-ignored, would need
  Postgres + provider keys + local LLM). Therefore **live runtime behavior cannot be exercised**;
  all verification here is static (`tsc`/lint + code reading). Claiming "works" requires the owner
  to run `npm run dev` against a live backend.
- Dashboard sub-routes (20+) and `desktop`/`holographic`/`embedded-browser` were not fully sampled;
  their LIVE/partial status is pending targeted reads.
- `features/voice/realtime/` and several control-center tabs not inspected line-by-line.

---

## Phase C — Core conversation workspace (verified gaps)

| # | Gap | Fix approach | Verify |
| --- | --- | --- | --- |
| C1 | `websocket.ts:133` reads `isConnected.current` during render (`react-hooks/refs` error) — affects any consumer of `useWebSocket`/`useHealthWebSocket`/`useAgentWebSocket` (monitoring/voice real-time). | Expose `isConnected` as state updated in `onopen`/`onclose` + `disconnect`, instead of reading the ref at return. | `tsc --noEmit` (PASS) + `eslint src/lib/websocket.ts` (refs error gone) |
| C2 | Streaming cancel doesn't abort `fetch`. | Lift the `AbortController` out of `sendStreamingMessage` so `ChatInput.stop` can call `.abort()`. | `tsc` + lint clean on touched files; manual against live backend |
| C3 | `/chat` route never passes `onVoiceClick` → Mic button absent. | Pass a voice handler from `/chat` (open voice panel) into `<ChatWindow onVoiceClick={…} />`. | `tsc` + lint clean; visual on `/chat` |

## Evidence index (file paths read this session)

```
_tier1/canonical_repo/platform/frontend/web/package.json
_tier1/canonical_repo/platform/frontend/web/eslint.config.mjs
_tier1/canonical_repo/platform/frontend/web/next.config.mjs   (head 40)
_tier1/canonical_repo/platform/frontend/web/tailwind.config.js
_tier1/canonical_repo/platform/frontend/web/tsconfig.json
_tier1/canonical_repo/platform/frontend/web/.env.example
_tier1/canonical_repo/platform/frontend/web/src/config/env.ts
_tier1/canonical_repo/platform/frontend/web/src/config/api.ts
_tier1/canonical_repo/platform/frontend/web/src/lib/api-client.ts
_tier1/canonical_repo/platform/frontend/web/src/lib/api.ts                 (1–500; 1509 total, legacy layer)
_tier1/canonical_repo/platform/frontend/web/src/lib/websocket.ts
_tier1/canonical_repo/platform/frontend/web/src/lib/design-tokens.ts
_tier1/canonical_repo/platform/frontend/web/src/app/globals.css            (1–500; 1512 total)
_tier1/canonical_repo/platform/frontend/web/src/app/layout.tsx
_tier1/canonical_repo/platform/frontend/web/src/app/page.tsx
_tier1/canonical_repo/platform/frontend/web/src/app/chat/page.tsx
_tier1/canonical_repo/platform/frontend/web/src/app/chat/layout.tsx
_tier1/canonical_repo/platform/frontend/web/src/app/dashboard/page.tsx
_tier1/canonical_repo/platform/frontend/web/src/app/login/page.tsx
_tier1/canonical_repo/platform/frontend/web/src/components/chat/chat-window.tsx
_tier1/canonical_repo/platform/frontend/web/src/components/chat/chat-input.tsx
_tier1/canonical_repo/platform/frontend/web/src/components/voice/voice-interface.tsx
_tier1/canonical_repo/platform/frontend/web/src/features/chat/api.ts
_tier1/canonical_repo/platform/frontend/web/src/features/chat/store.ts     (1–500; 606 total)
_tier1/canonical_repo/platform/frontend/web/src/features/chat/types.ts      (1–105, 328–352)
_tier1/canonical_repo/platform/frontend/web/src/features/auth/store.ts
_tier1/canonical_repo/platform/frontend/web/src/features/auth/api.ts
_tier1/canonical_repo/platform/frontend/web/src/features/voice/api.ts
_tier1/canonical_repo/platform/frontend/web/src/features/voice/store.ts
_tier1/canonical_repo/platform/frontend/web/src/features/monitoring/api.ts
_tier1/canonical_repo/platform/frontend/web/src/features/monitoring/store.ts
_tier1/canonical_repo/platform/frontend/web/src/components/widgets/system-metrics-widget.tsx
_tier1/canonical_repo/platform/frontend/web/src/stores/index.ts            (barrel, read)
```
