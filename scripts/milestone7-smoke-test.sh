#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
SYSLOG_HOST="${SYSLOG_HOST:-$(hostname -I | awk '{print $1}')}"
SYSLOG_PORT="${SYSLOG_PORT:-5514}"
marker="osl-m7-$RANDOM-$(date +%s)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

SYSLOG_HOST="$SYSLOG_HOST" SYSLOG_PORT="$SYSLOG_PORT" MARKER="$marker" TIMESTAMP="$timestamp" \
python3 - <<'PY'
import os
import socket

message = (
    f'<34>1 {os.environ["TIMESTAMP"]} homelab osl-smoke 1234 ID47 '
    f'- {os.environ["MARKER"]}\n'
).encode()
with socket.create_connection((os.environ["SYSLOG_HOST"], int(os.environ["SYSLOG_PORT"])), 5) as sock:
    sock.sendall(message)
PY

token="$(./scripts/get-access-token.sh)"
for _ in $(seq 1 20); do
  response="$(curl --fail --silent --show-error \
    --header "Authorization: Bearer $token" \
    --header "Content-Type: application/json" \
    --data '{"source":"test-syslog","limit":1000}' \
    "$API_URL/api/v1/investigations/search")"
  if RESPONSE="$response" MARKER="$marker" python3 -c \
    'import json,os,sys; data=json.loads(os.environ["RESPONSE"]); sys.exit(0 if any(os.environ["MARKER"] in e["raw_event_json"] for e in data["events"]) else 1)'
  then
    RESPONSE="$response" python3 -c \
      'import json,os; d=json.loads(os.environ["RESPONSE"]); print("Milestone 7 smoke test passed: {} isolated test event(s) queryable.".format(d["returned_count"]))'
    exit 0
  fi
  sleep 1
done

echo "Milestone 7 smoke test failed: syslog marker was not queryable" >&2
exit 1
