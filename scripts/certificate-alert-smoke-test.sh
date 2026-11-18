#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository"
set -a
. ./.env
set +a
api_url="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
marker="OSL mTLS certificate check failed:"

if ./scripts/check-mtls-certificates.py \
  --root /tmp/osl-mtls-monitor-e2e-missing \
  --warning-days 30 --emit-syslog --syslog-tag osl-smoke >/tmp/osl-certificate-alert-test.json
then
  echo "isolated certificate check unexpectedly succeeded" >&2
  exit 1
fi

token="$(./scripts/get-access-token.sh)"
for _ in $(seq 1 30); do
  result="$(curl --fail --silent --show-error \
    -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
    --data "{\"source\":\"test-syslog\",\"message_contains\":\"$marker\",\"min_severity\":4,\"limit\":100}" \
    "$api_url/api/v1/investigations/search")"
  count="$(RESULT="$result" python3 -c 'import json,os; print(json.loads(os.environ["RESULT"])["total_count"])')"
  test "$count" -ge 1 && break
  sleep 2
done
test "${count:-0}" -ge 1 || { echo "test event was not searchable" >&2; exit 1; }

run="$(curl --fail --silent --show-error -X POST \
  -H "Authorization: Bearer $token" \
  "$api_url/api/v1/detections/rules/test-certificate-monitor-alert/run")"
RUN="$run" python3 -c 'import json,os; assert json.loads(os.environ["RUN"])["alert_created"]'
alerts="$(curl --fail --silent --show-error \
  -H "Authorization: Bearer $token" "$api_url/api/v1/alerts?limit=100")"
alert_id="$(ALERTS="$alerts" python3 -c '
import json, os
items = [a for a in json.loads(os.environ["ALERTS"]) if a["rule_id"] == "test-certificate-monitor-alert"]
print(items[0]["alert_id"] if items else "")
')"
test -n "$alert_id" || { echo "test detection did not return an alert" >&2; exit 1; }

evidence="$(curl --fail --silent --show-error \
  -H "Authorization: Bearer $token" "$api_url/api/v1/alerts/$alert_id/evidence")"
EVIDENCE="$evidence" python3 -c '
import json, os
d = json.loads(os.environ["EVIDENCE"])
assert d["rule"]["id"] == "test-certificate-monitor-alert"
assert d["events"] and all(e["source"] == "test-syslog" for e in d["events"])
'

curl --fail --silent --show-error -X POST \
  -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
  --data '{"body":"Automated isolated certificate-monitor alert-path validation."}' \
  "$api_url/api/v1/alerts/$alert_id/comments" >/dev/null
curl --fail --silent --show-error -X PATCH \
  -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
  --data '{"status":"false_positive"}' "$api_url/api/v1/alerts/$alert_id" >/dev/null
detail="$(curl --fail --silent --show-error \
  -H "Authorization: Bearer $token" "$api_url/api/v1/alerts/$alert_id")"
DETAIL="$detail" python3 -c '
import json, os
d = json.loads(os.environ["DETAIL"])
assert d["alert"]["status"] == "false_positive"
assert any(c["body"].startswith("Automated isolated") for c in d["comments"])
assert any(h["action"] == "status_changed" for h in d["history"])
'

echo "Certificate alert path passed and test alert was closed: $alert_id"
