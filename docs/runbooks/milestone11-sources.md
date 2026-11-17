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

# Operational meaning of source status

For event-driven sources, `silent` means that no matching telemetry arrived within the
configured interval. It does not alone prove that the collector process failed. Check the
systemd service health together with the catalog timestamp.

Install the homelab Docker collector as a restricted host service:

```bash
./scripts/install-docker-collector.sh
systemctl status osl-docker-collector.service
```

The API and Vector containers never receive the Docker socket. Only the host-side service
runs under the homelab user, with membership in the existing `docker` group and a
root-owned credential file.
