# Backup and restore

`deployment/production/backup/backup.sh` creates a PostgreSQL custom-format
dump, archives the persistent `jarvis_data` and `jarvis_uploads` volumes,
verifies both archives, records SHA-256 checksums, and applies the configured
local retention period.
The repository includes a daily systemd timer. On a host using the documented
`/opt/jarvis` checkout, install and enable it with:

```sh
sudo install -m 0644 deployment/production/backup/jarvis-backup.service /etc/systemd/system/
sudo install -m 0644 deployment/production/backup/jarvis-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-backup.timer
systemctl list-timers jarvis-backup.timer
sudo systemctl start jarvis-backup.service
sudo journalctl -u jarvis-backup.service --since today
```

The service runs at 02:00 UTC with up to 15 minutes of randomized delay,
retains 30 days under `/var/lib/jarvis-backups`, and runs after Docker starts.
Change `ExecStart` if the checkout is elsewhere. Copy verified backups to
encrypted, off-host/object storage; local disk alone is not disaster recovery.

Configuration metadata currently lives in the PostgreSQL-backed application
store. Secret files are intentionally not included in backups: back them up
through the host's secret-manager process. Compose volume snapshots and
database dumps should be tested on an isolated restore host at least quarterly.

## Restore PostgreSQL

1. Stop JARVIS API, worker, and scheduler; retain the existing data volume
   until the restored service has been checked.
2. Verify the selected backup checksum with `sha256sum -c` and inspect its
   archive using `pg_restore --list`.
3. Restore into a fresh database or a separately named volume. For an
   intentional in-place restore, require an explicit maintenance window and
   confirm the target before running:

   ```sh
   docker compose --env-file .env -f docker-compose.prod.yml \
     exec -T postgres sh -c \
     'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
     < database.dump
   ```

   The command above is destructive when pointed at a populated database;
   take and verify another backup first.
4. Restore `jarvis_data` and `jarvis_uploads` from the verified tar archive
   into empty replacement volumes, then start the API and workers and check
   database readiness, login, conversations, and artifacts before restoring
   public traffic.
5. Record the incident, restored backup timestamp, and any work lost since the
   backup.

PostgreSQL backup consistency is provided by `pg_dump`. The data/upload tar
archive is not a transactionally consistent point-in-time snapshot while files
are being modified; pause writes for a strict consistency point.
