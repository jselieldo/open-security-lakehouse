#!/usr/bin/env bash
set -euo pipefail

client="${1:-}"
case "$client" in
  homelab) san="DNS:homelab" ;;
  windows) san="DNS:windows-workstation" ;;
  *) echo "usage: $0 {homelab|windows}" >&2; exit 2 ;;
esac

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="${OSL_MTLS_DIR:-$repository/data/mtls}"
valid_days="${OSL_MTLS_VALID_DAYS:-825}"
target="$root/clients/$client"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
retired="$root/retired/$client-$timestamp"
staging="$(mktemp -d)"
extension="$staging/client.ext"
trap 'rm -rf "$staging"' EXIT

test "$valid_days" -ge 30 -a "$valid_days" -le 825
for file in "$root/ca/ca.key" "$root/ca/ca.crt" "$target/client.key" "$target/client.crt"; do
  test -f "$file" || { echo "required mTLS file is missing: $file" >&2; exit 1; }
done

umask 077
printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=clientAuth\nsubjectAltName=%s\n' \
  "$san" > "$extension"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$staging/client.key"
openssl req -new -sha256 -key "$staging/client.key" \
  -subj "/CN=$client-client/O=Open Security Lakehouse" -out "$staging/client.csr"
openssl x509 -req -sha256 -days "$valid_days" -in "$staging/client.csr" \
  -CA "$root/ca/ca.crt" -CAkey "$root/ca/ca.key" -CAcreateserial \
  -extfile "$extension" -out "$staging/client.crt"
openssl verify -CAfile "$root/ca/ca.crt" "$staging/client.crt"
openssl x509 -in "$staging/client.crt" -noout -subject | grep -F "CN = $client-client"

mkdir -p "$retired"
install -m 0600 "$target/client.key" "$retired/client.key"
install -m 0644 "$target/client.crt" "$retired/client.crt"
install -m 0600 "$staging/client.key" "$target/client.key"
install -m 0644 "$staging/client.crt" "$target/client.crt"
install -m 0644 "$root/ca/ca.crt" "$target/ca.crt"

echo "Rotated $client client certificate; rollback material: $retired"
