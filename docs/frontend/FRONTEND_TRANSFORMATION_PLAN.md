# Frontend Transformation Plan

> **Goal:** Modernize the JARVIS frontend into a polished, responsive, production-minded AI
> application with a **ChatGPT-quality conversation experience** while keeping **JARVIS's own
> identity** (holographic cyan/teal theme, "Operator workbench", semantic presentation contracts).
>
> **Constraint:** *Do not destroy existing functionality.* Every change is incremental, verified
> with the local toolchain (`tsc` + `eslint`), and preserves the live backend contracts enumerated
> in `FRONTEND_REALITY_AUDIT.md` and `FRONTEND_PRESERVATION_REGISTER.md`.
>
> **Branch:** `feat/frontend-modernization` (off `docs/jarvis-audit-integration` @ `b8c47c7`).
> **Target canonical frontend:** `_tier1/canonical_repo/platform/frontend/web/`.

The reality audit shows the core is **already real and ChatGPT-quality** (SSE streaming, provider
model selector, session history, drafts, error boundary w/ retry, voice via backend, live
dashboard polling). The transformation is therefore **refinement, consistency, and gap-closure** —
not a rebuild. Each phase below lists acceptance criteria and the check used to verify it.

---

## 0. Design system (foundational, no behavior change)

### 0.1 Tokens — already established
`src/lib/design-tokens.ts` (263 lines, `as const`) + `src/app/globals.css` (~1.5k lines) already
define and wire the JARVIS token system. **Preserve & extend, don't replace.**

### 0.2 Theme-token consistency fix (small, verifiable)
- **Problem:** `src/app/login/page.tsx` uses raw Tailwind `gray-{}`/`purple-{}` utilities + an inline
  blob `@keyframes` instead of the project's `holo-*` / `designTokens` tokens. It visually clashes
  with the rest of the app.
- **Plan:** Migrate the login page to the JARVIS token theme (`bg-background`, `text-foreground`,
  `border-border`, `--shadow-glow`, `holo-button` class helpers, `gradient-primary` for the JARVIS
  logotype). Keep the password toggle, error block, and links intact.
- **Acceptance:** visually consistent with dashboard; `tsc` clean; `eslint` clean on `login/page.tsx`.
- **Risk:** styling-only; no auth contract change. **Defer** if it risks regressions without a
  visual diff (no screenshot tool here) → mark as planned, not done.

> ✅ Phase B deliverable: this plan documents the tokens as "established"; no rewrite.

## 1. Phase C — Core conversation workspace

| ID | Item | Plan | Acceptance | Status |
| --- | --- | --- | --- | --- |
| C1 | `websocket.ts` refs defect | Move `isConnected` to React state updated in `onopen`/`onclose` + `disconnect`; return state, not `ref.current`. | `tsc` PASS; `eslint src/lib/webSocket.ts` refs error gone; `useWebSocket`/`useHealthWebSocket`/`useAgentWebSocket` return values unchanged. | **TODO** |
| C2 | Streaming cancel | Lift `AbortController` out of `chatApi.sendStreamingMessage` so the stop button actually aborts the in-flight SSE fetch (and marks the assistant message appropriately). | `tsc` clean; behavior preserved (stop still clears `isStreaming`); live verification against backend in §Validation. | **TODO** |
| C3 | Wire voice into `/chat` | Pass `onVoiceClick` from `app/chat/page.tsx` → `ChatWindow` (e.g., open the voice panel / focus Mic). Currently the Mic is hidden on `/chat`. | `tsc` + lint clean; Mic renders on `/chat`. | **TODO** |
| C4 | Responsive history/rendering | Chat already uses `dvh`/`min-w-0`/breakpoints + mobile session drawer. Verify on tablet breakpoints; tighten `max-w` + empty-state copy. | No a11y/overflow regressions; `tsc` clean. | **TODO** |

## 2. Phase D — Voice interaction

| ID | Item | Plan | Acceptance | Status |
| --- | --- | --- | --- | --- |
| D1 | Voice route wiring | `app/voice/page.tsx` already mounts `VoiceInterface`. Verify it's reachable from the dashboard "Voice" link (it is: `WORKSPACE_LINKS`). | Link works (code path); `tsc` clean. | **TODO** |
| D2 | Voice orb / visualizer | `design-tokens.ts` defines `voice.*` states + `audio.*` geometry (48 bars, `orbSize=220`, fft params) **but `voice-interface.tsx` does not render them.** Implement a real-time visualizer component driven by voice state, **honestly labeled** (only rendered when `listen`/`speak` are active). | Rendered when active; idle = no fake animation. | **TODO** |
| D3 | STT path | `listen` is server-side (`POST /api/v1/voice/listen`). No browser `getUserMedia`/`SpeechRecognition`. | Document as server-side STT; optionally add a client-side fallback toggle. | **TODO** |

