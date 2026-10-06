# Production operations

## Routine deployment

Use a SHA-tagged GHCR image only. Review CI, back up, update the candidate and
previous release tags in the protected deployment `.env`, then run
`deployment/production/deploy.sh`. Do not use `latest`, mount a source
checkout, or run development servers in production.
The backup step restores the PostgreSQL archive into an isolated temporary
PostgreSQL instance before reporting success; restore failure blocks rollout.

## Health and logs

- Process liveness: `${PUBLIC_BASE_URL}/health/live`
- Database/runtime readiness: `${PUBLIC_BASE_URL}/health/ready`
- Build metadata: `${PUBLIC_BASE_URL}/api/version`
- Container logs: `docker compose --env-file .env -f docker-compose.prod.yml logs`
- Optional internal Prometheus: see `deployment/production/monitoring/README.md`

The monitoring profile currently scrapes API request/error metrics and
evaluates local Prometheus rules. There is no configured alert receiver, and
the application does not yet publish complete host, provider, connector,
queue-depth, or storage telemetry. Operators must monitor disk, backups,
certificate state, and notifications through host-level or external tooling.

## Host restart and capacity

Keep Docker enabled at boot, retain named volume backups, and verify the
production services after a planned reboot. The current SQL collection store
uses per-process caches and replace-all writes; run a single API replica only.
The Celery worker consumes both `research` and `commands` queues. Production
command submissions are persisted before enqueue, use owner-scoped request
idempotency, and execute through this worker rather than an API-process task.
Late acknowledgements and worker-loss rejection allow broker redelivery; the
execution fabric reloads its persisted task checkpoint instead of creating a
second command. Capability side effects still need connector/provider
idempotency for exactly-once behavior. This queue does not route every
automation workflow or connector operation.

Review `docker compose ps` and `/health/ready` before and after upgrades.
Investigate repeated failures and expired authorizations rather than endlessly
retrying side effects. Do not claim service continuity until the host, domain,
provider, identity, and multi-device flows have been exercised against the
actual deployment.
