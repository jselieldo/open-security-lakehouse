#!/usr/bin/env bash
set -euo pipefail

backup_file="${1:?Usage: $0 <backup.tar.enc>}"
key_file="${OSL_BACKUP_KEY_FILE:-$HOME/.config/osl/backup.key}"
work="$(mktemp -d)"
suffix="$(date +%s)-$$"
osl_db="osl_restore_test_${suffix//-/_}"
keycloak_db="keycloak_restore_test_${suffix//-/_}"
test_bucket="osl-restore-test-$suffix"

cleanup() {
  docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$osl_db" >/dev/null 2>&1 || true
  docker compose exec -T keycloak-db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$keycloak_db" >/dev/null 2>&1 || true
  docker compose exec -T -e S3_BUCKET="$test_bucket" api python -m app.backup purge >/dev/null 2>&1 || true
  rm -rf -- "$work"
}
trap cleanup EXIT

test -f "$backup_file"
test -f "$key_file"
test -f "$backup_file.sha256"
(cd "$(dirname "$backup_file")" && sha256sum -c "$(basename "$backup_file").sha256")
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$key_file" \
  -in "$backup_file" | tar -C "$work" -xf -
(cd "$work" && sha256sum -c SHA256SUMS)

docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$osl_db"
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$1" --exit-on-error' sh "$osl_db" < "$work/osl.dump"
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$1" -Atc "SELECT count(*) FROM ingestion_batches"' sh "$osl_db" >/dev/null

docker compose exec -T keycloak-db sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$keycloak_db"
docker compose exec -T keycloak-db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$1" --exit-on-error' sh "$keycloak_db" < "$work/keycloak.dump"
docker compose exec -T keycloak-db sh -c 'psql -U "$POSTGRES_USER" -d "$1" -Atc "SELECT count(*) FROM realm"' sh "$keycloak_db" >/dev/null

mkdir "$work/grafana"
tar -C "$work/grafana" -xf "$work/grafana.tar"
python3 - "$work/grafana/grafana.db" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
PY

actual="$(docker compose exec -T -e S3_BUCKET="$test_bucket" api python -m app.backup import < "$work/objects.tar")"
ARCHIVE="$work/objects.tar" ACTUAL="$actual" python3 - <<'PY'
import json
import os
import tarfile

actual = json.loads(os.environ["ACTUAL"])
with tarfile.open(os.environ["ARCHIVE"]) as archive:
    members = [item for item in archive if item.isfile() and item.name.startswith("objects/")]
expected = {"objects": len(members), "bytes": sum(item.size for item in members)}
assert actual == expected, (actual, expected)
PY

echo "Backup verified: checksums, OSL DB, Keycloak DB, Grafana DB, and object lake restored successfully."
