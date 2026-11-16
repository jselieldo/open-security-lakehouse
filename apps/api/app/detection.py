import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import Alert, DetectionRun
from .investigation import investigate
from .metrics import DETECTION_DURATION, DETECTION_RUNS
from .schemas import AlertResponse, DetectionRunResponse, InvestigationRequest
from .storage import get_object_bytes, put_object


class DetectionRule(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    severity: str = Field(pattern=r"^(low|medium|high|critical)$")
    enabled: bool = True
    schedule_minutes: int = Field(default=15, ge=1, le=1440)
    threshold: int = Field(default=1, ge=1, le=1000)
    lookback_minutes: int = Field(default=20, ge=1, le=10080)
    query: InvestigationRequest


def load_rules() -> list[DetectionRule]:
    rules_dir = Path(get_settings().detection_rules_dir)
    if not rules_dir.exists():
        return []
    rules = [
        DetectionRule.model_validate(yaml.safe_load(path.read_text()))
        for path in rules_dir.glob("*.yaml")
    ]
    ids = [rule.id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate detection rule id")
    return sorted(rules, key=lambda rule: rule.id)


def get_rule(rule_id: str) -> DetectionRule | None:
    return next((rule for rule in load_rules() if rule.id == rule_id), None)


def execute_rule(rule: DetectionRule, db: Session) -> DetectionRunResponse:
    run_id = str(uuid4())
    run = DetectionRun(run_id=run_id, rule_id=rule.id, status="running")
    db.add(run)
    db.commit()
    started = perf_counter()

    try:
        query = rule.query
        if query.start_time is None:
            query = query.model_copy(
                update={"start_time": datetime.now(UTC) - timedelta(minutes=rule.lookback_minutes)}
            )
        result = investigate(query)
        run.matched_count = result.returned_count
        if result.returned_count >= rule.threshold:
            run.alert_created = _create_alert(rule, run_id, result.events, db)
        run.status = "completed"
        run.duration_ms = round((perf_counter() - started) * 1000, 3)
        run.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(run)
        DETECTION_RUNS.labels(rule_id=rule.id, status="completed").inc()
        DETECTION_DURATION.labels(rule_id=rule.id).observe(run.duration_ms / 1000)
        return _run_response(run)
    except Exception as exc:
        run.status = "failed"
        run.duration_ms = round((perf_counter() - started) * 1000, 3)
        run.error_message = type(exc).__name__
        run.completed_at = datetime.now(UTC)
        db.commit()
        DETECTION_RUNS.labels(rule_id=rule.id, status="failed").inc()
        DETECTION_DURATION.labels(rule_id=rule.id).observe(run.duration_ms / 1000)
        raise


def _create_alert(rule: DetectionRule, run_id: str, events: list[dict], db: Session) -> bool:
    event_ids = sorted(str(event["event_id"]) for event in events)
    fingerprint = sha256(f"{rule.id}:{','.join(event_ids)}".encode()).hexdigest()
    existing = db.scalar(select(Alert).where(Alert.fingerprint == fingerprint))
    if existing:
        return False

    alert_id = str(uuid4())
    now = datetime.now(UTC)
    evidence_key = (
        f"artifacts/detection-evidence/rule={rule.id}/year={now:%Y}/month={now:%m}/"
        f"day={now:%d}/alert={alert_id}.json"
    )
    evidence = {
        "alert_id": alert_id,
        "run_id": run_id,
        "rule": rule.model_dump(mode="json"),
        "created_at": now.isoformat(),
        "event_count": len(events),
        "events": events,
    }
    put_object(
        evidence_key,
        json.dumps(evidence, separators=(",", ":"), default=str).encode(),
        "application/json",
    )
    db.add(
        Alert(
            alert_id=alert_id,
            fingerprint=fingerprint,
            rule_id=rule.id,
            title=rule.title,
            severity=rule.severity,
            status="open",
            event_count=len(events),
            evidence_object_key=evidence_key,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def list_alerts(db: Session, limit: int = 100) -> list[AlertResponse]:
    alerts = db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(limit)).all()
    return [_alert_response(alert) for alert in alerts]


def get_alert_evidence(alert_id: str, db: Session) -> dict | None:
    alert = db.get(Alert, alert_id)
    if alert is None:
        return None
    return json.loads(get_object_bytes(alert.evidence_object_key))


def _run_response(run: DetectionRun) -> DetectionRunResponse:
    return DetectionRunResponse(
        run_id=run.run_id,
        rule_id=run.rule_id,
        status=run.status,
        matched_count=run.matched_count,
        alert_created=run.alert_created,
        duration_ms=run.duration_ms,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
    )


def _alert_response(alert: Alert) -> AlertResponse:
    return AlertResponse(
        alert_id=alert.alert_id,
        rule_id=alert.rule_id,
        title=alert.title,
        severity=alert.severity,
        status=alert.status,
        event_count=alert.event_count,
        evidence_object_key=alert.evidence_object_key,
        created_at=alert.created_at.isoformat(),
    )
