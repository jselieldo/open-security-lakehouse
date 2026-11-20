# ADR 0002: OIDC identity and schema migrations

## Status

Accepted for Milestone 6.

## Decision

Use Keycloak 26.8.2 as the self-hosted OpenID Connect provider. The browser console uses Authorization Code with PKCE. FastAPI validates access tokens locally against Keycloak JWKS and requires the configured issuer and `osl-api` audience.

Realm roles map to four application capabilities: `viewer`, `ingestor`, `analyst`, and `admin`. The API persists a current user projection and append-only access/denial audit entries in its metadata PostgreSQL database. Keycloak uses a separate PostgreSQL database and volume.

Use Alembic 1.20.0 for database revisions. The baseline revision safely adopts tables from Milestones 1–5 and creates missing identity/audit tables. Its downgrade is intentionally non-destructive.

## Security boundary

The legacy static token is accepted only in explicit `static` or transitional `hybrid` mode. Normal operation uses `oidc`. API port 8000 and Keycloak port 8080 bind to the homelab loopback; remote operators map Keycloak to local port 18080 through SSH, which is also its advertised public origin. The bundled Keycloak `start-dev` configuration is not approved for direct internet exposure.

## Licenses

- Keycloak 26.8.2: Apache License 2.0.
- PyJWT 2.15.1: MIT License; the `crypto` extra uses the Apache-2.0/BSD-licensed Cryptography package.
- Alembic 1.20.0: MIT License.

All versions are pinned in Compose or Python requirements for repeatable builds.
