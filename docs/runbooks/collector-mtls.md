# Collector mTLS migration

Generate the authority once on the homelab, using the stable LAN address in the server SAN:

```bash
OSL_MTLS_SERVER_IP=192.168.3.120 ./scripts/generate-mtls-certs.sh
docker compose up -d --force-recreate vector
```

Validate the server with the Linux client certificate:

```bash
set -a; . ./.env; set +a
./scripts/mtls-smoke-test.sh
```

Install the pinned Ubuntu TLS driver and then the homelab rsyslog client:

```bash
sudo apt-get install rsyslog-gnutls=8.2512.0-1ubuntu4.2
./scripts/install-homelab-autocollection.sh
```

The installer stores certificates under `/etc/rsyslog.d/osl-mtls`, which is already readable
under Ubuntu's packaged AppArmor profile for rsyslog. Only `root` and the dedicated `syslog`
group can traverse that subdirectory or read its certificate files. The Docker collector
environment under `/etc/osl` remains `root:root` mode `0600`; the AppArmor profile is not
weakened or locally overridden.
Copy only `data/mtls/clients/windows/{ca.crt,client.crt,client.key}` to the same ignored path
in the Windows checkout, then rerun the elevated Windows collector installer. Never transfer
the CA private key or another client's private key.

Rotate one client at a time without replacing the authority:

```bash
./scripts/rotate-mtls-client.sh homelab
./scripts/rotate-mtls-client.sh windows
```

The replacement subjects are `CN=homelab-client` and `CN=windows-client`. The script verifies
the new certificate before replacing the source files and keeps the previous key and
certificate under the ignored `data/mtls/retired` directory for rollback. Reinstall and
validate each collector before rotating the next one. After both replacements are confirmed
in raw event `tls_client` metadata, securely remove the retired private keys; keeping them
allows the retired identities to reconnect until the CA is replaced or revocation is added.

Run the inventory check on demand with:

```bash
./scripts/check-mtls-certificates.py --root data/mtls --warning-days 30
```

The homelab installer provisions a persistent daily systemd timer for the same check. It
validates the trust chain, exact subjects, expiry threshold, fingerprints, serial numbers and
the set of expected certificate files. A failure emits an `authpriv.err` event tagged
`osl-certificates`, which enters the lake through the existing Linux collector and matches the
high-severity detection rule. The report never reads or prints private-key material.

Vector 0.61.0 validates certificate chains and expiry but its syslog TLS configuration has no
explicit CRL option. Emergency revocation therefore requires rotating the collector CA,
deploying the new server trust first, replacing every authorized client, and then removing the
old CA. Do not assume deleting a certificate file revokes copies stored in encrypted backups.

## Full CA rotation and emergency revocation

Prepare, but do not activate, a complete candidate hierarchy:

```bash
OSL_MTLS_SERVER_IP=192.168.3.120 ./scripts/prepare-mtls-ca-rotation.sh
```

The command writes only under the ignored `data/mtls-rotation/<UTC timestamp>` directory. It
generates a new CA, server and client keys, plus `trust/ca-bundle.crt` containing the active and
candidate public CAs. It verifies current and candidate leaves against that bundle and records
certificate checksums. Private keys are deliberately excluded from the checksum manifest.

Use this order during an approved maintenance window:

1. Create and verify an encrypted OSL backup. Record the candidate path and fingerprints.
2. Save a root-only rollback copy of the active `data/mtls` directory outside the candidate.
3. Deploy only `trust/ca-bundle.crt` as the server's client trust, then recreate Vector. The
   active server certificate and both old clients remain unchanged; validate both sources.
4. For each client separately, install its candidate `client.crt`, `client.key`, and bundled
   `ca.crt`. Validate its new subject in stored `tls_client` metadata before continuing.
5. Replace the Vector server certificate and key with the candidate pair while keeping the
   dual-CA bundle. Recreate Vector and verify Linux and Windows reconnect.
6. Promote the candidate CA certificate and key, replace every client `ca.crt` with the new CA
   alone, and replace the server trust bundle with the new CA alone. Recreate/restart each
   component and run the inventory check.
7. Remove the old CA private key and rollback copies only after a new encrypted backup passes
   checksum validation. Protect or expire older backups because they may still contain it.

Rollback before step 6 by restoring the saved active directory, reinstalling both client files,
and recreating Vector. After the old CA is removed in step 6, rollback would re-authorize the
revoked CA and must be treated as an explicit security exception.

Never promote the candidate directory with a recursive copy. Copy the named certificate and key
files for the current phase so the dual-trust boundary remains visible and reviewable.

## Isolated alert-path validation

Run the end-to-end certificate-monitor alert test with:

```bash
./scripts/certificate-alert-smoke-test.sh
```

The script points the monitor at a nonexistent `/tmp` directory and emits the expected failure
with the reserved `osl-smoke` tag. Vector classifies it as `test-syslog`, which production rules
exclude. The dedicated `[TEST]` rule is then run explicitly; the script verifies searchable
telemetry and immutable evidence, adds a triage comment, and closes the resulting test alert as
`false_positive`. No active certificate or production alert is modified.

Linux and Windows were both observed after collector and server restarts with certificate
metadata retained in their raw events. The transitional TCP 5514 listener has therefore been
removed. Confirm TCP 6514 after future upgrades and treat any reintroduction of plaintext
syslog as a security regression.

Backups created after mTLS activation contain `mtls.tar` inside the encrypted archive. Treat
that archive and its encryption key as sufficient to impersonate every collector.
