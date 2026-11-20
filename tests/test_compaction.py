import io
import json
from datetime import UTC, date, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from app.compaction import PartitionPlan, compact_partition, plan_compaction
from app.investigation import _select_query_objects


def parquet_bytes(event_id: str) -> bytes:
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist([{"event_id": event_id}]), buffer)
    return buffer.getvalue()


def test_plan_only_selects_completed_uncompacted_partitions() -> None:
    old = "normalized/source=windows/year=2026/month=11/day=16"
    current = "normalized/source=windows/year=2026/month=11/day=18"
    compacted = "normalized/source=linux/year=2026/month=11/day=15"
    keys = [f"{old}/batch={index}.parquet" for index in range(3)]
    keys += [f"{current}/batch={index}.parquet" for index in range(3)]
    keys += [f"{compacted}/batch={index}.parquet" for index in range(3)]
    keys.append(f"{compacted}/_compaction.json")

    plans = plan_compaction(
        date(2026, 11, 18),
        minimum_objects=2,
        keys=keys,
        manifests={
            compacted: {
                "source_objects": [f"{compacted}/batch={index}.parquet" for index in range(3)]
            }
        },
    )

    assert [plan.partition for plan in plans] == [old]
    assert plans[0].source_objects == 3
    assert plans[0].source_keys == tuple(f"{old}/batch={index}.parquet" for index in range(3))


def test_plan_recompacts_partition_after_enough_late_objects() -> None:
    partition = "normalized/source=windows/year=2026/month=11/day=17"
    covered = [f"{partition}/batch={index}.parquet" for index in range(3)]
    late = [f"{partition}/batch=late-{index}.parquet" for index in range(2)]
    keys = covered + late + [f"{partition}/_compaction.json"]

    plans = plan_compaction(
        date(2026, 11, 18),
        minimum_objects=2,
        keys=keys,
        manifests={partition: {"source_objects": covered}},
    )

    assert len(plans) == 1
    assert plans[0].source_keys == tuple(sorted(covered + late))


def test_compaction_publishes_manifest_only_after_verified_object(monkeypatch) -> None:
    partition = "normalized/source=windows/year=2026/month=11/day=16"
    source_keys = [f"{partition}/batch={index}.parquet" for index in range(2)]
    objects = {key: parquet_bytes(key) for key in source_keys}
    writes: list[str] = []

    monkeypatch.setattr("app.compaction.list_object_keys", lambda _prefix: list(objects))
    monkeypatch.setattr("app.compaction.get_object_bytes", lambda key: objects[key])

    def fake_put(key: str, body: bytes, _content_type: str) -> None:
        objects[key] = body
        writes.append(key)

    monkeypatch.setattr("app.compaction.put_object", fake_put)
    result = compact_partition(
        PartitionPlan(
            partition, "windows", "2026-11-16", len(source_keys), tuple(source_keys)
        )
    )

    assert result["row_count"] == 2
    assert writes[-1] == f"{partition}/_compaction.json"
    manifest = json.loads(objects[writes[-1]])
    assert manifest["source_objects"] == source_keys


def test_compaction_failure_does_not_publish_manifest(monkeypatch) -> None:
    partition = "normalized/source=windows/year=2026/month=11/day=16"
    source_keys = [f"{partition}/batch={index}.parquet" for index in range(2)]
    objects = {key: parquet_bytes(key) for key in source_keys}
    writes: list[str] = []
    monkeypatch.setattr("app.compaction.list_object_keys", lambda _prefix: source_keys)
    monkeypatch.setattr("app.compaction.get_object_bytes", lambda key: objects[key])

    def failing_put(key: str, _body: bytes, _content_type: str) -> None:
        writes.append(key)
        raise OSError("storage unavailable")

    monkeypatch.setattr("app.compaction.put_object", failing_put)
    with pytest.raises(OSError, match="storage unavailable"):
        compact_partition(
            PartitionPlan(
                partition, "windows", "2026-11-16", len(source_keys), tuple(source_keys)
            )
        )
    assert not any(key.endswith("_compaction.json") for key in writes)


def test_compaction_records_event_time_bounds(monkeypatch) -> None:
    partition = "normalized/source=windows/year=2026/month=11/day=16"
    keys = [f"{partition}/batch={index}.parquet" for index in range(2)]
    objects = {}
    for index, key in enumerate(keys):
        table = pa.Table.from_pylist([{
            "event_id": str(index),
            "event_time": datetime(2026, 11, 15 + index, 12, tzinfo=UTC),
        }])
        buffer = io.BytesIO()
        pq.write_table(table, buffer)
        objects[key] = buffer.getvalue()
    monkeypatch.setattr("app.compaction.get_object_bytes", lambda key: objects[key])
    monkeypatch.setattr(
        "app.compaction.put_object",
        lambda key, body, _type: objects.__setitem__(key, body),
    )
    result = compact_partition(PartitionPlan(partition, "windows", "2026-11-16", 2, tuple(keys)))
    assert result["compact_event_time_bounds"] == {
        "min_event_time": "2026-11-15T12:00:00+00:00",
        "max_event_time": "2026-11-16T12:00:00+00:00",
    }


def test_investigation_prefers_compact_objects_only_after_manifest() -> None:
    partition = "normalized/source=windows/year=2026/month=11/day=16"
    originals = [f"{partition}/batch={index}.parquet" for index in range(3)]
    compact = f"{partition}/compact=abc-0000.parquet"

    manifest = {
        partition: {"source_objects": originals, "compact_objects": [compact]}
    }
    assert _select_query_objects(originals + [compact]) == originals
    assert _select_query_objects(originals + [compact], manifest) == [compact]


def test_investigation_includes_events_arriving_after_active_compaction() -> None:
    partition = "normalized/source=windows/year=2026/month=11/day=18"
    compacted_sources = [f"{partition}/batch={index}.parquet" for index in range(2)]
    late_event = f"{partition}/batch=late.parquet"
    compact = f"{partition}/compact=abc-0000.parquet"
    manifest = {
        partition: {
            "source_objects": compacted_sources,
            "compact_objects": [compact],
        }
    }

    selected = _select_query_objects(
        compacted_sources + [late_event, compact], manifest
    )

    assert selected == [late_event, compact]
