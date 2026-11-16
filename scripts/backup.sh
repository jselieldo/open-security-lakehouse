#!/usr/bin/env bash
set -euo pipefail

backup_dir="${OSL_BACKUP_DIR:-$HOME/osl-backups}"
key_file="${OSL_BACKUP_KEY_FILE:-$HOME/.config/osl/backup.key}"
retention_days="${OSL_BACKUP_RETENTION_DAYS:-14}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="osl-backup-$timestamp"
stage="$(mktemp -d)"
grafana_stopped=0

cleanup() {
  rm -rf -- "$stage"
  if [ "$grafana_stopped" -eq 1 ]; then docker compose start grafana >/dev/null; fi
}
trap cleanup EXIT

test -f "$key_file" || {
  echo "Backup key not found: $key_file" >&2
  echo "Create it with: mkdir -p \"$(dirname "$key_file")\" && openssl rand -base64 48 > \"$key_file\" && chmod 600 \"$key_file\"" >&2
  exit 1
}
test "$backup_dir" != "/" || {
  echo "Refusing to use the filesystem root as backup directory" >&2
  exit 1
}
test "$(stat -c '%a' "$key_file")" = "600" || {
  echo "Backup key must have mode 600: $key_file" >&2
  exit 1
}
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$stage/osl.dump"
docker compose exec -T keycloak-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$stage/keycloak.dump"
docker compose exec -T api python -m app.backup export > "$stage/objects.tar"

docker compose stop grafana >/dev/null
grafana_stopped=1
docker run --rm --volume open-security-lakehouse_grafana-data:/data:ro \
  --entrypoint tar grafana/grafana:13.2.1 -C /data -cf - . > "$stage/grafana.tar"
docker compose start grafana >/dev/null
grafana_stopped=0

cp .env "$stage/environment.env"
cp compose.yaml "$stage/compose.yaml"
git rev-parse HEAD > "$stage/git-commit.txt"
(
  cd "$stage"
  sha256sum osl.dump keycloak.dump objects.tar grafana.tar environment.env compose.yaml git-commit.txt > SHA256SUMS
)
tar -C "$stage" -cf - . | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
  -pass "file:$key_file" -out "$backup_dir/$name.tar.enc"
(cd "$backup_dir" && sha256sum "$name.tar.enc" > "$name.tar.enc.sha256")
find "$backup_dir" -type f -name 'osl-backup-*.tar.enc*' -mtime "+$retention_days" -delete
echo "$backup_dir/$name.tar.enc"
