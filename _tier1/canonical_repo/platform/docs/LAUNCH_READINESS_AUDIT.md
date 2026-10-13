# JARVIS Launch Readiness Audit

## Release decision

**NO-GO.** The checked-in application has a successful frontend production
build and deterministic runtime/provider coverage, but no staging or
production host, real provider credential, external HTTPS verification, or
verified database backup/restore path was available in this checkout. Do not
interpret fixture-backed provider tests as live provider evidence.

This audit was performed against the existing dirty working tree on branch
`main` (`ba23621` at `HEAD`; one commit ahead and one behind `origin/main`).
The tree already contained numerous user and prior-agent changes, including a
modified tracked `platform/tests/_test_jarvis.db`; these were preserved.
`platform/pnpm-lock.yaml` remains unchanged. No commit, deployment, paid API
call, or destructive migration was performed.

## Gate results

| Gate | Result | Evidence |
|---|---|---|
| Frontend production compilation and type checking | PASS | Local Node `v20.20.2`; `node .\node_modules\next\dist\bin\next build` compiled, ran TypeScript, generated all 46 static pages, and completed. A separate `tsc --noEmit -p tsconfig.json` completed without errors. |
| Frontend presentation adapter | PASS | `node --test src/features/chat/presentation-adapter.test.mjs`: 10 passed. |
| Changed frontend lint | PASS | Targeted ESLint on modified routes and layouts completed with no findings. Canvas helpers are module-scoped, `ArcReactor` is declared outside render, and the changed login/shell code is typed and lint-clean. |
| Provider readiness and credential handling | PASS (deterministic) | Tests cover explicit provider selection, secret-file configuration, redaction, missing credentials, and rate limits. A configured provider stays `configured_unverified` until a real operation succeeds. |
| Authenticated image request-to-result path | PASS (fixture-backed) | A deterministic provider fixture exercises authenticated `/api/chat` → `image.generate` → provider adapter → owner-bound media → Presentation Contract 1.1, durable execution events, presentation revision, and idempotent replay. It verifies a real adapter request shape, but does not contact the provider. |
| Authorization and owner isolation | PASS (deterministic) | Runtime tests cover authenticated command/event access, user ownership, media references, and denial of cross-owner event replay. |
| Voice failure honesty | PASS (deterministic) | Runtime tests assert unavailable TTS returns 503, unsupported transcription returns 501, and status is degraded rather than successful. |
| Backend runtime and compatibility tests | PASS (deterministic) | Focused run: 99 passed, 1 skipped. Capability/MCP/command integration run: 71 passed, 1 skipped. Plan-validator run: 13 passed. Exact commands are in `PRODUCTION_VERIFICATION.md`. |
| Database and Redis persistence/connectivity | BLOCKED | Compose declares PostgreSQL/Redis volumes, health checks, secret-backed URLs, and startup dependencies. Docker is not installed here; no database or Redis service was contacted or restarted. |
| Deployment Compose execution | BLOCKED | Compose YAML parses successfully, but `docker compose config`, image build, startup, health checks, restart, and shutdown were not run because the Docker CLI/engine is unavailable. |
| HTTPS, DNS, secure-cookie behavior in a deployment | BLOCKED | Caddy TLS configuration and `Secure`, `HttpOnly`, `SameSite=Lax` auth-cookie flags exist in code. `DOMAIN` and `ACME_EMAIL` are unset; DNS, certificate issuance, and the public endpoint were not tested. |
| Backup and restore | BLOCKED | No backup/restore/rollback scripts were found under `platform/deployment`. Database restoration has not been exercised. |
| Operational log and error redaction | NOT TESTED | Provider response redaction is covered deterministically; deployed log shipping, retention, access controls, and alert delivery were not available to verify. |
| Live image provider smoke | BLOCKED / NOT RUN | No opt-in, selected live provider, provider credential, base URL, or test-user token is configured. The smoke script exited before making a network request. |
| Independent-client and worker-restart verification | BLOCKED | No staging hostname or independently hosted deployment was identified. Persistence across a remote worker restart is therefore unverified. |

