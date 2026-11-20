import io
import json
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
from app.event_index_backfill import backfill_event_indexes


def parquet_bytes() -> bytes:
    buffer = io.BytesIO()
    pq.write_table(
        pa.Table.from_pylist([{"event_time": datetime(2026, 11, 20, 12, tzinfo=UTC)}]),
        buffer,
    )
    return buffer.getvalue()


def test_backfill_creates_only_missing_indexes(monkeypatch) -> None:
    first = "normalized/source=linux/year=2026/month=11/day=20/batch=one.parquet"
    second = "normalized/source=linux/year=2026/month=11/day=20/batch=two.parquet"
    objects = {first: parquet_bytes(), second: parquet_bytes(), f"{second}.index.json": b"{}"}
    writes = {}
    monkeypatch.setattr("app.event_index_backfill.list_object_keys", lambda _prefix: list(objects))
    monkeypatch.setattr("app.event_index_backfill.get_object_bytes", lambda key: objects[key])
    monkeypatch.setattr(
        "app.event_index_backfill.put_object",
        lambda key, body, content_type: writes.update({key: (body, content_type)}),
    )

    result = backfill_event_indexes()

    assert result == {"examined": 2, "created": 1, "skipped": 1}
    body, content_type = writes[f"{first}.index.json"]
    assert content_type == "application/json"
    assert json.loads(body)["min_event_time"] == "2026-11-20T12:00:00+00:00"


def test_backfill_rejects_unsafe_worker_count() -> None:
    try:
        backfill_event_indexes(17)
    except ValueError as exc:
        assert "between 1 and 16" in str(exc)
    else:
        raise AssertionError("unsafe backfill concurrency was accepted")
