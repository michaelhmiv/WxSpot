"""Shared immutable model field and profile cache pointers."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_weather_cache"
down_revision = "0004_weather_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "weather_cache",
        sa.Column("content_key", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("weather_cache_expiry", "weather_cache", ["expires_at"])


def downgrade():
    op.drop_table("weather_cache")
