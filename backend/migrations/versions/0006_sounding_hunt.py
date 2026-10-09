"""Additive schema for private IGRA candidates and Sounding Hunt results."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_sounding_hunt"
down_revision = "0005_weather_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sounding_hunt_stations",
        sa.Column("station_id", sa.String(11), primary_key=True),
        sa.Column("name", sa.String(70), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("elevation_m", sa.Float(), nullable=False),
        sa.Column("source_version", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sounding_hunt_observations",
        sa.Column("identity", sa.String(64), primary_key=True),
        sa.Column(
            "station_id",
            sa.String(11),
            sa.ForeignKey("sounding_hunt_stations.station_id"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nominal_time", sa.DateTime(timezone=True)),
        sa.Column("profile", postgresql.JSONB(), nullable=False),
        sa.Column("validation", postgresql.JSONB(), nullable=False),
        sa.Column("source_revision", sa.String(64)),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.Text()),
        sa.UniqueConstraint("station_id", "observed_at", name="uq_hunt_station_observation"),
    )
    op.create_index(
        "ix_sounding_hunt_observations_station_id",
        "sounding_hunt_observations",
        ["station_id"],
    )
    op.create_index(
        "ix_sounding_hunt_observations_observed_at",
        "sounding_hunt_observations",
        ["observed_at"],
    )
    op.create_index(
        "ix_sounding_hunt_observations_eligible",
        "sounding_hunt_observations",
        ["eligible"],
    )
    op.create_index(
        "hunt_observation_eligible_time",
        "sounding_hunt_observations",
        ["eligible", "observed_at"],
    )
    op.create_table(
        "sounding_hunt_ingestion_status",
        sa.Column(
            "station_id",
            sa.String(11),
            sa.ForeignKey("sounding_hunt_stations.station_id"),
            primary_key=True,
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "observation_identity",
            sa.String(64),
            sa.ForeignKey("sounding_hunt_observations.identity"),
        ),
        sa.Column("source_revision", sa.String(64)),
    )
    op.create_table(
        "sounding_hunt_daily_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("challenge_day", sa.Date(), nullable=False, unique=True),
        sa.Column("challenge_number", sa.Integer(), nullable=False, unique=True),
        sa.Column(
            "observation_identity",
            sa.String(64),
            sa.ForeignKey("sounding_hunt_observations.identity"),
            nullable=False,
            unique=True,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scoring_version", sa.String(32), nullable=False),
        sa.Column("score_scale_miles", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_hunt_challenge_window"),
    )
    op.create_index(
        "ix_sounding_hunt_daily_challenges_starts_at",
        "sounding_hunt_daily_challenges",
        ["starts_at"],
    )
    op.create_index(
        "ix_sounding_hunt_daily_challenges_ends_at",
        "sounding_hunt_daily_challenges",
        ["ends_at"],
    )
    op.create_table(
        "sounding_hunt_daily_guesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column(
            "challenge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sounding_hunt_daily_challenges.id"),
            nullable=False,
        ),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("distance_miles", sa.Float(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("scoring_version", sa.String(32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "challenge_id", name="uq_hunt_daily_player_attempt"),
        sa.CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_hunt_daily_guess_latitude",
        ),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_hunt_daily_guess_longitude",
        ),
    )
    op.create_index(
        "ix_sounding_hunt_daily_guesses_user_id",
        "sounding_hunt_daily_guesses",
        ["user_id"],
    )
    op.create_index(
        "ix_sounding_hunt_daily_guesses_challenge_id",
        "sounding_hunt_daily_guesses",
        ["challenge_id"],
    )
    op.create_index(
        "hunt_daily_leaderboard",
        "sounding_hunt_daily_guesses",
        ["challenge_id", "score", "distance_miles", "submitted_at"],
    )
    op.create_table(
        "sounding_hunt_practice",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column(
            "observation_identity",
            sa.String(64),
            sa.ForeignKey("sounding_hunt_observations.identity"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("distance_miles", sa.Float()),
        sa.Column("score", sa.Integer()),
        sa.Column("scoring_version", sa.String(32)),
        sa.Column("score_scale_miles", sa.Float(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_hunt_practice_latitude",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_hunt_practice_longitude",
        ),
    )
    op.create_index(
        "ix_sounding_hunt_practice_user_id",
        "sounding_hunt_practice",
        ["user_id"],
    )
    op.create_index(
        "ix_sounding_hunt_practice_observation_identity",
        "sounding_hunt_practice",
        ["observation_identity"],
    )
    op.create_index(
        "hunt_practice_player_time",
        "sounding_hunt_practice",
        ["user_id", "created_at"],
    )


def downgrade():
    op.drop_table("sounding_hunt_practice")
    op.drop_table("sounding_hunt_daily_guesses")
    op.drop_table("sounding_hunt_daily_challenges")
    op.drop_table("sounding_hunt_ingestion_status")
    op.drop_table("sounding_hunt_observations")
    op.drop_table("sounding_hunt_stations")
