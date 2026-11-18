"""Non-destructive compaction for completed normalized lake partitions."""

import argparse
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256

import pyarrow as pa
import pyarrow.parquet as pq

from .storage import get_object_bytes, list_object_keys, put_object

PARTITION_PATTERN = re.compile(
    r"^normalized/source=(?P<source>[^/]+)/year=(?P<year>\d{4})/"
    r"month=(?P<month>\d{2})/day=(?P<day>\d{2})$"
)
MANIFEST_NAME = "_compaction.json"


@dataclass(frozen=True)
class PartitionPlan:
    partition: str
    source: str
    partition_date: str
    source_objects: int
    source_keys: tuple[str, ...]


def plan_compaction(
    before: date,
    minimum_objects: int = 10,
    keys: list[str] | None = None,
    manifests: dict[str, dict[str, object]] | None = None,
) -> list[PartitionPlan]:
    supplied_keys = keys is not None
    keys = keys if supplied_keys else list_object_keys("normalized/")
    batches: dict[str, list[str]] = {}
    manifest_keys = [key for key in keys if key.endswith(f"/{MANIFEST_NAME}")]
    if manifests is None:
        manifests = {}
        if not supplied_keys:
            for key in manifest_keys:
                try:
                    document = json.loads(get_object_bytes(key))
                except (json.JSONDecodeError, OSError, ValueError):
                    continue
                if isinstance(document, dict):
                    manifests[key.rsplit("/", 1)[0]] = document
    for key in keys:
        if "/batch=" not in key or not key.endswith(".parquet"):
            continue
        partition = key.rsplit("/", 1)[0]
        batches.setdefault(partition, []).append(key)

    plans: list[PartitionPlan] = []
    for partition, objects in sorted(batches.items()):
        match = PARTITION_PATTERN.fullmatch(partition)
        if not match:
            continue
        manifest = manifests.get(partition)
        if manifest:
            covered = {
                str(key)
                for key in manifest.get("source_objects", [])
                if isinstance(key, str)
            }
            eligible_count = len(set(objects) - covered)
        else:
            eligible_count = len(objects)
        if eligible_count < minimum_objects:
            continue
        partition_date = date(
            int(match["year"]), int(match["month"]), int(match["day"])
        )
        if partition_date >= before:
            continue
        plans.append(
            PartitionPlan(
                partition=partition,
                source=match["source"],
                partition_date=partition_date.isoformat(),
                source_objects=len(objects),
                source_keys=tuple(sorted(objects)),
            )
        )
    return plans


def compact_partition(plan: PartitionPlan) -> dict[str, object]:
    source_keys = list(plan.source_keys)
    if len(source_keys) != plan.source_objects:
        raise RuntimeError("invalid compaction plan")

    tables = [pq.read_table(io.BytesIO(get_object_bytes(key))) for key in source_keys]
    table = pa.concat_tables(tables, promote_options="default")
    digest = sha256("\n".join(source_keys).encode()).hexdigest()[:16]
    compact_key = f"{plan.partition}/compact={digest}-0000.parquet"
    body = _parquet_bytes(table)
    put_object(compact_key, body, "application/vnd.apache.parquet")

    verified = pq.read_table(io.BytesIO(get_object_bytes(compact_key)))
    if verified.num_rows != table.num_rows:
        raise RuntimeError("compacted object row-count verification failed")

    manifest = {
        "version": 1,
        "partition": plan.partition,
        "created_at": datetime.now(UTC).isoformat(),
        "source_objects": source_keys,
        "compact_objects": [compact_key],
        "row_count": table.num_rows,
        "parquet_bytes": len(body),
    }
    put_object(
        f"{plan.partition}/{MANIFEST_NAME}",
        json.dumps(manifest, separators=(",", ":")).encode(),
        "application/json",
    )
    return manifest


def apply_compaction(
    before: date,
    minimum_objects: int = 10,
) -> dict[str, object]:
    plans = plan_compaction(before=before, minimum_objects=minimum_objects)
    results = [compact_partition(plan) for plan in plans]
    return {
        "mode": "apply",
        "before": before.isoformat(),
        "partitions": len(results),
        "source_objects": sum(len(item["source_objects"]) for item in results),
        "compact_objects": sum(len(item["compact_objects"]) for item in results),
        "rows": sum(int(item["row_count"]) for item in results),
    }


def _parquet_bytes(table: pa.Table) -> bytes:
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument(
        "--before",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="compact partitions strictly older than YYYY-MM-DD (default: today UTC)",
    )
    parser.add_argument("--minimum-objects", type=int, default=10)
    args = parser.parse_args()
    if args.minimum_objects < 2:
        parser.error("--minimum-objects must be at least 2")

    if args.command == "plan":
        plans = plan_compaction(args.before, args.minimum_objects)
        result: object = {
            "mode": "plan",
            "before": args.before.isoformat(),
            "partitions": len(plans),
            "source_objects": sum(plan.source_objects for plan in plans),
            "items": [
                {
                    "partition": plan.partition,
                    "source": plan.source,
                    "partition_date": plan.partition_date,
                    "source_objects": plan.source_objects,
                }
                for plan in plans
            ],
        }
    else:
        result = apply_compaction(args.before, args.minimum_objects)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
