#!/bin/bash
set -euo pipefail

# JARVIS Cloud Deployment
# Usage: ./deploy-cloud.sh <aws|gcp|azure> [--build] [--tag <version>]

CLOUD_PROVIDER="${1:?"Usage: $0 <aws|gcp|azure> [--build] [--tag <version>]"}"
BUILD=false
TAG="latest"

shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build) BUILD=true; shift ;;
    --tag)   TAG="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

export CLOUD_PROVIDER
export IMAGE_TAG="$TAG"

echo "=== JARVIS Cloud Deployment ==="
echo "Provider: $CLOUD_PROVIDER"
echo "Tag:      $TAG"

case "$CLOUD_PROVIDER" in
  aws)
    AWS_ECS_CLUSTER="${AWS_ECS_CLUSTER:-jarvis-cluster}"
    AWS_ECS_SERVICE="${AWS_ECS_SERVICE:-jarvis-service}"
    AWS_REGION="${AWS_REGION:-us-east-1}"

    if [ "$BUILD" = true ]; then
      ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
      aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
      docker build -f deployment/Dockerfile.backend -t "jarvis:$TAG" .
      docker tag "jarvis:$TAG" "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/jarvis:$TAG"
      docker push "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/jarvis:$TAG"
    fi

    aws ecs update-service \
      --cluster "$AWS_ECS_CLUSTER" \
      --service "$AWS_ECS_SERVICE" \
      --force-new-deployment \
      --region "$AWS_REGION"
    echo "ECS service update triggered for $AWS_ECS_SERVICE"
    ;;

  gcp)
    GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project)}"
    GCP_CLOUD_RUN_SERVICE="${GCP_CLOUD_RUN_SERVICE:-jarvis}"
    GCP_REGION="${GCP_REGION:-us-central1}"

    gcloud run deploy "$GCP_CLOUD_RUN_SERVICE" \
      --source . \
      --region "$GCP_REGION" \
      --project "$GCP_PROJECT" \
      --allow-unauthenticated
    echo "Cloud Run service deployed: $GCP_CLOUD_RUN_SERVICE"
    ;;

  azure)
    AZURE_WEBAPP_NAME="${AZURE_WEBAPP_NAME:-jarvis-app}"
    AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-jarvis-rg}"

    if [ "$BUILD" = true ]; then
      az acr login --name "${AZURE_REGISTRY:-jarvisregistry}"
      docker build -f deployment/Dockerfile.backend -t "jarvis:$TAG" .
      docker tag "jarvis:$TAG" "${AZURE_REGISTRY:-jarvisregistry}.azurecr.io/jarvis:$TAG"
      docker push "${AZURE_REGISTRY:-jarvisregistry}.azurecr.io/jarvis:$TAG"
    fi

    az webapp deploy \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --name "$AZURE_WEBAPP_NAME" \
      --src-path "."
    echo "Azure WebApp deployed: $AZURE_WEBAPP_NAME"
    ;;

  *)
    echo "Unsupported provider: $CLOUD_PROVIDER"
    echo "Supported: aws, gcp, azure"
    exit 1
    ;;
esac

echo ""
echo "=== Cloud deployment initiated ==="
echo "Monitor: $CLOUD_PROVIDER console for rollout status"
