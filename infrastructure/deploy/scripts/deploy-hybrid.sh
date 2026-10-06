#!/bin/bash
set -euo pipefail

# JARVIS Hybrid Deployment
# Local core services + Cloud AI providers
# Usage: ./deploy-hybrid.sh [--build] [--ai-provider openai|gemini]

BUILD=false
AI_PROVIDER="${AI_PROVIDER:-gemini}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)      BUILD=true; shift ;;
    --ai-provider) AI_PROVIDER="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

COMPOSE_FILE="deployment/docker-compose.yml"
ENV_FILE=".env"
[ ! -f "$ENV_FILE" ] && ENV_FILE=".env.example"

COMPOSE_CMD="docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE"

echo "=== JARVIS Hybrid Deployment ==="
echo "AI Provider: $AI_PROVIDER"
echo "Compose:     $COMPOSE_FILE"

# Validate AI provider keys
case "$AI_PROVIDER" in
  openai)
    [ -z "${OPENAI_API_KEY:-}" ] && { echo "ERROR: OPENAI_API_KEY not set"; exit 1; }
    echo "OpenAI API key found ✓"
    ;;
  gemini)
    [ -z "${GOOGLE_GEMINI_API_KEY:-}" ] && { echo "ERROR: GOOGLE_GEMINI_API_KEY not set"; exit 1; }
    echo "Gemini API key found ✓"
    ;;
  ollama)
    echo "Using local Ollama (no cloud key needed)"
    ;;
  *)
    echo "Unsupported AI provider: $AI_PROVIDER"
    echo "Supported: openai, gemini, ollama"
    exit 1
    ;;
esac

# Deploy local core services
echo "Deploying local core services (db, redis, backend)..."
$COMPOSE_CMD pull db redis backend
if [ "$BUILD" = true ]; then
  $COMPOSE_CMD build db redis backend
fi
$COMPOSE_CMD up -d db redis backend

# Wait for core services
echo "Waiting for core services..."
sleep 15

# Show status
echo ""
echo "=== Hybrid Deployment Status ==="
$COMPOSE_CMD ps db redis backend

echo ""
echo "=== Local Endpoints ==="
echo "API:      http://localhost:8000/api/v1"
echo "Docs:     http://localhost:8000/docs"
echo ""
echo "Cloud AI provider: $AI_PROVIDER"
echo "To view logs:  $COMPOSE_CMD logs -f"
echo "To stop:       $COMPOSE_CMD down"
