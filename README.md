# Open Security Lakehouse

Milestone 2 is an executable first-data pipeline for a security lakehouse on a native Linux host with 16 GB RAM. It provides a FastAPI control plane, PostgreSQL batch metadata, Apache-2.0-licensed SeaweedFS object storage, raw-event preservation, initial OCSF normalization, Parquet output, quarantine, idempotency, and automated validation.

This is a development foundation, not a production-ready SIEM. The Compose topology is single-host and has no high availability or TLS termination.

## Prerequisites

- Native Linux (x86_64 or arm64)
- Docker Engine 24+ with Docker Compose v2
- GNU Make, curl, and OpenSSL
- Python 3.12+ only when running tests outside containers
- Recommended: 4 CPU cores, 16 GB RAM, and 20 GB free disk

## Install and start

```bash
git clone <repository-url> open-security-lakehouse
cd open-security-lakehouse
cp .env.example .env
```

Edit `.env`. Replace every `CHANGE_ME` value. Generate secrets, for example:

```bash
openssl rand -hex 32
```

Validate and start:

```bash
docker compose config --quiet
docker compose up --build --wait
docker compose ps
```

Only the API is exposed, at `http://127.0.0.1:8000` by default. PostgreSQL and SeaweedFS are reachable only by containers on private networks.

## Validate the installation

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
set -a; source .env; set +a
curl --fail -H "Authorization: Bearer $OSL_API_TOKEN" \
  http://127.0.0.1:8000/api/v1/system/info
./scripts/smoke-test.sh
./scripts/milestone2-smoke-test.sh
```

Expected readiness response:

```json
{"status":"ready","database":"ok","object_storage":"ok"}
```

## Automated tests

```bash
make install
make lint
make test
```

The unit suite does not need Docker. The smoke test requires the full Compose stack.

## Ingest the first events

Load the local environment and send a mixed synthetic batch:

```bash
set -a; source .env; set +a
./scripts/ingest-synthetic.sh --count 10 --invalid 1
```

The authenticated `POST /api/v1/ingestion/batches` endpoint stores the original JSON batch under `raw/`, writes valid normalized rows as Zstandard-compressed Parquet under `normalized/`, and writes invalid events with validation errors under `quarantine/invalid-events/`. Reusing the same `batch_id` and source returns the persisted result without writing duplicate objects.

Retrieve batch state with:

```bash
curl --fail -H "Authorization: Bearer $OSL_API_TOKEN" \
  http://127.0.0.1:8000/api/v1/ingestion/batches/<batch-id>
```

## Operations

```bash
docker compose logs -f --tail=100
docker compose down                 # preserve named volumes
docker compose down --volumes       # destructive: delete all local platform data
```

Back up the named volumes before upgrades. Do not expose port 8000 publicly without a TLS reverse proxy, token rotation, rate limiting, and an identity-aware authentication layer. The initial static bearer token is deliberately small in scope and should evolve to OIDC plus RBAC.

## Repository map

```text
apps/api/                    FastAPI control plane
infrastructure/seaweedfs/    S3 gateway configuration
docs/architecture/           current architecture
docs/adr/                    architecture decisions
scripts/                     operator smoke tests
tests/                       automated API tests
compose.yaml                 executable local topology
```

See [architecture overview](docs/architecture/overview.md) and [ADR 0001](docs/adr/0001-object-storage.md).

## Next milestone

Milestone 3 adds DuckDB-backed investigation by IP, time range, source, and severity over the normalized Parquet data.
