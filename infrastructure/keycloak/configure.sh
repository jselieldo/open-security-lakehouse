#!/usr/bin/env bash
set -euo pipefail

KCADM=/opt/keycloak/bin/kcadm.sh
"$KCADM" config credentials \
  --server http://keycloak:8080 \
  --realm master \
  --user "$KEYCLOAK_ADMIN" \
  --password "$KEYCLOAK_ADMIN_PASSWORD"

ensure_user() {
  local username="$1"
  local password="$2"
  shift 2

  local user_id
  user_id=$("$KCADM" get users -r osl -q "username=$username" --fields id --format csv --noquotes | head -n 1)
  if [[ -z "$user_id" ]]; then
    "$KCADM" create users -r osl \
      -s "username=$username" \
      -s enabled=true >/dev/null
    user_id=$("$KCADM" get users -r osl -q "username=$username" --fields id --format csv --noquotes | head -n 1)
  fi
  "$KCADM" update "users/$user_id" -r osl \
    -s firstName=OSL \
    -s "lastName=$username" \
    -s "email=$username@localhost.invalid" \
    -s emailVerified=true \
    -s 'requiredActions=[]'
  "$KCADM" set-password -r osl --username "$username" --new-password "$password"
  "$KCADM" add-roles -r osl --uusername "$username" "$@"
}

ensure_user "$OIDC_TEST_USERNAME" "$OIDC_TEST_PASSWORD" \
  --rolename viewer --rolename ingestor --rolename analyst
ensure_user "$OIDC_ADMIN_USERNAME" "$OIDC_ADMIN_PASSWORD" \
  --rolename admin