> Honesty rule: do **not** claim a voice orb exists until D2 lands. The tokens exist; the component does not.

## 3. Phase E — Dashboard & control center

| ID | Item | Plan | Acceptance | Status |
| --- | --- | --- | --- | --- |
| E1 | Capability sampling | Read the 20+ `dashboard/*` sub-pages to classify LIVE vs partial/mock. (Pending this pass.) | Register populated; `tsc` clean where edited. | **TODO** |
| E2 | Control-center tabs | Inspect 10 tabs' data sources; confirm they call control-center API, not local state. | Classification recorded. | **TODO** |
| E3 | Control-center API surface | `lib/control-center-api.ts` — verify calls match `config/api.ts`. | No broken calls. | **TODO** |

## 4. Phase F — Auth/security review

| ID | Item | Plan | Acceptance | Status |
| --- | --- | --- | --- | --- |
| F1 | Two auth layers | `lib/api.ts` (`jarvisAPI`, used by `/login`) vs `features/auth/api.ts` (`authApi`, newer). Reconcile to one client (prefer `api-client.ts`), keeping `LoginResponse`/`ProviderSettings` type names stable. | Single auth path; `tsc` clean; `/login` still works. | **TODO** |
| F2 | Token storage hardening | Frontend-only scope is limited (HttpOnly needs backend). At minimum: ensure tokens are never logged; verify `console.*` doesn't leak tokens. | Grep: no token logging in src. | **TODO** |
| F3 | Login theme (0.2) | Merge login into JARVIS theme. | Consistent. | **defer** |

## 5. Phase G — Responsive polish

| ID | Item | Plan | Acceptance |
| --- | --- | --- | --- |
| G1 | Breakpoint audit | Verify chat + dashboard + control-center on `sm`/`md`/`lg`/`xl`; fix overflow/ellipsis. | Responsive; `tsc` clean. |
| G2 | Mobile nav | `sidebar.tsx` collapse behavior on small viewports. | Usable on tablet/mobile. |

## 6. Phase H — Regression testing & CI

The frontend has **no test runner** (`package.json` has no `test`). A regression guard is required
before any non-trivial change so the build stays green and the `websocket.ts` / streaming cancel
fixes don't regress.

| ID | Item | Plan | Acceptance |
| --- | --- | --- | --- |
| H1 | Pick a runner | Add `vitest` (lightweight, works with Vite/Next) as a `devDependency`; add `test`/`test:watch`/`test:ci` scripts. **Lockfile change only if this dep is added** (documented justification). | `npm test` runs. |
| H2 | Regression guard | Add `tests/frontend/websocket.test.ts` covering `useWebSocket` returning a **stateful** `isConnected` (not a ref read at render). Minimal, deterministic (mock `WebSocket`). | Test green; `npm run test:ci` exits 0. |
| H3 | CI gate | Add `.github/workflows/frontend.yml` running `tsc --noEmit` + `eslint` + `test` on the `web/` dir, on every push/PR to the frontend branch. | CI passes green. |

> **Note:** This differs from the Python `tests/test_audit_guard.py` + `audit-guard.yml` (already
> passing on `docs/jarvis-audit-integration`); the Python guard must **not** be touched.

---

## 7. Execution order (this branch, verified as it goes)

1. **(this session)** Establish docs (`docs/frontend/*`) + `C1` (websocket refs fix) — verifiable
   with `tsc` + `eslint` now; runtime verification deferred to owner (needs backend).
2. **Phase C** C2 (streaming cancel), C3 (voice into `/chat`), C4 (responsive).
3. **Phase D** D2 (voice orb — only render when active).
4. **Phase F** F1 (auth layer reconciliation) — **large**; coordinate with backend; flag as
   cross-cutting.
5. **Phase H** test runner + regression guard + CI — prerequisite for H2/H3 trust.

## 8. Non-goals (explicitly avoided)

- Rewriting the 352-line `SemanticPresentationContract` type or the SSE framing (working).
- Replacing shadcn/ui primitives or the `globals.css` holographic theme.
- Touching git-ignored duplicate frontends (`Jarvis-super-intelligence-/`, `_worktrees/...`).
- Mass `--fix` of 937 lint problems (most are `no-explicit-any`; only new/touched files linted).
- Any network/provider/GPU/backend work requiring authorization.
