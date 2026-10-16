# AUDIT.md — JARVIS audit findings (integration tracker)

This file is the **single source of truth** for audit findings as they are
discovered, fixed, and verified in this repository
(`github.com/ndichiv-spec/jarvis-super-intelligence`, branch
`docs/jarvis-audit-integration`).

- The **verbatim original audit report** is preserved at
  `docs/audits/initial-audit-report.md` (byte-for-byte copy of
  `JARVIS_BLOCKER_RESOLUTION_AND_VERIFICATION.md`).
- The remaining original audit reports are preserved **byte-for-byte** under
  `docs/audits/` with their original filenames.
- `docs/audits/README.md` explains how findings are tracked, verified, and
  closed.
- `docs/audits/audited-baseline.md` identifies the precise audited baseline
  and its limitations.
- `docs/AGENTS.md` is read by every coding agent before changes.

Findings are prioritised **P1 (critical/operational)** → **P2 (medium)** →
**P3 (hygiene/visibility)**. Each finding has a stable ID, a status, the
evidence observed in *this* workspace, and a remediation note. **A finding is
never closed because documentation was added; it is closed only when a verified
test or check confirms the fix.**

## Tracking table

| ID | Priority | Finding | Status | Evidence |
|----|----------|---------|--------|----------|
| P1-1 | P1 | Hardcoded default admin password in `.env.example` | ✅ FIXED | `git diff`; `.env.example` line 44 now commented placeholder |
| P1-2 | P1 | Auth/session weaknesses (HS256 JWT, no rotation/reuse-detection, localStorage bearer, sessions `ip/user_agent=NULL` no expiry, `get_current_user` ignores session/refresh/status, no PKCE, no HttpOnly cookies, no OIDC id_token verification) | 📄 DOCUMENTED | `jarvis_backend/routers/auth.py`, `jarvis_backend/core.py`; owner-only model in platform recovery (82 auth tests) |
| P1-3 | P1 | Fragmented plaintext secrets (extensions OAuth plaintext in KV, plaintext `developer.py` keys, dead `VaultFileBackend`, no key rotation) | 📄 DOCUMENTED | `infrastructure/vault/manager.py`, `connectors/crypto.py`, `routers/extensions.py` |
| P1-4 | P1 | `research_engine` import gap — backend imports an untracked sibling workspace package; clean-clone reproduction unverified | ⚠️ OPEN | `tests/conftest.py` sys.path pin; collection works only with sibling present |
| P1-5 | P1 | Code duplication — divergent copies of `backend/` & `providers/` across root, `_tier1/canonical_repo`, and `Jarvis-super-intelligence-/` | ⚠️ OPEN | `JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md` |
| P1-6 | P1 | Entry-point ambiguity — multiple launchers for the JARVIS app | 📄 DOCUMENTED | `jarvis_api:app` canonical; `unified_jarvis_api:app` compat; dashboards |
| P2-1 | P2 | `diag_harvest.py` syntax error (malformed escaped-quote `for` loop) | ✅ FIXED | `py_compile` passes; `test_diag_harvest_compiles` |
| P2-2 | P2 | Eager heavy imports blocked collection without torch (`silverwing_runtime` backends/perplexity/harness/inference) | ✅ FIXED | `test_silverwing_backends_import_without_torch`; 868 collected, exit 0 |
| P2-3 | P2 | No pinned root requirements / lockfile (`pyproject.toml`/requirements absent at repo root) | ⚠️ OPEN | `.github/workflows/audit-guard.yml` installs ad-hoc deps |
| P2-4 | P2 | Dependency constraint drift (`pip check` conflicts) | ⚠️ OPEN | openai 3.23 vs langchain/litellm<3; opentelemetry 0.65 vs 0.66; pydantic-ai vs slim; sqlmodel vs SQLAlchemy 2.1.2 |
| P2-5 | P2 | Vulnerable dependencies (pip-audit: 68 vulns / 15 pkgs; 573 Dependabot) | ⚠️ OPEN | pip-audit exit 1, env-level, no lockfile; pyjwt/gitpython/litellm/oauthlib/mcp/etc — no broad upgrade attempted |
| P2-6 | P2 | Lint / line-ending hygiene | 📄 DOCUMENTED | ruff 0.16.1 not configured at root; 54 findings on changed files (pre-existing legacy debt, not enforced by CI); pre-existing CRLF on tracked Python files retained — no mass normalization |
| P3-1 | P3 | Secret scanning | ✅ COMPLETED (no real secrets) | One AWS-pattern in red-team fixture = documented example key; `.env*`/`.mcp.json` gitignored |
| P3-2 | P3 | Env/config hygiene (`.env.bak`, `.env.bak2`, `.mcp.json.tmp`) | 📄 DOCUMENTED | gitignored or benign; no secrets committed |
| FRONTEND-1 | P2 | Frontend lint/CI is effectively non-enforced: `npx eslint .` resolves to a stray EOL ESLint 10 (missing config) in this sandbox, and the local flat-config baseline is **937 problems** (450 errors / 487 warnings, dominated by `no-explicit-any`). No `frontend.yml` CI gate exists. | ⚠️ OPEN | `node_modules/.bin/eslint .` → 937 problems; `npx eslint .` → exit 2; `eslint.config.mjs` present; `frontend.yml` CI gate added (tsc+vitest green) |
| FRONTEND-2 | P2 | Frontend had **no test runner**: `package.json` had no `test` script; no Jest/Vitest; only an orphaned `features/chat/presentation-adapter.test.mjs` not wired to any harness → no regression guard for frontend behavior. | ✅ FIXED | `vitest ^1.6.1` added as devDep; `test`/`test:ci`/`test:watch` scripts; `vitest.config.ts`; regression tests for SSE parsing + API-contract (`sse.test.ts`, `api.test.ts`) — 12 passed; `tsc --noEmit` exit 0; `eslint` on touched files = 0 problems |
| FRONTEND-3 | P2 | `useWebSocket` (`src/lib/websocket.ts`) returned `isConnected.current` (a ref read during render), flagged `react-hooks/refs` ("Cannot access refs during render"); affected `useHealthWebSocket`/`useAgentWebSocket` consumers (monitoring/voice real-time). | ✅ FIXED | `tsc --noEmit` → exit 0; `eslint src/lib/websocket.ts` → refs error removed (6→5 problems); public return shape unchanged |
| BACKEND-1 | P1 | Two divergent `jarvis_backend` packages: canonical tracked (`_tier1/canonical_repo/platform/jarvis_backend/`) vs git-ignored operational superset (`Jarvis-super-intelligence-/jarvis_backend/`); `start_jarvis.py` imports the git-ignored copy, so the live backend cannot be reproduced from a clean checkout. | 📄 DOCUMENTED | `docs/backend/BACKEND_RECONCILIATION.md`; `diff -rq` -> 49 differ, 12 tracked-only, 37 op-only |
| BACKEND-2 | P1 | Stub launcher route collision: `start_jarvis_unified.py` & `start_unified_jarvis.py` both write a synthetic `unified_backend.py` defining `GET /` and `GET /api/v1/status`, colliding with real `jarvis_backend/main.py:unified_status`. | 📄 DOCUMENTED | `docs/backend/BACKEND_RECONCILIATION.md` sec.4; stubs serve none of chat/auth/voice |
| BACKEND-3 | P2 | No backend CI gate: only `.github/workflows/audit-guard.yml` (Python pytest); no backend unit/integration/CI, no frontend CI. | ⚠️ OPEN | exactly one CI workflow at `.github/workflows/` |
| BACKEND-4 | P2 | Backup artifacts: committed `jarvis_backend/gateway.py.before-silverwing-http-fix` + corrupted `routers/system.py.corrupted-backup-20261001_133146` (op copy). | 📄 DOCUMENTED | `docs/backend/BACKEND_RECONCILIATION.md` sec.7; cleanup deferred (non-destructive pass) |

