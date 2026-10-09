# JARVIS Core Runtime Boundary

## Responsibility boundary

JARVIS Core is the server-side authority for identity, authorization, conversations,
memory, planning, model orchestration, capabilities, execution, tasks, runtime events,
and presentation decisions. A Core instance is considered operational from its liveness
and readiness probes and its persistent dependencies; it is not considered offline
because an endpoint disconnects.

An endpoint is an authenticated presentation and I/O client. It owns local input,
device-specific rendering, presentation capabilities, and its own connection state.
Endpoint registration, credentials, capability negotiation, and session attachment are
server-authorized. Endpoint credentials are hashed in persistent storage; a client
cannot select its owner. The endpoint is not an authority for Core state.

## Runtime event durability and recovery

The canonical `RuntimeEvent` contract is stored in the existing SQL persistence layer,
in `jarvis_runtime_streams` and `jarvis_runtime_events`. The stream row owns the
monotonic per-owner/session sequence and snapshot; event rows are deduplicated by event
ID and ordered by sequence. PostgreSQL row locks serialize writers. SQLite uses an
immediate write transaction for development and local multi-process tests.

SSE reads the SQL journal, so workers sharing the configured database see the same
truth; the event fabric's in-process subscriber list is dispatch plumbing, not the
journal. Ephemeral events advance the retention floor but are not persisted. If a
client's cursor predates retained history, replay explicitly reports that a resnapshot
is required rather than fabricating missing events. Session and audit-retention
durations are configurable with `JARVIS_RUNTIME_SESSION_RETENTION_DAYS` and
`JARVIS_RUNTIME_AUDIT_RETENTION_DAYS`.

Endpoint reconnect uses its bearer credential to authenticate and attach only to an
owner-authorized session. It obtains a snapshot and sequence cursor, resumes from the
client's acknowledged sequence, and returns an explicit resynchronization response
when the cursor has expired. User-cookie authorization remains available for owner
clients. The event route checks session ownership before snapshot, replay, and SSE.

## Identifier and audit continuity

The HTTP request middleware's request ID is propagated through chat verification,
provider/router metadata, Silverwing's `X-Request-ID`, canonical runtime event
correlation, presentation, and audit records. Provider implementations that create
their own internal span/trace IDs may still have a distinct observability identifier;
that identifier is not substituted for the canonical request ID.

Endpoint registration/credential rotation, endpoint authentication, session
attachment, and disconnection are recorded with the existing SQL-backed audit event
service. Secrets and endpoint bearer tokens are excluded from audit metadata and
runtime payloads.

## Existing deployment boundary

`deployment/production/docker-compose.prod.yml` already defines the minimum intended
independent deployment: API Core, PostgreSQL, Redis cache/queue, Celery worker/beat,
frontend, and Caddy TLS/SSE proxy. PostgreSQL is the durable source of runtime events,
conversations, endpoint records, and audit records. Redis is used for cache and job
transport, not runtime event truth. The migration service owns schema setup. Secrets
are supplied via Docker secrets backed by operator-managed files. Provider credentials
are server-side secret files. Caddy terminates TLS and proxies streaming responses.
Health checks distinguish process liveness from database-backed readiness.

No additional cloud service is required by this boundary. To deploy independently of
a developer workstation, operators must provide a reachable PostgreSQL instance (or
the existing PostgreSQL service), the existing Redis services, immutable backend and
frontend images, protected secret files, public URL/CORS settings, outbound provider
access, persistent database/volume backups, and TLS/DNS for the endpoint gateway.
Additional API replicas may share PostgreSQL; correctness of SSE replay does not depend
on process-local pub/sub.

## Assumption classification

