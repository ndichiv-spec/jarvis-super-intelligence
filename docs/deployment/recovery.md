# Recovery and rollback

## Service recovery

Production services use `restart: unless-stopped`, dependency health checks,
and persistent Compose volumes. Caddy, the API, Celery worker, and scheduler
restart after process or host failure when Docker starts. API liveness is
separate from readiness; the runtime reports database, provider, and queue
status. Celery tasks use late acknowledgements and worker-lost rejection with
bounded retry policy for the scheduled research task.

## Image rollback

Before each rollout, configure distinct immutable `JARVIS_VERSION` and
`PREVIOUS_JARVIS_VERSION` tags and run `deployment/production/deploy.sh`.
It backs up PostgreSQL and uploads, runs the migration job, applies the new
images, and probes HTTPS readiness. If the probe fails it restores the prior
image tag and verifies health again. Preserve host logs and backup checksums
when rollback is unsuccessful.

Current database initialization is an additive `create_all`/seed operation,
not a revisioned Alembic migration sequence. The script therefore does not
perform schema downgrade or guarantee compatibility for arbitrary future
destructive migrations. Back up and review migrations before rollout.

## Operator actions

```sh
docker compose --env-file .env -f docker-compose.prod.yml ps
docker compose --env-file .env -f docker-compose.prod.yml logs --tail=200 jarvis worker beat caddy
eval "$(python3 ./public_urls.py --env-file .env --shell --production)"
curl --fail "${PUBLIC_BASE_URL%/}/health/ready"
```

If PostgreSQL or Redis has unrecoverable data loss, stop dependent services and
follow [backup-restore.md](backup-restore.md). Do not repeatedly retry
destructive actions or restore over the only available backup.