Legend: ✅ = fixed & verified · 📄 = documented / partial · ⚠️ = open · ❓ = not verified here.

---

## P1 — Critical / operational

### P1-1 Hardcoded admin password in `.env.example`
- **Root cause:** `JARVIS_ADMIN_PASSWORD=Admin#Jarvis1` was a committed example
  value that operators routinely copy into `.env`, shipping a known-weak
  credential.
- **Fix applied:** replaced with a commented placeholder requiring a strong
  ≥16-char value.
  ```diff
  -JARVIS_ADMIN_PASSWORD=Admin#Jarvis1
  +# JARVIS_ADMIN_PASSWORD=<set-a-strong-password-minimum-16-chars>
  ```
- **Evidence:** `git diff -- .env.example`; `grep JARVIS_ADMIN_PASSWORD .env.example`
  returns the commented placeholder.
- **Remaining:** rotate any real password that originated from this example in
  existing deployments; see deployment pre-checks (P1-6 / deployment report).

### P1-2 Authentication / session / authorization weaknesses
- **Source:** `docs/audits/JARVIS_OWNER_ONLY_SECURITY_MODEL.md`,
  `docs/audits/JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md` (auth row), and
  `docs/JARVIS_PHASE1_AUDIT.md` §"current authentication".
- **Concerns** (in the platform checkout `jarvis_backend/`): hand-rolled HS256
  JWT with no rotation/reuse-detection/expiry beyond long lifetimes; bearer
  tokens in `localStorage`; session rows with `ip/user_agent = NULL` and no
  expiry; `get_current_user` never checks session/refresh/status; no PKCE
  (HMAC `state` only); no HttpOnly cookies; no OIDC user sign-in; id_token
  signature never verified; PBKDF2-SHA256(200k).
