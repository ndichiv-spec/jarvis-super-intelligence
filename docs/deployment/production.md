# Single-host production deployment

The supported initial production topology uses a Linux VPS with Docker Compose:

`Internet -> Caddy (public 80/443, automatic TLS) -> Next.js / FastAPI -> PostgreSQL + Redis`

The Celery worker and scheduler are separate long-lived services. PostgreSQL,
the Celery broker, cache, uploads, scheduler state, and Caddy certificates use
named persistent volumes. The production Compose file is
`deployment/production/docker-compose.prod.yml`; the repository-root
`docker-compose.yml` is retained as an integration/local stack and is not the
public deployment target. Kubernetes manifests remain available separately.

## Prerequisites

- A supported Linux host with Docker Engine and the Docker Compose plugin.
- A real domain and DNS records pointing to the host; see
  [domain-and-tls.md](domain-and-tls.md).
- GHCR access to pull immutable backend/frontend image tags published by the
  repository workflow.
- Server-side secret files and a real OpenAI API key; only its path is placed
  in Compose configuration. Do not put credential contents in the repository,
  `.env`, container labels, or command arguments.

Create `deployment/production/.env` from `.env.production.example`; set `JARVIS_DOMAIN`,
`ACME_EMAIL`, the initial `JARVIS_ADMIN_EMAIL`, a published `JARVIS_VERSION`
such as a workflow-generated `sha-<commit>` tag, and
`PREVIOUS_JARVIS_VERSION` before rollout. Set `GIT_SHA` to the matching full
40-character commit SHA, `BUILD_TIME` to its UTC ISO-8601 image build time, and
`DEPLOYMENT_ID` to a unique safe identifier. Set file source paths to absolute
paths outside the checkout. The mounted files should be readable only by the
host administrator and Docker (`0600` on the host). Required secret material:

- PostgreSQL password; Redis cache and queue passwords.
- Stable JARVIS signing/encryption key (at least 32 characters).
- Initial administrator password (at least 16 characters).
- OpenAI provider key, OAuth client JSON (use `{}` until configured), and the
  alert webhook signing-secret file (an empty file is acceptable until a
  webhook URL is configured).
- PostgreSQL URL, Redis cache URL, and Celery broker URL.

The PostgreSQL and Redis URL files contain service DNS names, not public
addresses. Generate URL-safe passwords, then write their URIs to the
corresponding protected files. The PostgreSQL URL must use
`postgresql://...@postgres:5432/<database>`; cache and queue URLs must target
`redis-cache:6379/0` and `redis-queue:6379/0`.

Alert delivery is opt-in. Set `JARVIS_ALERT_WEBHOOK_URL` to a trusted HTTPS
receiver and place a random signing secret of at least 32 characters in the
file referenced by `ALERT_WEBHOOK_SECRET_FILE_SOURCE`. The API signs each JSON
delivery with HMAC-SHA256 and retries transient failures up to three times.
With no URL or signing secret, delivery state remains
`ALERT_DELIVERY_NOT_CONFIGURED`; no success is simulated.

## Deployment

From the deployment directory:

```sh
docker login ghcr.io
eval "$(python3 ./public_urls.py --env-file .env --shell --production)"
docker compose --env-file .env -f docker-compose.prod.yml config
bash ./deploy.sh
```

`public_urls.py` derives the public, API, and WebSocket URLs from
`JARVIS_DOMAIN`, `JARVIS_SCHEME`, `JARVIS_PUBLIC_PORT`, `JARVIS_BASE_PATH`,
`JARVIS_API_PATH`, and `JARVIS_WS_PATH`. Production Caddy requires HTTPS on
port 443 and an externally reachable HTTP port 80 for automatic TLS. Set
`JARVIS_API_PATH=/api` and `JARVIS_WS_PATH=/ws`; those are the backend's
existing public routes. `JARVIS_BASE_PATH` may be `/` or a deployment prefix.
For a prefix, set the GitHub Actions repository variable `JARVIS_BASE_PATH` to
the same path before publishing images; Next.js embeds that prefix at build
time. The browser uses the deployed same-origin URL model and derives `wss:`
from its HTTPS origin; internal service addresses remain private to Compose
networks.

