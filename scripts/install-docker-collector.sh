#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template="$repository/infrastructure/systemd/osl-docker-collector.service.template"
service_file="/etc/systemd/system/osl-docker-collector.service"
environment_dir="/etc/osl"
environment_file="$environment_dir/docker-collector.env"
collector_user="$(id -un)"
collector_group="$(id -gn)"
token="$(sed -n 's/^COLLECTOR_API_TOKEN=//p' "$repository/.env" | tail -n 1)"

test -n "$token" || { echo "COLLECTOR_API_TOKEN not found in .env" >&2; exit 1; }
printf '%s' "$token" | grep -Eq '^[A-Za-z0-9._-]{32,}$' || {
  echo "COLLECTOR_API_TOKEN has an unsupported format" >&2
  exit 1
}
getent group docker >/dev/null || { echo "Docker group not found" >&2; exit 1; }
id -nG "$collector_user" | tr ' ' '\n' | grep -qx docker || {
  echo "$collector_user must belong to the docker group" >&2
  exit 1
}

temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
sed \
  -e "s|__OSL_USER__|$collector_user|g" \
  -e "s|__OSL_GROUP__|$collector_group|g" \
  -e "s|__OSL_REPOSITORY__|$repository|g" \
  "$template" > "$temporary"

sudo install -d -o root -g root -m 0750 "$environment_dir"
printf 'COLLECTOR_API_TOKEN=%s\nOSL_DOCKER_INGEST_URL=http://127.0.0.1:8000/api/v1/ingestion/docker\n' "$token" \
  | sudo tee "$environment_file" >/dev/null
sudo chown root:root "$environment_file"
sudo chmod 0600 "$environment_file"
sudo install -o root -g root -m 0644 "$temporary" "$service_file"
sudo systemctl daemon-reload
sudo systemctl enable --now osl-docker-collector.service
sudo systemctl is-active --quiet osl-docker-collector.service
echo "Docker event collector installed and active."
