# ADR 0005: Source coverage and host-side Docker collection

## Status

Accepted for Milestone 11 (incremental rollout).

## Decision

Keep source configuration, last successful ingestion, event counts and silence
thresholds in PostgreSQL. Event content remains in S3. Operators register sources
with an administrator token. Unknown sources are observed as *unclassified*, not
automatically trusted or assigned a device type. A registered host-specific entry
matches the declared `hostname`; otherwise an unclassified source-wide entry is
used. A missing event is **silence**, not proof that a device is offline.

Use the Docker CLI on the host to stream container lifecycle events. It forwards
one authenticated event at a time and saves a checkpoint **after** API success.
Replays derive deterministic IDs. Do not mount `docker.sock` into Vector or the
API: the Docker socket grants host-level privileges. No new runtime dependency is
introduced; Python standard library and the existing Docker CLI suffice.

Old Parquet files remain queryable: missing host/application/type columns are
filled with null at read time. This is a local compatibility step, not Iceberg
schema evolution. Syslog hostnames and Docker payloads are self-declared; neither
is cryptographically authenticated as a device. Per-device credentials and
transport authentication are deferred to the security-hardening milestone.

## Limits

Firewall/router vendor parsers require actual sanitized samples and known export
protocols. Application log adapters similarly require concrete formats. No
vendor-specific mapping is claimed in this milestone.
