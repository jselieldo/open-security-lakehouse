import io
from datetime import UTC, datetime, timedelta

import pyarrow as pa
import pyarrow.parquet as pq
from app.investigation import investigate
from app.schemas import InvestigationRequest


def parquet_bytes(rows: list[dict]) -> bytes:
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buffer)
    return buffer.getvalue()


def rows() -> list[dict]:
    now = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    return [
        {
            "event_id": "evt-high",
            "source": "synthetic-linux",
            "event_time": now,
            "ingested_at": now,
            "schema_name": "ocsf",
            "schema_version": "1.3.0",
            "class_uid": 4002,
            "severity_id": 5,
            "src_ip": "198.51.100.42",
            "product_name": "synthetic-linux",
            "raw_event_json": "{}",
        },
        {
            "event_id": "evt-low",
            "source": "synthetic-linux",
            "event_time": now - timedelta(hours=1),
            "ingested_at": now,
            "schema_name": "ocsf",
            "schema_version": "1.3.0",
            "class_uid": 4002,
            "severity_id": 1,
            "src_ip": "203.0.113.10",
            "product_name": "synthetic-linux",
            "raw_event_json": "{}",
        },
    ]


def test_investigation_filters_ip_and_severity(monkeypatch) -> None:
    body = parquet_bytes(rows())
    monkeypatch.setattr(
        "app.investigation.list_object_keys",
        lambda prefix: [f"{prefix}batch=test.parquet"],
    )
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)

    result = investigate(
        InvestigationRequest(src_ip="198.51.100.42", source="synthetic-linux", min_severity=4)
    )
    assert result.query_engine == "duckdb"
    assert result.scanned_objects == 1
    assert result.returned_count == 1
    assert result.events[0]["event_id"] == "evt-high"


def test_investigation_filters_time_range(monkeypatch) -> None:
    body = parquet_bytes(rows())
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["one.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)
    result = investigate(
        InvestigationRequest(start_time=datetime(2026, 11, 16, 11, 30, tzinfo=UTC))
    )
    assert [event["event_id"] for event in result.events] == ["evt-high"]


def test_empty_lake_returns_empty_result(monkeypatch) -> None:
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: [])
    result = investigate(InvestigationRequest(src_ip="192.0.2.1"))
    assert result.scanned_objects == 0
    assert result.returned_count == 0
    assert result.events == []


def test_result_limit_is_enforced(monkeypatch) -> None:
    body = parquet_bytes(rows())
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["one.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)
    result = investigate(InvestigationRequest(limit=1))
    assert result.returned_count == 1
    assert result.total_count == 2
    assert result.events[0]["event_id"] == "evt-high"


def test_result_offset_pages_through_matches(monkeypatch) -> None:
    body = parquet_bytes(rows())
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["one.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)
    result = investigate(InvestigationRequest(limit=1, offset=1))
    assert result.total_count == 2
    assert result.offset == 1
    assert result.events[0]["event_id"] == "evt-low"
