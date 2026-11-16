# Backup and restore runbook

## Scope and recovery model

Milestone 9 protects the OSL operational database, Keycloak database, Grafana state, object lake, runtime configuration, and deployed Git revision. The default local retention is 14 days. Copy encrypted archives and their `.sha256` sidecars to separate storage; a backup kept only on the homelab does not protect against host or disk loss.

The encryption key must be backed up separately from the archives. Loss of the key makes every archive unrecoverable. Restrict it to mode `600` and never commit it.

## Schedule

After creating the key, use a rootless user timer or cron entry. Example daily cron job:

```cron
15 2 * * * cd /home/jselieldo/open-security-lakehouse && ./scripts/backup.sh >> /home/jselieldo/osl-backups/backup.log 2>&1
```

Run `verify-backup.sh` at least monthly and after changes to database, storage, or identity versions. The verification is a real isolated restore, not only an archive checksum.

## Full disaster recovery

1. Provision a clean Linux host with Docker and the Compose plugin.
2. Check out the revision recorded in `git-commit.txt` from the decrypted archive.
3. Restore `environment.env` as `.env` with mode `600` and start only PostgreSQL, Keycloak PostgreSQL, and SeaweedFS.
4. Restore `osl.dump` and `keycloak.dump` with `pg_restore --clean --if-exists` into the database names defined by `.env`.
5. Import `objects.tar` with `python -m app.backup import` in the API image.
6. With Grafana stopped, extract `grafana.tar` into the empty `grafana-data` volume.
7. Start the full stack, run all health checks and smoke tests, then confirm users, alerts, investigation results, dashboards, and audit records.

Always rehearse these steps on an isolated host. Never run a destructive restore against the active homelab merely to test a backup; use `verify-backup.sh` instead.
