"""Add managed asset context and alert asset snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0006_asset_context"
down_revision = "0005_asset_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assets", sa.Column("aliases_json", sa.Text(), nullable=False, server_default="[]")
    )
    op.add_column("assets", sa.Column("owner", sa.String(200)))
    op.add_column("alerts", sa.Column("asset_id", sa.String(64)))
    op.add_column("alerts", sa.Column("asset_display_name", sa.String(255)))
    op.add_column("alerts", sa.Column("asset_criticality", sa.String(20)))
    op.create_index("ix_alerts_asset_id", "alerts", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_asset_id", table_name="alerts")
    op.drop_column("alerts", "asset_criticality")
    op.drop_column("alerts", "asset_display_name")
    op.drop_column("alerts", "asset_id")
    op.drop_column("assets", "owner")
    op.drop_column("assets", "aliases_json")