`deploy.sh` requires `PREVIOUS_JARVIS_VERSION`, verifies pre-rollout backups,
pulls immutable images, runs the explicit migration/seed job, starts services,
and polls the public readiness endpoint. It restores the previous image tag if
the candidate does not become healthy. Schema changes run in the explicit
migration job and are recorded in the `jarvis_schema_migrations` ledger. `python scripts/migrate_persistence.py
--status` lists applied and pending revisions; `--upgrade` applies the ordered
registry; `--check` fails unless every expected table and revision is present.
Revision `001_initial_kv_store` establishes/adopts the existing key/value
schema; `002_durable_command_events` adds an ordered event table and backfills
the existing command event snapshots. Revision
`003_durable_runtime_event_journal` adds the owner/session-scoped canonical
runtime stream, monotonic sequences, snapshots, replay payloads, and retention
metadata. Session and audit records expire according to
`JARVIS_RUNTIME_SESSION_RETENTION_DAYS` (30 by default) and
`JARVIS_RUNTIME_AUDIT_RETENTION_DAYS` (90 by default); the newest 5,000
session-retained events per session are kept. Expired or trimmed history
advances a retention floor and clients must fetch a fresh snapshot rather than
attempting to reconstruct missing events. Durable records have no automatic
expiry. Revision 003 can be downgraded only while its runtime journal is empty;
revision 002 can be downgraded only while its command-event table is empty.
The baseline is intentionally irreversible. There is no automatic
schema-diff generation; add explicit reviewed migrations and back up before
changes.

The scheduled and pre-deployment backup job validates each PostgreSQL archive
by restoring it into an isolated, network-disabled PostgreSQL 16 container,
then runs database/table integrity queries. It also validates the uploads/data
archive. A failed restore aborts the backup and deployment; `pg_restore --list`
alone is not considered a verified restore.

The production GitHub Actions workflow publishes SHA-tagged images after tests
and scans. Automatic deployment is opt-in: set repository variable
`JARVIS_DEPLOY_ENABLED=true`, `JARVIS_DEPLOY_HOST`, `JARVIS_DEPLOY_USER`, and
`JARVIS_DEPLOY_PATH`; add secrets `JARVIS_DEPLOY_SSH_KEY` and
`JARVIS_DEPLOY_KNOWN_HOSTS` containing the pinned SSH host key. Configure the
GitHub `production` environment with required reviewers before enabling this
switch. The host must have a clean Git checkout with `origin` configured,
read-only repository access, Docker Compose, server-side secrets, and an
authenticated GHCR pull for the JARVIS package. The workflow fetches and checks
out the exact commit, then invokes `deploy.sh` with the SHA image tag and build
metadata. The job remains skipped until explicitly enabled and configured.

Only Caddy publishes host ports 80 and 443 (TCP and HTTP/3 UDP). PostgreSQL,
Redis, workers, Prometheus, and API ports are not published. The frontend uses
same-origin API and WebSocket requests; the edge proxies API, health, MCP,
Silverwing, and WebSocket routes to FastAPI.
The worker joins the private data network for PostgreSQL/Redis and a separate
unpublished egress network for outbound provider and connector calls; neither
network publishes an application port.

Production readiness behavior distinguishes process liveness
(`/health/live`), database-backed readiness (`/health/ready`), and runtime
provider/queue state included in readiness/system status. API readiness does
not imply a configured model provider or a functioning GitHub connection.

## Scope and known limits

The current Celery configuration schedules the Bio-Growth research poll and
routes production command submissions through the persistent `commands` queue.
It does not yet route all workflows or connector operations through Celery.
PostgreSQL is selected explicitly for the existing SQL key/value store; its
cached replace-all writes are not safe for horizontal replicas.
Deploy one API instance until that persistence layer is redesigned. Redis is
split into a cache and a durable-configured Celery broker, but Celery task
results are not the authoritative execution history.

The runtime journal is separate from the generic key/value store: each
canonical event and the corresponding snapshot/sequence update are committed
in one SQL transaction. API workers sharing the same PostgreSQL database read
the same journal, and SSE workers poll that shared store rather than relying
on process-local queues. The event bus and runtime service retain only
non-authoritative in-process buffers/caches. This does not make the generic
`jarvis_kv` collections safe for multiple API replicas; the supported
production topology remains one API instance until those call sites are
reworked.

