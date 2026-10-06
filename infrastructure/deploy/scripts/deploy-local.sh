#!/bin/bash
set -euo pipefail

# JARVIS Local Deployment
# Usage: ./deploy-local.sh [--build] [--prod] [--profile <name>]

MODE="local"
BUILD=false
PROFILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build) BUILD=true; shift ;;
    --prod)  MODE="prod"; shift ;;
    --profile) PROFILE="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

COMPOSE_FILE="deployment/docker-compose.yml"
[ "$MODE" = "prod" ] && COMPOSE_FILE="deployment/docker-compose.prod.yml"
ENV_FILE=".env"
[ ! -f "$ENV_FILE" ] && ENV_FILE=".env.example"

COMPOSE_CMD="docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE"
[ -n "$PROFILE" ] && COMPOSE_CMD="$COMPOSE_CMD --profile $PROFILE"

echo "=== JARVIS Local Deployment ==="
echo "Mode:   $MODE"
echo "Compose: $COMPOSE_FILE"

# Pull latest images
echo "Pulling images..."
$COMPOSE_CMD pull

# Build if requested
if [ "$BUILD" = true ]; then
  echo "Building images..."
  $COMPOSE_CMD build
fi

# Start services
echo "Starting services..."
$COMPOSE_CMD up -d

# Wait for health
echo "Waiting for services to become healthy..."
sleep 10

# Show status
echo ""
echo "=== Deployment Status ==="
$COMPOSE_CMD ps

echo ""
echo "=== Endpoints ==="
echo "API:      http://localhost:8000/api/v1"
echo "Docs:     http://localhost:8000/docs"
echo "Frontend: http://localhost:3000"
echo "Grafana:  http://localhost:3001"
echo "Prometheus: http://localhost:9090"
echo ""
echo "To view logs:  $COMPOSE_CMD logs -f"
echo "To stop:       $COMPOSE_CMD down"
