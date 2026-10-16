# AGENTS.md — instructions for coding agents

This repository (`github.com/ndichiv-spec/jarvis-super-intelligence`) contains
the JARVIS / Silverwing **brain, provider fabric, and backends** packages
(`providers/`, `silverwing_runtime/`, `jarvis_brain/`, `research_engine/`,
`backend/`, `brain_runtime/`, `brain_training/`) plus the integration test
suite and architecture docs. The full JARVIS platform application
(`jarvis_backend/`, `frontend/`, `deployment/`, `infrastructure/`) lives in the
**gitignored** sibling checkout `Jarvis-super-intelligence-/` and is *not*
part of this git tree — see `docs/audits/audited-baseline.md`.

Before making **any significant change**, every agent (human or automated)
must do the following. These are mandatory, not optional polish.

## 1. Read the audit materials first
- Read **`AUDIT.md`** — the prioritized findings list and this file.
- Read **`docs/audits/README.md`** — how findings are tracked, verified, and
  closed.
- Read **`docs/audits/audited-baseline.md`** — what was audited and its limits.
- Read the relevant **verbatim original report** under `docs/audits/`
  (the master report is `docs/audits/initial-audit-report.md`).

Do not start a feature or fix until you can point to the findings that affect
the component you are about to change.

## 2. Review findings before modifying affected components
Use the tracking table in `AUDIT.md` to find open findings (⚠️ / 📄) that touch
your area, e.g.:

| Area | Relevant findings | Key original report |
|------|-------------------|---------------------|
| Auth / sessions / RBAC | P1-2, P1-3 | `JARVIS_OWNER_ONLY_SECURITY_MODEL.md`, `JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md` |
| Dependencies / lockfile / vulns | P2-3, P2-4, P2-5 | `JARVIS_INTEGRATION_TEST_AND_RELEASE_EVIDENCE.md` |
| Secrets & env files | P1-3, P3-1 | `JARVIS_EXTERNAL_SERVICE_CAPABILITY_MATRIX.md` |
| `research_engine` / clean clone | P1-4 | `JARVIS_BLOCKER_RESOLUTION_AND_VERIFICATION.md` |
| Code duplication / entry points | P1-5, P1-6 | `JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md` |
| Silverwing runtime / torch imports | P2-2 | (in-tree, kept import-safe) |
| `diag_harvest.py` | P2-1 | (in-tree) |
| Frontend (Next.js 16) | FRONTEND-1, FRONTEND-2, FRONTEND-3 | docs/frontend/FRONTEND_REALITY_AUDIT.md |

**Do not merge by file name.** The code-duplication audit (line 9 of
`JARVIS_CODE_DUPLICATION_AND_CONSOLIDATION.md`) warns that the same basename
can appear in `F:\AI/`, `_tier1/canonical_repo/`, and `Jarvis-super-intelligence-/`
with **different semantics**. `tests/conftest.py` pins the workspace copy of
`backend`/`providers` as authoritative; keep it authoritative.

## 3. Fix defects in the relevant source files
- **Fix in place.** Address confirmed findings in the actual source files
  rather than creating disconnected replacement files, demos, or scratch
  scripts that duplicate behavior.
- **Import safety:** any new module-level dependency that is heavy or optional
  (e.g. `torch`) must be imported lazily or guarded so that
  `python -m pytest --collect-only` still succeeds without it. The Silverwing
  backends package must remain importable without `torch`
  (`test_silverwing_backends_import_without_torch`).
- **No fabrication:** provider/brain/Silverwing results that are unavailable or
  failing must be reported honestly (off/outage), never faked. See
  `JARVIS_WORLD_WORKSPACE_AND_AI_COOPERATION.md`.
- **Entry points:** do not remove or rename Python launchers, dashboards, or
  mount points until deployment references are reviewed.

## 4. Add regression tests and run the relevant checks
Every fix that changes behavior must come with a regression test in `tests/`.
At minimum, every PR must keep the audit regression guard green:

```bash
python -m pytest tests/test_audit_guard.py -q
```

For Silverwing/provider changes also run the scoped suites:

```bash
python -m pytest tests/test_silverwing_runtime.py tests/test_silverwing_gateway.py \
                 tests/test_silverwing_evaluation.py tests/test_provider_fabric.py -q -m "not integration"
```

Compilation must pass for everything you touch:

```bash
python -m py_compile <changed files>
```

## 5. Update audit status with evidence
When you close or open a finding, **update `AUDIT.md`** with:
- the finding ID,
- the verified status change (✅ FIXED only after a green test, ⚠️ OPEN otherwise),
- the exact check/test that proves it, and
- remaining risks.

**Never claim a fix, test, security property, or deployment succeeded without
evidence.** If a check could not be run (no GPU, no Postgres, no provider
credentials, no network), state that explicitly and keep the finding open.

## 6. Preserve existing demos and simulations
This tree contains many simulations, pilots, baseline notebooks, and logs
(`silverwing_120m_smoke.py`, `phase6_*`, `stage3a_*`, baseline JSON, `*.log`).
**Preserve** existing demos/simulations unless a finding explicitly calls for
their removal. Do not delete generated artifacts that are currently tracked as
fixtures without owner review. Environment/credential files (`.env`,
`.env.bak`, `.mcp.json`, `_kaggle_auth.txt`, `__pycache__`, `.venv`, `*.pyc`)
are gitignored and must **never** be committed.

