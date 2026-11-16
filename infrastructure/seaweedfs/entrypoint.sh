#!/bin/sh
set -eu

case "${S3_ACCESS_KEY}${S3_SECRET_KEY}" in
  *[!A-Za-z0-9_-]*)
    echo "S3 credentials may contain only letters, digits, underscore, and hyphen." >&2
    exit 1
    ;;
esac

sed -e "s|__ACCESS_KEY__|${S3_ACCESS_KEY}|g" \
    -e "s|__SECRET_KEY__|${S3_SECRET_KEY}|g" \
    /etc/seaweedfs/s3.json.template > /tmp/s3.json
exec /usr/bin/weed s3 \
  -ip=seaweed-s3 \
  -filer=seaweed-filer:8888 \
  -port=8333 \
  -config=/tmp/s3.json

