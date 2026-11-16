from app.database import Alert, Base
from app.schemas import AlertUpdateRequest
from app.security import Principal
from app.triage import InvalidAlertTransitionError, add_comment, get_alert_detail, update_alert
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def principal() -> Principal:
    return Principal(
        subject="analyst-1",
        username="analyst",
        email=None,
        display_name="Analyst",
        roles=frozenset({"analyst"}),
        auth_method="test",
    )


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


def test_alert_triage_tracks_assignment_status_comment_and_history() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(alert())
        db.commit()
        updated = update_alert(
            "alert-1",
            AlertUpdateRequest(status="investigating", assign_to_me=True),
            principal(),
            db,
        )
        comment = add_comment("alert-1", "Reviewing authentication evidence.", principal(), db)
        detail = get_alert_detail("alert-1", db)

    assert updated is not None
    assert updated.status == "investigating"
    assert updated.assignee_username == "analyst"
    assert comment is not None
    assert detail is not None
    assert len(detail.comments) == 1
    assert {item.action for item in detail.history} == {
        "status_changed",
        "assignee_changed",
        "comment_added",
    }


def test_alert_triage_rejects_invalid_transition() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = alert()
        item.status = "resolved"
        db.add(item)
        db.commit()
        try:
            update_alert(
                "alert-1", AlertUpdateRequest(status="investigating"), principal(), db
            )
        except InvalidAlertTransitionError:
            pass
        else:
            raise AssertionError("invalid transition was accepted")
