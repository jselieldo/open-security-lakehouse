#!/usr/bin/env bash
set -Eeuo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
lock_file="${OSL_COMPACTION_LOCK_FILE:-/run/lock/osl-lake-compaction.lock}"
minimum_objects="${OSL_COMPACTION_MINIMUM_OBJECTS:-100}"
memory_limit="${OSL_COMPACTION_MEMORY_LIMIT:-6g}"

on_error() {
  status=$?
  logger -p authpriv.err -t osl-compaction \
    "OSL lake compaction failed status=$status"
  exit "$status"
}
trap on_error ERR

exec 9>"$lock_file"
if ! flock -n 9; then
  logger -p authpriv.notice -t osl-compaction \
    "OSL lake compaction skipped because another run is active"
  exit 0
fi

before="$(date -u -d tomorrow +%F)"
cd "$repository"
result="$(
  timeout --signal=TERM --kill-after=2m 40m \
    docker compose run --rm --no-deps --memory "$memory_limit" api \
    python -m app.compaction apply \
    --before "$before" --minimum-objects "$minimum_objects"
)"
logger -p authpriv.info -t osl-compaction \
  "OSL lake compaction completed $result"
printf '%s\n' "$result"
