#!/usr/bin/env python3
import json

from app.database import Alert, SessionLocal
from app.storage import get_object_bytes
from sqlalchemy import select


def main() -> None:
    with SessionLocal() as db:
        alert = db.scalar(select(Alert).order_by(Alert.created_at.desc()).limit(1))
    if alert is None:
        raise SystemExit("No alerts found")

    evidence = json.loads(get_object_bytes(alert.evidence_object_key))
    assert evidence["alert_id"] == alert.alert_id
    assert evidence["rule"]["id"] == alert.rule_id
    assert evidence["event_count"] == alert.event_count
    assert len(evidence["events"]) == alert.event_count
    print(f"ALERT_ID={alert.alert_id}")
    print(f"RULE_ID={alert.rule_id}")
    print(f"EVENT_COUNT={alert.event_count}")
    print(f"EVIDENCE_OBJECT={alert.evidence_object_key}")
    print("EVIDENCE_VERIFIED=true")


if __name__ == "__main__":
    main()
