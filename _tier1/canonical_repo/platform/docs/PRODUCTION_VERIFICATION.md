# Production Verification Evidence

## Scope and runtime

This is local deterministic verification of the current checkout, not evidence
of a running production deployment. The supported frontend container pins
Node `22.14.0`; the local checks below used Node `20.20.2`, which successfully
ran the installed Next.js 16.2.4 build and TypeScript compiler. The global
pnpm version is 11.18.0 and requires Node >=22.13.0. Frontend scripts were
invoked directly with the installed project dependencies to avoid the
workspace's POSIX `sh` preinstall hook on Windows. The build did not alter the
checked-in `platform/pnpm-lock.yaml`.

The Next build emitted workspace-root inference and stale Browserslist-data
warnings, then completed successfully. It compiled, ran TypeScript, generated
all 46 static pages, and finalized production output.

## Deterministic test/build results

| Command (from indicated directory) | Result | Scope |
|---|---|---|
| `platform/frontend/web`: `node .\node_modules\typescript\bin\tsc --noEmit -p tsconfig.json` | PASS | Frontend TypeScript check, Node 20.20.2. |
| `platform/frontend/web`: `node .\node_modules\next\dist\bin\next build` | PASS | Production Next.js build; TypeScript completed and all 46 static pages generated under Node 20.20.2. |
| `platform/frontend/web`: `node --test src/features/chat/presentation-adapter.test.mjs` | PASS: 10 passed | Presentation Contract compatibility and fallback behavior, including v1.1 generated-image reference validation. |
| `platform/frontend/web`: ESLint on changed chat and voice runtime files | PASS | Chat `store.ts`/`types.ts` and voice `store.ts`/`streamClient.ts`/`voiceEngine.ts`; no findings. |
| `platform`: `pytest -q tests/test_media.py tests/test_runtime_truthfulness.py tests/test_image_capability_runtime.py tests/test_presentation_contract.py tests/test_presentation_revisions.py tests/test_runtime_durability.py tests/test_endpoint_registry_runtime.py tests/test_world_resolver.py tests/test_voice_runtime.py` | PASS: 99 passed, 1 skipped | Provider configuration/error handling, image runtime, presentation, owner isolation, durable events, endpoint state, resolver, and voice truthfulness. |
| `platform`: `pytest -q tests/test_capability_contract.py tests/test_capability_fabric.py tests/test_mcp_runtime.py tests/test_command_runtime_integration.py` | PASS: 71 passed, 1 skipped | Capability registration/fabric, MCP, command runtime. |
| Repository root: `pytest -q tests/test_plan_validator.py` | PASS: 13 passed | Plan validation with explicit runtime bootstrap in its fixture. |
| `platform`: Python `yaml.safe_load` of `deployment/production/docker-compose.prod.yml` | PASS: YAML parse | Syntax parse only; it is not Compose schema validation or a container test. |
| `platform`: `python -m py_compile scripts\live_image_smoke.py` | PASS | Smoke script syntax. |
| `platform`: `python scripts/live_image_smoke.py` without opt-in | EXPECTED BLOCK | Exited before network with “Live test is disabled”; no provider request was sent. |
| `platform/frontend/web`: targeted ESLint on modified routes and layouts | PASS | No findings across the modified dashboard, login, chat, and holographic pages and shell components. |
| `platform`: selected runtime/compatibility tests, including image, voice, research comparison, and isolated-candidate modules | PASS: 118 passed, 1 skipped | Ran with a unique temporary SQLite database; no live provider calls. |
| `platform`: `pytest -q tests/infrastructure/test_config.py` | PASS: 19 passed | Configuration priority and environment/source precedence. |
| Repository root: targeted `ruff check --output-format concise` on modified Python paths | FAIL: 292 diagnostics | Existing debt spans long-lived runtime/capability files; details summarized in `LAUNCH_READINESS_AUDIT.md`. |
| Repository root: `git -c core.whitespace=cr-at-eol diff --check` | PASS | CRLF endings are recognized; the default check otherwise flags added carriage returns as trailing whitespace. |

Backend tests use deterministic provider fixtures. In particular, the
image-generation runtime fixture verifies the selected adapter endpoint,
validated output bytes, owner-scoped media reference, correlated lifecycle
events, persisted presentation revision, replay idempotency, and the absence
of a second provider invocation on replay. It is not a live OpenAI, Replicate,
or Stability result.

The 118-test compatibility run was executed from `platform` with
`JARVIS_TEST_DB_PATH` set to a unique temporary file:

```powershell
python -m pytest -q tests/test_media.py tests/test_runtime_truthfulness.py tests/test_image_capability_runtime.py tests/test_presentation_contract.py tests/test_presentation_revisions.py tests/test_runtime_durability.py tests/test_endpoint_registry_runtime.py tests/test_world_resolver.py tests/test_voice_runtime.py tests/test_research_compare_runtime.py tests/test_isolated_candidate.py
```

The runtime tests also cover missing provider credentials, explicit provider
selection, credentials loaded from a server-side file, provider rate limits,
malformed output, timeout without retry, cancellation, approval/permission
denial, and media ownership. The voice tests verify actual status/error
semantics and use controlled adapter fixtures for the separately implemented
ASR/TTS request path.

## Provider readiness and live evidence

At verification time, the following variables were absent from the process
environment: `JARVIS_LIVE_BASE_URL`, `JARVIS_LIVE_AUTH_TOKEN`,
`JARVIS_LIVE_IMAGE_PROVIDER`, `OPENAI_API_KEY`, `REPLICATE_API_KEY`,
`STABILITY_API_KEY`, `DOMAIN`, `ACME_EMAIL`, `DATABASE_URL`, and `REDIS_URL`.
This is an environment-presence check only; it does not inspect external
secret stores or a remote server.

