from types import SimpleNamespace

from app.database import Alert, Base, NotificationDelivery
from app.notifications import notify_new_alert
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def alert() -> Alert:
    return Alert(
        alert_id="alert-1",
        fingerprint="f" * 64,
        rule_id="test-rule",
        title="Test alert",
        severity="high",
        status="open",
        event_count=1,
        evidence_object_key="artifacts/test.json",
    )


def test_webhook_failure_is_recorded_without_interrupting_detection(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        "app.notifications.get_settings",
        lambda: SimpleNamespace(
            alert_webhook_url="https://alerts.example.test/osl",
            alert_webhook_timeout_seconds=1,
        ),
    )
    monkeypatch.setattr(
        "app.notifications.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    with Session(engine) as db:
        item = alert()
        db.add(item)
        db.commit()
        notify_new_alert(item, db)
        delivery = db.scalar(select(NotificationDelivery))

    assert delivery is not None
    assert delivery.status == "failed"
    assert delivery.error_message == "TimeoutError"
