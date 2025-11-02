#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR="$1"
IMAGE_TAG="$2"

if [[ -z "${AWS_ACCOUNT_ID:-}" ]]; then
  echo "AWS_ACCOUNT_ID is not set" >&2
  exit 1
fi

if [[ -z "${AWS_REGION:-}" ]]; then
  echo "AWS_REGION is not set" >&2
  exit 1
fi

REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Logging into ${REGISTRY}"
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${REGISTRY}"

docker build "${SERVICE_DIR}" -t "${IMAGE_TAG}"
docker tag "${IMAGE_TAG}" "${REGISTRY}/${IMAGE_TAG}"
docker push "${REGISTRY}/${IMAGE_TAG}"
