import json
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy.orm import Session

from .config import get_settings
from .database import Alert, NotificationDelivery


def notify_new_alert(alert: Alert, db: Session) -> None:
    settings = get_settings()
    if not settings.alert_webhook_url:
        return
    delivery = NotificationDelivery(
        delivery_id=str(uuid4()),
        alert_id=alert.alert_id,
        channel="webhook",
        status="sending",
    )
    db.add(delivery)
    db.commit()
    if urlparse(settings.alert_webhook_url).scheme not in {"http", "https"}:
        delivery.status = "failed"
        delivery.error_message = "InvalidWebhookURL"
        db.commit()
        return
    payload = json.dumps(
        {
            "type": "osl.alert.created",
            "sent_at": datetime.now(UTC).isoformat(),
            "alert": {
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "title": alert.title,
                "severity": alert.severity,
                "event_count": alert.event_count,
            },
        }
    ).encode()
    try:
        request = Request(  # noqa: S310 -- scheme is restricted above.
            settings.alert_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "OSL/1.0"},
            method="POST",
        )
        with urlopen(request, timeout=settings.alert_webhook_timeout_seconds) as response:  # noqa: S310
            if response.status >= 300:
                raise RuntimeError(f"webhook returned HTTP {response.status}")
        delivery.status = "delivered"
    except Exception as exc:
        delivery.status = "failed"
        delivery.error_message = type(exc).__name__
    db.commit()
