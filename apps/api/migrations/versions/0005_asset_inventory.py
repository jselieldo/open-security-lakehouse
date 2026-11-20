"""Add the observed asset inventory."""

import sqlalchemy as sa
from alembic import op

revision = "0005_asset_inventory"
down_revision = "0004_source_silence_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "assets" in inspector.get_table_names():
        return
    op.create_table(
        "assets",
        sa.Column("asset_id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("hostname", sa.String(255)),
        sa.Column("primary_ip", sa.String(64)),
        sa.Column("ip_addresses_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("criticality", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assets_kind", "assets", ["kind"])
    op.create_index("ix_assets_hostname", "assets", ["hostname"])
    op.create_index("ix_assets_primary_ip", "assets", ["primary_ip"])


def downgrade() -> None:
    op.drop_table("assets")
