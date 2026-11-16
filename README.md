# Open Security Lakehouse

Milestone 6 adds Keycloak OIDC login, persisted users, role-based access control, audit trails, and Alembic database migrations. The legacy bearer token remains available only when `AUTH_MODE=hybrid` or `static`.

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

The API and Keycloak are exposed on loopback at `http://127.0.0.1:8000` and `http://127.0.0.1:8080`. PostgreSQL and SeaweedFS remain private.

## Validate the installation

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
set -a; source .env; set +a
./scripts/smoke-test.sh
./scripts/milestone2-smoke-test.sh
docker compose exec -T api python - < scripts/verify-milestone2-storage.py
./scripts/milestone3-smoke-test.sh
./scripts/milestone4-smoke-test.sh
docker compose exec -T api python - < scripts/verify-milestone4-evidence.py
./scripts/milestone6-smoke-test.sh
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

The unit suite does not need Docker. Smoke tests require the full Compose stack and obtain an OIDC access token from Keycloak.

## Identity, roles, and audit

The installation creates two local test identities from `.env`: an analyst with `viewer`, `ingestor`, and `analyst` roles, and an administrator with `admin`. Change these credentials before first start.

| Role | Access |
| --- | --- |
| `viewer` | dashboards, batches, rules, alerts, and investigations |
| `ingestor` | event ingestion and batch status |
| `analyst` | investigations and detection execution |
| `admin` | all operations and audit-log access |

Tokens are verified with the realm's published signing keys plus strict issuer and audience checks. Successful authenticated requests and authorization denials are recorded in PostgreSQL. The `GET /api/v1/users/me` endpoint returns the current identity; `GET /api/v1/audit` is admin-only.

For an existing installation, set `AUTH_MODE=hybrid`, deploy once, confirm OIDC with `milestone6-smoke-test.sh`, then change it to `oidc` and recreate the API. New and upgraded deployments run `alembic upgrade head` before the API starts. To inspect migration state:

```bash
docker compose exec api alembic current
docker compose exec api alembic history
```

## Ingest the first events

Load the local environment and send a mixed synthetic batch:

```bash
set -a; source .env; set +a
./scripts/ingest-synthetic.sh --count 10 --invalid 1
```

The authenticated `POST /api/v1/ingestion/batches` endpoint stores the original JSON batch under `raw/`, writes valid normalized rows as Zstandard-compressed Parquet under `normalized/`, and writes invalid events with validation errors under `quarantine/invalid-events/`. Reusing the same `batch_id` and source returns the persisted result without writing duplicate objects.

Retrieve batch state with:

```bash
TOKEN="$(./scripts/get-access-token.sh)"
curl --fail -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/ingestion/batches/<batch-id>
```

## Investigate normalized events

Investigations accept structured filters only; clients cannot submit arbitrary SQL:

```bash
TOKEN="$(./scripts/get-access-token.sh)"
curl --fail \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "src_ip": "198.51.100.42",
    "source": "synthetic-linux",
    "start_time": "2026-11-15T00:00:00Z",
    "min_severity": 2,
    "limit": 100
  }' \
  http://127.0.0.1:8000/api/v1/investigations/search
```

The API lists matching Parquet objects through the S3 contract, loads their Arrow tables, and executes a parameterized DuckDB query. The response includes scanned object count, duration, and matching events.

## Run detections and inspect alerts

Rules live under `detections/rules/` as reviewed YAML files. List and run them with:

```bash
TOKEN="$(./scripts/get-access-token.sh)"
curl --fail -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/detections/rules

curl --fail -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/detections/rules/high-severity-events/run

curl --fail -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/alerts
```

Enabled rules run on their configured interval inside the single API process. Matching event identifiers form a deterministic alert fingerprint, preventing repeated runs from generating duplicate alerts. Full evidence is written under `artifacts/detection-evidence/` and the alert metadata is stored in PostgreSQL.

## Open the web console

The console is available at `http://127.0.0.1:8000/console/`. From another computer, keep the API private and use an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 -L 8080:127.0.0.1:8080 homelab-lan
```

Open `http://127.0.0.1:8000/console/`, choose **Entrar com OIDC**, and authenticate through Keycloak. The console uses Authorization Code with PKCE and keeps the access token only in browser `sessionStorage`.

## Operations

```bash
docker compose logs -f --tail=100
docker compose down                 # preserve named volumes
docker compose down --volumes       # destructive: delete all local platform data
```

Back up the named volumes before upgrades. Do not expose ports 8000 or 8080 publicly without TLS termination, hardened Keycloak production settings, rate limiting, and trusted hostname configuration. `start-dev` is appropriate only for this loopback homelab topology.

## Repository map

```text
apps/api/                    FastAPI control plane
infrastructure/keycloak/     OIDC realm and identity bootstrap
infrastructure/seaweedfs/    S3 gateway configuration
docs/architecture/           current architecture
docs/adr/                    architecture decisions
scripts/                     operator smoke tests
tests/                       automated API tests
compose.yaml                 executable local topology
```

See [architecture overview](docs/architecture/overview.md), [ADR 0001](docs/adr/0001-object-storage.md), and [ADR 0002](docs/adr/0002-identity-and-migrations.md).

## Next milestone

Milestone 7 can add TLS termination, refresh-token lifecycle, identity federation, and a multi-process scheduler/worker split.
