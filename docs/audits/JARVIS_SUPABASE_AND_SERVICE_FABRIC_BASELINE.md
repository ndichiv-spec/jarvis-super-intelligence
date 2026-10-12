# JARVIS Supabase and service fabric baseline

**Scope:** source and deployment configuration in this checkout on
`recovery/integration-20261012`. This report describes locally verified code
and configuration; it does not claim access to a Supabase project, production
environment, or external provider account.

## Executive decision

JARVIS already has a server-side persistence, identity, runtime-event, worker,
provider, and artifact architecture. Supabase is not configured or integrated
as a product service in this checkout. Do not add a second user/session
authority or replace the existing runtime. A Supabase-hosted PostgreSQL
endpoint is technically compatible with the existing SQLAlchemy path when
provisioned as a TLS-enabled server-side `DATABASE_URL`; no endpoint or
credentials are present to test it. The SQLAlchemy pool improvements in this
change apply to PostgreSQL connections, but do not establish a live Supabase
integration.

| Concern | Existing authority and code path | Status and boundary |
|---|---|---|
| Persistence | `jarvis_backend/db.py::database_url`, `get_engine`, `jarvis_backend/core.py::Store`, `jarvis_backend/persistence.py` | SQLite is used for local/test operation; server-side `DATABASE_URL` and `DATABASE_URL_FILE` support PostgreSQL. The legacy collection contract persists through `jarvis_kv`; normalized repositories use the same engine. No Supabase project was available. |
| Schema changes | `jarvis_backend/schema_migrations.py`, `scripts/migrate_persistence.py` | Ordered revisions through `003_durable_runtime_event_journal`; deployment runs the migration command before backend startup and requires premigrated schema for the API. This is the migration authority; `metadata.create_all()` is not a complete upgrade strategy. PostgreSQL execution was unavailable (`psql` and Docker not installed). |
| Identity and sessions | `jarvis_backend/routers/auth.py`, `jarvis_backend/core.py` | JARVIS JWT/cookie/session authority remains canonical. Login, registration, refresh, verification, API-key, and session flows are in the JARVIS backend. Production owner-only checks now compare the stored principal email to configured `JARVIS_ADMIN_EMAIL`; Supabase Auth is deferred. |
| Authorization | `jarvis_backend/core.py::get_current_user`, role/permission helpers, `jarvis_backend/routers/*` | Authorization remains enforced by the application. A server-side PostgreSQL connection with privileged credentials bypasses Supabase RLS; backend authorization remains mandatory even if RLS is later enabled. |
| Runtime and durable work | `jarvis_backend/runtime_events.py`, `jarvis_backend/db.py`, `jarvis_backend/event_fabric.py`, `jarvis_backend/celery_app.py`, `jarvis_backend/execution_fabric.py` | A durable event journal and Celery-backed work path already exist. Realtime and Edge Functions would duplicate or displace clear existing boundaries without a demonstrated requirement. Multi-worker production behavior is not verified in this environment. |
| Models and providers | `jarvis_backend/gateway.py`, `jarvis_backend/chat_service.py`, `providers/`, `infrastructure/model_registry.py`, `infrastructure/provider_registry.py`, `silverwing-backend/` | Existing gateway, provider adapters, registries, and Silverwing integration are reused. Deterministic tests exercise routing; actual provider availability/inference is not verified without credentials. |
| Files and artifacts | `infrastructure/artifact_registry.py`, backend upload/artifact code, Compose private volumes | Private local/volume-backed artifact paths exist. No Supabase Storage integration or policy was found. The storage lifecycle and cross-device behavior need production-backed verification. |
| Operations | `deployment/production/docker-compose.prod.yml`, `deployment/production/Caddyfile`, `deployment/production/public_urls.py` | Compose defines Postgres, Redis cache/queue, backend, worker, and Caddy. Only the gateway publishes public web ports in the file. External DNS, firewall, TLS, host access, and restart recovery were not tested. |

