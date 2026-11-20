# Architecture overview

The architecture keeps identity, control-plane metadata, and security telemetry separated while remaining executable on a 16 GB single-host homelab.

```text
Browser --OIDC/PKCE--> Keycloak --dedicated DB--> PostgreSQL
   |                       |
   +--Bearer token--> FastAPI --metadata/audit--> PostgreSQL
                         |
                     S3 contract
                         |
                      SeaweedFS

Linux/rsyslog --mTLS TCP 6514--> Vector --disk buffer--> FastAPI ingestion
Windows Event Log --Vector/RFC5424 mTLS TCP 6514--> Vector --> FastAPI ingestion

FastAPI + Vector --metrics--> Prometheus --datasource--> Grafana
```

The Prometheus scrape endpoint never lists the object lake. Full S3 inventory
scans are maintenance operations because large object counts can exceed scrape
timeouts and make the API appear unavailable. Lake object/byte gauges therefore
remain unchanged until an isolated inventory refresher is introduced.

- PostgreSQL stores operational metadata only; security events will live in object storage.
- The API talks to storage through the S3 contract. A later Ceph or cloud migration does not change application domain code.
- `storage` is an internal Compose network. `backend` permits publishing the API on
  loopback, while PostgreSQL remains private because it has no published ports.
- Liveness verifies the API process. Readiness verifies PostgreSQL and the configured S3 bucket.
- Milestone 2 writes immutable raw JSON, OCSF-normalized Parquet, and validation failures to quarantine. PostgreSQL tracks batch state and idempotency.
- Milestone 3 uses DuckDB behind a structured query interface. S3 objects are loaded as Arrow tables, keeping arbitrary SQL outside the public API. The interface can later target Trino/Iceberg.
- New normalized batches publish optional event-time min/max sidecars; compacted partitions publish event-time bounds in the verified manifest. Bounded investigations skip Parquet downloads only when trustworthy bounds exclude the requested event-time window. Legacy objects without indexes remain readable; listing all object keys and loading matching objects into memory still limit scale.
- Milestone 4 keeps versioned YAML rules in Git, schedules them in the control plane, stores alert state in PostgreSQL, and writes immutable evidence to the object lake. Event fingerprints deduplicate repeated matches.
- Milestone 5 serves a static, responsive console from FastAPI. It calls only structured authenticated APIs and stores its bearer token in browser session memory.
- Milestone 6 uses Keycloak as the OIDC provider. FastAPI validates RS256 signatures, issuer, audience, and required claims, then enforces realm roles. First-seen user attributes and per-request audit records stay in PostgreSQL. Alembic owns schema evolution and runs before the API process.
- Milestone 7 adds Vector as the first data-plane collector. Syslog is CIDR-restricted and mutually authenticated with TLS, delivery to FastAPI is retried from a durable disk buffer, and a separate ingestion-only machine token prevents the collector from acquiring control-plane read access.
- Milestone 8 instruments the API and Vector with Prometheus metrics. Versioned rules detect availability and pipeline-quality problems, while Grafana receives a Git-provisioned datasource and operations dashboard. Both UIs remain loopback-only.
- Milestone 10 runs scheduled detections in a dedicated worker, connects Prometheus to Alertmanager, and provides alert triage/history.
- Milestone 11 catalogs configured and observed sources in PostgreSQL, ingests Docker lifecycle events through a host-side authenticated forwarder, and exposes source coverage and structured host/application/type filters. Raw and normalized telemetry remain in object storage. Vendor parsers and independently authenticated host collectors are not yet provided.
- Milestone 12 derives an asset inventory from accepted normalized events. PostgreSQL keeps only identity, source, counters, first/last-seen and operator-managed context; event bodies remain in object storage. Hostname correlation is case-insensitive and should be treated as observed context, not proof of device identity. New single-asset alerts snapshot the asset name and criticality so later inventory edits do not rewrite alert history or immutable evidence.
- Asset discovery and context changes are queued as operational metadata during ingestion, then converted asynchronously into deduplicated alerts and immutable object-storage evidence. This keeps notification and storage dependency failures outside the data-plane ingestion transaction.
- The first Windows increment uses pinned Vector 0.61.0 on the workstation. It
  preserves native event fields, checkpoints locally, and enters through the
  CIDR-restricted, mutually authenticated TLS syslog listener on TCP 6514.

## Intended object layout

```text
s3://osl-security-data/
  raw/<source>/year=YYYY/month=MM/day=DD/
  normalized/source=<source>/year=YYYY/month=MM/day=DD/
  quarantine/invalid-events/
  artifacts/investigation-results/
  artifacts/detection-evidence/
```
