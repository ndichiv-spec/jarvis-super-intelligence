# Production Deployment Runbook

## Current status

This is a preparation checklist, not a record of a completed deployment.
There is no verified staging hostname, production host, Docker engine, domain,
or provider credential in the current environment. No deployment or public
endpoint was contacted. A launch remains **NO-GO** until the checklist has
been executed and independently evidenced.

The production stack is in `deployment/production/docker-compose.prod.yml`.
It uses Docker Compose, PostgreSQL, Redis, a single Uvicorn API worker,
Next.js standalone output, and Caddy-managed HTTPS. Use immutable release
identifiers through `JARVIS_VERSION`, `GIT_SHA`, `BUILD_TIME`, and
`DEPLOYMENT_ID`.

## 1. Provision host and network

- Choose an owner-approved Linux host with supported Docker Engine and Docker
  Compose v2; restrict SSH and inbound network access to the operational
  policy.
- Create a DNS A record (and AAAA only if IPv6 is correctly routed) for the
  public hostname. Permit inbound TCP 80/443; permit UDP 443 only if HTTP/3 is
  intended. Do not expose PostgreSQL or Redis ports publicly.
- Create a unique staging domain first. Verify DNS from an independent
  network, then let Caddy obtain the certificate using the configured
  `ACME_EMAIL`.
- Confirm the system clock, filesystem capacity, memory/CPU, and a protected
  location for persistent Docker volumes and encrypted backups.

## 2. Provision configuration and secrets

1. Copy `deployment/production/.env.example` to a deployment-only `.env`.
   Never commit the copy or place raw credentials in version control.
2. Set `DOMAIN`, `NEXT_PUBLIC_APP_URL=https://<domain>`,
   `ACME_EMAIL`, `JARVIS_ADMIN_EMAIL`, a release version, and deployment
   identifiers. Keep public API/WS URLs empty only when same-origin routing is
   intended and verified.
3. Provision these files through the host's approved secret manager; ensure
   they are readable by Docker but not by untrusted host users:
   `POSTGRES_PASSWORD_FILE_SOURCE`,
   `REDIS_PASSWORD_FILE_SOURCE`,
   `JARVIS_SECRET_KEY_FILE_SOURCE`,
   `JARVIS_ADMIN_PASSWORD_FILE_SOURCE`,
   `DATABASE_URL_FILE_SOURCE`, and `REDIS_URL_FILE_SOURCE`.
   The signing key must be at least 32 characters and the admin password at
   least 16 characters. Database/Redis URLs must resolve to the Compose
   services and use the provisioned credentials.
4. Keep image generation disabled unless the owner approves provider data
   egress and billing. For an approved provider, set
   `JARVIS_IMAGE_PROVIDER` to exactly one supported provider and
   `JARVIS_IMAGE_PROVIDER_KEY_FILE_SOURCE` to its server-side key file. Do
   not put the key in a `NEXT_PUBLIC_*` variable.
5. Public web research is disabled by default. To enable it, set
   `JARVIS_BROWSER_SEARCH_ENABLED=1` and provision only owner-approved model
   provider keys using `JARVIS_RESEARCH_OPENAI_KEY_FILE_SOURCE` and/or
   `JARVIS_RESEARCH_GOOGLE_KEY_FILE_SOURCE`. The API reads the mounted
   Docker-secret files through `SecretManager`; raw keys are not copied into
   ordinary environment values. A configured key does not establish provider
   health or impose a billing ceiling. Set provider-side spend limits and
   request limits before enabling live research.
6. Confirm the `.env` and secret files are excluded from backups accessible to
   untrusted users, while encrypted copies are included in the approved
   recovery plan.

## 3. Pre-deployment checks

Run from the platform checkout on the host, with the actual deployment
environment loaded securely:

```sh
docker compose --env-file deployment/production/.env \
  -f deployment/production/docker-compose.prod.yml config --quiet
```

