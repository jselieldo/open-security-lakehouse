"""Track source monitoring start and associate silence alerts with a source."""

import sqlalchemy as sa
from alembic import op

revision = "0004_source_silence_alerts"
down_revision = "0003_source_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    source_columns = {item["name"] for item in inspector.get_columns("source_catalog")}
    if "created_at" not in source_columns:
        op.add_column(
            "source_catalog",
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    alert_columns = {item["name"] for item in inspector.get_columns("alerts")}
    if "source_id" not in alert_columns:
        op.add_column("alerts", sa.Column("source_id", sa.String(100)))
        op.create_index("ix_alerts_source_id", "alerts", ["source_id"])


def downgrade() -> None:
    alert_columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns("alerts")
    }
    if "source_id" in alert_columns:
        op.drop_index("ix_alerts_source_id", table_name="alerts")
        op.drop_column("alerts", "source_id")
    source_columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns("source_catalog")
    }
    if "created_at" in source_columns:
        op.drop_column("source_catalog", "created_at")
