# Frontend Changelog

All notable changes to the JARVIS frontend
(`_tier1/canonical_repo/platform/frontend/web/`) on the `feat/frontend-modernization` branch are
documented here. This project **does not** follow strict SemVer for the frontend (it is internal);
entries are grouped by phase and tagged with the verification available in this environment.

Conventions:
- `tsc` = `node_modules/.bin/tsc --noEmit` run from `frontend/web/`.
- `eslint` = `node_modules/.bin/eslint` (local v9) — **not** `npx eslint .`, which resolves to a
  stray EOL v10 in this sandbox.
- **Live runtime** = behavior exercised against a running backend. The backend is **not**
  runnable in this environment (git-ignored, needs Postgres + provider keys), so live runtime is
  marked `[live: pending owner]` when applicable.

---

## [Unreleased]

### Added — Phase A reality audit
- `docs/frontend/FRONTEND_REALITY_AUDIT.md` — evidence-based reality audit of the canonical
  Next.js 16 frontend (framework, tooling, routes, components, API contract, auth, chat, voice,
  dashboard, design tokens, checks). **Verified** by reading actual source files and running the
  local toolchain. Classifications: chat/auth/voice/dashboard = **LIVE**; theme/design-tokens =
  **LIVE**; test runner = **NONE**.
- `docs/frontend/FRONTEND_PRESERVATION_REGISTER.md` — do-not-destroy surface, simulations vs live,
  security-sensitive surfaces, explicitly-excluded directories.
- `docs/frontend/FRONTEND_TRANSFORMATION_PLAN.md` — route-by-route modernization plan with
  acceptance criteria; explicitly scoped non-goals to prevent over-reach.

### Added — Audit guidance integration
- `AGENTS.md` §9 "Frontend area" — guidance that the authoritative, Git-trackable frontend is
  `_tier1/.../frontend/web/` (not the git-ignored `Jarvis-super-intelligence-/frontend/`);
  requires reading `docs/frontend/FRONTEND_REALITY_AUDIT.md` before frontend edits; documents the
  local-only toolchain and the 937-problem lint baseline (do not mass-fix); notes the absence of a
  frontend test runner and the unavailability of the backend for runtime verification.
- `AUDIT.md` tracking table — added `FRONTEND-*` findings (FRONTEND-1 lint/CI, FRONTEND-2 no test
  runner, FRONTEND-3 websocket refs defect) and a "Frontend reality audit" section.

### Fixed — Phase C (conversation workspace)
- **`FRONTEND-3` ✅ FIXED:** `src/lib/websocket.ts` — `useWebSocket` returned
  `isConnected: isConnected.current` (a `ref` read **during render**), which ESLint flagged as
  `react-hooks/refs` ("Cannot access refs during render"). `isConnected` is now a `useState`
  value updated in `onopen`/`onclose`/`disconnect`, making the connection state reactive and
  removing the render-time ref read.
  - **Evidence:** `tsc --noEmit` → exit 0; `eslint src/lib/websocket.ts` → `react-hooks/refs` error
    removed (websocket.ts lint errors 6 → 5); return shape unchanged (`{isConnected, send,
    disconnect, reconnect}`), so `useHealthWebSocket`/`useAgentWebSocket` and all consumers are
    unaffected by the public API.
  - **Remaining in file (pre-existing, not introduced):** 4× `@typescript-eslint/no-explicit-any`
    and 1× `react-hooks/immutability` (reconnect `setTimeout` self-references `connect` before
    declaration — a stale-closure hazard) — documented as known, left for Phase H regression test
    coverage rather than a riskier reconnect restructure.
  - `[live: pending owner]` — real-time WS behavior (monitoring/voice) needs a live backend to
    exercise end-to-end.

### Verification (this environment)
| Check | Command | Result |
| --- | --- | --- |
| Type-check (full project) | `npx --no-install tsc --noEmit` | exit 0 |
| Lint (websocket.ts) | `node_modules/.bin/eslint src/lib/websocket.ts` | refs error gone; 5 remaining (4× `any`, 1× `immutability`) |
| Build / dev server | `next dev` / `next build` | **Not run** — backend at `127.0.0.1:8000` unavailable; expected to be blocked on backend-dependent pages. |

### Planned (not yet implemented)
- **FrONTEND C2:** Lift the `AbortController` out of `chatApi.sendStreamingMessage` so the chat
  "stop" button aborts the in-flight SSE fetch (currently only flips a flag).
- **FRONTEND C3:** Wire `onVoiceClick` from `app/chat/page.tsx` into `<ChatWindow />` so the Mic
  renders on the primary chat route (currently hidden).
- **FRONTEND D2:** Render the voice orb / 48-bar visualizer defined in `design-tokens.ts`
  (currently token-only, not rendered) — only animate when listen/speak are active.
- **FRONTEND F1:** Reconcile the two auth layers (`lib/api.ts` `jarvisAPI` vs `features/auth/api.ts`
  `authApi`) into one client (cross-cutting; coordinate with backend).
- **FRONTEND-1 / FRONTEND H:** Add a frontend test runner (vitest) + regression guard +
  `.github/workflows/frontend.yml` CI gate (requires a lockfile change for the new devDep).

---

## Notes on ordering & scope

This branch builds on `docs/jarvis-audit-integration` (`b8c47c7`) so it inherits the
Phase-1 audit docs. The frontend changes here are **additive** to the audit work; the audit PR #4 is
**not modified** by this branch (new commits land only on `feat/frontend-modernization`).