The minimum independent Core deployment boundary is the FastAPI runtime plus
its persistent PostgreSQL database, authentication/signing secrets, and
server-side provider credentials, fronted by the existing public TLS gateway.
Browser endpoints consume the authenticated snapshot/resume/SSE API and do
not own conversations or runtime truth. The endpoint registry still uses
`jarvis_kv`, so endpoint writes inherit the single-API deployment limitation.
Health/readiness, existing logs/metrics/traces, and the existing gateway
provide health checks and observability; no new cloud service is required.
Provider access and secret rotation remain operator-managed server
configuration. Do not interpret shared event-journal support as proof that
every workflow, generic store, or task subsystem is safe for horizontal
scaling.

Provider keys are loaded from Docker secret files into the backend process
environment at startup because existing provider integrations read
environment variables. Connector-specific OAuth and GitHub authorization
remain configured through the existing server-side connection flows. This
deployment does not add full multi-tenant data isolation, device management,
MFA, a universal connector vault, autonomous repository writes, or external
alert delivery.

Account registration, verification, and password recovery require SMTP
configuration (`SMTP_HOST`, `SMTP_USER`, `SMTP_FROM`, and the mounted
`smtp_password` secret). The service refuses to create an account or issue a
recovery flow when delivery is unavailable; one-time tokens are never returned
by the API. Configure `SMTP_USE_SSL=true` for implicit TLS (typically port
465); otherwise STARTTLS is required (typically port 587).

No VPS, domain, DNS, provider credentials, or deployment credentials were
provided with this change. Do not report this service as live until a real
public endpoint and the two-device acceptance flow have been verified.

## Production smoke test

After DNS and TLS are active, run the checks from an external machine. Every
HTTP check must return success; readiness must report `ready`, a live worker
consuming the `commands` queue, and an online runtime. Set
`JARVIS_SMOKE_EMAIL` and `JARVIS_SMOKE_PASSWORD` in the operator shell; never
put credentials in a command committed to Git.

```sh
set -eu
BASE_URL="${PUBLIC_BASE_URL:?Derive public URLs with public_urls.py}"
curl --fail --silent --show-error "$BASE_URL/"
curl --fail --silent --show-error "$BASE_URL/health/live"
curl --fail --silent --show-error "$BASE_URL/health/ready"
```

Authenticate with `POST /api/v1/auth/login` using JSON fields `identifier` and
`password`, then use the returned access token to verify
`GET /api/v1/auth/me`, `GET /api/chat/sessions`, and a real
`POST /api/chat` request. Confirm the chat response has a provider/model,
completed status, and non-empty assistant text; then retrieve that session's
history after a page refresh or from a second client. A provider error,
empty response, missing provider identity, or missing persisted message is a
failed smoke test—not a successful fallback.

For streaming, repeat the authenticated chat request against
`POST /api/chat/stream` with `Accept: text/event-stream`; require a terminal
completion event and confirm it contains the same provider-backed result.
For WebSockets, obtain a short-lived origin-bound ticket from
`POST /api/v1/auth/ws-ticket` and connect to `${WS_BASE_URL}/health`
using the same browser origin; verify authenticated ping/pong, disconnect,
and reconnect. Confirm command status/events remain retrievable after an API
container restart. This procedure must be run against a real deployment; a
local test response does not establish public service availability.

## Product acceptance: provider-backed chat and worker recovery

Run this only against the deployed HTTPS origin with a real user account and a
configured provider. Stream an authenticated `/api/chat/stream` request and
require a `complete` event with non-empty content plus the real provider and
model identifiers. Reject canned/local-rule results and any failed/error
terminal event. Retrieve the conversation history and verify the same
assistant result is persisted.

While that conversation remains available, restart the API container and
confirm the authenticated history still returns the completed conversation.
Separately submit a supervised command that runs long enough to observe its
worker assignment, then stop the assigned worker process during execution.
Confirm the persisted lease expires, the recovery task queues the existing
execution checkpoint, a worker claims it, and the command reaches its actual
terminal state with ordered events. A duplicate active claim or a command
stuck in `EXECUTING` fails acceptance. Record the deployed image SHA, command
and execution IDs, event history, and provider/model in the operator's
release record; do not record credentials or prompt content.
