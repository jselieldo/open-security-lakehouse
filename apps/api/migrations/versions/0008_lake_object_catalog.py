"""Add an operational event-time catalog for lake objects."""

import sqlalchemy as sa
from alembic import op

revision = "0008_lake_object_catalog"
down_revision = "0007_asset_changes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lake_objects",
        sa.Column("object_key", sa.Text(), primary_key=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("min_event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("row_count", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_lake_objects_source", "lake_objects", ["source"])
    op.create_index("ix_lake_objects_active", "lake_objects", ["active"])
    op.create_index(
        "ix_lake_objects_time_range",
        "lake_objects",
        ["active", "source", "max_event_time", "min_event_time"],
    )


def downgrade() -> None:
    op.drop_table("lake_objects")
