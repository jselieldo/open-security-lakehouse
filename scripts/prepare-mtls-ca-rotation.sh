#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
current="${OSL_MTLS_DIR:-$repository/data/mtls}"
server_ip="${OSL_MTLS_SERVER_IP:-$(hostname -I | awk '{print $1}')}"
valid_days="${OSL_MTLS_VALID_DAYS:-825}"
rotation_id="${OSL_MTLS_ROTATION_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
candidate="${OSL_MTLS_ROTATION_DIR:-$repository/data/mtls-rotation/$rotation_id}"

test "$valid_days" -ge 30 -a "$valid_days" -le 825
printf '%s' "$server_ip" | grep -Eq '^[0-9a-fA-F:.]+$'
test -f "$current/ca/ca.crt"
test -f "$current/server/server.crt"
test -f "$current/clients/homelab/client.crt"
test -f "$current/clients/windows/client.crt"
test ! -e "$candidate" || {
  echo "rotation candidate already exists: $candidate" >&2
  exit 1
}

umask 077
mkdir -p "$candidate/ca" "$candidate/server" \
  "$candidate/clients/homelab" "$candidate/clients/windows" "$candidate/trust"
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$candidate/ca/ca.key"
openssl req -x509 -new -sha256 -days "$valid_days" -key "$candidate/ca/ca.key" \
  -subj '/CN=OSL Collector CA/O=Open Security Lakehouse' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' -out "$candidate/ca/ca.crt"

issue_certificate() {
  name="$1"
  common_name="$2"
  directory="$3"
  usage="$4"
  san="$5"
  extension="$staging/$name.ext"
  printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=%s\nsubjectAltName=%s\n' \
    "$usage" "$san" > "$extension"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$directory/$name.key"
  openssl req -new -sha256 -key "$directory/$name.key" \
    -subj "/CN=$common_name/O=Open Security Lakehouse" -out "$staging/$name.csr"
  openssl x509 -req -sha256 -days "$valid_days" -in "$staging/$name.csr" \
    -CA "$candidate/ca/ca.crt" -CAkey "$candidate/ca/ca.key" -CAcreateserial \
    -extfile "$extension" -out "$directory/$name.crt"
}

issue_certificate server server "$candidate/server" serverAuth \
  "DNS:osl-syslog,DNS:homelab,IP:$server_ip"
issue_certificate client homelab-client "$candidate/clients/homelab" clientAuth "DNS:homelab"
issue_certificate client windows-client "$candidate/clients/windows" clientAuth \
  "DNS:windows-workstation"

cat "$current/ca/ca.crt" "$candidate/ca/ca.crt" > "$candidate/trust/ca-bundle.crt"
cp "$candidate/trust/ca-bundle.crt" "$candidate/clients/homelab/ca.crt"
cp "$candidate/trust/ca-bundle.crt" "$candidate/clients/windows/ca.crt"

openssl verify -CAfile "$candidate/ca/ca.crt" "$candidate/server/server.crt" \
  "$candidate/clients/homelab/client.crt" "$candidate/clients/windows/client.crt"
openssl verify -CAfile "$candidate/trust/ca-bundle.crt" \
  "$current/server/server.crt" "$current/clients/homelab/client.crt" \
  "$current/clients/windows/client.crt" "$candidate/server/server.crt" \
  "$candidate/clients/homelab/client.crt" "$candidate/clients/windows/client.crt"

chmod 600 "$candidate/ca/ca.key" "$candidate/server/server.key" \
  "$candidate/clients/homelab/client.key" "$candidate/clients/windows/client.key"
chmod 644 "$candidate/ca/ca.crt" "$candidate/server/server.crt" \
  "$candidate/trust/ca-bundle.crt" "$candidate/clients/"*/{ca.crt,client.crt}
(
  cd "$candidate"
  sha256sum ca/ca.crt server/server.crt clients/homelab/client.crt \
    clients/windows/client.crt trust/ca-bundle.crt > CERTIFICATE-SHA256SUMS
)

echo "Prepared mTLS CA rotation candidate: $candidate"
echo "No active certificate or service was changed."
