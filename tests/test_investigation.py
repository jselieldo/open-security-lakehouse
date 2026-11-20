import io
import json
from datetime import UTC, datetime, timedelta

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from app.investigation import investigate
from app.schemas import InvestigationRequest
from pydantic import ValidationError


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


def test_bounded_investigation_uses_catalog_without_s3_listing(monkeypatch) -> None:
    key = "normalized/source=synthetic-linux/year=2026/month=11/day=20/batch=one.parquet"
    monkeypatch.setattr("app.investigation.catalog_keys", lambda *_args: [key])
    monkeypatch.setattr(
        "app.investigation.list_object_keys",
        lambda *_args: (_ for _ in ()).throw(AssertionError("S3 listing used")),
    )
    monkeypatch.setattr(
        "app.investigation.get_object_bytes", lambda _key: parquet_bytes(rows())
    )
    result = investigate(
        InvestigationRequest(
            source="synthetic-linux",
            start_time=datetime(2026, 11, 16, 11, 30, tzinfo=UTC),
        )
    )
    assert result.scanned_objects == 1
    assert result.total_count == 1


def test_event_time_index_skips_unrelated_objects_even_when_ingested_later(monkeypatch) -> None:
    old = "normalized/source=linux/year=2026/month=11/day=18/batch=old.parquet"
    late = "normalized/source=linux/year=2026/month=11/day=18/batch=late.parquet"
    objects = {
        old: parquet_bytes([rows()[1]]),
        late: parquet_bytes([rows()[0]]),
        f"{old}.index.json": json.dumps({
            "version": 1, "min_event_time": "2026-11-16T11:00:00+00:00",
            "max_event_time": "2026-11-16T11:00:00+00:00",
        }).encode(),
        f"{late}.index.json": json.dumps({
            "version": 1, "min_event_time": "2026-11-16T12:00:00+00:00",
            "max_event_time": "2026-11-16T12:00:00+00:00",
        }).encode(),
    }
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: list(objects))
    reads = []

    def read(key):
        reads.append(key)
        return objects[key]

    monkeypatch.setattr("app.investigation.get_object_bytes", read)
    result = investigate(
        InvestigationRequest(start_time=datetime(2026, 11, 16, 11, 30, tzinfo=UTC))
    )
    assert result.scanned_objects == 1
    assert result.total_count == 1
    assert old not in reads
    assert late in reads


def test_missing_or_malformed_index_keeps_parquet_in_search(monkeypatch) -> None:
    key = "normalized/source=linux/year=2026/month=11/day=18/batch=legacy.parquet"
    objects = {
        key: parquet_bytes(rows()),
        f"{key}.index.json": b'{"version":1,"min_event_time":"bad"}',
    }
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: list(objects))
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda candidate: objects[candidate])
    result = investigate(
        InvestigationRequest(start_time=datetime(2026, 11, 16, 11, 30, tzinfo=UTC))
    )
    assert result.scanned_objects == 1
    assert result.total_count == 1


def test_compaction_bounds_skip_compact_but_include_new_batch(monkeypatch) -> None:
    partition = "normalized/source=synthetic-linux/year=2026/month=11/day=18"
    compact = f"{partition}/compact=abc-0000.parquet"
    original = f"{partition}/batch=original.parquet"
    new = f"{partition}/batch=new.parquet"
    manifest = f"{partition}/_compaction.json"
    objects = {
        compact: parquet_bytes([rows()[1]]),
        original: parquet_bytes([rows()[1]]),
        new: parquet_bytes([rows()[0]]),
        manifest: json.dumps({
            "source_objects": [original], "compact_objects": [compact],
            "compact_event_time_bounds": {
                "min_event_time": "2026-11-16T11:00:00+00:00",
                "max_event_time": "2026-11-16T11:00:00+00:00",
            },
        }).encode(),
    }
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: list(objects))
    reads = []

    def read(key):
        reads.append(key)
        return objects[key]

    monkeypatch.setattr("app.investigation.get_object_bytes", read)
    result = investigate(
        InvestigationRequest(start_time=datetime(2026, 11, 16, 11, 30, tzinfo=UTC))
    )
    assert result.total_count == 1
    assert result.scanned_objects == 1
    assert compact not in reads
    assert new in reads


