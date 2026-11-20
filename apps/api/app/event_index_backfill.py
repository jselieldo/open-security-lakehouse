"""Create optional event-time indexes for legacy normalized Parquet objects."""

import io
import json

import pyarrow.parquet as pq

from .event_index import event_time_bounds
from .storage import get_object_bytes, list_object_keys, put_object


def backfill_event_indexes() -> dict[str, int]:
    keys = list_object_keys("normalized/")
    available = set(keys)
    result = {"examined": 0, "created": 0, "skipped": 0}
    for key in keys:
        if not key.endswith(".parquet"):
            continue
        result["examined"] += 1
        index_key = f"{key}.index.json"
        if index_key in available:
            result["skipped"] += 1
            continue
        table = pq.read_table(io.BytesIO(get_object_bytes(key)), columns=["event_time"])
        values = table["event_time"].to_pylist()
        if not values or any(value is None for value in values):
            result["skipped"] += 1
            continue
        body = json.dumps(
            {"version": 1, **event_time_bounds(values)}, separators=(",", ":")
        ).encode()
        put_object(index_key, body, "application/json")
        result["created"] += 1
    return result


if __name__ == "__main__":
    print(json.dumps(backfill_event_indexes(), sort_keys=True))
