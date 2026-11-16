#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
analyst_token=$(AUTH_MODE=oidc ./scripts/get-access-token.sh)

me=$(curl --fail --silent --show-error \
  --header "Authorization: Bearer $analyst_token" "$API_URL/api/v1/users/me")
denied=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  --header "Authorization: Bearer $analyst_token" "$API_URL/api/v1/audit")
test "$denied" = "403"

: "${OIDC_ADMIN_USERNAME:?Set OIDC_ADMIN_USERNAME}"
: "${OIDC_ADMIN_PASSWORD:?Set OIDC_ADMIN_PASSWORD}"
admin_token=$(OIDC_TEST_USERNAME="$OIDC_ADMIN_USERNAME" OIDC_TEST_PASSWORD="$OIDC_ADMIN_PASSWORD" \
  AUTH_MODE=oidc ./scripts/get-access-token.sh)
audit=$(curl --fail --silent --show-error \
  --header "Authorization: Bearer $admin_token" "$API_URL/api/v1/audit?limit=100")

ME="$me" AUDIT="$audit" python3 - <<'PY'
import json
import os

me = json.loads(os.environ["ME"])
audit = json.loads(os.environ["AUDIT"])
assert me["auth_method"] == "oidc", me
assert {"viewer", "ingestor", "analyst"}.issubset(me["roles"]), me
assert any(item["outcome"] == "denied" and item["resource"] == "/api/v1/audit" for item in audit), audit
print(f"Milestone 6 smoke test passed: OIDC, RBAC and {len(audit)} audit entries validated.")
PY