No live smoke was attempted because the required opt-in and deployment
configuration were absent. To run one approved generation against staging:

1. Provision exactly one provider key server-side and configure
   `JARVIS_IMAGE_PROVIDER` to that provider. Do not put provider credentials in
   the browser or test result file.
2. Create a dedicated authenticated staging user and obtain a short-lived
   token.
3. Set `JARVIS_LIVE_IMAGE_OPT_IN=1`,
   `JARVIS_LIVE_IMAGE_PROVIDER=openai|replicate|stability`,
   `JARVIS_LIVE_BASE_URL=https://<staging-host>`,
   `JARVIS_LIVE_AUTH_TOKEN=<short-lived-token>`, and
   `JARVIS_LIVE_SMOKE_RESULT_FILE=<new-absolute-path-outside-repository>`.
4. After explicit owner approval for one potentially billable image, run
   `python scripts/live_image_smoke.py` from `platform`.

The script checks selected-provider readiness, issues one authenticated
conversation request with a fixed small test prompt, validates the correlated
Presentation Contract 1.1 result and durable command events, fetches and
validates owner-authorized image bytes, checks persisted presentation
revisions, and verifies idempotent replay without another generation. It
uses bounded HTTP timeouts and does not retry a failed request. Its output is
redacted metadata; the result path must not exist and must be outside the
repository.

**Live result: NOT RUN.** Do not represent deterministic fixtures or a
`configured_unverified` status as live-provider evidence.

## Deployment and recovery evidence

`deployment/production/docker-compose.prod.yml` defines PostgreSQL 16.4 and
Redis 7.4.2 with named data volumes and health checks; an idempotent migration
service; API/frontend readiness checks; persistent runtime/media volumes;
resource limits, dropped capabilities, read-only container roots, and graceful
stop windows; and Caddy on ports 80/443 with automatic certificate handling.
The backend production startup checks for a 32-character signing key,
16-character admin password, PostgreSQL URL, explicit CORS origins, and admin
identity. Compose uses server-mounted secret files. The auth cookie code sets
`Secure`, `HttpOnly`, and `SameSite=Lax`.

These are configuration/code observations, not a deployment verification:

* Docker was not available, so Compose schema validation, image builds,
  PostgreSQL/Redis connections, migration execution, container health,
  shutdown, or restart were **NOT TESTED**.
* `DOMAIN` and `ACME_EMAIL` were unset, so DNS, HTTPS, and certificate
  issuance were **NOT TESTED**.
* No backup/restore or rollback scripts were found under `platform/deployment`;
  backup creation and restoration were **BLOCKED**.
* No production/staging URL or independent client was configured. Remote
  availability, persistent login/chat after refresh, and restart recovery were
  **NOT TESTED**.
* No migration reset or destructive data operation was run.

See `DEPLOYMENT_RUNBOOK.md` for the explicit external prerequisites and
operator steps that remain.

## Controlled live research preflight — 2026-10-10

**Live staging research: BLOCKED; no external calls made.** The inspected
checkout is local development on branch `main` (two commits ahead of
`origin/main`) with a dirty worktree that was preserved. No staging target,
hostname, dedicated staging identity, or separate approval for potentially
billable calls was available. The production Compose template exists, but its
`.env` is absent, Docker is not installed, and the template does not currently
wire research-provider credentials to the API. External secret stores were not
inspected; deployment credential state is unknown.

The process had `JARVIS_BROWSER_SEARCH_ENABLED` unset and no inspected
OpenAI/Google/NVIDIA/Hugging Face/AWS provider credentials configured.
PostgreSQL 17 and Redis were listening locally on 5432 and 6379, but were not
contacted. No listener was found on backend ports 8000/8001 or frontend ports
3000/3101; local backend health probes were unavailable. This is not a
staging or production health result.

Exact fixture command run from `platform` (with a unique temporary
`JARVIS_TEST_DB_PATH`, removed afterward):

```powershell
pytest -q tests/test_research_compare_runtime.py tests/test_presentation_contract.py tests/test_runtime_durability.py
```

Result: **36 passed in 34.23s**. These fixtures mock provider and search
adapters; no live search/provider request was made. The tracked SQLite test
database was inspected read-only for hashes, schemas, and table row counts.
Its modified copy and tracked baseline were both preserved; see
`INTERNET_NATIVE_RESEARCH_SLICE.md` for their exact deltas and safe
reconciliation recommendation.

This preflight observed **0** search calls, **0** provider calls, **0**
synthesis calls, and **0** live cost records; actual external cost was `$0`.
The existing task budget's estimated `$1.00` maximum is accounted after tool
execution and is not an enforceable pre-call spend ceiling. A capability
invocation nominally requests at most two concurrent consultations and one
synthesis, but the generic orchestrator retry policy means no end-to-end
request attempt ceiling has been evidenced. No live attribution, `/chat`
rendering, source retrieval, provider billing, staging authorization,
cross-owner denial, deployed cancellation/replay, HTTPS, operational log
redaction, or worker-restart recovery has been verified.

Do not run the live request until a dedicated HTTPS staging target and owner
identity exist; search is enabled on that backend; two distinct, approved
provider credentials are injected server-side; a hard per-request cost and
attempt ceiling is enforced before external calls; and the owner explicitly
approves the one-request scope. The runbook and research-slice document retain
the remaining configuration and verification steps.
