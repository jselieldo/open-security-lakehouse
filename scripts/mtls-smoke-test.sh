#!/usr/bin/env bash
set -euo pipefail

host="${SYSLOG_HOST:-127.0.0.1}"
port="${SYSLOG_MTLS_PORT:-6514}"
cert_dir="${OSL_MTLS_CLIENT_DIR:-data/mtls/clients/homelab}"
marker="mtls-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

for file in ca.crt client.crt client.key; do test -f "$cert_dir/$file"; done
message="<84>1 $timestamp homelab osl-smoke - MTLS01 - $marker"
printf '%s\n' "$message" | timeout 10 openssl s_client -quiet \
  -connect "$host:$port" -servername osl-syslog -verify_return_error \
  -CAfile "$cert_dir/ca.crt" -cert "$cert_dir/client.crt" -key "$cert_dir/client.key" \
  >/dev/null 2>&1 || test "$?" -eq 124

BEARER_TOKEN="$(./scripts/get-access-token.sh)"
for _ in $(seq 1 15); do
  result="$(curl --fail --silent --show-error \
    -H "Authorization: Bearer $BEARER_TOKEN" -H 'Content-Type: application/json' \
    --data "{\"source\":\"test-syslog\",\"message_contains\":\"$marker\",\"limit\":10}" \
    http://127.0.0.1:8000/api/v1/investigations/search)"
  count="$(RESULT="$result" python3 -c 'import json,os; print(json.loads(os.environ["RESULT"])["total_count"])')"
  if test "$count" -ge 1; then
    echo "mTLS syslog accepted and searchable: $marker"
    exit 0
  fi
  sleep 2
done
echo "mTLS event was not searchable before timeout" >&2
exit 1
