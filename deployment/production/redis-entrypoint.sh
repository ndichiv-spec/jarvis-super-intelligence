#!/bin/sh
set -eu

memory_limit="${1:?Redis memory limit is required}"
eviction_policy="${2:?Redis eviction policy is required}"
secret_path="${3:?Redis secret path is required}"
password="$(cat "$secret_path")"
test -n "$password"
exec redis-server --appendonly yes --appendfsync everysec \
  --maxmemory "$memory_limit" --maxmemory-policy "$eviction_policy" \
  --requirepass "$password"
