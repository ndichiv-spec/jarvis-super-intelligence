# JARVIS deployment and portless access assessment

## 2026-10-13 verification update

Static verification passed for 12 tests in `tests/deployment/test_validation.py`.
The production Compose file and Caddy configuration remain deployment
templates; this session had no Docker executable/daemon, host, domain, DNS,
certificate, production secret store, or credentials. Therefore the private
port topology was not exercised at runtime, and no deployment, public URL,
HTTPS, restart recovery, device login, or rollback is claimed. See the
standalone `JARVIS_DEPLOYMENT_VERIFICATION.md` for the per-criterion status
and exact infrastructure requirements.

## Intended and implemented topology

The checked-in `deployment/production/docker-compose.prod.yml` describes
JARVIS backend, a private PostgreSQL service, private Redis cache and queue,
Celery worker and beat, and Caddy as the public HTTPS gateway. Application
health checks use container loopback. The backend and data services do not
publish host ports in the Compose file; Caddy is the intended public entry
point on standard HTTP/HTTPS ports. `deployment/production/Caddyfile` routes
traffic to internal service names. `deployment/production/public_urls.py`
derives HTTPS/API/WebSocket addresses from the deployment's canonical public
URL and validates configuration.

The deployment artifacts therefore support the intended portless access
shape, but do not prove a real deployment. No owner-controlled domain,
deployment host, DNS/firewall configuration, certificate, external secret
store, or cloud credential was available. No DNS, TLS, public reachability,
device reconnect, restart recovery, or rollback check was performed. Do not
represent this system as deployed or internet-accessible yet.

## Configuration and persistence

Production Compose requires an immutable `JARVIS_VERSION`, public/API/WS
addresses derived from configuration, an owner email, server-side secrets,
database and Redis URLs, and CORS origins. Backend and workers read secret
files, not frontend bundles. `jarvis_backend/db.py` supports a server-side
`DATABASE_URL_FILE`; this change adds bounded PostgreSQL connection pooling
and timeout settings to backend, worker and beat. Production API startup
requires a premigrated schema; the migration service runs
`scripts/migrate_persistence.py --seed` and the API waits for migration
completion.

Compose currently provisions its own Postgres and makes the migration/API
depend on it. Pointing its database secret at Supabase without a deliberate
deployment mode would leave a redundant database and incorrect startup
dependency. A managed-Postgres mode must be explicit and must preserve the
ordered `jarvis_backend/schema_migrations.py` authority. The managed endpoint
must use provider-supported TLS, compatible pooler settings, bounded
connections, backup/restore procedures, and a tested recovery path. Neither
the PostgreSQL service nor containers were run here because Docker and
`psql` are unavailable.

## Owner-only production configuration

Production authentication remains JARVIS-native. The configured owner account
is selected with `JARVIS_ADMIN_EMAIL`; startup refuses the development
placeholder in production. This change restricts production login and
authenticated API/API-key principals to that stored owner identity and
disables production registration. It does not create a public SaaS account
flow. The remaining deployment gate is to provision actual values through a
trusted secrets/configuration system and verify the owner login, device
enrollment, revocation and cross-device session behavior in staging.

## Required pre-deployment checks

1. Provision an owner-controlled HTTPS domain/URL and DNS; issue and test a
   valid TLS certificate and secure WebSocket/SSE routing.
2. Apply a firewall allowing public gateway traffic only; verify backend,
   database, Redis, worker and administrative ports are not public. Restrict
   SSH/administration to an owner-authorized path.
3. Provide production-only secrets through the deployment platform; rotate
   initial credentials, verify permissions and redaction, and keep secrets
   out of images, logs and browser configuration.
4. Choose either the Compose-managed database or a deliberately supported
   managed PostgreSQL mode. Apply migrations to disposable staging data;
   test connection failures, bounded pool behavior, backup and restore.
5. Start backend and worker, verify health and queue task completion, restart
   the host/services, and prove durable session/task recovery without an
   owner PC terminal or local process.
6. Verify only the owner can authenticate from a second authorized device;
   revoke a device/session and confirm it cannot reconnect or perform actions.
7. Test rollback to the preceding immutable image and compatible schema
   without destructive migration or data loss.
8. Verify monitor/alert delivery, resource/quota limits, logs and error
   responses do not disclose credentials or private conversation content.

Until those checks run on actual infrastructure, this is a deployment
configuration assessment, not production release approval.
