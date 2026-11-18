#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plan_file="${OSL_RETENTION_PLAN:-$repository/retention-plan.json}"
command="${1:-plan}"
shift || true

case "$command" in
  plan)
    temporary="$(mktemp)"
    trap 'rm -f "$temporary"' EXIT
    docker compose exec -T api python -m app.retention plan "$@" > "$temporary"
    python3 -m json.tool "$temporary" >/dev/null
    mv "$temporary" "$plan_file"
    echo "Retention plan written to $plan_file"
    python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print({"candidate_count":p["candidate_count"],"candidate_bytes":p["candidate_bytes"],"expires_at":p["expires_at"]})' "$plan_file"
    ;;
  apply)
    test -f "$plan_file" || { echo "Create $plan_file with '$0 plan' first" >&2; exit 1; }
    docker compose exec -T api python -m app.retention apply < "$plan_file"
    ;;
  *) echo "Usage: $0 [plan|apply] [retention options]" >&2; exit 2 ;;
esac
