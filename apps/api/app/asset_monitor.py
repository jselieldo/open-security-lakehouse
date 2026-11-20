import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Alert, Asset, AssetChange
from .notifications import notify_new_alert
from .storage import put_object


def process_asset_changes(db: Session, limit: int = 100) -> dict[str, int]:
    changes = db.scalars(
        select(AssetChange)
        .where(AssetChange.alert_id.is_(None))
        .order_by(AssetChange.observed_at)
        .limit(limit)
    ).all()
    created: list[Alert] = []
    for change in changes:
        asset = db.get(Asset, change.asset_id)
        if asset is None:
            continue
        alert_id = str(uuid4())
        now = datetime.now(UTC)
        rule_id = "asset-new" if change.change_type == "new_asset" else "asset-context-change"
        title = (
            f"Novo ativo observado: {asset.display_name}"
            if change.change_type == "new_asset"
            else f"Mudança observada no ativo: {asset.display_name}"
        )
        severity = "high" if asset.criticality == "critical" else (
            "medium" if change.change_type == "new_asset" else "low"
        )
        evidence_key = (
            f"artifacts/asset-observations/year={now:%Y}/month={now:%m}/"
            f"day={now:%d}/change={change.change_id}.json"
        )
        evidence = {
            "alert_id": alert_id,
            "change_id": change.change_id,
            "asset_id": asset.asset_id,
            "asset_display_name": asset.display_name,
            "asset_criticality": asset.criticality,
            "change_type": change.change_type,
            "old_value": change.old_value,
            "new_value": change.new_value,
            "source": change.source,
            "observed_at": change.observed_at.isoformat(),
        }
        put_object(
            evidence_key,
            json.dumps(evidence, separators=(",", ":")).encode(),
            "application/json",
        )
        alert = Alert(
            alert_id=alert_id,
            fingerprint=sha256(f"asset-change:{change.change_id}".encode()).hexdigest(),
            rule_id=rule_id,
            asset_id=asset.asset_id,
            asset_display_name=asset.display_name,
            asset_criticality=asset.criticality,
            title=title,
            severity=severity,
            status="open",
            event_count=1,
            evidence_object_key=evidence_key,
        )
        db.add(alert)
        change.alert_id = alert_id
        created.append(alert)
    db.commit()
    for alert in created:
        notify_new_alert(alert, db)
    return {"examined": len(changes), "alerts_created": len(created)}
