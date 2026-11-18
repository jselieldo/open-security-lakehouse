import io
import json
from datetime import UTC, datetime, timedelta

import pyarrow.parquet as pq
import pytest
from app.database import Base, SourceCatalog
from app.ingestion import docker_events_to_request, docker_logs_to_request, ingest_batch
from app.main import app, process_docker_log_batch, read_sources, upsert_source
from app.schemas import SourceRegistration
from app.security import Principal
from app.sources import list_sources, register_source, source_response
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request


def event() -> dict:
    return {
        "Type": "container",
        "Action": "die",
        "Actor": {"ID": "abc123", "Attributes": {"name": "app"}},
        "timeNano": 1794823200000000000,
        "osl_hostname": "homelab",
    }


def test_docker_adapter_is_deterministic_and_preserves_raw() -> None:
    body = json.dumps(event()).encode()
    first = docker_events_to_request(body)
    assert first == docker_events_to_request(body)
    assert first.source == "docker-events"
    assert first.events[0]["event_type"] == "container.die"
    assert first.events[0]["docker"] == event()
    assert first.events[0]["severity_id"] == 4
    fixture = {**event(), "osl_test": True}
    assert docker_events_to_request(json.dumps(fixture).encode()).source == "test-docker"
    labeled = event()
    labeled["Actor"]["Attributes"]["osl.test"] = "true"
    assert docker_events_to_request(json.dumps(labeled).encode()).source == "test-docker"
    clean_exit = event()
    clean_exit["Actor"]["Attributes"]["exitCode"] = "0"
    assert docker_events_to_request(json.dumps(clean_exit).encode()).events[0]["severity_id"] == 2


def test_docker_adapter_rejects_wrong_type_and_missing_timestamp() -> None:
    for payload in (
        {**event(), "Type": "image"},
        {**event(), "timeNano": None},
        {**event(), "Action": "unknown"},
    ):
        try:
            docker_events_to_request(json.dumps(payload).encode())
        except ValueError:
            continue
        raise AssertionError("invalid Docker event was accepted")


def docker_log(stream: str = "stdout") -> dict:
    return {
        "timestamp": "2026-11-18T04:45:00.123456789Z",
        "stream": stream,
        "message": "application started",
        "container_id": "a" * 64,
        "container_name": "example-api",
        "image": "example/api:1.0",
        "osl_hostname": "homelab",
    }


def test_docker_log_adapter_batches_and_preserves_application_context() -> None:
    payload = [docker_log(), docker_log("stderr") | {"message": "connection failed"}]
    first = docker_logs_to_request(json.dumps(payload).encode())
    assert first == docker_logs_to_request(json.dumps(payload).encode())
    assert first.source == "docker-logs"
    assert len(first.events) == 2
    assert first.events[0]["application"] == "example-api"
    assert first.events[0]["event_type"] == "container.log.stdout"
    assert first.events[1]["event_type"] == "container.log.stderr"
    assert first.events[1]["severity_id"] == 3
    assert first.events[0]["docker_log"] == payload[0]
    test_payload = [docker_log() | {"osl_test": True}]
    assert docker_logs_to_request(json.dumps(test_payload).encode()).source == "test-docker-logs"


def test_docker_log_adapter_rejects_mixed_test_batch() -> None:
    payload = [docker_log(), docker_log() | {"osl_test": True}]
    with pytest.raises(ValueError, match="cannot mix"):
        docker_logs_to_request(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "change",
    [
        {"stream": "unknown"},
        {"timestamp": "2026-11-18T04:45:00"},
        {"message": ""},
        {"container_id": "not-an-id"},
        {"container_name": ""},
    ],
)
def test_docker_log_adapter_rejects_invalid_records(change) -> None:
    with pytest.raises((ValueError, OverflowError)):
        docker_logs_to_request(json.dumps([docker_log() | change]).encode())


def test_registered_source_tracks_ingestion_and_silence(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    objects = {}
    monkeypatch.setattr(
        "app.ingestion.put_object",
        lambda key, data, _content_type: objects.update({key: data}),
    )
    with Session(engine, expire_on_commit=False) as db:
        register_source(
            SourceRegistration(
                source_id="docker-homelab", source="docker-events", kind="docker",
                hostname="homelab", display_name="Docker homelab",
                expected_interval_minutes=30,
            ),
            db,
        )
        payload = docker_events_to_request(json.dumps(event()).encode())
        response = ingest_batch(payload, db)
        assert ingest_batch(payload, db).idempotent_replay
        source = list_sources(db)[0]
        assert source.source_id == "docker-homelab"
        assert source.accepted_events == 1
        assert source.status == "active"
        assert source_response(
            db.get(SourceCatalog, "docker-homelab"),
            datetime.now(UTC) + timedelta(minutes=31),
        ).status == "silent"
        assert pq.read_table(io.BytesIO(objects[response.normalized_object_key])).column(
            "hostname"
        )[0].as_py() == "homelab"


def test_source_public_endpoints_and_conflict() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/v1/sources" in paths
    assert "/api/v1/ingestion/docker" in paths
    assert "/api/v1/ingestion/docker-logs" in paths
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    payload = SourceRegistration(
        source_id="router",
        source="router-syslog",
        kind="router",
        display_name="Router",
        expected_interval_minutes=60,
    )
    with Session(engine) as db:
        created = upsert_source(payload, None, db)  # type: ignore[arg-type]
        assert created.source_id == "router"
        assert read_sources(None, db)[0].source_id == "router"  # type: ignore[arg-type]
        try:
            upsert_source(
                payload.model_copy(update={"source": "other"}),
                None,  # type: ignore[arg-type]
                db,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("source identity conflict was accepted")


def test_windows_source_kind_is_supported() -> None:
    source = SourceRegistration(
        source_id="windows-workstation",
        source="windows-eventlog",
        kind="windows",
        hostname="DESKTOP-OSL",
        display_name="Windows workstation",
    )
    assert source.kind == "windows"


def test_source_endpoint_role_contracts(monkeypatch) -> None:
    monkeypatch.setattr("app.security._record_access", lambda *_args, **_kwargs: None)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    source_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/sources" and "GET" in route.methods
    )
    docker_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/ingestion/docker"
    )
    docker_log_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/ingestion/docker-logs"
    )
    source_dependency = source_route.dependant.dependencies[0].call
    docker_dependency = docker_route.dependant.dependencies[0].call
    docker_log_dependency = docker_log_route.dependant.dependencies[0].call
    viewer = Principal("viewer", "viewer", None, None, frozenset({"viewer"}), "test")
    ingestor = Principal("ingestor", "ingestor", None, None, frozenset({"ingestor"}), "test")
    assert source_dependency(request, viewer) == viewer
    assert docker_dependency(request, ingestor) == ingestor
    assert docker_log_dependency(request, ingestor) == ingestor
    try:
        source_dependency(request, ingestor)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("ingestor could read the source catalog")


def test_source_endpoint_reports_dependency_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.list_sources", lambda _db: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    try:
        read_sources(None, None)  # type: ignore[arg-type]
    except RuntimeError as exc:
        assert str(exc) == "db down"
    else:
        raise AssertionError("database failure was hidden")


def test_docker_log_endpoint_reports_dependency_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.ingest_batch", lambda *_args: (_ for _ in ()).throw(RuntimeError("db down"))
    )

    with pytest.raises(RuntimeError, match="db down"):
        process_docker_log_batch(json.dumps([docker_log()]).encode(), None)  # type: ignore[arg-type]
