# Architecture overview

Milestone 1 establishes the control plane and durable infrastructure without coupling future data-plane components to a particular storage implementation.

```text
Host (127.0.0.1:8000)
        |
    FastAPI control plane
       / \
PostgreSQL  S3 contract
(metadata)      |
            SeaweedFS
       master/filer/volume
```

- PostgreSQL stores operational metadata only; security events will live in object storage.
- The API talks to storage through the S3 contract. A later Ceph or cloud migration does not change application domain code.
- `storage` is an internal Compose network. `backend` permits publishing the API on
  loopback, while PostgreSQL remains private because it has no published ports.
- Liveness verifies the API process. Readiness verifies PostgreSQL and the configured S3 bucket.
- Milestone 2 can add Vector, raw event ingestion, OCSF normalization, Parquet, and quarantine prefixes.
- Milestone 3 can add DuckDB behind a query interface; the interface can later target Trino/Iceberg.

## Intended object layout

```text
s3://osl-security-data/
  raw/<source>/year=YYYY/month=MM/day=DD/
  normalized/source=<source>/year=YYYY/month=MM/day=DD/
  quarantine/invalid-events/
  artifacts/investigation-results/
  artifacts/detection-evidence/
```

