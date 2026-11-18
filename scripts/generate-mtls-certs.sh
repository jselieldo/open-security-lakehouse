#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="${OSL_MTLS_DIR:-$repository/data/mtls}"
server_ip="${OSL_MTLS_SERVER_IP:-$(hostname -I | awk '{print $1}')}"
valid_days="${OSL_MTLS_VALID_DAYS:-825}"

test "$valid_days" -ge 30 -a "$valid_days" -le 825
printf '%s' "$server_ip" | grep -Eq '^[0-9a-fA-F:.]+$'
test ! -e "$root/ca/ca.key" || {
  echo "mTLS authority already exists at $root; refusing to overwrite it" >&2
  exit 1
}

umask 077
mkdir -p "$root/ca" "$root/server" "$root/clients/homelab" "$root/clients/windows"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$root/ca/ca.key"
openssl req -x509 -new -sha256 -days "$valid_days" -key "$root/ca/ca.key" \
  -subj '/CN=OSL Collector CA/O=Open Security Lakehouse' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' -out "$root/ca/ca.crt"

issue_certificate() {
  name="$1"
  directory="$2"
  usage="$3"
  san="$4"
  extension="$(mktemp)"
  trap 'rm -f "$extension"' RETURN
  printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=%s\nsubjectAltName=%s\n' \
    "$usage" "$san" > "$extension"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$directory/${name}.key"
  openssl req -new -sha256 -key "$directory/${name}.key" -subj "/CN=$name/O=Open Security Lakehouse" \
    -out "$directory/${name}.csr"
  openssl x509 -req -sha256 -days "$valid_days" -in "$directory/${name}.csr" \
    -CA "$root/ca/ca.crt" -CAkey "$root/ca/ca.key" -CAcreateserial \
    -extfile "$extension" -out "$directory/${name}.crt"
  rm -f "$directory/${name}.csr" "$extension"
  trap - RETURN
}

issue_certificate server "$root/server" serverAuth "DNS:osl-syslog,DNS:homelab,IP:$server_ip"
mv "$root/server/server.key" "$root/server/server.key.tmp"
mv "$root/server/server.key.tmp" "$root/server/server.key"
issue_certificate client "$root/clients/homelab" clientAuth "DNS:homelab"
issue_certificate client "$root/clients/windows" clientAuth "DNS:windows-workstation"
cp "$root/ca/ca.crt" "$root/clients/homelab/ca.crt"
cp "$root/ca/ca.crt" "$root/clients/windows/ca.crt"
chmod 600 "$root/ca/ca.key" "$root/server/server.key" "$root/clients/"*/client.key
chmod 644 "$root/ca/ca.crt" "$root/server/server.crt" "$root/clients/"*/{ca.crt,client.crt}
openssl verify -CAfile "$root/ca/ca.crt" "$root/server/server.crt" \
  "$root/clients/homelab/client.crt" "$root/clients/windows/client.crt"
echo "Generated OSL mTLS authority and certificates under $root"