## Existing issues and scope

The frontend full build and targeted lint on modified frontend paths succeed.
The repository also has previously observed Ruff lint debt; a targeted run over
the modified Python paths reported 292 diagnostics, including unused
imports/locals, mutable class defaults, blocking calls in async code, and
undefined `__all__` exports in the large capability module. This broad debt was
not mass-fixed as part of launch-gate work. The tracked files use CRLF line
endings; the default `git diff --check` treats added CR characters as trailing
whitespace, while `git -c core.whitespace=cr-at-eol diff --check` passes.
Backend tests emit a pre-existing
Silverwing startup/shutdown warning because its `APIRouter` object is called as
if it had `startup()` and `shutdown()` methods. This integration was not
changed as part of launch-gate work.

An earlier plan-validator run had environment-dependent failures because its
fixture did not initialize the runtime. The fixture now bootstraps the
runtime, and the complete plan-validator module passes (13 tests). One
provider-selection test initially expected a missing credential name in an
HTTP error; it was corrected to assert that the fixture key is not exposed,
and the final focused backend run passes.

## Required before reconsidering the gate

1. Provision a staging host, DNS, ACME email, and server-side secret files using
   `DEPLOYMENT_RUNBOOK.md`; validate and start the production Compose stack.
2. Establish and test a database backup plus restoration into an isolated
   database before accepting real user data.
3. Configure one approved image provider credential and run the opt-in smoke
   once with a dedicated staging account. Preserve its redacted evidence file.
4. Verify sign-in, conversation persistence, media ownership, HTTPS cookies,
   health reporting, and recovery after worker restart from a separate client.
5. Review the remaining repository-wide lint debt.

## Controlled live research preflight — 2026-10-10

**Decision remains NO-GO for live research.** The current checkout is local
development, not a classified staging target. It is on `main`, two commits
ahead of `origin/main`, with the pre-existing dirty worktree preserved. No
staging hostname, dedicated staging identity, or separate owner approval for
potentially billable calls was available. No external endpoint or secret store
was inspected or contacted.

PowerShell found local PostgreSQL 17 on port 5432 and Redis on 6379; neither
was contacted. No application listener was found on ports 8000/8001 or
3000/3101, and the local backend health probes were unavailable. Docker is not
installed; the production `.env` file is absent. Provider/search environment
presence checks found the browser-search gate and inspected provider key
variables unset. Deployment credentials and external secret-store state remain
unknown. The production Compose file does not currently inject research
provider secrets into the API service.

The research path has fixture-backed evidence but no live evidence:
**0** external search calls, **0** provider calls, **0** synthesis calls, **0**
live cost records, and `$0` incurred for this preflight. The code has a
five-minute task time budget and an estimated `$1.00` task cost budget, but
cost accounting occurs after capability execution; no enforceable server-side
pre-call cost ceiling was verified. The nominal two consultations plus one
synthesis are per capability invocation; the shared orchestrator can retry a
transient failed capability under its generic retry budget.

The only tests run in this preflight were isolated fixture tests:

```powershell
pytest -q tests/test_research_compare_runtime.py tests/test_presentation_contract.py tests/test_runtime_durability.py
```

Run from `platform` with `JARVIS_TEST_DB_PATH` set to a unique temporary
database, removed after the run: **36 passed in 34.23s**. No provider or public
search request was made. The test database comparison and safe reconciliation
recommendation, along with the full capability status matrix and required
staging configuration, are recorded in
`INTERNET_NATIVE_RESEARCH_SLICE.md`.

The next milestone is limited to an isolated HTTPS staging target, a dedicated
owner account, server-side search enablement and two approved distinct
provider credentials, a pre-call hard spending/request ceiling, and explicit
approval for one authenticated `/chat` research request. Until those exist,
live research, cross-owner staging denial, deployed cancellation/replay,
worker restart, HTTPS, and operational log-redaction checks remain blocked or
not tested.
