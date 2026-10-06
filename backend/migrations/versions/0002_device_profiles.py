"""Add persistent device profiles for community access without sign-in."""

import sqlalchemy as sa
from alembic import op

revision = "0002_device_profiles"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_profiles",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("device_profiles")
