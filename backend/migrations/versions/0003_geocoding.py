"""Cache explicit place searches and coordinate the public geocoder limit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_geocoding"
down_revision = "0002_device_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "geocode_cache",
        sa.Column("query_key", sa.String(64), primary_key=True),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("geocode_cache_expires", "geocode_cache", ["expires_at"])
    op.create_table(
        "geocoder_budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_geocoder_budget_singleton"),
    )
    op.bulk_insert(
        sa.table(
            "geocoder_budget",
            sa.column("id", sa.Integer()),
            sa.column("last_requested_at", sa.DateTime(timezone=True)),
        ),
        [{"id": 1, "last_requested_at": None}],
    )


def downgrade():
    op.drop_table("geocoder_budget")
    op.drop_index("geocode_cache_expires", table_name="geocode_cache")
    op.drop_table("geocode_cache")
