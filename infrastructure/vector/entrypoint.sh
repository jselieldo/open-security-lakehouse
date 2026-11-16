#!/bin/sh
set -eu

case "${SYSLOG_ALLOWED_CIDR:?Set SYSLOG_ALLOWED_CIDR}" in
  *[!0-9a-fA-F:./]*)
    echo "SYSLOG_ALLOWED_CIDR contains invalid characters" >&2
    exit 1
    ;;
esac

sed "s|__SYSLOG_ALLOWED_CIDR__|${SYSLOG_ALLOWED_CIDR}|g" \
  /etc/vector/vector.toml.template > /tmp/vector.toml

exec vector "$@"
