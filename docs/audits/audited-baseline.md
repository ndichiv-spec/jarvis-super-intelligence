# docs/audits/audited-baseline.md — audited baseline & limitations

This document fixes **what** the audit findings below apply to, so agents never
audit (or "fix") the wrong tree.

## Precise baseline

| Item | Value |
|------|-------|
| Repository under modification | `github.com/ndichiv-spec/jarvis-super-intelligence` |
| Git remote (this tree) | `origin = https://github.com/ndichiv-spec/jarvis-super-intelligence.git` |
| Active branch | `docs/jarvis-audit-integration` |
| Baseline commit (this tree) | `fd39c1d157c07ebd06c9643ab865a8dfcf9ffb4f` (== `main`) |
| Canonical reference checkout | `_tier1/canonical_repo` @ `fd39c1d157c07ebd06c9643ab865a8dfcf9ffb4f` (same nominal commit; carries an extra untracked `platform/` working-tree copy) |
| Platform application checkout | `Jarvis-super-intelligence-/` @ `30ec1595926f760cec6f45dd8fc2fc4ba2b11a72` (branch `recovery/wip-inventory-20261014`; recovery reports reference `recovery/integration-20261012` @ `19bd962`) |

The original audit reports in this directory were produced by the JARVIS
recovery audit and describe the JARVIS system end-to-end. They are preserved
**verbatim** and are **not** re-audited here; `AUDIT.md` (repo root) maps those
findings onto the *actionable* items in this tree.

## What this tree tracks vs. what it does **not** track

### Tracked by this repo (`F:\AI`)
- Brain / provider / backends packages: `providers/`, `silverwing_runtime/`,
  `jarvis_brain/`, `backend/` (`control_plane`, `model_gateway`), `brain_runtime`,
  `brain_training`, `learning_arena`, `model_lifecycle`, `teacher_*`, `identity/`.
- Integration test suite `tests/` (root `conftest.py`-based, `pytest.ini`,
  asyncio mode auto, default `not integration`).
- Architecture docs: `docs/JARVIS_PHASE1_AUDIT.md`, `docs/PHASE9_AUDIT.md`,
  `docs/PHASE9_PLAN.md`, plus this `docs/audits/` set.
- Scripts: `diag_harvest.py`, `start_*.py`, `phase6_*`, `stage3a_*`,
  `silverwing_120m_*`, etc. (demos/simulations — preserved).
- CI: `.github/workflows/audit-guard.yml`.

### **Not** tracked by this repo (gitignored / sibling checkout)
- `Jarvis-super-intelligence-/` — a **gitignored nested git repository**
  (see `.gitignore` §10). Per `.gitignore`, this checkout "contains committed
  encryption keys" and is "Left EXCLUDED pending a merge/decision so git does
  not record it as a gitlink and silently drop its content." It hosts the
  **full JARVIS platform application** (`jarvis_api.py`, `jarvis_backend/`,
  `frontend/`, `deployment/`, `infrastructure/`, `scripts/`) which is **absent**
  from this tree's git history.
- `F:\AI/research_engine` — the `research_engine` package is imported by
  in-tree and platform modules but is **not tracked** here; it resolves only
  from the untracked sibling workspace on this machine.
- `.env`, `.env.bak`, `.env.bak2`, `.mcp.json`, `*_auth.txt`, `*.pem`,
  `__pycache__/`, `.venv/` — gitignored; never committed.

> **Consequence:** a clean clone of `github.com/ndichiv-spec/jarvis-super-intelligence`
> is **not** a self-contained JARVIS deployment. It builds the
> brain/provider/backends packages and the in-tree test suite, but it does
> **not** reproduce the platform app, the frontend, or production deployment.

## Limitations (what is NOT verified in this tree)

1. **Clean-clone reproducibility is blocked (P1-4).** The platform app relies on
   `research_engine` from the untracked sibling `F:\AI/research_engine`, and
   `jarvis_backend` lives only in the excluded platform checkout. A fresh clone
   therefore cannot run the full backend test suite or start the platform API
   without that external workspace. Collection in *this* sandbox succeeds only
   because the sibling workspace is present.
2. **No live providers / no GPU / limited network.** No `NVIDIA_API_KEY`,
   `HF_TOKEN`, or Kaggle token is configured. Provider/cloud suites must remain
   `@pytest.mark.skipif`/`importorskip` and report truthful
   UNCONFIGURED/OFFLINE states. (This sandbox had PyPI access for `pip-audit`;
   provider endpoints are not reachable.)
3. **No PostgreSQL or Docker.** `psql` and Docker are unavailable; SQLite is the
   disposable test database (`JARVIS_TEST_DATABASE_PATH`). Migration
   (`scripts/migrate_persistence.py`) and pool behavior toward PostgreSQL are
   **not** exercised here.
4. **No production deployment.** No DNS, TLS certificate, host, or cloud
   credential is available or claimed. Deployment findings are **documented**
   against `Jarvis-super-intelligence-/deployment/production/*` (excluded
   tree) and are **not** fixed in this tree.
5. **Dependency manifests not pinned (P2-3).** There is no root
   `pyproject.toml`/`requirements.txt` in this tree, so the audit-guard CI
   installs `pytest httpx pydantic` ad hoc. The live sandbox Python environment
   additionally carries unrelated transitive packages with version conflicts
   (`pip check`, P2-4); these reflect the sandbox, not a pinned tree manifest.
6. **573 GitHub Dependabot alerts** are recorded against the platform
   manifest tree (torch, pypdf, GitPython, urllib3, aiohttp among critical/high
   examples); they are **not** individually triaged here (P2-5).
7. **Secret scan scope.** Scanning covered tracked source and full Git history
   of *this* tree. The excluded platform checkout and untracked `.env`/`research_engine`
   are **not** scanned for live secrets in this pass.
8. **Code duplication.** `backend/`, `providers/` and other packages have
   divergent copies across `F:\AI/`, `_tier1/canonical_repo/`, and
   `Jarvis-super-intelligence-/`. Only the `F:\AI/` (workspace) copy is treated
   as authoritative for this tree (pinned by `tests/conftest.py`).

## What changes must pass
Any change committed on `docs/jarvis-audit-integration` must keep:
- `python -m pytest tests/test_audit_guard.py -q` green (regressions pinned).
- `python -m py_compile` clean on every touched Python file.
- `git diff --check` introduces **no new** trailing-whitespace errors; note
  several tracked Python files retain pre-existing **CRLF** baseline endings
  (no `.gitattributes`) which `git diff --check` reports as `\r` — these are
  inherited, not introduced here, and are not mass-normalized in this pass
  (see AUDIT.md P2-6).
- No secrets, `.env*`, or excluded-platform content added to the tree.
