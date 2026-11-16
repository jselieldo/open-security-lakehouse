#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
BEARER_TOKEN="$(./scripts/get-access-token.sh)"

run_rule() {
  curl --fail --silent --show-error \
    --request POST \
    --header "Authorization: Bearer ${BEARER_TOKEN}" \
    "${API_URL}/api/v1/detections/rules/high-severity-events/run"
}

first="$(run_rule)"
second="$(run_rule)"
alerts="$(curl --fail --silent --show-error \
  --header "Authorization: Bearer ${BEARER_TOKEN}" \
  "${API_URL}/api/v1/alerts?limit=100")"

FIRST="${first}" SECOND="${second}" ALERTS="${alerts}" python3 - <<'PY'
import json
import os

first = json.loads(os.environ["FIRST"])
second = json.loads(os.environ["SECOND"])
alerts = json.loads(os.environ["ALERTS"])
assert first["status"] == "completed", first
assert first["matched_count"] >= 1, first
assert second["status"] == "completed", second
assert second["alert_created"] is False, second
matching = [item for item in alerts if item["rule_id"] == "high-severity-events"]
assert matching, alerts
assert matching[0]["evidence_object_key"].startswith("artifacts/detection-evidence/"), matching[0]
print(
    f"Milestone 4 smoke test passed: {first['matched_count']} matches, "
    f"{len(matching)} persisted alert(s), deduplication confirmed."
)
PY
