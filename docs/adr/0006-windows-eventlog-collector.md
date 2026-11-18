# ADR 0006: Windows Event Log collection

## Status

Accepted for the trusted single-subnet homelab.

## Decision

Use Vector 0.61.0 on Windows with the native `windows_event_log` source. Vector
is already part of the platform, is pinned, and is distributed under MPL-2.0.
The agent keeps durable checkpoints and a disk buffer on the Windows host.
Server-side Vector batches up to 100 records or two seconds before ingestion to
bound object-count growth without changing the immutable raw-event contract.

The Windows agent serializes the native record into the syslog message and sends
RFC 5424 over the existing TCP listener. Server-side Vector identifies the
`windows-eventlog` application and forwards the event through the existing
ingestion-only machine identity. The API adapter maps stable Windows fields to
the common normalized contract while preserving the full source record.

PostgreSQL stores only source and ingestion metadata. Raw and normalized Windows
telemetry remains in S3-compatible object storage.

## Consequences

- The API and its bearer token remain unavailable on the LAN.
- Windows collection receives the same retry, disk-buffer and idempotency
  behavior as the Linux path.
- The Windows Security channel needs explicit local permission.
- ADR 0007 supersedes the initial trusted-LAN transport: Windows now uses
  mutually authenticated TLS on TCP 6514 and the plaintext listener is removed.
- The first deployment limits backlog age, event rate, field size and excludes
  raw XML to control volume and sensitive-data exposure.
- Detection rules select exact event types through bounded structured lists
  rather than relying on untrusted raw-text fragments for event-ID matching.