- **Status:** the owner-only security model
  (`is_canonical_owner`/`require_canonical_owner`) was applied in the platform
  recovery and is covered by `tests/test_auth.py` / `tests/test_security_regression.py`
  (82 selected tests). This F:\AI tree ships the **brain/provider/backends**
  packages, not the platform auth layer, so the auth findings are **documented
  and preserved** rather than remediated here. The F:\AI `identity/` and
  `providers/secrets.py` packages are consumed by the platform auth boundary;
  the audit guard pins the `backend` package to the workspace copy so auth
  behavior is not silently shadowed.
- **Action for agents:** before touching authn/authz, read
  `docs/audits/JARVIS_OWNER_ONLY_SECURITY_MODEL.md`; do not weaken the owner
  gate or introduce a second identity authority (e.g., client-supplied owner
  IDs).

### P1-3 Fragmented secret handling
- **Source:** `docs/JARVIS_PHASE1_AUDIT.md` §"current secrets";
  `docs/audits/JARVIS_SUPABASE_AND_SERVICE_FABRIC_BASELINE.md`;
  `docs/audits/JARVIS_EXTERNAL_SERVICE_CAPABILITY_MATRIX.md`.
- **Concerns:** env → `.env` → Fernet `VaultFileBackend` (dead code, never
  instantiated) → Fernet connector OAuth tokens (key = SHA-256 of
  `JARVIS_SECRET_KEY`) → **plaintext** extensions OAuth tokens in KV
  (`routers/extensions.py`) → PBKDF2-hashed API keys → plaintext
  `developer.py` keys. No key rotation: changing `JARVIS_SECRET_KEY` orphans
  stored secrets.
- **Action for agents:** never log secrets; prefer `*_FILE` server-side
  secret files (deployment report); do not add a second credential store
  without an explicit migration; keep secrets out of images, logs, and
  frontend config.

