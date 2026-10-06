#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.prod.yml"
ENV_FILE="$DEPLOY_DIR/.env"
BACKUP_DIR="${BACKUP_DIR:-$DEPLOY_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing production environment file: $ENV_FILE" >&2
  exit 1
fi
if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  echo "RETENTION_DAYS must be a non-negative integer." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
database_backup="$BACKUP_DIR/jarvis-postgres-$stamp.dump"
artifact_backup="$BACKUP_DIR/jarvis-data-uploads-$stamp.tar.gz"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
  exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$database_backup"
pg_restore --list "$database_backup" >/dev/null
bash "$SCRIPT_DIR/verify-restore.sh" "$database_backup"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
  exec -T jarvis tar -C /app -czf - jarvis_data jarvis_uploads > "$artifact_backup"
tar -tzf "$artifact_backup" >/dev/null

(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$database_backup")" "$(basename "$artifact_backup")" \
    > "jarvis-$stamp.sha256"
)
find "$BACKUP_DIR" -maxdepth 1 -type f \
  \( -name 'jarvis-postgres-*.dump' -o -name 'jarvis-data-uploads-*.tar.gz' -o -name 'jarvis-uploads-*.tar.gz' -o -name 'jarvis-*.sha256' \) \
  -mtime "+$RETENTION_DAYS" -delete

echo "Verified database and upload backups written to $BACKUP_DIR"
