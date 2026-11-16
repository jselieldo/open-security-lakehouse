import io
import json
from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest
from app.database import Base, IngestionBatch
from app.ingestion import (
    BatchConflictError,
    _parquet_bytes,
    get_batch_status,
    ingest_batch,
    vector_events_to_request,
)
from app.normalization import normalize_events
from app.schemas import IngestionRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def valid_event(event_id: str = "evt-1") -> dict:
    return {
        "event_id": event_id,
        "event_time": "2026-11-15T12:00:00Z",
        "severity_id": 3,
        "class_uid": 4002,
        "src_endpoint": {"ip": "198.51.100.42"},
    }


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def test_normalization_splits_valid_and_invalid_events() -> None:
    normalized, rejected = normalize_events(
        "synthetic-linux",
        [valid_event(), {"event_id": "bad", "severity_id": 99}],
        datetime.now(UTC),
    )
    assert len(normalized) == 1
    assert normalized[0]["schema_name"] == "ocsf"
    assert normalized[0]["src_ip"] == "198.51.100.42"
    assert len(rejected) == 1
    assert rejected[0]["index"] == 1


def test_parquet_output_is_readable() -> None:
    normalized, _ = normalize_events("linux", [valid_event()], datetime.now(UTC))
    table = pq.read_table(io.BytesIO(_parquet_bytes(normalized)))
    assert table.num_rows == 1
    assert table.column("event_id")[0].as_py() == "evt-1"


def test_ingestion_writes_raw_normalized_and_quarantine(db: Session, monkeypatch) -> None:
    objects: dict[str, tuple[bytes, str]] = {}

    def fake_put(key: str, body: bytes, content_type: str) -> None:
        objects[key] = (body, content_type)

    monkeypatch.setattr("app.ingestion.put_object", fake_put)
    request = IngestionRequest(
        batch_id="batch-001",
        source="synthetic-linux",
        events=[valid_event(), {"event_id": "bad", "severity_id": 99}],
    )
    response = ingest_batch(request, db)

    assert response.status == "completed"
    assert response.accepted_count == 1
    assert response.rejected_count == 1
    assert response.raw_object_key in objects
    assert response.normalized_object_key in objects
    assert response.quarantine_object_key in objects
    raw = json.loads(objects[response.raw_object_key][0])
    assert len(raw["events"]) == 2
    assert objects[response.normalized_object_key][1] == "application/vnd.apache.parquet"


def test_idempotent_replay_does_not_write_again(db: Session, monkeypatch) -> None:
    writes = 0

    def fake_put(*_args) -> None:
        nonlocal writes
        writes += 1

    monkeypatch.setattr("app.ingestion.put_object", fake_put)
    request = IngestionRequest(batch_id="batch-replay", source="linux", events=[valid_event()])
    first = ingest_batch(request, db)
    first_writes = writes
    second = ingest_batch(request, db)

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert writes == first_writes


def test_batch_id_cannot_be_reused_with_different_content(db: Session, monkeypatch) -> None:
    monkeypatch.setattr("app.ingestion.put_object", lambda *_args: None)
    ingest_batch(IngestionRequest(batch_id="shared-id", source="linux", events=[valid_event()]), db)
    with pytest.raises(BatchConflictError):
        ingest_batch(
            IngestionRequest(
                batch_id="shared-id", source="linux", events=[valid_event("different")]
            ),
            db,
        )


def test_all_invalid_events_are_quarantined(db: Session, monkeypatch) -> None:
    monkeypatch.setattr("app.ingestion.put_object", lambda *_args: None)
    response = ingest_batch(
        IngestionRequest(
            batch_id="invalid-only",
            source="linux",
            events=[{"event_id": "bad", "severity_id": 99}],
        ),
        db,
    )
    assert response.status == "quarantined"
    assert response.accepted_count == 0
    assert response.rejected_count == 1
    assert response.normalized_object_key is None


def test_batch_status_is_persisted(db: Session) -> None:
    db.add(
        IngestionBatch(
            batch_id="known",
            source="linux",
            payload_hash="0" * 64,
            status="completed",
            received_count=1,
            accepted_count=1,
            rejected_count=0,
        )
    )
    db.commit()
    status = get_batch_status("known", db)
    assert status is not None
    assert status.batch_id == "known"
    assert get_batch_status("missing", db) is None


def test_vector_ndjson_is_converted_to_idempotent_linux_batch() -> None:
    body = (
        b'{"message":"sshd login failed","severity":"err",'
        b'"timestamp":"2026-11-15T12:00:00Z","source_ip":"192.0.2.10"}\n'
        b'{"message":"session opened","severity":"info",'
        b'"timestamp":"2026-11-15T12:00:01Z"}\n'
    )
    first = vector_events_to_request(body)
    second = vector_events_to_request(body)
    assert first.batch_id == second.batch_id
    assert first.source == "linux-syslog"
    assert first.events[0]["severity_id"] == 4
    assert first.events[0]["src_endpoint"] == {"ip": "192.0.2.10"}
    assert first.events[1]["severity_id"] == 1


def test_vector_payload_rejects_empty_or_non_object_content() -> None:
    with pytest.raises(ValueError):
        vector_events_to_request(b"")
    with pytest.raises(ValueError):
        vector_events_to_request(b"[1, 2]")


def test_vector_test_events_use_isolated_source() -> None:
    request = vector_events_to_request(
        b'{"message":"smoke","appname":"osl-smoke","osl_source":"test-syslog"}'
    )
    assert request.source == "test-syslog"


def test_vector_rejects_mixed_source_batch() -> None:
    with pytest.raises(ValueError, match="single OSL source"):
        vector_events_to_request(
            b'{"message":"live","osl_source":"linux-syslog"}\n'
            b'{"message":"test","osl_source":"test-syslog"}\n'
        )
