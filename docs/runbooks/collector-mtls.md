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

Linux and Windows were both observed after collector and server restarts with certificate
metadata retained in their raw events. The transitional TCP 5514 listener has therefore been
removed. Confirm TCP 6514 after future upgrades and treat any reintroduction of plaintext
syslog as a security regression.

Backups created after mTLS activation contain `mtls.tar` inside the encrypted archive. Treat
that archive and its encryption key as sufficient to impersonate every collector.
