# Milestone 11 — staged source onboarding

1. Back up the installation before applying migration `0003_source_catalog`.
   Deploy the API and worker together with the revised Parquet reader.
2. Validate with `alembic current` and `./scripts/milestone11-smoke-test.sh`
   after sourcing `.env`. The smoke event is tagged `test-docker`; it does not
   appear in operational Docker detections.
3. Register the host's Docker collector (admin bearer token required):

   ```sh
   curl -X POST http://127.0.0.1:8000/api/v1/sources \
     -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
     -d '{"source_id":"docker-homelab","source":"docker-events","kind":"docker","hostname":"YOUR_HOSTNAME","display_name":"Docker homelab","expected_interval_minutes":1440}'
   ```

   `YOUR_HOSTNAME` must match `OSL_DOCKER_HOSTNAME` (defaults to the host's
   `socket.gethostname()`). Sources that rarely emit events need an interval
   matching their expected *maximum silence*, not an arbitrary 60-minute timer.
4. On the host, provide `COLLECTOR_API_TOKEN` through a protected environment
   file (not command-line arguments), then run
   `python3 scripts/collect-docker-events.py` under an unprivileged service
   account authorized to use the Docker CLI. A supervisor should restart it on
   failure. The Docker group itself is effectively root access; limit membership.
   The script stores its checkpoint in `~/.local/state/osl/` by default. Back up
   this checkpoint if a gap in Docker's finite event history would be unacceptable.
5. Onboard a second Linux host using the existing TCP rsyslog forwarding policy
   (`infrastructure/rsyslog/60-osl.conf`); register an entry with
   `source=linux-syslog`, `kind=linux`, and that machine's syslog `hostname`.
   Both hosts still share the Vector credential: hostname separation is coverage
   metadata, **not** verified machine identity. Verify its events using the
   hostname filter in the console. Restrict `SYSLOG_ALLOWED_CIDR` appropriately.
6. For firewall/router or application onboarding, collect sanitized sample
   messages plus model, firmware and export method (syslog/CEF/LEEF/JSON/API).
   Do not classify them as Linux or claim OCSF conformity without a tested parser.

Use **Fontes** in the console or `GET /api/v1/sources` to see configured versus
observed entries and `waiting`, `active`, `silent`, or `disabled` states.
`last_received_at` is updated only after a completed batch. Existing pre-migration
batches are not backfilled into the catalog.

The detection worker checks configured sources every five minutes by default
(`SOURCE_HEALTH_CHECK_MINUTES`). After `expected_interval_minutes` elapses without a completed
batch, it creates a deduplicated high-severity `source-silence` alert and stores an immutable
operational snapshot under `artifacts/source-health/`. A source that has never sent data gets
the same grace period starting at registration. When ingestion resumes, the active silence
alert is resolved automatically with a system-authored history entry. A later silence episode
uses the new `last_received_at` value and can create a new alert.

# Operational meaning of source status

For event-driven sources, `silent` means that no matching telemetry arrived within the
configured interval. It does not alone prove that the collector process failed. Check the
systemd service health together with the catalog timestamp.

Install the homelab Docker collector as a restricted host service:

```bash
./scripts/install-docker-collector.sh
systemctl status osl-docker-collector.service
```

The API and Vector containers never receive the Docker socket. Only the host-side services
run under the homelab user, with membership in the existing `docker` group and a
root-owned credential file.

# Docker application logs

The installer also enables `osl-docker-log-collector.service`. It polls `stdout` and
`stderr` through the host Docker CLI, sends batches to `/api/v1/ingestion/docker-logs`, and
stores a per-container checkpoint under `/var/lib/osl-docker-log-collector/`. Messages are
limited to 16 KiB; container environment variables and labels are not collected.

Containers whose names start with `open-security-lakehouse-` are excluded by default. This
prevents an ingestion request from producing another API log and creating a feedback loop.
Use anchored regular expressions in `/etc/osl/docker-collector.env` to select workloads:

```ini
OSL_DOCKER_LOG_INCLUDE=^(business-api|worker)-
OSL_DOCKER_LOG_EXCLUDE=^open-security-lakehouse-
OSL_DOCKER_LOG_INTERVAL_SECONDS=15
```

Restart the collector after changing filters and confirm its health:

```bash
sudo systemctl restart osl-docker-log-collector.service
systemctl status osl-docker-log-collector.service
```

In the console, investigate with `Fonte = docker-logs`, application equal to the container
name, and event type `container.log.stdout` or `container.log.stderr`.

Three enabled detection rules evaluate this source every five minutes:

- `docker-app-auth-failures`: five authentication denials in ten minutes;
- `docker-app-exceptions`: three unhandled exceptions or fatal failures in ten minutes;
- `docker-app-stderr-burst`: ten stderr messages in five minutes.

These are generic text detections. Review real application vocabulary and tune thresholds
before treating them as production-grade controls. Test traffic remains isolated under
`test-docker-logs` and is not queried by these rules.
