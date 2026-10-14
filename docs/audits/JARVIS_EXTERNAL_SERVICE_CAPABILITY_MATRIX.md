# JARVIS external service capability matrix

## 2026-10-13 implementation update

| Service/capability | Implemented | Locally verified | Integration verified | Production verified | Blocked / limit |
|---|---|---|---|---|---|
| Web search | Existing `BrowserTool` and `HttpBrowserEngine` now sit behind the canonical chat capability orchestrator; natural-language research/lookup/compare requests route into that path. | Yes: permission denial, invalid result, total provider outage, truthful provenance, and partial-model fallback tests. | Yes: opt-in `tests/integration/test_world_workspace_live.py` performed real DuckDuckGo search through `ChatService`, persisted sources/tool calls and runtime events. | No. | Automatic path does not fetch result pages; only search provider payload and safe HTTP(S) URLs are checked. No internet-wide API/site discovery. |
| AI providers / cooperation | Provider gateway and provider adapter/catalog modules are present in this integration worktree; backend startup initializes the fabric and retains the existing routing path. | Startup and truthful degraded/unconfigured health path observed. | No model endpoint call. | No. | No provider credentials were supplied. Live health, round-trip inference, multi-model cooperation, data-sharing policy, and quality/cost comparison remain unverified. |
| JARVIS database | Existing SQLite/PostgreSQL SQLAlchemy paths remain canonical for identity, commands, runtime events, and records. | SQLite persistence/event/recovery tests pass. | No external PostgreSQL service. | No. | Needs a provisioned PostgreSQL staging service and restart/backup/restore evidence. |
| Supabase | PostgreSQL URL compatibility only; no Supabase-specific integration was added. | No Supabase project. | No. | No. | Auth, Storage, Realtime, Edge Functions, and RLS are not configured. |
| Email/OAuth and other third-party services | Existing connector framework remains. | Auth/connector ownership tests only. | No provider account call. | No. | Client secrets and account credentials absent. |
| Portless HTTPS | Existing Caddy + production Compose topology remains. | Static deployment validation: **12 passed**. | No. | No. | Docker, domain, host, TLS, DNS/firewall, and release credentials absent. |

This update supersedes the older `research_engine` clean-checkout blocker below:
13 package source modules are now in the integration worktree and local
import/path tests pass. It does not claim a fresh remote clone or clean
production container build. See
`JARVIS_CLEAN_CHECKOUT_REPRODUCIBILITY.md` and
`JARVIS_WORLD_WORKSPACE_IMPLEMENTATION.md`.

The provider fabric is also present in this worktree; older statements below
that it is absent are historical. It initializes locally but reports
unavailable/degraded without configured provider credentials. No model call is
claimed.

**Status vocabulary:** *implemented* means a tracked execution path exists;
*configured* means deployment wiring exists; *verified* means the specified
behavior was actually exercised. A connector or SDK alone is not integration
evidence. No secret values or account data are recorded here.