Review the rendered configuration locally for correct domain, volume paths,
secret sources, image provider selection, and absence of credential values in
ordinary environment fields. Do not publish rendered secret-bearing output.
Build images only after code review and tests:

```sh
docker compose --env-file deployment/production/.env \
  -f deployment/production/docker-compose.prod.yml build
```

The API production startup is intended to reject missing/weak signing keys,
admin passwords, PostgreSQL configuration, and CORS origins. Validate all
secret-file paths and permissions before starting containers.

## 4. Establish backup and migration recovery before first real data

There is currently no checked-in backup/restore automation and no verified
recovery evidence. Before accepting user data:

- Define encrypted, access-controlled, off-host PostgreSQL backups with
  retention, integrity checks, and monitored failure reporting.
- Back up the PostgreSQL database plus required JARVIS runtime and media
  volumes. Document key custody and recovery access separately.
- Perform a restoration into an isolated, empty recovery environment; verify
  schema, user/session ownership, command history, media retrieval, and
  application readiness. Record operator, timestamp, image version, and
  evidence.
- Establish a database migration review and rollback/forward-fix plan. The
  Compose `migrate` service runs `scripts/migrate_persistence.py --seed`.
  Do not use `--reset` in production; it clears persisted collections.

Do not run a destructive migration or restore over a live database without
explicit owner approval and a verified backup.

## 5. Deploy staging first

After backup/recovery procedures exist, stage an immutable release. The
Compose stack starts PostgreSQL and Redis, runs the migration service, starts
the API and frontend, and then starts Caddy after health checks:

```sh
docker compose --env-file deployment/production/.env \
  -f deployment/production/docker-compose.prod.yml up -d
docker compose --env-file deployment/production/.env \
  -f deployment/production/docker-compose.prod.yml ps
```

Verify `/health/live` and `/health/ready` on the API through the intended
routes; readiness must be truthful about database/provider state. Verify
frontend availability, Caddy certificate issuance, redirect/HTTPS behavior,
security headers, and auth cookies (`Secure`, `HttpOnly`, `SameSite=Lax`).
Inspect logs through the approved access path; do not copy tokens, prompts,
provider responses, or secrets into tickets.

From a separate client/network, sign in with a dedicated account, start a
conversation, refresh the page, and verify owner-only conversation and media
access. Restart the API worker and repeat reads. Verify unauthorized users
cannot read the conversation, execution events, or media. Record exact
release ID, timestamps, redacted health evidence, and test outcome.

Only after this staging gate, explicit owner approval, and provider egress/bill
approval should the single-request image smoke be run. Follow
`PRODUCTION_VERIFICATION.md`; never run it from a deployment hook or ordinary
test suite.

## 6. Rollback and incident recovery

- Keep the previous immutable API/frontend images available and record the
  exact `JARVIS_VERSION` and configuration used for each deployment.
- For an application-only rollback, restore the prior reviewed image tags and
  redeploy the API/frontend after confirming the database schema remains
  compatible. Do not assume code rollback reverses schema changes.
- If data is corrupted, stop writes, preserve logs and a forensic snapshot,
  then restore only under the owner-approved database recovery procedure.
- Verify readiness, authentication, owner isolation, conversation history,
  media retrieval, and runtime event correlation after recovery.
- Record impact, image versions, backup identifiers, operator approvals, and
  validation evidence. No such rollback or restoration has been exercised in
  this checkout.

## 7. Production go-live evidence

Do not promote beyond staging until the launch audit records PASS for:
container startup and health, PostgreSQL/Redis persistence, HTTPS and secure
cookies, secret handling, backup restoration, authenticated conversation
persistence, worker restart recovery, cross-owner denial, approved real
provider execution and stored media retrieval, operational log redaction, and
independent-client verification. Update
`docs/LAUNCH_READINESS_AUDIT.md` and `docs/PRODUCTION_VERIFICATION.md` with
the command or external evidence for each gate.
