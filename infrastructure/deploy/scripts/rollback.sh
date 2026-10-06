#!/bin/bash
set -euo pipefail

# JARVIS Rollback
# Usage: ./rollback.sh <local|cloud> [service]

MODE="${1:?"Usage: $0 <local|cloud> [service]"}"

echo "=== JARVIS Rollback ($MODE) ==="

case "$MODE" in
  local)
    COMPOSE_FILE="deployment/docker-compose.yml"
    [ -f "deployment/docker-compose.prod.yml" ] && COMPOSE_FILE="deployment/docker-compose.prod.yml"

    if [ $# -ge 2 ]; then
      echo "Stopping service: $2"
      docker-compose -f "$COMPOSE_FILE" stop "$2"
      docker-compose -f "$COMPOSE_FILE" rm -f "$2"
    else
      echo "Stopping all services..."
      docker-compose -f "$COMPOSE_FILE" down
    fi
    echo "Rollback complete."
    ;;

  cloud)
    CLOUD_PROVIDER="${CLOUD_PROVIDER:-aws}"
    echo "Rolling back $CLOUD_PROVIDER deployment..."

    case "$CLOUD_PROVIDER" in
      aws)
        [ -z "${AWS_PREVIOUS_TASK_DEF:-}" ] && { echo "ERROR: AWS_PREVIOUS_TASK_DEF not set"; exit 1; }
        aws ecs update-service \
          --cluster "${AWS_ECS_CLUSTER:-jarvis-cluster}" \
          --service "${AWS_ECS_SERVICE:-jarvis-service}" \
          --task-definition "$AWS_PREVIOUS_TASK_DEF"
        echo "ECS rollback triggered to previous task definition"
        ;;

      gcp)
        [ -z "${GCP_PREVIOUS_REVISION:-}" ] && { echo "ERROR: GCP_PREVIOUS_REVISION not set"; exit 1; }
        gcloud run services update-traffic \
          "${GCP_CLOUD_RUN_SERVICE:-jarvis}" \
          --to-revisions="${GCP_PREVIOUS_REVISION}=100" \
          --region="${GCP_REGION:-us-central1}"
        echo "Cloud Run rollback to revision $GCP_PREVIOUS_REVISION"
        ;;

      azure)
        [ -z "${AZURE_PREVIOUS_DEPLOYMENT:-}" ] && { echo "ERROR: AZURE_PREVIOUS_DEPLOYMENT not set"; exit 1; }
        az webapp deployment source config-zip \
          --resource-group "${AZURE_RESOURCE_GROUP:-jarvis-rg}" \
          --name "${AZURE_WEBAPP_NAME:-jarvis-app}" \
          --src "$AZURE_PREVIOUS_DEPLOYMENT"
        echo "Azure rollback to previous deployment"
        ;;

      *) echo "Unsupported cloud provider: $CLOUD_PROVIDER"; exit 1 ;;
    esac
    ;;

  *)
    echo "Usage: $0 <local|cloud> [service]"
    exit 1
    ;;
esac