| Service/provider | Existing code path and capability | Status and necessity | Benefit / security and operational requirements | Credentials, verification, failure behavior, decision |
|---|---|---|---|---|
| SQL database (SQLite/PostgreSQL) | `jarvis_backend/db.py`, `jarvis_backend/persistence.py`, `jarvis_backend/schema_migrations.py`; state, identity, command and runtime-event persistence | Implemented; PostgreSQL configured in production Compose, SQLite tested; no managed Supabase endpoint verified. Necessary. | Durable state and cross-restart memory. Server-only URL, TLS for managed endpoints, pool sizing, migrations, backup/restore, ownership checks. | `DATABASE_URL`/file secret; SQLite migration and persistence tests, PostgreSQL integration unavailable. Fail startup/migration clearly; keep existing SQLAlchemy authority. |
| Supabase PostgreSQL | Existing SQLAlchemy URL path; no Supabase-specific SDK, project, or policies found | Compatible but not integrated. Optional deployment provider. | May provide managed database operations; same JARVIS schema and authorization boundaries required. | No endpoint/credential available, so no live test. Require TLS, pooler-aware connection testing, migration/restore evidence. Reuse DB path, do not add a competing persistence service. |
| Supabase Auth | None; identity authority is `jarvis_backend/routers/auth.py` and JARVIS JWT/session code | Deferred; redundant absent an approved federation/migration. | Avoid split-brain accounts and sessions. Any adoption requires server verification, verified owner claims, revocation, MFA/recovery, abuse limits, and owner-only authorization. | No project credentials. JARVIS auth tests cover current local contract; keep JARVIS authoritative. |
| Supabase Storage | Existing private volume/local artifact handling, `infrastructure/artifact_registry.py` | Local path exists; managed storage unconfigured and optional. | Cross-device durable objects if needed; private bucket, owner-scoped paths, server authorization, file limits, scanning, short-lived signed URLs, lifecycle cleanup. | No bucket/account available; access-policy tests absent. Defer until production storage requirement and object lifecycle are specified. |
| Supabase Realtime | `jarvis_backend/event_fabric.py`, `runtime_events.py`, SSE/WebSocket runtime routes | Existing canonical event path implemented; Realtime redundant/deferred. | Live progress is already represented by durable owner/session event streams. Adding a second feed risks duplicate/out-of-order events. | No Supabase channel configured. Existing event tests; defer unless a bounded complementary channel is justified and tested for authorization/reconnect/deduplication. |
| Supabase Edge Functions | No deployed function path found | Deferred; not required for long-running orchestration. | JARVIS Brain, routing, and persistent task execution stay in backend/Celery. | No function deployment. Require a concrete isolated task, auth, validation, secret controls, timeout and observability before adoption. |
| AI/model providers | `jarvis_backend/gateway.py`, `chat_service.py`, the checkout-local `providers/` package, `infrastructure/model_registry.py`, `silverwing-backend/` | Provider fabric initializes at startup; readiness reports unavailable/degraded when no provider is configured. | Provider secrets server-only, task-level data minimization, explicit privacy policy, cost/latency limits, timeout and truthful fallback. | No model was invoked; no credentials were used. Local checks cover initialization and unavailable reporting, not live inference or multi-model cooperation. Do not claim cooperation is operational until authorized provider calls are verified. |
| JARVIS Brain / Silverwing | `jarvis_backend/chat_service.py`, gateway, mounted Silverwing backend and runtime adapters | Existing integration paths; runtime environment not fully verified. | Reuse existing capability and inference layers; enforce same principal, audit, limits, and durable results. | Locally covered by focused provider/capability tests in prior recovery; actual production runtime and model calls unavailable. Keep canonical adapters. |
| Search and browsing | `jarvis_backend/chat_service.py`, `browser_engine.py`, `capabilities/tools/browser_tool.py`, existing capability/runtime routes | Natural-language read-only search delegates to registered `browser.search`; intent/permission/failure tests pass. | One opt-in real DuckDuckGo search traversed canonical `ChatService` and persisted source/tool/runtime records. | No. | Live search queries are sent to DuckDuckGo. Search results have validated URL shape/provenance, but page contents are not fetched in this path. Treat snippets as untrusted; full SSRF/prompt-injection protections and source-claim verification are not established by this test. |
| Tools / code execution | `jarvis_backend/execution_fabric.py`, existing capability/plugin registries, sandbox, checkout-local `research_engine/` | 13 `research_engine` source modules are included in the integration worktree; import/project-root tests pass. Command runtime tests cover owner authorization, idempotency, leases and recovery. | Browser search only; no arbitrary code execution or third-party write capability was performed. | No. | Docker/sandbox and multi-worker recovery were not started here. The provider delegation dependency remains missing separately; never treat discovery as permission. |
| Email | Auth email service in backend plus configured SMTP environment/secrets in production Compose | Account-verification path exists; SMTP operation not verified. Necessary for production registration/recovery only if enabled. | Minimize scopes; never log tokens; deliverability, abuse throttling, recovery controls. | SMTP secrets/environment are provisioned externally; none available here. Tests validate local contracts, not delivery. Preserve explicit not-configured failure. |
| OAuth-connected accounts | JARVIS OAuth and endpoint credential pathways; `jarvis_backend/endpoint_gateway.py`, auth/identity routers | Existing connector framework; individual external provider readiness varies and was not comprehensively live-tested. | Minimal scopes, state/ownership validation, encrypted server-only refresh tokens, revocation and masking. | Provider client secrets absent. Use focused OAuth/ownership tests; do not declare a provider connected based on configuration alone. |
| Maps/location | No verified production-ready map/location provider path established by this audit | Optional/deferred. | Only with explicit device consent, least collection, retention controls, server-side API credentials and anti-tracking ownership enforcement. | No provider credentials or live tests. Do not collect owner location by default. |
| Voice, vision, media | Existing voice, browser/media and provider capability modules | Capability paths exist; capability-specific live providers unverified. Optional by task and available provider. | Capability-aware routing, consent, safe media handling and truthful unsupported/unavailable states. | Provider credentials not available. Local tests do not prove live speech/vision/media. Reuse existing adapters. |
| Redis/cache/queue | Compose `redis-cache`, `redis-queue`; `jarvis_backend/celery_app.py`; worker and beat | Deployment configured, not run locally (Docker unavailable). Necessary for production worker path. | Private networking, authenticated URLs, no public ports, durable queue semantics, task idempotency, retries/cancellation, resource limits. | Secrets supplied at deployment. No live queue/restart tests in this environment. Verify delivery/recovery before production. |
| Secrets | Compose secret files (`*_FILE`), environment examples and provider boundaries | Existing server-side secret-file pattern configured; external secret-manager integration unverified. Necessary. | Least privilege, rotation/revocation, log redaction, encrypted backups, no frontend secrets. | No secret values were inspected or recorded. Require deployment secret inventory and rotation drill; do not introduce another secret service without need. |
| Observability | `jarvis_backend/observability.py`, `infrastructure/observability/`, structured logging and health routes | Local paths exist; external metrics/tracing and production alerting not verified. Necessary for production operations. | Correlation IDs, safe metrics, access/error alerts, no indiscriminate prompt/token/file logging. | No observability account credentials. Local tests cover selected health/error behavior; configure and exercise production alerts before deployment. |
| Hosting and HTTPS gateway | `deployment/production/docker-compose.prod.yml`, `Caddyfile`, `public_urls.py` | Deployment artifacts exist; public URL, DNS and host are unconfigured/unverified. Necessary to deploy. | TLS, standard HTTPS/WSS, private application/data ports, firewall/SSH policy, persistent volumes, restart and rollback. | No domain/host/DNS credentials. Static validation only; no public reachability claim. |

