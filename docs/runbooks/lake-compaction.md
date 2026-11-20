# Lake compaction runbook

Do not run event-index backfill inside the API container while the platform is
serving requests. On lakes with tens of thousands of objects it can exhaust the
shared S3 path and make readiness or Prometheus scrapes time out. The homelab
backfill is currently paused pending an isolated, rate-limited maintenance job.

Compaction reduces investigation latency by combining the many small normalized Parquet
objects created by ingestion. Raw evidence, quarantine objects, and original normalized
batch objects are not deleted. This first phase is deliberately non-destructive.

Only daily partitions strictly older than the UTC date passed to `--before` are eligible.
The current UTC day is therefore excluded by default, preventing a race with active
ingestion. A partition must contain at least ten batch objects unless the operator changes
`--minimum-objects`.

Preview the operation:

```bash
./scripts/compact-lake.sh plan
```

Create and verify the compacted objects, then publish their manifests:

```bash
./scripts/compact-lake.sh apply
```

The manifest is written last. Investigation continues to read original batch objects until
that marker exists, and then reads only the compacted object for the partition. If an upload
or verification fails, the marker is not published and queries remain on the originals.
New compaction manifests include minimum and maximum **event** times for indexed time-range
searches. New ingestion batches write optional `.parquet.index.json` sidecars. Missing or
invalid bounds leave an object eligible for search; old objects need no migration. Index
lookups add small object reads but can avoid much larger Parquet downloads. This is not yet
an indexed catalog or partition pruning at S3 listing time: searches still list all keys
under the selected source and load remaining Parquet objects into memory. Do not infer event
time from the directory date, which is the ingestion date and may differ for late arrivals.
For a one-time safe backfill after upgrading a legacy lake, run
`docker compose exec -T api python -m app.event_index_backfill`. The command adds
only missing `.index.json` sidecars and never rewrites Parquet telemetry. Repeating
it is safe; verify the reported examined, created and skipped counts. The command
uses eight workers by default and rejects values above 16; set
`OSL_EVENT_INDEX_WORKERS=4` before the command on a constrained host.
Events arriving after the compaction snapshot are read alongside the compacted object, so an
operator may explicitly include the active day by passing tomorrow's UTC date to `--before`.
The safe default still excludes the active day.
On later runs, a previously compacted partition becomes eligible again after it accumulates
at least `--minimum-objects` late arrivals. The replacement compact object covers the full
partition snapshot; its manifest atomically supersedes the earlier compact object.

Run an encrypted backup before the first production compaction and after a successful run.
Compare a representative investigation before and after applying compaction. The command
prints partition, source-object, compact-object, and row totals as JSON for operational logs.

Original normalized batches remain available for lineage and rollback. Deleting them is a
separate future retention decision and must not be combined with routine compaction.