### P1-4 `research_engine` import gap (clean-clone blocker)
- **Source:** `docs/JARVIS_PHASE1_AUDIT.md`; `docs/PHASE9_AUDIT.md`;
  `docs/audits/JARVIS_BLOCKER_RESOLUTION_AND_VERIFICATION.md` ("Dependency
  blocker"); `docs/audits/JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md`
  ("Inventory method and limits").
- **Root cause:** `jarvis_backend` modules import `research_engine`, but no
  `research_engine` package is tracked in this checkout; it resolves from the
  untracked sibling `F:\AI/research_engine` workspace. A clean clone is
  therefore **not demonstrably self-contained** and is a release/CI blocker.
- **Mitigation in this tree:** `tests/conftest.py` pins `backend`/`providers`
  to the workspace copy and imports them explicitly so collection does not
  depend on `_tier1/canonical_repo`. This is a *working-tree* workaround, not a
  fix.
- **Status:** ⚠️ OPEN. **Do not** create an empty substitute package or claim
  the catalog is complete. Resolve by versioning `research_engine` or
  obtaining authorization to migrate it.

### P1-5 Code duplication / divergent copies
- **Source:** `docs/audits/JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md`.
- **Root cause:** `backend/`, `providers/`, `silverwing_runtime/`,
  `jarvis_brain/` etc. exist in three divergent locations: the F:\AI root,
  `_tier1/canonical_repo`, and the gitignored platform checkout
  `Jarvis-super-intelligence-/`. Layouts differ (e.g. `jarvis_backend` at the
  platform root vs under `platform/` in `canonical_repo`).
- **Action for agents:** do not "merge by file name"; treat each layer by its
  canonical responsibility (conftest pins the workspace copy as authoritative
  for `backend`/`providers`). Verify ownership/consumers before deleting.

### P1-6 Entry points & application topology
- **Source:** `docs/audits/JARVIS_BLOCKER_RESOLUTION_AND_VERIFICATION.md`
  §"Entrypoints and architectural boundaries"; `docs/JARVIS_PHASE1_AUDIT.md`
  §"Runtime topology"; `docs/PHASE9_AUDIT.md`.
- **Authoritative entry (F:\AI packages):**
  - Silverwing runtime: `silverwing_runtime/server.py` → `app = FastAPI(...)`
    (OpenAI-compatible `/v1/*`, port 8010).
  - Brain runtime: `brain_runtime/server.py`.
  - Provider fabric: `providers/` (`ProviderRouter`, `ProviderGateway`).
  - Brain orchestration: `jarvis_brain/` (`BrainOrchestrator`).
- **Authoritative full-platform entry (platform checkout, excluded from F:\AI
  git):** `jarvis_api:app` → `jarvis_backend.main:app` assembled on
  `jarvis_backend.core:app`; mounts `silverwing-backend/main.py` at `/silverwing`.
  `unified_jarvis_api:app` is a compatibility adapter.
- **Action for agents:** route supported launch/imports through `jarvis_api:app`
  (or, in this tree, the canonical service module). Do not remove Python
  dashboards/launchers until deployment references are reviewed.

---

## P2 — Medium / build & test

### P2-1 `diag_harvest.py` syntax error
- **Root cause:** a `for term in [""\"name\": ...]` block used malformed
  escaped quotes, producing a `SyntaxError` and breaking `py_compile` /
  collection of any test that imported it.
- **Fix applied:** the malformed loop was removed (it was a no-op `pass` body).
- **Evidence:** `python -m py_compile diag_harvest.py` exits 0;
  `tests/test_audit_guard.py::test_diag_harvest_compiles` passes.
- **Action for agents:** keep `diag_harvest.py` compile-clean; do not reintroduce
  inline data that embeds unescaped quotes next to `for` literals.

### P2-2 Eager heavy imports blocked collection without torch
- **Root cause:** `silverwing_runtime/backends/__init__.py` eagerly imported
  `TorchBackend` at package import time; `perplexity.py` imported `torch` at
  module top-level; `harness.py` and `inference.py` assumed `torch` was present.
  On hosts without `torch` this raised `ImportError` during collection.
- **Fix applied:** `TorchBackend` is now lazy (`__getattr__`); `torch` is
  imported lazily inside `compute_perplexity` and guarded in `capture_hardware`
  / `InferenceService`; `tests/test_silverwing_runtime_real.py` uses
  `pytest.importorskip("torch")` and `tests/test_silverwing_evaluation.py`
  skips torch-requiring cases.
- **Evidence:** `test_silverwing_backends_import_without_torch` passes (fresh
  subprocess asserts `torch` not in `sys.modules` after importing the
  backends package); `python -m pytest --collect-only -q` → **868 collected,
  exit 0** (verified in this workspace on Python 3.13.14).
- **Action for agents:** keep `torch` optional at import time for dev/test;
  any new module-level dependency must not break collection when it is absent.

### P2-3 No pinned root requirements / lockfile
- **Root cause:** the repo root has no `pyproject.toml`/`setup.py`/
  `requirements.txt`; dependencies are not pinned for reproduction.
- **Evidence:** `ls pyproject.toml setup.py setup.cfg requirements*.txt` → none.
  The audit-guard CI therefore installs `pytest httpx pydantic` ad hoc
  (`AUDIT.md` P2-3, `.github/workflows/audit-guard.yml`).
- **Action for agents / status:** ⚠️ OPEN. Add a `pyproject.toml` (or root
  `requirements.txt`) and a lockfile to make installs reproducible; do not
  commit a `.venv` or lockfile that pins non-public package indexes.

### P2-4 Dependency constraint drift
- **Evidence:** `python -m pip check` reports conflicts, e.g.
  `langchain-anthropic`/`langchain-openai`/`litellm` require `openai<3.0` while
  `openai 3.23.0` is installed; `opentelemetry-instrumentation-asgi 0.65b0`
  vs `0.66b0`; `pydantic-ai 2.32.1` vs `pydantic-ai-slim 2.53.0`;
  `sqlmodel` vs `SQLAlchemy 2.1.2`.
- **Status:** ⚠️ OPEN (environment-level). This is the live sandbox env; the
  repo's own manifests are not pinned (P2-3), which is the root cause.
- **Action for agents:** align versions in a pinned manifest before upgrading.

### P2-5 Vulnerable dependencies
- **Source:** `docs/audits/JARVIS_INTEGRATION_TEST_AND_RELEASE_EVIDENCE.md`,
  `docs/audits/JARVIS_EXTERNAL_SERVICE_CAPABILITY_MATRIX.md` — GitHub
  Dependabot recorded **573 open alerts** (33 critical, 293 high, 196 medium,
  51 low) on the default branch; triage examples: `torch` in
  `videlisndichi-jarvis-brain-qwen3-4b-sft-train/requirements.txt`;
  `pypdf`/`GitPython`/`urllib3`/`aiohttp` in
  `_tier1/canonical_repo/platform/requirements.txt`.
- **Evidence (this run):** `python -m pip_audit` → **68 known vulnerabilities
  across 15 packages** (exit 1). Notable / auth-relevant: `pyjwt 2.13.0`
  (PYSEC-2026-4145/4146/4149), `gitpython 3.1.57`, `litellm 1.95.0`,
  `oauthlib 3.3.1`, `ecdsa 0.19.2`, `mcp 2.1.1` (CVE-2026-59951),
  `multidict 6.7.1`, `pip 24.1.2`, `pydantic-ai 2.32.1`, `langgraph-sdk 0.4.2`.
  Several `jarvis-*` findings are editable installs from a **separate** local
  PyCharm project (`C:\Users\Administrator\PyCharmProjects\Jarvis\packages\*`),
  not this repo's tracked source.
- **Status:** ⚠️ OPEN. No broad upgrade was attempted (would be a broad refactor
  outside this audit's scope). Each critical/high alert needs an owner, affected
  manifest/build path, fixed-version compatibility, and test/release
  verification.

### P2-6 Lint / line-ending hygiene
- **Lint (ruff 0.16.1):** `python -m ruff check` on the changed files reports
  54 findings, dominated by pre-existing legacy style debt (UP006/UP045 type
  annotations, F401, RUF059, …). ruff is **not configured** for this tree (no
  `pyproject.toml`/`ruff.toml` at the repo root; the platform's
  `check_ruff_debt.py` is absent here) and **not enforced** by the audit-guard
  CI. No broad `ruff --fix` was applied — it would touch large swathes of
  unrelated, pre-existing code. The enforced gate stays green via
  `tests/test_audit_guard.py`.
- **Line endings:** tracked Python/test files in this tree are **CRLF**
  (inherited from the Windows working-tree baseline) with no `.gitattributes`.
  `git diff --check` therefore reports `\r` as trailing whitespace on changed
  lines of those files — this is inherited baseline noise, **not** introduced by
  the audit fixes. New docs authored in this pass are written **LF**.
  Normalizing CRLF→LF is a repo-wide hygiene change, deferred and tracked
  separately; `git diff --check` cleanliness is asserted for new/LF content
  only (audited-baseline.md §"What changes must pass").

---

## P3 — Hygiene / visibility

### P3-1 Secret scanning (working tree + Git history)
- **Method:** regex scan of tracked source for GitHub tokens (`ghp_`), Slack,
  Google, Stripe, and cloud access-key patterns, over both the working tree and
  `git log --all -p` history.
- **Result:** no private-key markers, GitHub/Slack/Google/Stripe token formats,
  or real cloud credentials found in non-ignored project files.
- **History match:** one `AKIA…` AWS-pattern match in
  `_tier1/canonical_repo/platform/tests/test_experiment_redteam.py` — a
  red-team fixture that exactly matches the AWS **documented example** access
  key identifier and is **not** a real credential (no value was printed).
- **Env hygiene:** `.env`, `.env.bak`, `.env.bak2`, `.mcp.json` are gitignored
  and **not** tracked. `.env.example` is the only tracked environment sample
  and contains no live values (P1-1 fixed). `.mcp.json.tmp` is tracked but
  contains only localhost MCP URLs (no secrets).
- **Status:** ✅ COMPLETED. Remaining risk: rotating any real credential whose
  hash/key was derived from the old `JARVIS_SECRET_KEY` example, and removing
  the AWS example key from the fixture (see P1-3).

### P3-2 Environment / workspace hygiene
- **Status:** 📄 DOCUMENTED. `.env.bak`/`_env`/`.mcp.json.tmp` and generated
  artifacts exist on disk but are gitignored or benign. `tests/test_audit_guard.py`
  does not depend on them.

---

## What is NOT fixed here (and why)
- Platform-layer authn/authz/PKCE/JWT hardening (P1-2/P1-3): lives in the
  gitignored platform checkout, out of scope to refactor from this tree;
  documented and preserved instead.
- `research_engine` packaging (P1-4): requires cross-repo decisions; documented.
- Dependency lockfile / vulnerable-upgrade sweep (P2-3/P2-4/P2-5): broad change
  needing per-alert review; documented and scoped, not attempted.
- Full offline backend suite (2,572 tests) cited by the recovery report: that
  figure is from the platform checkout tree; this F:\AI tree collects **868**
  items and is validated separately (see Phase 4).

---

## Phase 4 — Validation evidence (this run)

Environment: Python 3.13.14 (system), pytest 9.1.1, httpx 0.28.1, pydantic
2.13.5, torch 2.14.0+cpu, ruff 0.16.1, gh 2.97.0. `pytest.ini` applies
`addopts = -q -m "not integration"`, so the `not integration` filter and `-q`
are implicit on every pytest invocation below.

| Check | Command | Result |
|-------|---------|--------|
| Audit regression guard | `python -m pytest tests/test_audit_guard.py -q` | **10 passed** in 2.41s |
| Compile (touched files) | `python -W error::SyntaxWarning -m py_compile <touched>` | exit 0, no SyntaxWarning |
| Full compile sweep | `python -m compileall -q silverwing_runtime backend providers jarvis_brain brain_runtime brain_training learning_arena model_lifecycle teacher_node teacher_mesh identity` | exit 0, no SyntaxWarning |
| Test collection (full) | `python -m pytest --collect-only -q` | **868 items collected**, exit 0, 0 import errors |
| Scoped backend tests | `python -m pytest tests/test_silverwing_runtime.py tests/test_silverwing_gateway.py tests/test_silverwing_evaluation.py tests/test_provider_fabric.py` | **119 passed, 1 deselected**, 0 failed/skipped/error |
| Dependency check | `python -m pip check` | conflicts (P2-4) — live env, not a pinned manifest |
| Dependency scan | `python -m pip_audit` | **68 vulns / 15 packages**, exit 1 (P2-5) |
| Lint (available) | `python -m ruff check --statistics <changed files>` | 54 findings (pre-existing legacy debt; not enforced — P2-6) |
| Secret scan (tracked src) | regex over `git ls-files` | none (P3-1) |
| Secret scan (git history) | `git log --all -p` regex | none real; one AWS-pattern = documented example key (P3-1) |
| Env-file exposure | `git status --ignored` | `.env`/`.mcp.json`/`*_auth.txt`/`*.pem` gitignored, not tracked |
| Frontend type-check | `node_modules/.bin/tsc --noEmit` (in `web/`) | **exit 0** (Next 16.2.4 / TS 6) |
| Frontend unit tests | `node_modules/.bin/vitest run` (vitest 1.6.1) | **12 passed** (`sse.test.ts` 6 + `api.test.ts` 6) |
| Frontend lint (touched files) | `node_modules/.bin/eslint <touched>` | **0 errors, 0 warnings** (sse.ts, sse.test.ts, api.test.ts, api.ts, vitest.config.ts) |
| Frontend build (not run) | `next build` | NOT run - needs backend at 127.0.0.1:8000 (BLOCKED; BACKEND-1/BACKEND-2) |

---

## Frontend reality audit (FRONTEND-* findings)

A full, evidence-based reality audit of the canonical, Git-trackable frontend lives at
`docs/frontend/FRONTEND_REALITY_AUDIT.md`. Summary of what was verified:

- **Framework:** Next.js 16.2.4, React 19.2.5, TS 6.0.3, Tailwind 3.4 + `tailwindcss-animate`,
  Radix UI, Zustand 4.5, `react-markdown` 9 + `remark-gfm`, `framer-motion`, `lucide-react`,
  `recharts`, `maplibre-gl`, `socket.io-client`, `sonner`, CVA, `clsx`, `date-fns`, `uuid` 13,
  `next-themes`. Shadcn-style `components/ui/*` primitives.
- **Routes:** ~30 App Router routes (root, chat, dashboard/* with 20+ sub-routes, voice,
  knowledge-hub, locations, image-generation, embedded-browser, workflows, stark-control, omega,
  login/register/billing/oauth).
- **Auth (LIVE, weak):** JWT login/refresh/logout against `/api/v1/auth/*`; token persisted in
  `localStorage` (`jarvis-auth-storage`); 401→silent refresh. Two auth layers coexist
  (`lib/api.ts` legacy `jarvisAPI` + `features/auth/api.ts`). Matches P1-2 weaknesses (localStorage
  bearer, no refresh-token rotation, no HttpOnly cookies, no PKCE).
- **Chat (LIVE):** `features/chat` — SSE streaming (`/api/v1/chat/stream`) w/ 120s abort,
  placeholder + auto-scroll, model/provider selector (jarvis-brain Qwen3-4B, silverwing,
  openai/claude/gemini/bedrock/ollama/…), session history, drafts persisted to `localStorage`,
  edit-and-resend, feedback, export, `SemanticPresentationContract` typed rendering.
- **Voice (LIVE):** backend-driven TTS/STT via `/api/v1/voice/*`; `VoiceInterface` mounts on
  `app/voice`. Voice orb/visualizer exist **only as design tokens** (not yet rendered).
- **Dashboard/monitoring (LIVE):** `dashboard/page.tsx` polls `/api/v1/status` (30s, AbortController
  cleanup); widgets poll `/api/v1/dashboard/widgets/data/system-metrics` + `/api/v1/monitoring/*`.
- **Theme (LIVE, distinctive):** `design-tokens.ts` (263 lines) + `globals.css` (~1.5k lines) wire
  the holographic cyan/teal/JARVIS-mansion dark theme. Not a ChatGPT clone.
- **Tests:** none configured (`package.json` has no `test` script; no Jest/Vitest); one orphaned
  `features/chat/presentation-adapter.test.mjs`.

### Frontend — validation evidence (this run)

Environment: node v20.20.2, npm 10.8.2, local `node_modules` present. Backend at
`127.0.0.1:8000` **not** available (git-ignored, needs Postgres + provider keys) → `next dev`/`build`
not run.

| Check | Command | Result |
| --- | --- | --- |
| Type-check (full project) | `node_modules/.bin/tsc --noEmit` | exit 0 ✅ |
| Lint (whole project) | `node_modules/.bin/eslint .` | 937 problems (450 errors / 487 warnings), exit 1 ⚠️ |
| Lint (touched file) | `node_modules/.bin/eslint src/lib/websocket.ts` | refs error **gone** (6→5); 4× `no-explicit-any` + 1× pre-existing `immutability` remain (not introduced by this change) |
| Build / dev server | `next dev` / `next build` | **not run** — backend unavailable; runtime verification deferred to owner 📛 |

### Fixes landed on `feat/frontend-modernization`

- **FRONTEND-3 ✅** `src/lib/websocket.ts`: replaced render-time ref read
  (`isConnected: isConnected.current`) with `useState`; connection state is now reactive.
  `tsc` clean; lint error removed; public API unchanged.
- **AGENTS.md §9** (frontend area) + tracking-table row.
- **AUDIT.md** tracking-table rows `FRONTEND-1/2/3` + this section + validation table.
- `docs/frontend/{FRONTEND_REALITY_AUDIT,PRESERVATION_REGISTER,TRANSFORMATION_PLAN,CHANGELOG}.md`.

### Remaining frontend risks (no owner action taken)

- **FRONTEND-1** lint/CI not enforced; **FRONTEND-2** no test runner — both ⚠️ OPEN.
- Streaming "stop" only flips a flag, does not abort the SSE `fetch` (chat store).
- Voice Mic not wired into `/chat`; voice visualizer token-only.
- Login page theme-inconsistent with the JARVIS holographic theme.
- Two auth layers to reconcile (F1) — cross-cutting, coordinate with backend.
- Dashboard sub-routes (20+) + `desktop`/`holographic`/`embedded-browser` not sampled
  line-by-line; classified as present, detail-pending.


---

## Backend reconciliation (BACKEND-* findings)

Authoritative full-platform architecture lives in `jarvis_backend/` (FastAPI). This `F:\AI` tree
tracks the **canonical, reproducible** backend at `_tier1/canonical_repo/platform/jarvis_backend/`
(`main.py` wires 44 routers, including `routers/legacy.py`, which serves the Next.js chat SSE
contract: `/api/v1/chat/stream`, `/api/chat/sessions`, `/api/chat/history/{id}`, `/api/chat/switch`,
...). The **operational** superset at the git-ignored `Jarvis-super-intelligence-/jarvis_backend/` is
richer (celery/grpc/a2a/temporal/langsmith/phoenix/openai_compat + `secret_config.py` + `data/`) but
is NOT reproducible from a clean checkout and is NOT committed. `start_jarvis.py` imports that
git-ignored operational copy, so the live running backend cannot be reproduced from this git tree
alone.

- **Canonical backend (this tree):** `_tier1/canonical_repo/platform/jarvis_backend/` — only copy in git.
- **Operational reference (git-ignored):** `Jarvis-super-intelligence-/jarvis_backend/` — richer superset to MERGE FROM, not copy wholesale; contains local secrets/data/`.venv`.
- **File-by-file diff:** 49 differ, 12 tracked-only, 37 op-only. See `docs/backend/BACKEND_RECONCILIATION.md` sec.2.
- **Startup conflict:** `start_jarvis_unified.py` & `start_unified_jarvis.py` are STUB generators that
  write a synthetic `unified_backend.py` (routes `GET /`, `GET /api/v1/status`, `/components`,
  `/metrics`, `/control/{action}`, `/drive/status`, `/ai/status`, `/monitoring/dashboard`), colliding
  with the real app on `/` and `/api/v1/status`. Authoritative boot = `python start_jarvis.py`
  (seeds `admin@jarvis.local`, writes JWT to `_token.txt`, `uvicorn jarvis_backend.main:app @127.0.0.1:8000`).
  Stub launchers are **recommended for deprecation** (not deleted — preserve).
- **API-contract alignment (verified):** tracked `routers/legacy.py` + `main.py` serve every route
  the Next.js front end expects (chat SSE, sessions/history/regenerate/resend/feedback/switch, auth,
  ai, voice, monitoring, status). The frontend<->backend link is real, not simulated.
- **Reproducible-merge plan (owner-supervised, NOT executed this pass):** secret-scrub the operational
  superset into a tracked location (exclude `secret_config.py`, `data/`, `.env`, `*.corrupted-backup`,
  `__pycache__`, `.venv`); merge the 49 differing files + 37 op-only capability files one-by-one (gated
  by `py_compile` + tests); add `openai_compat`/`notifications`/`runtime_events` routers; reconcile
  `endpoint_registry.py` (tracked) vs `endpoint_gateway.py` (op); `git rm --cached` the committed
  `gateway.py.before-silverwing-http-fix`; replace the two stub launchers with one authoritative entry.
- **Status:** 📄 DOCUMENTED. Backend merge is deferred: the backend is not runnable in this sandbox
  (no Postgres/provider keys/GPU/network; `start_jarvis.py` not authorized this pass) and the operational
  copy is git-ignored with local secrets that must be scrubbed before any import.
