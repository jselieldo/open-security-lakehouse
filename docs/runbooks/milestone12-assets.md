# Milestone 12 — observed asset inventory

## Scope of this increment

Every newly accepted normalized event may update an operational asset record. A
hostname is the preferred correlation key; when it is absent, a source IP becomes
the key. The record contains first/last seen timestamps, observed IP addresses,
contributing sources and an event counter. Full events and raw payloads remain in
the object lake.

The console **Ativos** view lists this context and can open an investigation
filtered by hostname or, for IP-only assets, by source IP. API access requires the
`viewer` or `analyst` role:

```text
GET /api/v1/assets
GET /api/v1/assets/{asset_id}
GET /api/v1/assets/{asset_id}/activity
PATCH /api/v1/assets/{asset_id}   (admin)
```

Administrators can assign `criticality`, `owner` and up to 20 normalized aliases.
New detection alerts that contain events from one known asset receive an immutable
snapshot of its identifier, display name and criticality. Changing an asset later
does not rewrite existing alert evidence or historical alert context.

The detection worker also consumes operational change records every five minutes.
It creates `asset-new` alerts for newly observed assets and
`asset-context-change` alerts when an existing asset appears with a new IP or a
new telemetry source. Evidence is written under `artifacts/asset-observations/`.
Sources prefixed with `test-` update their test inventory context but never queue
these operational alerts. A storage failure leaves the change pending for retry.

The **Ativos** view exposes a detail panel with the latest 100 observed changes
and related alerts. It contains only control-plane metadata and links to alert
triage; full event payloads remain available through investigation and immutable
evidence in object storage.

The console starts an asset timeline with a 24-hour window to avoid an accidental
full-lake scan. Analysts may change or remove that period explicitly. Older
objects created before event-time indexes remain searchable but can make broad
queries slow.

## Trust boundaries

- Hostnames and source IPs are claims observed in telemetry, not authenticated
  inventory facts.
- The inventory never stores full event bodies in PostgreSQL.
- Test sources also create observed assets so test data remains explainable; do
  not treat their presence as production coverage.
- Existing lake objects are not backfilled by migration `0005_asset_inventory`.
  New accepted ingestion populates the inventory incrementally.

## Validation

After deployment, emit a Linux, Windows or Docker event, open **Ativos**, and
confirm that the relevant host has a recent observation. Use **Investigar linha
do tempo** and confirm the investigation is filtered to that hostname.

If no asset appears, verify that the ingestion batch has at least one accepted
event and that the normalized event contains `hostname` or `src_ip`. Quarantined
events intentionally do not change the inventory.
