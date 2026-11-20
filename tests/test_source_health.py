from datetime import UTC, datetime, timedelta

import pytest
from app.database import Alert, AlertHistory, Base, SourceCatalog
from app.source_health import check_source_health
from app.sources import list_sources
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def source(now: datetime) -> SourceCatalog:
    return SourceCatalog(
        source_id="windows-workstation",
        source="windows-eventlog",
        kind="windows",
        hostname="NOTE-SAM",
        display_name="Windows workstation",
        expected_interval_minutes=60,
        configured=True,
        enabled=True,
        created_at=now - timedelta(hours=2),
    )


def test_silent_source_alert_is_deduplicated_and_auto_resolved(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    objects: dict[str, bytes] = {}
    notifications: list[str] = []
    monkeypatch.setattr(
        "app.source_health.put_object",
        lambda key, body, _content_type: objects.__setitem__(key, body),
    )
    monkeypatch.setattr(
        "app.source_health.notify_new_alert",
        lambda alert, _db: notifications.append(alert.alert_id),
    )
    now = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as db:
        item = source(now)
        db.add(item)
        db.commit()

        first = check_source_health(db, now)
        second = check_source_health(db, now + timedelta(minutes=1))
        alert = db.scalar(select(Alert).where(Alert.rule_id == "source-silence"))
        assert first == {"checked": 1, "created": 1, "resolved": 0}
        assert second == {"checked": 1, "created": 0, "resolved": 0}
        assert alert is not None
        assert alert.source_id == item.source_id
        assert alert.event_count == 0
        assert len(objects) == 1
        assert notifications == [alert.alert_id]
        catalog = list_sources(db)
        assert catalog[0].active_silence_alert_id == alert.alert_id
        assert catalog[0].seconds_until_silent is not None
        assert catalog[0].seconds_until_silent < 0

        item.last_received_at = now + timedelta(minutes=2)
        db.commit()
        recovered = check_source_health(db, now + timedelta(minutes=3))
        db.refresh(alert)
        assert recovered == {"checked": 1, "created": 0, "resolved": 1}
        assert alert.status == "resolved"
        history = db.scalar(select(AlertHistory).where(AlertHistory.alert_id == alert.alert_id))
        assert history is not None
        assert history.actor_subject == "system:source-health"


def test_silence_alert_waits_for_expected_interval_and_ignores_disabled(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.source_health.put_object", lambda *_args: None)
    monkeypatch.setattr("app.source_health.notify_new_alert", lambda *_args: None)
    now = datetime.now(UTC)
    with Session(engine) as db:
        waiting = source(now)
        waiting.created_at = now - timedelta(minutes=30)
        disabled = source(now)
        disabled.source_id = "disabled-linux"
        disabled.source = "linux-syslog"
        disabled.enabled = False
        db.add_all([waiting, disabled])
        db.commit()
        result = check_source_health(db, now)
        assert result == {"checked": 2, "created": 0, "resolved": 0}
        assert db.scalar(select(Alert)) is None


def test_source_health_storage_failure_does_not_create_metadata_alert(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        "app.source_health.put_object",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.add(source(now))
        db.commit()
        with pytest.raises(RuntimeError, match="storage unavailable"):
            check_source_health(db, now)
        assert db.scalar(select(Alert)) is None
