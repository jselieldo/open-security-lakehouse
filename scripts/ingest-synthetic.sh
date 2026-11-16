#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
BEARER_TOKEN="$(./scripts/get-access-token.sh)"

payload="$(python3 ./scripts/generate-synthetic-events.py "$@")"
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${BEARER_TOKEN}" \
  --header "Content-Type: application/json" \
  --data "${payload}" \
  "${API_URL}/api/v1/ingestion/batches"
echo
