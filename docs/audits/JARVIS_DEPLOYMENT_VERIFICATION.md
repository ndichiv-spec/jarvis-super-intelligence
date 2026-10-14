# JARVIS deployment verification report

**Assessment date:** 2026-10-13
**Release decision:** **not deployed; production acceptance blocked**. No public service or externally reachable endpoint was created by this work.

## Current local runtime attempt — 2026-10-13

- The actual FastAPI backend (`jarvis_backend.main:app`) and Next.js frontend
  were started on `127.0.0.1:8000` and `127.0.0.1:3000`. Backend liveness
  returned `alive`; frontend `/login` returned HTTP 200 and rendered the sign-in
  form. The unauthenticated `/dashboard` route resolved to `/login`.
- `/health/ready` reported the SQLite database available and the overall
  service ready, but runtime health degraded: the configured Celery broker was
  unreachable, no workers were detected, and the brain/provider was not
  configured. `/silverwing/health` returned `integrated`. Anonymous command
  read/write requests returned HTTP 401.
- The first interactive attempt exposed a login hydration race: the browser
  could submit the SSR form natively before React attached the login handler.
  The login form now remains disabled until hydration, uses POST as a
  defense-in-depth form method, and has two frontend regression tests. A
  production Chromium smoke test now logs the owner into the workspace from
  both `localhost:3000` and `127.0.0.1:3000`; `/api/v1/auth/login` and `/me`
  returned 200. The same browser session also survived page reload and a
  supervised backend restart.
- The former SQLite file was integrity-checked and copied via SQLite's online
  backup API to `%LOCALAPPDATA%\JARVIS\jarvis.db`; the original file was left
  untouched. The local signing key is persistent and ACL-restricted to the
  installing owner and SYSTEM, so local tokens remain verifiable after restart.
  Migration check passed with 25 tables and revision 003. This is local SQLite
  evidence only; it does not verify PostgreSQL or worker/task recovery.
- A real DuckDuckGo search integration test passed through `ChatService`; no
  model-provider call was made. Provider code is present in this worktree and
  initializes, but runtime readiness is degraded and model credentials are
  absent.
- Docker/Compose, PostgreSQL, a compatible Redis broker, owner credentials,
  provider credentials, host/domain/DNS, and deployment authorization were not
  available. No public deployment, paid service call, or production mutation
  was attempted.

## Independent local Windows runtime

Verified 2026-10-13 on the integration worktree: the `JARVIS Local Runtime`
Task Scheduler task is running at the owner account's logon. Its project-owned
supervisor keeps the production Next.js frontend and FastAPI backend alive
without an IDE, restarts either after a process failure, and binds both only
to loopback (`127.0.0.1:3000` and `127.0.0.1:8000`). The login page returned
HTTP 200, the API liveness route returned `alive`, and database readiness
returned `ready` against `%LOCALAPPDATA%\JARVIS\jarvis.db`. The former runtime
SQLite database was copied with SQLite's backup API and integrity-checked;
the original was not overwritten. The persistent signing key is ACL-restricted
to the local owner and SYSTEM. A frontend crash/restart and graceful runtime
stop/start were exercised; an authenticated owner session survived a
supervised backend restart.

This is local availability only: the PC must remain powered on and the owner
account signed in. Runtime health currently reports no configured brain/model
providers and an unreachable worker broker, so autonomous model reasoning and
durable queue work are not verified or claimed. Availability while the PC is
off requires the separately documented authorized production host.
Installation and operator commands are in
[`windows-local-autostart.md`](../deployment/windows-local-autostart.md).

## Operator commands

The following foreground commands remain available for manual development.
They are separate from the verified, IDE-independent Task Scheduler runtime
above and do not establish a production deployment.

**Windows local SQLite backend** (run the migration before starting Uvicorn):

```powershell
Set-Location F:\AI\_worktrees\jarvis-world-workspace
$env:JARVIS_DB_PATH = Join-Path $PWD 'jarvis_data\jarvis.db'
.\.venv\Scripts\python.exe scripts\migrate_persistence.py --upgrade
.\.venv\Scripts\python.exe -m uvicorn jarvis_backend.main:app --host 127.0.0.1 --port 8000
```

**Frontend** (separate PowerShell window):

```powershell
Set-Location F:\AI\_worktrees\jarvis-world-workspace\frontend\web
npm ci
npm run dev -- --hostname 127.0.0.1
```

Press `Ctrl+C` in each owning terminal to stop its foreground process. The
worker cannot be started here: it requires a private supported Redis broker;
do not point it at the unrelated shared Redis service.

For the owner-controlled Linux deployment, provision the documented secret
files and immutable image tags first, then follow `docs/deployment/production.md`:

```sh
cd deployment/production
docker login ghcr.io
eval "$(python3 ./public_urls.py --env-file .env --shell --production)"
docker compose --env-file .env -f docker-compose.prod.yml config
bash ./deploy.sh
docker compose --env-file .env -f docker-compose.prod.yml stop
```

`deploy.sh` requires `JARVIS_VERSION` and `PREVIOUS_JARVIS_VERSION` and
performs its documented readiness/automatic image rollback checks. Database
restore and service recovery instructions are in
`docs/deployment/backup-restore.md` and `docs/deployment/recovery.md`. None of
these production commands was run because the required host, secrets, domain,
Docker runtime, and authorization are absent.

## Deployment acceptance status

