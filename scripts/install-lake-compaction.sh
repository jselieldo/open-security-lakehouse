#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_template="$repository/infrastructure/systemd/osl-lake-compaction.service.template"
timer_source="$repository/infrastructure/systemd/osl-lake-compaction.timer"
service_target="/etc/systemd/system/osl-lake-compaction.service"
timer_target="/etc/systemd/system/osl-lake-compaction.timer"
service_user="$(id -un)"
service_group="$(id -gn)"

getent group docker >/dev/null || { echo "Docker group not found" >&2; exit 1; }
id -nG "$service_user" | tr ' ' '\n' | grep -qx docker || {
  echo "$service_user must belong to the docker group" >&2
  exit 1
}

temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
sed \
  -e "s|__OSL_USER__|$service_user|g" \
  -e "s|__OSL_GROUP__|$service_group|g" \
  -e "s|__OSL_REPOSITORY__|$repository|g" \
  "$service_template" > "$temporary"

sudo install -o root -g root -m 0644 "$temporary" "$service_target"
sudo install -o root -g root -m 0644 "$timer_source" "$timer_target"
sudo systemctl daemon-reload
sudo systemctl enable --now osl-lake-compaction.timer
sudo systemctl start osl-lake-compaction.service
sudo systemctl is-active --quiet osl-lake-compaction.timer
echo "Hourly lake compaction timer installed and first run completed."
