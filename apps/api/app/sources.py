from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Alert, SourceCatalog
from .schemas import SourceRegistration, SourceResponse


def register_source(payload: SourceRegistration, db: Session) -> SourceResponse:
    source = db.get(SourceCatalog, payload.source_id)
    if source is None:
        source = SourceCatalog(source_id=payload.source_id, source=payload.source)
        db.add(source)
    elif source.source != payload.source:
        raise ValueError("source_id is already assigned to a different source")
    source.kind = payload.kind
    source.hostname = payload.hostname
    source.display_name = payload.display_name
    source.expected_interval_minutes = payload.expected_interval_minutes
    source.enabled = payload.enabled
    source.configured = True
    db.commit()
    db.refresh(source)
    return source_response(source)


def record_source_batch(
    source_name: str, events: list[dict], accepted: int, rejected: int, db: Session
) -> None:
    # Only the transport's stable host field is used for attribution; payload bodies
    # remain untrusted and cannot create configured/verified identities.
    hosts = {
        str(event.get("hostname")) for event in events
        if isinstance(event.get("hostname"), str) and event["hostname"]
    }
    host = next(iter(hosts)) if len(hosts) == 1 else None
    candidates = db.scalars(
        select(SourceCatalog).where(SourceCatalog.source == source_name).with_for_update()
    ).all()
    matching = next(
        (item for item in candidates if item.hostname and item.hostname == host), None
    )
    matching = matching or next((item for item in candidates if item.hostname is None), None)
    if matching is None:
        fallback_id = (
            source_name
            if not candidates
            else f"{source_name}-{sha256(f'{source_name}:{host}'.encode()).hexdigest()[:16]}"
        )
        matching = SourceCatalog(
            source_id=fallback_id,
            source=source_name,
            kind="docker" if source_name in {"docker-events", "docker-logs"} else "unclassified",
            hostname=host,
            display_name={
                "docker-events": "Docker events",
                "docker-logs": "Docker application logs",
            }.get(source_name, source_name),
            configured=False,
        )
        db.add(matching)
    if accepted:
        matching.last_received_at = datetime.now(UTC)
    matching.accepted_events = (matching.accepted_events or 0) + accepted
    matching.rejected_events = (matching.rejected_events or 0) + rejected


def source_response(
    source: SourceCatalog,
    now: datetime | None = None,
    active_silence_alert_id: str | None = None,
) -> SourceResponse:
    now = now or datetime.now(UTC)
    last = source.last_received_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    monitoring_since = source.created_at
    if monitoring_since.tzinfo is None:
        monitoring_since = monitoring_since.replace(tzinfo=UTC)
    reference = last or monitoring_since
    silence_deadline = reference + timedelta(minutes=source.expected_interval_minutes)
    if not source.enabled:
        state = "disabled"
    elif last is None:
        state = "waiting"
    elif now - last > timedelta(minutes=source.expected_interval_minutes):
        state = "silent"
    else:
        state = "active"
    return SourceResponse(
        source_id=source.source_id,
        source=source.source,
        kind=source.kind,
        hostname=source.hostname,
        display_name=source.display_name,
        expected_interval_minutes=source.expected_interval_minutes,
        enabled=source.enabled,
        configured=source.configured,
        status=state,
        last_received_at=last,
        accepted_events=source.accepted_events,
        rejected_events=source.rejected_events,
        monitoring_since=monitoring_since,
        silence_deadline_at=silence_deadline if source.enabled else None,
        seconds_since_last_event=(
            max(0, int((now - last).total_seconds())) if last is not None else None
        ),
        seconds_until_silent=(
            int((silence_deadline - now).total_seconds()) if source.enabled else None
        ),
        active_silence_alert_id=active_silence_alert_id,
    )


def list_sources(db: Session) -> list[SourceResponse]:
    active_alerts = {
        item.source_id: item.alert_id
        for item in db.scalars(
            select(Alert).where(
                Alert.rule_id == "source-silence",
                Alert.status.in_({"open", "investigating", "reopened"}),
                Alert.source_id.is_not(None),
            )
        ).all()
        if item.source_id is not None
    }
    return [
        source_response(item, active_silence_alert_id=active_alerts.get(item.source_id))
        for item in db.scalars(select(SourceCatalog).order_by(SourceCatalog.source_id)).all()
    ]
