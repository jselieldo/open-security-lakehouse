#!/usr/bin/env bash
set -euo pipefail

: "${OSL_API_PORT:=8000}"
: "${COLLECTOR_API_TOKEN:?Set COLLECTOR_API_TOKEN}"
API_URL="http://127.0.0.1:${OSL_API_PORT}"
TOKEN="$(./scripts/get-access-token.sh)"
BODY="$(python3 - <<'PY'
import json
import socket
import time
print(json.dumps({
    "Type": "container", "Action": "start",
    "Actor": {"ID": "osl-milestone11-test", "Attributes": {"name": "osl-test"}},
    "timeNano": time.time_ns(), "osl_hostname": socket.gethostname(), "osl_test": True,
}))
PY
)"
RESPONSE="$(curl --fail --silent --show-error \
  -H "Authorization: Bearer ${COLLECTOR_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data "${BODY}" "${API_URL}/api/v1/ingestion/docker")"
printf '%s' "${RESPONSE}" | python3 -c '
import json, sys
r=json.load(sys.stdin)
assert r["source"] == "test-docker" and r["accepted_count"] == 1, r
print("Docker fixture accepted:", r["batch_id"])
'
SOURCES="$(curl --fail --silent --show-error -H "Authorization: Bearer ${TOKEN}" \
  "${API_URL}/api/v1/sources")"
printf '%s' "${SOURCES}" | python3 -c '
import json, sys
sources=json.load(sys.stdin)
assert any(s["source"] == "test-docker" and s["status"] == "active" for s in sources), sources
print("Source catalog: test-docker active")
'
EVENTS="$(curl --fail --silent --show-error -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"source":"test-docker","application":"docker","event_type":"container.start","limit":10}' \
  "${API_URL}/api/v1/investigations/search")"
printf '%s' "${EVENTS}" | python3 -c '
import json, sys
r=json.load(sys.stdin)
assert r["total_count"] >= 1, r
print("Docker investigation: matching events", r["total_count"])
'
