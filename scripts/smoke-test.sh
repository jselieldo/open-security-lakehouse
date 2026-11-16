#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
BEARER_TOKEN="$(./scripts/get-access-token.sh)"

echo "Checking liveness..."
curl --fail --silent --show-error "${API_URL}/health/live" >/dev/null

echo "Checking PostgreSQL and object storage readiness..."
curl --fail --silent --show-error "${API_URL}/health/ready" >/dev/null

echo "Checking bearer authentication..."
unauthorized_code="$(curl --silent --output /dev/null --write-out '%{http_code}' "${API_URL}/api/v1/system/info")"
test "${unauthorized_code}" = "401"
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${BEARER_TOKEN}" \
  "${API_URL}/api/v1/system/info" >/dev/null

echo "Smoke test passed."