## 7. Secrets and environment files
- **Never print, log, or commit credentials.** `.env`, `.env.bak*`,
  `.mcp.json`, `*_auth.txt`, and `*.pem` are gitignored.
- The only tracked environment sample is `.env.example`; it must contain **no
  live values** (the default admin password finding, P1-1, is the canonical
  example — do not reintroduce a default password).
- Server-side secrets must be provided via `*_FILE` mounts, never echoed into
  frontend config or images.

## 8. Deployment
- This repository is **not** the public deployment artifact. Production
  deployment uses `Jarvis-super-intelligence-/` (excluded from this git tree).
- Do **not** deploy to production, rotate real credentials, or change external
  infrastructure without explicit authorization.
- If a deployment-related finding is "fixed," evidence must come from the
  platform repo's deployment tests (`tests/deployment/test_validation.py`),
  not from this tree.

## Workspace layout quick reference
```
F:\AI (this repo, git root)
├── backend/                 # control_plane, model_gateway (authoritative in this tree)
├── providers/               # provider fabric (ProviderRouter/Adapter/SecretManager)
├── silverwing_runtime/      # Silverwing ASGI runtime (server.py -> app)
├── jarvis_brain/            # brain orchestrator
├── research_engine/         # capability tools/registry (NOT tracked in git; sibling workspace)
├── brain_runtime, brain_training, learning_arena, model_lifecycle, teacher_*
├── tests/                   # pytest suite (pytest.ini; -m "not integration")
├── docs/                    # architecture + docs/Phase1/Phase9 audits
├── docs/audits/             # VERBATIM original audit reports (see README.md)
├── .github/workflows/       # CI (audit-guard.yml)
├── AGENTS.md, AUDIT.md      # this file + findings tracker (ROOT, read first)
└── Jarvis-super-intelligence-/  [GITIGNORED nested platform repo — do not commit]
```

## 9. Frontend area

The authoritative, **Git-trackable** frontend for this project lives at:

```
_tier1/canonical_repo/platform/frontend/web/   (Next.js 16.2.4, React 19, TS 6, Tailwind 3.4)
```

It is tracked in this `F:\AI` git tree (208 source files under `…/frontend/web/src/`) and is the
surface for frontend work on this branch. The `frontend/` inside the git-ignored sibling checkout
`Jarvis-super-intelligence-/` is a **non-authoritative dev copy** (contains `.next` builds) — do
**not** edit or merge from it; prefer the `_tier1` canonical copy. The top-level
`./frontend/web/.tmp-jarvis-transformation/` scratch dir is empty (nothing to preserve).

Before editing the frontend, every agent must:

- **Read** `docs/frontend/FRONTEND_REALITY_AUDIT.md`, `FRONTEND_PRESERVATION_REGISTER.md`, and
  `FRONTEND_TRANSFORMATION_PLAN.md`. They record what is real (live) vs. simulated and the
  do-not-destroy surface (auth, chat SSE streams, voice, dashboard polling, the JARVIS holographic
  theme).
- **Run the local toolchain, not `npx`-resolved binaries.** In this sandbox `npx eslint .` resolves
  to a stray EOL ESLint 10 (no config) and fails. Always use the project-local binaries:
  ```bash
  cd _tier1/canonical_repo/platform/frontend/web
  node_modules/.bin/tsc --noEmit        # type-check — must stay exit 0
  node_modules/.bin/eslint <file>       # lint a touched file (NOT `eslint .` for a baseline)
  ```
- **Lint baseline is large and pre-existing** (`eslint .` → 937 problems; 450 errors / 487
  warnings, dominated by `@typescript-eslint/no-explicit-any`). Do **not** mass-`--fix` or add
  strict new rules — it would churn unrelated code. Keep each **touched file** clean relative to
  its prior state; the enforced green gate is `tsc --noEmit` (exit 0) plus zero **new** lint on
  changed lines.
- **No frontend test runner is configured** (`package.json` has no `test` script; no Jest/Vitest).
  Adding one (vitest) + a regression guard + a `frontend.yml` CI gate is in-scope for this branch
  (see `docs/frontend/FRONTEND_CHANGELOG.md`). A lockfile change is acceptable **only** if a new
  dev-dependency is genuinely required for a regression test, and it must be justified in the PR
  description.
- **The backend is not runnable here.** `next dev`/`next build` expect `jarvis_backend` at
  `http://127.0.0.1:8000` (git-ignored; needs Postgres + provider keys; no GPU/creds in this
  sandbox). Therefore **do not claim live behavior without owner runtime verification**, and do
  **not** fabricate provider/brain results or voice responses.
- **Preserve the JARVIS identity.** The holographic cyan/teal theme in `src/lib/design-tokens.ts`
  + `src/app/globals.css` is intentional and live — this is **not** a ChatGPT clone. Pages that
  deviate from it (e.g. `app/login/page.tsx`, which uses raw `gray-{}`/`purple-{}` Tailwind
  utilities + an inline blob animation) are migration targets, not rewrites.
- **Do not** touch git-ignored duplicate frontends, the `_worktrees/` submodule gitlink, root
  `package-lock.json` (81-byte stub), or any `package-lock.json` unless a real dependency change
  is required.
