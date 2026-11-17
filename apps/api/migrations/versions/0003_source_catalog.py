"""Operational source catalog; telemetry continues to live exclusively in S3."""

import sqlalchemy as sa
from alembic import op

revision = "0003_source_catalog"
down_revision = "0002_alert_triage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline uses metadata.create_all for new installations, so the table may
    # already exist before this revision runs.
    if "source_catalog" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "source_catalog",
        sa.Column("source_id", sa.String(100), primary_key=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("hostname", sa.String(255)),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("expected_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("configured", sa.Boolean(), nullable=False),
        sa.Column("last_received_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_events", sa.Integer(), nullable=False),
        sa.Column("rejected_events", sa.Integer(), nullable=False),
    )
    op.create_index("ix_source_catalog_source", "source_catalog", ["source"])


def downgrade() -> None:
    op.drop_index("ix_source_catalog_source", table_name="source_catalog")
    op.drop_table("source_catalog")
