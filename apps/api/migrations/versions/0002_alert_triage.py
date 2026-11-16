"""Add alert triage, history, comments, and notification delivery."""

import sqlalchemy as sa
from alembic import op

revision = "0002_alert_triage"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_columns = {item["name"] for item in inspector.get_columns("alerts")}
    if "assignee_subject" not in existing_columns:
        op.add_column("alerts", sa.Column("assignee_subject", sa.String(255)))
        op.add_column("alerts", sa.Column("assignee_username", sa.String(150)))
        op.add_column(
            "alerts",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.add_column("alerts", sa.Column("resolved_at", sa.DateTime(timezone=True)))
        op.create_index("ix_alerts_assignee_subject", "alerts", ["assignee_subject"])
    existing_tables = set(inspector.get_table_names())
    if "alert_comments" in existing_tables:
        return
    op.create_table(
        "alert_comments",
        sa.Column("comment_id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.alert_id"), nullable=False),
        sa.Column("author_subject", sa.String(255), nullable=False),
        sa.Column("author_username", sa.String(150), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alert_comments_alert_id", "alert_comments", ["alert_id"])
    op.create_table(
        "alert_history",
        sa.Column("history_id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.alert_id"), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("actor_username", sa.String(150), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("old_value", sa.Text),
        sa.Column("new_value", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alert_history_alert_id", "alert_history", ["alert_id"])
    op.create_table(
        "notification_deliveries",
        sa.Column("delivery_id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.alert_id"), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notification_deliveries_alert_id", "notification_deliveries", ["alert_id"])


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("alert_history")
    op.drop_table("alert_comments")
    op.drop_index("ix_alerts_assignee_subject", table_name="alerts")
    for column in ("resolved_at", "updated_at", "assignee_username", "assignee_subject"):
        op.drop_column("alerts", column)
