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

Confirm events from both hostnames continue to arrive and inspect Vector metrics for TLS or
discard errors. Keep TCP 5514 during this observation period. Remove its Compose port and the
`linux_syslog` source only after both clients have remained healthy through a restart and a
certificate-backed smoke test.

Backups created after mTLS activation contain `mtls.tar` inside the encrypted archive. Treat
that archive and its encryption key as sufficient to impersonate every collector.
