#!/usr/bin/env bash
set -euo pipefail

source_file="infrastructure/rsyslog/60-osl.conf"
target_file="/etc/rsyslog.d/60-osl.conf"
collector_host="${OSL_SYSLOG_HOST:-$(hostname -I | awk '{print $1}')}"

test -f "$source_file"
test -n "$collector_host"
temporary_file="$(mktemp)"
trap 'rm -f "$temporary_file"' EXIT
sed "s/__OSL_SYSLOG_HOST__/$collector_host/g" "$source_file" > "$temporary_file"
sudo install -o root -g root -m 0644 "$temporary_file" "$target_file"
sudo rsyslogd -N1
sudo systemctl restart rsyslog
sudo systemctl is-active --quiet rsyslog
logger --authpriv --priority authpriv.warning --tag osl-homelab "OSL homelab autocollection validation"
echo "Homelab autocollection installed and validation event emitted."
