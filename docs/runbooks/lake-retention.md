# Lake retention runbook

Retention is a two-phase, operator-controlled process. PostgreSQL metadata is not used for
telemetry retention; object storage remains the security data plane.

Default policy:

| Area | Retention |
| --- | ---: |
| Raw ingestion evidence | 90 days |
| Normalized Parquet | 90 days |
| Invalid-event quarantine | 90 days |
| Detection and investigation artifacts | 365 days |
| Original Parquet batches covered by verified compaction | 14 days |

Create a plan without deleting anything:

```bash
./scripts/retention.sh plan
cat retention-plan.json | python3 -m json.tool | less
```

The plan contains exact keys, reasons, sizes, timestamps, a SHA-256 digest, and a 24-hour
expiry. Unknown object areas are never selected. Superseded batches are eligible only when
their compaction manifest references a compact object that still exists.

After reviewing the plan and confirming a current off-host encrypted backup, apply exactly
that plan:

```bash
./scripts/retention.sh apply
```

Application is irreversible in the active lake. Recovery requires an encrypted backup.
Never schedule `apply` directly: schedule plan generation, review it, and apply deliberately.
Adjust periods during planning, for example `./scripts/retention.sh plan --raw-days 180`.