| Surface | Classification | Treatment |
| --- | --- | --- |
| `127.0.0.1` in container health probes | Configuration / container-local | Intentional probe against the same container; not a public Core address. |
| Mobile `localhost` fallback | Development-only | Retained only under the development build; production requires configured API origin. |
| Browser tab and frontend lifecycle | Endpoint | Browser is a client; its lifecycle does not determine Core readiness. |
| `SILVERWING_ENDPOINT` fallback | Removed runtime dependency | Core no longer defaults to `127.0.0.1:8010`; configure a reachable Silverwing URL only when using that separate provider runtime. |
| Outer workspace `_env.py` loopback defaults | Development configuration | Kept for existing developer workflows; the production image does not inherit the workstation workspace file. |
| Fixed `F:\AI` paths in cloud/brain fabric modules | Development-only / legacy tooling | Used by workstation training, artifact, and diagnostic helpers; not by runtime event, identity, conversation, or endpoint authority. |
| `OLLAMA_BASE_URL` and local-rule model references | Optional provider configuration / legacy | Local inference is opt-in; no local model is required for Core health or event persistence. |
| `jarvis_data` uploads, artifacts, and connector audit files | Persistent-volume configuration | Production Compose mounts the data directory; SQL remains authoritative for Core identity, conversations, endpoints, audit rows, and runtime events. |
| Desktop/dashboard/speech localhost URLs | Legacy / development-only | These standalone surfaces are not production Core endpoints; deployed clients must use configured public Core URLs. |
| Web API localhost fallback and example `.env` values | Development configuration | Development server fallback only; production image routes through the configured same-origin proxy. |
| Event-fabric subscriber registry | Process-local optimization/dispatch | Not authoritative; SQL journal is the source of replay and snapshots. |
| Chat-session JSON store cache | Process-local cache | Session reads reload from SQL and writes update individual persistent records. |
| Observability counters/traces | Process-local telemetry | Best-effort metrics are not application state or runtime journal. |
| OTLP tracing exporter | Optional configuration | Export is disabled unless `OTEL_EXPORTER_OTLP_ENDPOINT` is explicitly configured; Core does not require a workstation collector. |
| Endpoint records and credentials | Persistent runtime state | Stored in the existing database-backed key/value layer and updated atomically. |
| SQLite | Development/test configuration | Useful for restart and multi-process correctness tests; production deployment specifies PostgreSQL. |
| Local model/provider settings | Configuration | Provider availability is a Core dependency only when the selected operation requires it; endpoint availability is not. |

## Limits and production verification

The Compose deployment currently starts one API container by default; replica count is
an operator scaling decision. Production PostgreSQL multi-replica behavior must be
verified against the deployed database and proxy before claiming production
independence. SQLite multiprocess tests do not substitute for that verification.

### Executed shared-PostgreSQL multiprocess verification

Two independent Uvicorn API processes used PostgreSQL 17 against a uniquely named,
temporary schema in the configured local PostgreSQL service. A valid owner bearer
token authenticated endpoint registration on worker A; the endpoint authenticated,
heartbeated, attached to its owned session on worker B, and fetched a snapshot.
A separate backend process emitted a runtime event, which worker B replayed from
PostgreSQL. Worker A was stopped and restarted; the same endpoint credential
reconnected, reattached, restored a snapshot, and replayed the pre-restart event.
A subsequent event arrived over live SSE. Finally, disconnecting the endpoint left
its state `disconnected` while Core readiness remained `ready` before and after.
The isolated schema and temporary logs were removed after the run.

The owner account/session were seeded in the isolated verification schema and
authenticated with a server-signed bearer token; this verified the real HTTP
authorization path, not the interactive login UI. This proves shared PostgreSQL
behavior across independent processes, but it is not a deployment of the production
Compose stack or a remote replica test. Docker Desktop was installed but its Linux
engine could not start in this environment; WSL reported mount/drive-translation
failures. Production Compose/TLS/provider-secret integration therefore remains
unverified.

This boundary does not claim that every legacy in-process task executor or every
filesystem-backed feature has been migrated to a distributed worker. Existing Celery
and SQL task/job infrastructure should be used for work that must survive Core process
loss; each capability must be checked for durable dispatch and recovery before being
advertised as independently resumable.

## Internet Workspace prerequisites

Start the Internet Workspace slice only after a shared-database deployment proves:

1. Core readiness remains healthy with all endpoints disconnected.
2. Runtime events, sequences, and snapshots survive API restart.
3. Two API workers can publish, replay, and stream the same owner's events.
4. Endpoint authentication, ownership checks, reconnect replay, and retention-triggered
   resynchronization work across workers.
5. Conversation writes and audit records remain owner-scoped across workers.
6. Provider secrets remain server-side and endpoint input is treated as untrusted.

The Internet Workspace can then build on the existing capability-resolution and
browser/service infrastructure; it should not be implemented as a new dashboard.
