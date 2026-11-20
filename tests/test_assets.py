from datetime import UTC, datetime

import pytest
from app.assets import correlate_asset, get_asset, list_assets, record_assets, update_asset
from app.database import Base
from app.main import app, patch_asset, read_asset, read_assets
from app.schemas import AssetUpdateRequest
from app.security import Principal
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request


def normalized(hostname: str = "homelab", source_ip: str | None = "192.168.3.120") -> dict:
    return {
        "event_id": "evt-1",
        "event_time": datetime.now(UTC),
        "hostname": hostname,
        "src_ip": source_ip,
    }


def test_observed_assets_are_deduplicated_and_enriched() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        record_assets("linux-syslog", [normalized(), normalized(source_ip="192.168.3.121")], db)
        record_assets("docker-events", [normalized()], db)
        db.commit()
        assets = list_assets(db)
        assert len(assets) == 1
        assert assets[0].hostname == "homelab"
        assert assets[0].event_count == 3
        assert assets[0].ip_addresses == ["192.168.3.120", "192.168.3.121"]
        assert assets[0].sources == ["docker-events", "linux-syslog"]
        assert assets[0].aliases == []
        assert assets[0].owner is None
        assert get_asset(assets[0].asset_id, db) == assets[0]
        updated = update_asset(
            assets[0].asset_id,
            AssetUpdateRequest(
                criticality="critical", owner="SOC", aliases=["HOME-LAB", "home-lab"]
            ),
            db,
        )
        assert updated is not None
        assert updated.criticality == "critical"
        assert updated.owner == "SOC"
        assert updated.aliases == ["home-lab"]
        assert correlate_asset([normalized()], db).asset_id == assets[0].asset_id


def test_ip_only_asset_is_supported_without_trusting_event_body_storage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        record_assets("firewall", [normalized(hostname="", source_ip="192.0.2.10")], db)
        db.commit()
        asset = list_assets(db)[0]
        assert asset.hostname is None
        assert asset.primary_ip == "192.0.2.10"
        assert asset.display_name == "192.0.2.10"


def test_asset_public_endpoints_and_not_found() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/v1/assets" in paths
    assert "/api/v1/assets/{asset_id}" in paths
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        record_assets("linux-syslog", [normalized()], db)
        db.commit()
        result = read_assets(None, db)  # type: ignore[arg-type]
        assert read_asset(result[0].asset_id, None, db) == result[0]  # type: ignore[arg-type]
        changed = patch_asset(
            result[0].asset_id,
            AssetUpdateRequest(criticality="high", owner="Infrastructure"),
            None,  # type: ignore[arg-type]
            db,
        )
        assert changed.criticality == "high"
        with pytest.raises(HTTPException) as missing:
            read_asset("missing", None, db)  # type: ignore[arg-type]
        assert missing.value.status_code == 404


def test_asset_endpoint_role_contracts(monkeypatch) -> None:
    monkeypatch.setattr("app.security._record_access", lambda *_args, **_kwargs: None)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/assets")
    ]
    viewer = Principal("viewer", "viewer", None, None, frozenset({"viewer"}), "test")
    ingestor = Principal("ingestor", "ingestor", None, None, frozenset({"ingestor"}), "test")
    for route in routes:
        dependency = route.dependant.dependencies[0].call
        if "PATCH" in route.methods:
            admin = Principal("admin", "admin", None, None, frozenset({"admin"}), "test")
            assert dependency(request, admin) == admin
            allowed = admin
        else:
            assert dependency(request, viewer) == viewer
            allowed = viewer
        with pytest.raises(HTTPException) as denied:
            dependency(request, ingestor)
        assert denied.value.status_code == 403
        assert allowed is not ingestor


def test_asset_endpoint_reports_dependency_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.list_assets", lambda _db: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    with pytest.raises(RuntimeError, match="db down"):
        read_assets(None, None)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "app.main.get_asset", lambda *_args: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    with pytest.raises(RuntimeError, match="db down"):
        read_asset("asset", None, None)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "app.main.update_asset",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    with pytest.raises(RuntimeError, match="db down"):
        patch_asset(
            "asset", AssetUpdateRequest(criticality="high"), None, None
        )  # type: ignore[arg-type]
