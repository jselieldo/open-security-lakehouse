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
- Milestone 2 writes immutable raw JSON, OCSF-normalized Parquet, and validation failures to quarantine. PostgreSQL tracks batch state and idempotency.
- Milestone 3 uses DuckDB behind a structured query interface. S3 objects are loaded as Arrow tables, keeping arbitrary SQL outside the public API. The interface can later target Trino/Iceberg.
- Milestone 4 keeps versioned YAML rules in Git, schedules them in the control plane, stores alert state in PostgreSQL, and writes immutable evidence to the object lake. Event fingerprints deduplicate repeated matches.
- Milestone 5 serves a static, responsive console from FastAPI. It calls only structured authenticated APIs and stores its bearer token in browser session memory.

## Intended object layout

```text
s3://osl-security-data/
  raw/<source>/year=YYYY/month=MM/day=DD/
  normalized/source=<source>/year=YYYY/month=MM/day=DD/
  quarantine/invalid-events/
  artifacts/investigation-results/
  artifacts/detection-evidence/
```

