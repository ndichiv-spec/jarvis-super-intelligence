#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.prod.yml"
ENV_FILE="$SCRIPT_DIR/.env"
HEALTH_URL=""

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing production environment file: $ENV_FILE" >&2
  exit 1
fi

url_exports="$(python3 "$SCRIPT_DIR/public_urls.py" --env-file "$ENV_FILE" --shell --production)" || exit $?
eval "$url_exports"

read_env() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

set_env() {
  local key="$1"
  local value="$2"
  python3 -c '
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
key, value = sys.argv[2], sys.argv[3]
text = path.read_text(encoding="utf-8")
pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
updated, count = pattern.subn(f"{key}={value}", text)
if count != 1:
    raise SystemExit(f"Expected exactly one {key} setting in {path}, found {count}.")
path.write_text(updated, encoding="utf-8")
' "$ENV_FILE" "$key" "$value"
}

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

verify_runtime() {
  local payload
  payload="$(curl --fail --silent --show-error "$HEALTH_URL")" || return 1
  printf '%s' "$payload" | python3 -c '
import json
import sys

status = json.load(sys.stdin)
queue = status.get("queue", {})
raise SystemExit(
    0 if status.get("service_readiness") == "ready"
    and status.get("runtime_health") == "online"
    and queue.get("worker_probe") == "ok"
    and queue.get("command_queue_probe") == "ok"
    else 1
)
'
}

candidate="${1:-$(read_env JARVIS_VERSION)}"
git_sha="${2:-$(read_env GIT_SHA)}"
build_time="${3:-$(read_env BUILD_TIME)}"
deployment_id="${4:-$(read_env DEPLOYMENT_ID)}"
previous="$(read_env PREVIOUS_JARVIS_VERSION)"
domain="$(read_env JARVIS_DOMAIN)"
previous_git_sha="$(read_env GIT_SHA)"
previous_build_time="$(read_env BUILD_TIME)"
previous_deployment_id="$(read_env DEPLOYMENT_ID)"
deployment_started=false

if [[ -z "$candidate" || -z "$previous" || "$candidate" == "$previous" ]]; then
  echo "Set distinct JARVIS_VERSION and PREVIOUS_JARVIS_VERSION image tags first." >&2
  exit 1
fi
if [[ ! "$candidate" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ || ! "$previous" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ || "$candidate" == "latest" || "$previous" == "latest" ]]; then
  echo "Production image tags must be immutable safe tags; latest is not supported." >&2
  exit 1
fi
if [[ ! "$git_sha" =~ ^[0-9a-f]{40}$ || ! "$build_time" =~ ^[0-9TZ:.-]+$ || ! "$deployment_id" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "GIT_SHA, BUILD_TIME, or DEPLOYMENT_ID is missing or malformed." >&2
  exit 1
fi
if [[ -z "$domain" ]]; then
  echo "Set JARVIS_DOMAIN in $ENV_FILE." >&2
  exit 1
fi
HEALTH_URL="${PUBLIC_BASE_URL%/}/health/ready"

rollback_on_error() {
  local exit_code=$?
  trap - ERR
  set_env JARVIS_VERSION "$previous"
  set_env GIT_SHA "$previous_git_sha"
  set_env BUILD_TIME "$previous_build_time"
  set_env DEPLOYMENT_ID "$previous_deployment_id"
  if [[ "$deployment_started" == "true" ]]; then
    compose pull jarvis worker beat frontend || true
    compose up -d --no-deps jarvis worker beat frontend || true
  fi
  exit "$exit_code"
}
trap rollback_on_error ERR

"$SCRIPT_DIR/backup/backup.sh"
set_env JARVIS_VERSION "$candidate"
set_env GIT_SHA "$git_sha"
set_env BUILD_TIME "$build_time"
set_env DEPLOYMENT_ID "$deployment_id"
compose pull jarvis worker beat frontend
image_prefix="$(read_env JARVIS_IMAGE_PREFIX)"
image_prefix="${image_prefix:-ghcr.io/ndichiv-spec/jarvis-super-intelligence}"
frontend_image="${image_prefix%/}/frontend:$candidate"
image_base_path="$(docker image inspect --format '{{ index .Config.Labels "org.jarvis.public-base-path" }}' "$frontend_image")"
if [[ "$image_base_path" != "$JARVIS_FRONTEND_BASE_PATH" ]]; then
  echo "Frontend image base path does not match JARVIS_BASE_PATH; refusing deployment." >&2
  exit 1
fi
compose run --rm migrate
deployment_started=true
compose up -d --no-deps jarvis worker beat frontend

healthy=false
for attempt in $(seq 1 30); do
  if verify_runtime; then
    healthy=true
    break
  fi
  sleep 10
done

if [[ "$healthy" == "true" ]]; then
  set_env PREVIOUS_JARVIS_VERSION "$candidate"
  compose up -d caddy
  trap - ERR
  echo "JARVIS rollout $candidate is healthy at https://$domain."
  exit 0
fi

echo "Candidate failed health verification; rolling back to $previous." >&2
set_env JARVIS_VERSION "$previous"
set_env GIT_SHA "$previous_git_sha"
set_env BUILD_TIME "$previous_build_time"
set_env DEPLOYMENT_ID "$previous_deployment_id"
compose pull jarvis worker beat frontend
compose up -d --no-deps jarvis worker beat frontend

for attempt in $(seq 1 30); do
  if verify_runtime; then
    trap - ERR
    echo "Rollback to $previous restored service health." >&2
    exit 1
  fi
  sleep 10
done

echo "Rollback health verification failed. Preserve logs and recover from the latest backup." >&2
exit 2
