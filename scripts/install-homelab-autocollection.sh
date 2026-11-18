#!/usr/bin/env bash
set -euo pipefail

source_file="infrastructure/rsyslog/60-osl.conf"
target_file="/etc/rsyslog.d/60-osl.conf"
certificate_source="data/mtls/clients/homelab"
certificate_target="/etc/rsyslog.d/osl-mtls"
collector_host="${OSL_SYSLOG_HOST:-$(hostname -I | awk '{print $1}')}"
required_rsyslog_gnutls="8.2512.0-1ubuntu4.2"

test -f "$source_file"
test -n "$collector_host"
installed_rsyslog_gnutls="$(dpkg-query -W -f='${Version}' rsyslog-gnutls 2>/dev/null || true)"
test "$installed_rsyslog_gnutls" = "$required_rsyslog_gnutls" || {
  echo "Install the pinned TLS driver first:" >&2
  echo "  sudo apt-get install rsyslog-gnutls=$required_rsyslog_gnutls" >&2
  exit 1
}
for file in ca.crt client.crt client.key; do test -f "$certificate_source/$file"; done
temporary_file="$(mktemp)"
trap 'rm -f "$temporary_file"' EXIT
sed "s/__OSL_SYSLOG_HOST__/$collector_host/g" "$source_file" > "$temporary_file"
sudo install -o root -g root -m 0644 "$temporary_file" "$target_file"
# The Ubuntu AppArmor profile permits rsyslog to read /etc/rsyslog.d/**.
# Grant only the dedicated syslog account access to the certificate subdirectory.
sudo install -d -o root -g syslog -m 0750 "$certificate_target"
sudo install -o root -g syslog -m 0640 "$certificate_source/ca.crt" "$certificate_target/ca.crt"
sudo install -o root -g syslog -m 0640 "$certificate_source/client.crt" "$certificate_target/client.crt"
sudo install -o root -g syslog -m 0640 "$certificate_source/client.key" "$certificate_target/client.key"
sudo rsyslogd -N1
sudo systemctl restart rsyslog
sudo systemctl is-active --quiet rsyslog
logger -p authpriv.warning -t osl-homelab "OSL homelab autocollection validation"
echo "Homelab autocollection installed and validation event emitted."
