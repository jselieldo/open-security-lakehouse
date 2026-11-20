import json
from datetime import UTC, datetime

import pytest
from app.asset_monitor import process_asset_changes
from app.assets import record_assets
from app.database import Alert, AssetChange, Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def event(hostname: str = "new-host", source_ip: str = "192.0.2.10") -> dict:
    return {
        "event_id": "evt",
        "event_time": datetime.now(UTC),
        "hostname": hostname,
        "src_ip": source_ip,
    }


def test_new_asset_and_context_changes_create_enriched_alerts(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    objects = {}
    monkeypatch.setattr(
        "app.asset_monitor.put_object",
        lambda key, body, content_type: objects.update({key: (body, content_type)}),
    )
    monkeypatch.setattr("app.asset_monitor.notify_new_alert", lambda *_args: None)
    with Session(engine, expire_on_commit=False) as db:
        record_assets("linux-syslog", [event()], db)
        db.commit()
        first = process_asset_changes(db)
        record_assets("docker-events", [event(source_ip="192.0.2.11")], db)
        db.commit()
        second = process_asset_changes(db)
        alerts = db.scalars(select(Alert).order_by(Alert.created_at)).all()

    assert first == {"examined": 1, "alerts_created": 1}
    assert second == {"examined": 2, "alerts_created": 2}
    assert [item.rule_id for item in alerts] == [
        "asset-new",
        "asset-context-change",
        "asset-context-change",
    ]
    assert all(item.asset_display_name == "new-host" for item in alerts)
    evidence = json.loads(objects[alerts[1].evidence_object_key][0])
    assert evidence["change_type"] in {"new_ip", "new_source"}


def test_test_source_does_not_queue_asset_alert() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        record_assets("test-syslog", [event()], db)
        db.commit()
        assert db.scalars(select(AssetChange)).all() == []


def test_storage_failure_keeps_change_pending(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        record_assets("linux-syslog", [event()], db)
        db.commit()
        monkeypatch.setattr(
            "app.asset_monitor.put_object",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
        )
        with pytest.raises(RuntimeError, match="storage unavailable"):
            process_asset_changes(db)
        db.rollback()
        assert db.scalar(select(AssetChange)).alert_id is None
