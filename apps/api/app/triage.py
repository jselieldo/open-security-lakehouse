from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Alert, AlertComment, AlertHistory
from .detection import alert_response
from .schemas import (
    AlertCommentResponse,
    AlertDetailResponse,
    AlertHistoryResponse,
    AlertResponse,
    AlertUpdateRequest,
)
from .security import Principal

ACTIVE_STATUSES = {"open", "investigating", "reopened"}
ALLOWED_TRANSITIONS = {
    "open": {"investigating", "resolved", "false_positive"},
    "investigating": {"open", "resolved", "false_positive"},
    "resolved": {"reopened"},
    "false_positive": {"reopened"},
    "reopened": {"investigating", "resolved", "false_positive"},
}


class InvalidAlertTransitionError(ValueError):
    pass


def get_alert_detail(alert_id: str, db: Session) -> AlertDetailResponse | None:
    alert = db.get(Alert, alert_id)
    if alert is None:
        return None
    comments = db.scalars(
        select(AlertComment)
        .where(AlertComment.alert_id == alert_id)
        .order_by(AlertComment.created_at)
    ).all()
    history = db.scalars(
        select(AlertHistory)
        .where(AlertHistory.alert_id == alert_id)
        .order_by(AlertHistory.created_at)
    ).all()
    return AlertDetailResponse(
        alert=alert_response(alert),
        comments=[
            AlertCommentResponse(
                comment_id=item.comment_id,
                author_username=item.author_username,
                body=item.body,
                created_at=item.created_at.isoformat(),
            )
            for item in comments
        ],
        history=[
            AlertHistoryResponse(
                history_id=item.history_id,
                actor_username=item.actor_username,
                action=item.action,
                old_value=item.old_value,
                new_value=item.new_value,
                created_at=item.created_at.isoformat(),
            )
            for item in history
        ],
    )


def update_alert(
    alert_id: str, payload: AlertUpdateRequest, principal: Principal, db: Session
) -> AlertResponse | None:
    alert = db.get(Alert, alert_id)
    if alert is None:
        return None
    now = datetime.now(UTC)
    if payload.status and payload.status != alert.status:
        if payload.status not in ALLOWED_TRANSITIONS.get(alert.status, set()):
            raise InvalidAlertTransitionError(
                f"cannot transition {alert.status} to {payload.status}"
            )
        old_status = alert.status
        alert.status = payload.status
        alert.resolved_at = now if payload.status in {"resolved", "false_positive"} else None
        _history(alert, principal, "status_changed", old_status, payload.status, db)
    if payload.assign_to_me is not None:
        old_assignee = alert.assignee_username
        if payload.assign_to_me:
            alert.assignee_subject = principal.subject
            alert.assignee_username = principal.username
        else:
            alert.assignee_subject = None
            alert.assignee_username = None
        if old_assignee != alert.assignee_username:
            _history(
                alert,
                principal,
                "assignee_changed",
                old_assignee,
                alert.assignee_username,
                db,
            )
    alert.updated_at = now
    db.commit()
    db.refresh(alert)
    return alert_response(alert)


def add_comment(
    alert_id: str, body: str, principal: Principal, db: Session
) -> AlertCommentResponse | None:
    alert = db.get(Alert, alert_id)
    if alert is None:
        return None
    comment = AlertComment(
        comment_id=str(uuid4()),
        alert_id=alert_id,
        author_subject=principal.subject,
        author_username=principal.username,
        body=body.strip(),
    )
    db.add(comment)
    _history(alert, principal, "comment_added", None, comment.comment_id, db)
    alert.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(comment)
    return AlertCommentResponse(
        comment_id=comment.comment_id,
        author_username=comment.author_username,
        body=comment.body,
        created_at=comment.created_at.isoformat(),
    )


def _history(
    alert: Alert,
    principal: Principal,
    action: str,
    old_value: str | None,
    new_value: str | None,
    db: Session,
) -> None:
    db.add(
        AlertHistory(
            history_id=str(uuid4()),
            alert_id=alert.alert_id,
            actor_subject=principal.subject,
            actor_username=principal.username,
            action=action,
            old_value=old_value,
            new_value=new_value,
        )
    )
