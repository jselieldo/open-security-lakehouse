#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
: "${OSL_API_TOKEN:?Export OSL_API_TOKEN or load it from .env}"

batch_id="smoke-$(date -u +%Y%m%d%H%M%S)-$$"
payload="$(python3 ./scripts/generate-synthetic-events.py \
  --count 5 --invalid 1 --batch-id "${batch_id}")"

first="$(curl --fail --silent --show-error \
  --header "Authorization: Bearer ${OSL_API_TOKEN}" \
  --header "Content-Type: application/json" \
  --data "${payload}" \
  "${API_URL}/api/v1/ingestion/batches")"

second="$(curl --fail --silent --show-error \
  --header "Authorization: Bearer ${OSL_API_TOKEN}" \
  --header "Content-Type: application/json" \
  --data "${payload}" \
  "${API_URL}/api/v1/ingestion/batches")"

FIRST="${first}" SECOND="${second}" python3 - <<'PY'
import json
import os

first = json.loads(os.environ["FIRST"])
second = json.loads(os.environ["SECOND"])
assert first["status"] == "completed", first
assert first["received_count"] == 5, first
assert first["accepted_count"] == 4, first
assert first["rejected_count"] == 1, first
assert first["raw_object_key"], first
assert first["normalized_object_key"], first
assert first["quarantine_object_key"], first
assert second["idempotent_replay"] is True, second
print(f"Milestone 2 smoke test passed for {first['batch_id']}.")
PY