## PostgreSQL and Supabase fit

`jarvis_backend/db.py::database_url()` resolves `DATABASE_URL` or a
`DATABASE_URL_FILE` secret before local SQLite. PostgreSQL engine construction
now enables connection pre-ping, bounded pool size/overflow, pool timeout,
connection recycling, and a bounded DBAPI connect timeout. Settings are
`JARVIS_DB_POOL_SIZE`, `JARVIS_DB_MAX_OVERFLOW`,
`JARVIS_DB_POOL_TIMEOUT_SECONDS`, `JARVIS_DB_POOL_RECYCLE_SECONDS`, and
`JARVIS_DB_CONNECT_TIMEOUT_SECONDS`; they are passed to backend, worker, and
beat in `deployment/production/docker-compose.prod.yml`. The production env
examples document these settings. SQLite engine behavior remains unchanged.

For a future managed PostgreSQL deployment, put a provider-supported TLS URL
(for example, a URL with `sslmode=require`) in the server-only database secret.
Do not put it in frontend configuration. Connection-string compatibility,
provider pooler mode, TLS certificate verification, failover, schema
migrations, backup/restore, and quota limits still require a real staging
endpoint and tested procedures. Existing Compose assumes its own Postgres
service and migration dependency; a Supabase deployment mode must explicitly
avoid starting/depending on an unused local database rather than merely
changing the URL.

The JARVIS database includes the generic `jarvis_kv` store, command event
records, and owner/session-scoped runtime stream and event records. The code
also contains normalized repositories. These share the SQLAlchemy engine but
are not a demonstrated unified relational conversation/memory schema. No
database redesign or competing key/value layer is warranted by selecting
Supabase.

## Capability decisions

| Supabase capability | Decision | Reason / acceptance required before implementation |
|---|---|---|
| PostgreSQL | Compatible, not live-integrated | Use the existing engine and migration path. Require TLS, server-side secrets, measured pooler settings, migration tests, backup/restore evidence, and startup/health behavior on a provisioned non-production project. |
| Auth | Defer | JARVIS auth remains the single identity authority. Federation would require an explicit migration, claim validation, session revocation, verified-email, MFA, recovery, and owner binding design; a second independent authority is unsafe. |
| RLS | Conditional/deferred | A privileged direct server connection bypasses policies. If clients are ever granted direct data access, define trusted claim propagation and default-deny policies, then test client and server paths. RLS never replaces backend authorization. |
| Storage | Defer | Existing private artifact/upload storage must first be compared with deployment requirements. Integrate only with private buckets, server-side ownership checks, short-lived signed URLs, restrictions, scanning/lifecycle policy, and cross-identity tests. |
| Realtime | Do not duplicate by default | Durable JARVIS events already stream through the canonical runtime event service over SSE/WebSocket. Realtime is only justified for a precisely bounded complementary channel with authorization and reconnect/deduplication tests. |
| Edge Functions | Defer | Central orchestration and long-running work belong in the existing backend/worker. A small function would need a separate concrete use case and auth, validation, timeout, secret, observability, and regression requirements. |

## Evidence and unresolved gates

- The focused owner/auth, security-regression, endpoint-gateway, and PostgreSQL
  pool selection passed **82 tests** after the production identity changes.
- The complete offline backend selection passed **2,572 tests**, with 14
  skipped and 13 integration tests deselected, in 506.65 seconds on a unique
  disposable SQLite path outside the checkout. It does not establish live
  integration behavior.
- `python -m compileall -q jarvis_backend tests`, `git diff --check`, and the
  changed-file Ruff debt gate passed at the time of this report.
- The checkout imports `research_engine` from the sibling workspace
  `F:\AI\research_engine`; that source is not tracked here. Clean-clone
  reproducibility remains blocked until the dependency is versioned or
  provisioned explicitly.
- No Supabase URL/project, service credential, external database, DNS/domain,
  or deployment host was available or used. No live integration or deployment
  is claimed.
