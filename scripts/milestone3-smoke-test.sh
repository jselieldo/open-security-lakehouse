#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
: "${OSL_API_TOKEN:?Export OSL_API_TOKEN or load it from .env}"

response="$(curl --fail --silent --show-error \
  --header "Authorization: Bearer ${OSL_API_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{"source":"synthetic-linux","min_severity":1,"limit":10}' \
  "${API_URL}/api/v1/investigations/search")"

RESPONSE="${response}" python3 - <<'PY'
import json
import os

response = json.loads(os.environ["RESPONSE"])
assert response["query_engine"] == "duckdb", response
assert response["scanned_objects"] >= 1, response
assert response["returned_count"] >= 1, response
assert all(event["source"] == "synthetic-linux" for event in response["events"]), response
print(
    f"Milestone 3 smoke test passed: {response['returned_count']} events from "
    f"{response['scanned_objects']} Parquet object(s) in {response['duration_ms']} ms."
)
PY
