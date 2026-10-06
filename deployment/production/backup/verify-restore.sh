#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -s "$1" ]]; then
  echo "Usage: $0 POSTGRES_CUSTOM_FORMAT_DUMP" >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1 || ! command -v openssl >/dev/null 2>&1; then
  echo "Restore verification requires Docker and OpenSSL." >&2
  exit 1
fi

dump_file="$(realpath "$1")"
container_name="jarvis-restore-check-$(date -u +%Y%m%dT%H%M%SZ)-$$"
database_name="jarvis_restore_check"
temporary_password="$(openssl rand -hex 32)"

cleanup() {
  docker rm --force "$container_name" >/dev/null 2>&1 || true
  unset temporary_password
}
trap cleanup EXIT

docker run --detach --rm \
  --name "$container_name" \
  --network none \
  --env "POSTGRES_PASSWORD=$temporary_password" \
  --env "POSTGRES_DB=$database_name" \
  postgres:16.4-alpine >/dev/null

ready=false
for attempt in $(seq 1 60); do
  if docker exec "$container_name" pg_isready -U postgres -d "$database_name" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != "true" ]]; then
  echo "Isolated PostgreSQL restore target did not become ready." >&2
  docker logs "$container_name" >&2
  exit 1
fi

docker exec -i "$container_name" \
  pg_restore --exit-on-error --single-transaction --no-owner --no-privileges \
  --username=postgres --dbname="$database_name" < "$dump_file"

table_count="$(
  docker exec "$container_name" \
    psql --set=ON_ERROR_STOP=1 --username=postgres --dbname="$database_name" \
    --tuples-only --no-align \
    --command="SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
)"
if [[ ! "$table_count" =~ ^[0-9]+$ || "$table_count" -lt 1 ]]; then
  echo "Restored database integrity check found no user tables." >&2
  exit 1
fi

docker exec "$container_name" \
  psql --set=ON_ERROR_STOP=1 --username=postgres --dbname="$database_name" \
  --tuples-only --no-align --command="SELECT 1" >/dev/null

echo "Restore verified in isolated PostgreSQL: $table_count user table(s)."
