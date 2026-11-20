"""Create optional event-time indexes for legacy normalized Parquet objects."""

import io
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pyarrow.parquet as pq

from .event_index import event_time_bounds
from .storage import get_object_bytes, list_object_keys, put_object


def _create_index(key: str) -> bool:
    table = pq.read_table(io.BytesIO(get_object_bytes(key)), columns=["event_time"])
    values = table["event_time"].to_pylist()
    if not values or any(value is None for value in values):
        return False
    body = json.dumps(
        {"version": 1, **event_time_bounds(values)}, separators=(",", ":")
    ).encode()
    put_object(f"{key}.index.json", body, "application/json")
    return True


def backfill_event_indexes(workers: int = 1) -> dict[str, int]:
    if workers < 1 or workers > 16:
        raise ValueError("workers must be between 1 and 16")
    keys = list_object_keys("normalized/")
    available = set(keys)
    parquet = [key for key in keys if key.endswith(".parquet")]
    missing = [key for key in parquet if f"{key}.index.json" not in available]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        created = sum(executor.map(_create_index, missing))
    return {
        "examined": len(parquet),
        "created": created,
        "skipped": len(parquet) - created,
    }


if __name__ == "__main__":
    worker_count = int(os.environ.get("OSL_EVENT_INDEX_WORKERS", "8"))
    print(json.dumps(backfill_event_indexes(worker_count), sort_keys=True))
