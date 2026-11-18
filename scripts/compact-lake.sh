#!/usr/bin/env bash
set -euo pipefail

command="${1:-plan}"
shift || true
case "$command" in
  plan|apply) ;;
  *) echo "Usage: $0 [plan|apply] [--before YYYY-MM-DD] [--minimum-objects N]" >&2; exit 2 ;;
esac

docker compose exec -T api python -m app.compaction "$command" "$@"
