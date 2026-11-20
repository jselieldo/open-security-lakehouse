"""Queue observed asset changes for asynchronous alerting."""

import sqlalchemy as sa
from alembic import op

revision = "0007_asset_changes"
down_revision = "0006_asset_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_changes",
        sa.Column("change_id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("old_value", sa.String(500)),
        sa.Column("new_value", sa.String(500), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alert_id", sa.String(36)),
    )
    op.create_index("ix_asset_changes_asset_id", "asset_changes", ["asset_id"])
    op.create_index("ix_asset_changes_change_type", "asset_changes", ["change_type"])
    op.create_index("ix_asset_changes_alert_id", "asset_changes", ["alert_id"])


def downgrade() -> None:
    op.drop_table("asset_changes")