| Criterion | Implemented/configured | Locally verified | Integration verified | Production verified | Status / remaining evidence |
|---|---|---|---|---|---|
| Standard HTTPS URL / TLS | Caddy and public URL configuration exist in `deployment/production/`. | Configuration validation tests pass. | No deployment host or DNS. | No. | Blocked on an owner-controlled domain, DNS records, host, firewall, and certificate issuance/renewal test. |
| Internal backend/database/cache/worker ports private | Compose describes Caddy as public gateway and internal service names for backend, Postgres, Redis, worker, and beat. | Static tests pass; no daemon available to render/start Compose. | No. | No. | Must inspect rendered Compose and host firewall after Docker access is supplied; verify only intended 80/443 gateway ports are externally reachable. |
| Operates without owner's PC | Production Compose defines backend, worker, beat, database/cache services. | Not run. | No. | No. | Requires a persistent VPS/cloud host and deployment credentials. This local checkout/PC is not deployment infrastructure. |
| Authorized device login / owner enforcement | JARVIS-native owner gate, cookie sessions, endpoint registration/revocation and task-owner checks exist. | Auth/device/ownership tests pass in local backend selection. | Direct service integration uses synthetic principal, not live login. | No. | Needs staging owner login, second-device enrollment, session/device revoke and non-owner denial over HTTPS. |
| Persistent owner memory/task state across restarts | Existing SQLAlchemy persistence, command records, event journal, worker lease/recovery code exist. | A synthetic `ChatService` session survived an actual SQLite backend restart; focused SQLite idempotency/recovery tests passed. | No running PostgreSQL/Redis/worker restart test. | No. | Requires staging process/host restart, backup/restore and resumed-task observation. |
| Production provider health and capability truth | Provider fabric modules and adapters are present in this integration worktree; health reports unavailable/degraded when no credentials are configured. | Startup and truthful degraded-health path checked. | One real DuckDuckGo search was exercised for the World Workspace; no model call. | No. | No API credentials supplied; no live inference or multi-model call has been tested. |
| Clean-checkout build | `research_engine` source now resides in this integration tree; frontend Turbopack root is fixed to the app directory. | Checkout-local import/path tests, dependency dry-run, frontend `npm ci`, 123 frontend tests, typecheck and production build pass. Full offline backend suite has **13 failures**; see below. | No separate clean clone performed. | No. | Review/commit branch then run clean CI checkout; Docker image build unavailable. |
| Rollback and recovery | Immutable image version and database migration/backup mechanisms are present in deployment materials. | No rollback executed. | No. | No. | Needs previous-image inventory, staging DB snapshot/restore, forward/backward-compatible schema test, and recovery drill before release. |

## Local evidence

- `tests/deployment/test_validation.py`: **12 passed** (static configuration
  validation only).
- Full offline backend run:
  `python -m pytest -m 'not integration' --tb=short -q` — **2,561 passed,
  23 skipped, 13 deselected, 13 failed**, exit 1 in 672.14s. The failures are
  one missing legacy agents route expectation, 11 missing control-center route
  expectations, and one unavailable semantic-reranker expectation.
- Backend focused regression selection: **149 passed, 2 skipped, 1
  deselected**; the omitted existing `test_agents.py::test_agent_execution`
  expects the absent `/api/v1/agents/execute` route and is not a deployment
  check.
- Real web integration: **1 passed** for DuckDuckGo search through the
  canonical runtime. It does not prove deployed inference, source-page
  verification, or public reachability.
- Frontend: **123 tests passed**, typecheck passed, production build passed,
  changed-file ESLint passed. Whole-tree ESLint remains at 600 errors and
  1,121 warnings.
- `docker` is not installed/available in this environment. No deployment
  service was started.

## Required infrastructure and access

Provision these through the owner's normal infrastructure and secret-management
channels; do not put secret values in this report or a source change:

1. A long-running owner-controlled VPS/cloud host or approved deployment
   service, with Docker/Compose access, persistent volumes, a supported
   operating system, resource quotas, and restart policies.
2. A domain controlled by the owner, DNS access, and an HTTPS certificate
   issuance/renewal path. Configure the canonical public URL and standard
   HTTPS/WebSocket routing.
3. Host firewall/security-group access to allow public gateway traffic only;
   keep backend, PostgreSQL, Redis, worker, beat, and administrative ports
   private. Define a separate authenticated admin access path.
4. Production secret provisioning for the owner account, JARVIS signing and
   encryption keys, database and Redis URLs/credentials, CORS/origin policy,
   and any explicitly enabled SMTP/OAuth/model provider credentials.
5. A database decision: the current Compose topology provisions its own
   PostgreSQL service. A Supabase-managed database requires an explicit
   deployment mode, TLS/pooler testing, migrations, quota settings, and
   backup/restore evidence; a URL substitution alone is not an integrated
   deployment.
6. A provider-fabric source/reconciliation decision and authorized provider
   credentials before advertising model availability or multi-model
   cooperation.
7. A protected backup destination and restore owner, plus a staged immutable
   image/tag to roll back to.

## Release gate

Deployment may proceed only after the source branch has been reviewed and
reconciled safely, a clean checkout builds, the Docker image and rendered
Compose topology pass, staging confirms owner-only access and device
revocation, private ports are externally unreachable, PostgreSQL/worker task
recovery survives restart, HTTPS renewal and monitoring work, backups restore,
and rollback is rehearsed. None of those production checks has been performed
in this environment.
