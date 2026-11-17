import io
import json
from datetime import UTC, datetime, timedelta

import pyarrow.parquet as pq
from app.database import Base, SourceCatalog, get_db
from app.ingestion import docker_events_to_request, ingest_batch
from app.main import app
from app.schemas import SourceRegistration
from app.security import Principal, get_current_principal
from app.sources import list_sources, register_source, source_response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


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


def test_source_endpoints_require_roles_and_database(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ensure_bucket", lambda: None)
    monkeypatch.setattr("app.ingestion.put_object", lambda *_: None)
    monkeypatch.setattr("app.security._record_access", lambda *_args, **_kwargs: None)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = session
    body = {
        "source_id": "router", "source": "router-syslog", "kind": "router",
        "display_name": "Router", "expected_interval_minutes": 60,
    }
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/sources").status_code == 401
            assert client.post("/api/v1/sources", json=body).status_code == 401
    finally:
        app.dependency_overrides.clear()


    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        "ingestor", "collector", None, None, frozenset({"ingestor"}), "collector_token"
    )
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/sources").status_code == 403
            assert client.post("/api/v1/sources", json=body).status_code == 403
            assert client.post("/api/v1/ingestion/docker", json=event()).status_code == 200
            invalid = client.post("/api/v1/ingestion/docker", json={"Type": "image"})
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()


    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        "admin", "admin", None, None, frozenset({"admin"}), "oidc"
    )
    try:
        with TestClient(app) as client:
            assert client.post("/api/v1/sources", json=body).status_code == 200
            assert client.get("/api/v1/sources").json()[0]["source_id"] == "docker-events"
            conflict = client.post("/api/v1/sources", json={**body, "source": "other"})
            assert conflict.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_source_endpoint_reports_dependency_failure(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ensure_bucket", lambda: None)
    monkeypatch.setattr(
        "app.main.list_sources", lambda _db: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        "viewer", "viewer", None, None, frozenset({"viewer"}), "oidc"
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/v1/sources").status_code == 500
    finally:
        app.dependency_overrides.clear()
