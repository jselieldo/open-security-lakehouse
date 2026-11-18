# Lake compaction runbook

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

Run an encrypted backup before the first production compaction and after a successful run.
Compare a representative investigation before and after applying compaction. The command
prints partition, source-object, compact-object, and row totals as JSON for operational logs.

Original normalized batches remain available for lineage and rollback. Deleting them is a
separate future retention decision and must not be combined with routine compaction.