## Dependency-alert status

The GitHub alert inventory contained **573 open Dependabot alerts** at
inspection: 33 critical, 293 high, 196 medium and 51 low. Initial critical/high
summaries showed, among others, `torch` in
`videlisndichi-jarvis-brain-qwen3-4b-sft-train/requirements.txt`, and
`pypdf`, `GitPython`, `urllib3` and `aiohttp` in
`_tier1/canonical_repo/platform/requirements.txt`. These package paths span
multiple manifests and may include non-production, archived or separately
built components; do not infer canonical image reachability from an alert
alone. The alert set remains untriaged as a whole. No indiscriminate upgrades
were made. Each critical/high alert needs an owner, affected manifest/build
path, fixed version compatibility, and test/release verification.

## Prioritization

1. **Required operational gates:** package `research_engine`, obtain a clean
   checkout test, provision a real staging host/database/secrets, exercise the
   existing backend/Postgres/worker/Caddy stack, and validate backup/restore.
2. **Use existing capabilities:** JARVIS identity, SQLAlchemy/migrations,
   provider gateway, connector framework, Celery and durable event journal.
   Re-test each provider only when its authorized credentials are provisioned.
3. **Conditional integrations:** managed PostgreSQL (including Supabase),
   object storage, email delivery and specific OAuth providers, based on
   operational requirements and successful security tests.
4. **Deferred/redundant:** parallel Supabase Auth, duplicate Realtime event
   journal, Edge Functions for central orchestration, and unrequested
   maps/communication providers.
