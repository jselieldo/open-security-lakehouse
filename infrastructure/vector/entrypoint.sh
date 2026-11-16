#!/bin/sh
set -eu

case "${SYSLOG_ALLOWED_CIDR:?Set SYSLOG_ALLOWED_CIDR}" in
  *[!0-9a-fA-F:./]*)
    echo "SYSLOG_ALLOWED_CIDR contains invalid characters" >&2
    exit 1
    ;;
esac

case "${COLLECTOR_API_TOKEN:?Set COLLECTOR_API_TOKEN}" in
  *[!A-Za-z0-9_-]*)
    echo "COLLECTOR_API_TOKEN contains invalid characters" >&2
    exit 1
    ;;
esac

sed \
  -e "s|__SYSLOG_ALLOWED_CIDR__|${SYSLOG_ALLOWED_CIDR}|g" \
  -e "s|__COLLECTOR_API_TOKEN__|${COLLECTOR_API_TOKEN}|g" \
  /etc/vector/vector.toml.template > /tmp/vector.toml

exec vector "$@"