def test_legacy_compact_object_uses_backfilled_sidecar(monkeypatch) -> None:
    partition = "normalized/source=linux/year=2026/month=11/day=18"
    compact = f"{partition}/compact=legacy-0000.parquet"
    original = f"{partition}/batch=original.parquet"
    manifest = f"{partition}/_compaction.json"
    sidecar = f"{compact}.index.json"
    objects = {
        compact: parquet_bytes([rows()[1]]),
        original: parquet_bytes([rows()[1]]),
        manifest: json.dumps({
            "source_objects": [original], "compact_objects": [compact]
        }).encode(),
        sidecar: json.dumps({
            "version": 1,
            "min_event_time": "2026-11-16T11:00:00+00:00",
            "max_event_time": "2026-11-16T11:00:00+00:00",
        }).encode(),
    }
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: list(objects))
    reads = []

    def read(key):
        reads.append(key)
        return objects[key]

    monkeypatch.setattr("app.investigation.get_object_bytes", read)
    result = investigate(
        InvestigationRequest(start_time=datetime(2026, 11, 16, 11, 30, tzinfo=UTC))
    )
    assert result.scanned_objects == 0
    assert compact not in reads


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


def test_new_filters_on_old_parquet_remain_compatible(monkeypatch) -> None:
    body = parquet_bytes(rows())
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["old.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)
    assert investigate(InvestigationRequest(hostname="homelab")).total_count == 0
    assert investigate(InvestigationRequest()).total_count == 2


def test_host_application_and_type_filters(monkeypatch) -> None:
    records = rows()[:1]
    records[0].update(
        hostname="homelab", application="docker", event_type="container.die"
    )
    body = parquet_bytes(records)
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["new.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)
    result = investigate(
        InvestigationRequest(
            hostname="homelab", application="docker", event_type="container.die"
        )
    )
    assert result.total_count == 1
    assert investigate(InvestigationRequest(hostname="other")).total_count == 0


def test_investigation_filters_multiple_event_types(monkeypatch) -> None:
    records = rows()
    records[0]["event_type"] = "windows.security.4720"
    records[1]["event_type"] = "windows.security.4624"
    body = parquet_bytes(records)
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["one.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)
    result = investigate(
        InvestigationRequest(
            event_types=["windows.security.4720", "windows.security.4732"]
        )
    )
    assert result.total_count == 1
    assert result.events[0]["event_type"] == "windows.security.4720"


def test_event_types_are_deduplicated_and_bounded() -> None:
    request = InvestigationRequest(event_types=["windows.security.4625"] * 2)
    assert request.event_types == ["windows.security.4625"]


def test_investigation_filters_windows_channel_and_event_id(monkeypatch) -> None:
    records = rows()
    records[0]["event_type"] = "windows.security.4625"
    records[1]["event_type"] = "windows.system.7045"
    body = parquet_bytes(records)
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["one.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)

    by_channel = investigate(InvestigationRequest(windows_channel="Security"))
    assert [event["event_id"] for event in by_channel.events] == ["evt-high"]
    by_id = investigate(InvestigationRequest(windows_event_id=7045))
    assert [event["event_id"] for event in by_id.events] == ["evt-low"]
    exact = investigate(
        InvestigationRequest(windows_channel="System", windows_event_id=7045)
    )
    assert exact.total_count == 1


def test_windows_channel_is_normalized_and_rejects_wildcards() -> None:
    request = InvestigationRequest(
        windows_channel="Microsoft-Windows-PowerShell/Operational"
    )
    assert request.windows_channel == "microsoft-windows-powershell/operational"

    with pytest.raises(ValidationError):
        InvestigationRequest(windows_channel="Security%")


def test_investigation_filters_message_content(monkeypatch) -> None:
    data = rows()
    data[0]["raw_event_json"] = '{"message":"Failed password for root"}'
    body = parquet_bytes(data)
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["one.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)
    result = investigate(InvestigationRequest(message_contains="Failed password"))
    assert result.total_count == 1
    assert result.events[0]["event_id"] == "evt-high"


def test_investigation_filters_any_message_pattern(monkeypatch) -> None:
    data = rows()
    data[0]["raw_event_json"] = '{"message":"Unhandled exception in worker"}'
    data[1]["raw_event_json"] = '{"message":"service healthy"}'
    body = parquet_bytes(data)
    monkeypatch.setattr("app.investigation.list_object_keys", lambda _prefix: ["one.parquet"])
    monkeypatch.setattr("app.investigation.get_object_bytes", lambda _key: body)

    result = investigate(
        InvestigationRequest(message_contains_any=["traceback", "unhandled exception"])
    )

    assert [event["event_id"] for event in result.events] == ["evt-high"]


def test_message_patterns_are_deduplicated_and_bounded() -> None:
    request = InvestigationRequest(message_contains_any=[" panic ", "panic"])
    assert request.message_contains_any == ["panic"]

    with pytest.raises(ValidationError):
        InvestigationRequest(message_contains_any=["x" * 201])
