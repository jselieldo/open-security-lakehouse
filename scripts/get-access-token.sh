#!/usr/bin/env bash
set -euo pipefail

if [[ "${AUTH_MODE:-hybrid}" == "static" ]]; then
  : "${OSL_API_TOKEN:?Set OSL_API_TOKEN}"
  printf '%s' "$OSL_API_TOKEN"
  exit 0
fi

: "${OIDC_TEST_USERNAME:?Set OIDC_TEST_USERNAME}"
: "${OIDC_TEST_PASSWORD:?Set OIDC_TEST_PASSWORD}"
issuer="${OIDC_ISSUER_URL:-http://127.0.0.1:18080/realms/osl}"
token_url="${OIDC_TOKEN_URL:-$issuer/protocol/openid-connect/token}"
client_id="${OIDC_CLIENT_ID:-osl-console}"

response=$(curl --fail --silent --show-error \
  --data-urlencode grant_type=password \
  --data-urlencode "client_id=$client_id" \
  --data-urlencode "username=$OIDC_TEST_USERNAME" \
  --data-urlencode "password=$OIDC_TEST_PASSWORD" \
  "$token_url")

TOKEN_RESPONSE="$response" python3 -c \
  'import json, os; print(json.loads(os.environ["TOKEN_RESPONSE"])["access_token"], end="")'
