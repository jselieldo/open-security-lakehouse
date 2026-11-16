"""Adopt the existing schema and add identity and audit tables."""

from alembic import op
from app.database import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # Baseline adoption is intentionally irreversible to protect existing lake metadata.
    pass
