#!/usr/bin/env bash
set -euo pipefail

if [[ "${AUTH_MODE:-hybrid}" == "static" ]]; then
  : "${OSL_API_TOKEN:?Set OSL_API_TOKEN}"
  printf '%s' "$OSL_API_TOKEN"
  exit 0
fi

: "${OIDC_TEST_USERNAME:?Set OIDC_TEST_USERNAME}"
: "${OIDC_TEST_PASSWORD:?Set OIDC_TEST_PASSWORD}"
issuer="${OIDC_ISSUER_URL:-http://127.0.0.1:8080/realms/osl}"
client_id="${OIDC_CLIENT_ID:-osl-console}"

response=$(curl --fail --silent --show-error \
  --data-urlencode grant_type=password \
  --data-urlencode "client_id=$client_id" \
  --data-urlencode "username=$OIDC_TEST_USERNAME" \
  --data-urlencode "password=$OIDC_TEST_PASSWORD" \
  "$issuer/protocol/openid-connect/token")

TOKEN_RESPONSE="$response" python3 -c \
  'import json, os; print(json.loads(os.environ["TOKEN_RESPONSE"])["access_token"], end="")'
