# JARVIS integration test and release evidence

## Current local verification

| Check | Evidence | Interpretation |
|---|---|---|
| Focused owner/auth/security and persistence configuration | `python -m pytest tests/test_auth.py tests/test_security_regression.py tests/test_endpoint_gateway.py tests/test_postgres_engine_config.py -q --tb=short` — **82 passed** | Confirms the focused locally testable owner, endpoint, security and PostgreSQL engine-configuration paths after changes. Does not test an actual PostgreSQL service. |
| Complete offline backend suite | PowerShell: `$env:JARVIS_TEST_DATABASE_PATH = Join-Path $env:TEMP '<unique>.sqlite'; python -m pytest -q -m 'not integration' --tb=short` — **2,572 passed, 14 skipped, 13 deselected** in 506.65s | Final run against this mission's backend changes using a unique disposable SQLite database. `tests/conftest.py` enforces that the configured file is outside the repository. Live/integration tests remain excluded. |
| Syntax | `python -m compileall -q jarvis_backend tests` — passed | Python sources compiled at check time. |
| Changed-file Ruff gate | `python scripts/check_ruff_debt.py --base HEAD` — passed | Touched Python files do not add Ruff findings relative to current HEAD; this is not a clean whole-repository Ruff result. |
| Whitespace | `git diff --check` — passed | No whitespace errors at check time. |
| Earlier backend baseline | `docs/audits/JARVIS_BLOCKER_RESOLUTION_AND_VERIFICATION.md` records **2,566 passed, 14 skipped, 13 deselected** for `pytest -m "not integration"` | Historical result from the earlier recovery state. The current-tree run above supersedes it for this mission's backend changes. |
| Earlier frontend baseline | Same prior recovery report records **118 passed** with frontend Vitest, plus typecheck and production build | Not rerun for this backend-only change; frontend was not changed by this mission. |
| PostgreSQL, Supabase, containers, providers | Not run | No `psql`, Docker, Supabase project, provider credentials, or deployment host was available. |
| Dependabot alert inventory | GitHub API inventory recorded **573 open alerts**: 33 critical, 293 high, 196 medium, and 51 low. Initial critical/high summaries included `torch` in `videlisndichi-jarvis-brain-qwen3-4b-sft-train/requirements.txt` and `pypdf`, `GitPython`, `urllib3`, and `aiohttp` in `_tier1/canonical_repo/platform/requirements.txt`. | The alert set spans many manifests. The listed package/path pairs are triage examples, not a complete review or proof those requirements are deployed by the canonical production image. No broad package upgrade was attempted; manifest ownership and active build reachability need per-alert review. |

## Reproducible local test requirements

Use repository-declared Python dependencies (`pyproject.toml` and the
requirements files) and pytest configuration (`pytest.ini` and
`pyproject.toml`). Tests must use an isolated disposable database. In
PowerShell, set `$env:JARVIS_TEST_DATABASE_PATH` to a unique file under
`$env:TEMP`; never point it at tracked, production, or development data.
`tests/conftest.py` rejects a configured path inside the checkout. Do not start
services on ports 5000/8000; use in-process ASGI test clients for API unit
tests. Live provider and infrastructure tests remain explicitly
marked integration/live-provider tests with controlled setup.

The recovered suite's previous successful run used a unique temporary SQLite
database and deselected integration cases. The full offline suite passed on
this mission's changed backend tree using that isolation contract. The sibling
`F:\AI\research_engine` import is currently required on this machine but is
untracked and outside the checkout; consequently a clean clone has not been
proven reproducible.

## Release gate

Release requires: successful full offline backend tests on the final tree;
critical auth/ownership/API-key/OAuth regression tests; compile and changed
file lint checks; frontend checks when its files change; clean-clone
dependency resolution; container build and Compose validation; staging
PostgreSQL migration/connection and backup/restore tests; authorized-provider
integration tests where advertised; Caddy/TLS/DNS/public-route verification;
owner-only multi-device session and revocation checks; and rollback/restart
evidence. Static files and unit tests cannot substitute for those
infrastructure checks.

No production release, Supabase integration, external provider health, or
public internet reachability is claimed by this evidence.
