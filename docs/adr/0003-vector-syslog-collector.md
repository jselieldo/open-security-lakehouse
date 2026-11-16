# ADR 0003: Vector for Linux/syslog collection

## Status

Accepted for Milestone 7.

## Decision

Use Vector 0.61.0 as the first collector, receiving RFC 3164/5424 syslog over TCP. Vector forwards newline-delimited JSON batches to a dedicated FastAPI adapter and persists pending deliveries in a disk buffer configured for backpressure instead of dropping new events.

The collector authenticates with a random machine token that maps only to the `ingestor` role. Interactive users continue to authenticate through OIDC. The API deterministically derives batch and event identifiers from canonical content, preserving idempotency when Vector retries an HTTP request.

## Consequences

TCP is used instead of UDP so the sender and Vector can apply retry/backpressure. Syslog itself does not provide end-to-end acknowledgements, so Linux clients should use a persistent rsyslog queue. The Vector-to-API hop currently stays inside the private Compose network; TLS or mTLS is required before splitting these components across hosts.

This milestone collects syslog but does not yet claim complete OCSF mapping for every Linux facility or application. Source-specific adapters will refine event classes in later revisions.

## License

Vector 0.61.0 is distributed under Mozilla Public License 2.0. The version is pinned in Compose.
