"""Shared bounded weather preparation queue and immutable artifact manifests."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_weather_jobs"
down_revision = "0003_geocoding"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "weather_jobs",
        sa.Column("content_key", sa.String(64), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("manifest", postgresql.JSONB()),
        sa.Column("error", sa.String(300)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('queued','running','ready','failed')"),
    )
    op.create_index("weather_jobs_state_available", "weather_jobs", ["state", "available_at"])
    op.create_index("weather_jobs_expiry", "weather_jobs", ["expires_at"])
    op.create_table(
        "weather_artifacts",
        sa.Column("object_key", sa.String(200), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("weather_artifacts_expiry", "weather_artifacts", ["expires_at"])


def downgrade():
    op.drop_table("weather_artifacts")
    op.drop_table("weather_jobs")
