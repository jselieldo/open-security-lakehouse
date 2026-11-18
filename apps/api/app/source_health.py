import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Alert, AlertHistory, SourceCatalog
from .metrics import SOURCE_SILENT
from .notifications import notify_new_alert
from .storage import put_object

ACTIVE_ALERT_STATUSES = {"open", "investigating", "reopened"}


def check_source_health(db: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    created = 0
    resolved = 0
    checked = 0
    sources = db.scalars(
        select(SourceCatalog).where(SourceCatalog.configured.is_(True))
    ).all()
    for source in sources:
        checked += 1
        reference = source.last_received_at or source.created_at
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        silent = source.enabled and now - reference > timedelta(
            minutes=source.expected_interval_minutes
        )
        SOURCE_SILENT.labels(source_id=source.source_id, source=source.source).set(
            1 if silent else 0
        )
        if silent:
            if _create_silence_alert(source, reference, now, db):
                created += 1
        else:
            resolved += _resolve_silence_alerts(source.source_id, now, db)
    db.commit()
    return {"checked": checked, "created": created, "resolved": resolved}


def _create_silence_alert(
    source: SourceCatalog, reference: datetime, now: datetime, db: Session
) -> bool:
    fingerprint = sha256(
        f"source-silence:{source.source_id}:{reference.isoformat()}".encode()
    ).hexdigest()
    if db.scalar(select(Alert).where(Alert.fingerprint == fingerprint)):
        return False
    alert_id = str(uuid4())
    evidence_key = (
        f"artifacts/source-health/source={source.source_id}/year={now:%Y}/"
        f"month={now:%m}/day={now:%d}/alert={alert_id}.json"
    )
    evidence = {
        "alert_id": alert_id,
        "rule_id": "source-silence",
        "created_at": now.isoformat(),
        "source": {
            "source_id": source.source_id,
            "source": source.source,
            "kind": source.kind,
            "hostname": source.hostname,
            "display_name": source.display_name,
            "expected_interval_minutes": source.expected_interval_minutes,
            "last_received_at": (
                source.last_received_at.isoformat() if source.last_received_at else None
            ),
            "monitoring_since": source.created_at.isoformat(),
        },
    }
    put_object(
        evidence_key,
        json.dumps(evidence, separators=(",", ":"), default=str).encode(),
        "application/json",
    )
    alert = Alert(
        alert_id=alert_id,
        fingerprint=fingerprint,
        rule_id="source-silence",
        source_id=source.source_id,
        title=f"Source silent: {source.display_name}",
        severity="high",
        status="open",
        event_count=0,
        evidence_object_key=evidence_key,
        created_at=now,
        updated_at=now,
    )
    db.add(alert)
    db.commit()
    notify_new_alert(alert, db)
    return True


def _resolve_silence_alerts(source_id: str, now: datetime, db: Session) -> int:
    alerts = db.scalars(
        select(Alert).where(
            Alert.rule_id == "source-silence",
            Alert.source_id == source_id,
            Alert.status.in_(ACTIVE_ALERT_STATUSES),
        )
    ).all()
    for alert in alerts:
        old_status = alert.status
        alert.status = "resolved"
        alert.resolved_at = now
        alert.updated_at = now
        db.add(
            AlertHistory(
                history_id=str(uuid4()),
                alert_id=alert.alert_id,
                actor_subject="system:source-health",
                actor_username="source-health-monitor",
                action="status_changed",
                old_value=old_status,
                new_value="resolved",
                created_at=now,
            )
        )
    return len(alerts)
