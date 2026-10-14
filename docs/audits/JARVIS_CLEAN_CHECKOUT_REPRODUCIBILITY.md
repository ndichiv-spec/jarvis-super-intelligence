# JARVIS clean-checkout reproducibility report

**Assessment date:** 2026-10-13
**Working branch:** `integration/world-workspace-owner-deploy`
**Status:** checkout-local dependency resolution and frontend production build verified; a new remote clone and production container build were not available.

## Changes made

The canonical runtime imported `research_engine`, but that package was only
present in the surrounding `F:\AI` workspace and absent from the recovery
checkout. The package's 13 source modules are now part of this integration
branch:

`__init__.py`, `agent.py`, `capability_contract.py`, `capability_tools.py`,
`data_tools.py`, `document_tools.py`, `geography_math.py`,
`geography_tools.py`, `models.py`, `project_tools.py`, `research_engine.py`,
`tool_registry.py`, and `verification.py`.

`tests/test_research_engine_dependency.py` checks that checkout-local imports
resolve, the existing `ToolRegistry` and `capability_contract` expose
`search_web`, and an isolated subprocess resolves the project root to the
current checkout with inherited `PYTHONPATH`/workspace overrides removed.
`research_engine.project_tools.PROJECT_ROOT` now defaults to the package's
checkout root while still honoring an explicit `JARVIS_WORKSPACE_ROOT`.

Dependency manifests were aligned with the imported Google GenAI client and
generated protocol code:

- `pyproject.toml`, `requirements.txt`, and
  `deployment/production/requirements-production.txt` use
  `google-genai>=1.0,<3`, replacing the legacy `google-generativeai` package.
- `grpcio` and `protobuf>=7.35.1,<8` are declared for the generated gRPC and
  Protobuf interfaces.
- `frontend/web/next.config.mjs` fixes `turbopack.root` to the directory
  containing the config, so an unrelated parent lockfile cannot redirect the
  build root.

The modern Google package follows Google's official `google-genai` SDK
documentation and repository; the application code imports `google.genai`.
This dependency change does not establish a live Gemini provider call.

## Verification

| Check | Result | Scope |
|---|---|---|
| Checkout-local dependency tests | **3 passed** in the backend batch | Import and path checks run from this recovery-based worktree. |
| Python compile | Passed for `jarvis_backend`, `research_engine`, and `tests` | Syntax/import compilation only; does not validate external service access. |
| Production dependency resolver dry run | Passed in this work session before report update | `pip install --dry-run --ignore-installed -r deployment/production/requirements-production.txt`; resolver selected `google-genai` 2.x and Protobuf 7.x with the declared bounds. No image was built. |
| Frontend dependency install | `npm ci --no-audit --no-fund` completed; 753 packages installed | Install scripts were disabled by npm configuration for `esbuild`, `sharp`, and `unrs-resolver`; build subsequently passed. |
| Frontend tests | **123 passed / 32 files** | Full Vitest suite, serial worker mode. |
| Frontend typecheck | Passed | `npm run typecheck`. |
| Frontend production build | Passed | `npm run build`, 51 static pages generated. Explicit Turbopack root removed the parent-workspace warning. |
| Changed frontend ESLint | Passed | Changed task-panel, command API, chat type/workspace, and Next config paths. |
| Whole frontend ESLint | Failed on existing debt | 600 errors and 1,121 warnings across the project; see implementation/release evidence reports. |
| Python changed-file Ruff gate | Not verified | The script failed to parse Ruff JSON because `ruff` is not installed/available in this checkout's configured environment. Python `compileall` passed. |
| Docker image / Compose runtime | Blocked | Docker CLI/daemon is unavailable; no service image or private-port runtime test was performed. |

## Limits

The integration tests were run in the existing isolated Git worktree, not a
fresh `git clone`. The vendored package makes its imports checkout-local and
the subprocess test removes inherited sibling-root hints, but no clean
remote checkout was constructed. `npm ci` and the backend dependency dry run
were performed in the current worktree. Final verification of a pristine
clone should run after the reviewed implementation commit is available to CI.

Provider adapter modules are present in this integration worktree under
`providers/`, and the backend reports that the provider fabric initializes at
startup. A fresh remote clone has not been built, and no real model request was
made: active provider health is degraded/unavailable because no provider
credentials were supplied. This runtime configuration blocker is distinct
from checkout-local `research_engine` imports.
