import uuid
from datetime import UTC, date, datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wxspot.database import Base

Json = JSONB()


class WeatherCache(Base):
    __tablename__ = "weather_cache"
    content_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    manifest: Mapped[dict] = mapped_column(Json)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class WeatherArtifact(Base):
    __tablename__ = "weather_artifacts"
    object_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class WeatherJob(Base):
    __tablename__ = "weather_jobs"
    content_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(Json)
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    attempts: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict | None] = mapped_column(Json)
    error: Mapped[str | None] = mapped_column(String(300))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("state IN ('queued','running','ready','failed')"),
        Index("weather_jobs_state_available", "state", "available_at"),
        Index("weather_jobs_expiry", "expires_at"),
    )


def now() -> datetime:
    return datetime.now(UTC)


class User(SQLAlchemyBaseUserTableUUID, Base):
    display_name: Mapped[str] = mapped_column(String(60), default="WXspot Player")
    self_role: Mapped[str] = mapped_column(String(30), default="enthusiast")
    verified_role: Mapped[str | None] = mapped_column(String(30))
    is_moderator: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    pass


class DeviceProfile(Base):
    """A revocable device credential for the no-sign-in community experience."""

    __tablename__ = "device_profiles"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    content_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str | None] = mapped_column(Text)
    watch_next: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list] = mapped_column(Json, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
    moderation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    footprint: Mapped[object] = mapped_column(Geometry("GEOMETRYCOLLECTION", srid=4326))
    author: Mapped[User] = relationship(lazy="selectin")
    context: Mapped["ContextRecord"] = relationship(lazy="selectin")
    elements: Mapped[list["ElementRecord"]] = relationship(
        lazy="selectin", order_by="ElementRecord.position"
    )
    archives: Mapped[list["LayerArchive"]] = relationship(lazy="selectin")
    __table_args__ = (
        CheckConstraint("status IN ('active','hidden','removed','under_review')"),
        CheckConstraint("content_type IN ('analysis','observation','question','photo_report')"),
        Index("posts_status_time", "status", "created_at"),
        Index("posts_type_time", "content_type", "created_at"),
        Index("posts_time_id", "created_at", "id"),
        Index("posts_topics", "topics", postgresql_using="gin"),
    )


class ContextRecord(Base):
    __tablename__ = "weather_contexts"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"), unique=True)
    data: Mapped[dict] = mapped_column(Json)


class ElementRecord(Base):
    __tablename__ = "annotation_elements"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"), primary_key=True, index=True)
    position: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(Json)


class LayerArchive(Base):
    __tablename__ = "layer_archives"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"), index=True)
    layer_id: Mapped[str] = mapped_column(String(60))
    object_key: Mapped[str] = mapped_column(String(240))
    bounds: Mapped[list] = mapped_column(Json)


class Media(Base):
    __tablename__ = "media"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    post_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("posts.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("comments.id"))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    author: Mapped[User] = relationship(lazy="selectin")
    __table_args__ = (CheckConstraint("status IN ('active','hidden','removed','under_review')"),)


class Like(Base):
    __tablename__ = "likes"
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Follow(Base):
    __tablename__ = "follows"
    follower_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20), primary_key=True, default="person")
    target_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("follow_target", "target_type", "target_id"),)


class Block(Base):
    __tablename__ = "blocks"
    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), primary_key=True)
    blocked_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), primary_key=True)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID] = mapped_column(index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("reporter_id", "target_type", "target_id"),)


class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    moderator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID] = mapped_column(index=True)
    previous_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    kind: Mapped[str] = mapped_column(String(30))
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"))
    comment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("comments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Quota(Base):
    __tablename__ = "posting_quotas"
    actor: Mapped[str] = mapped_column(String(100), primary_key=True)
    action: Mapped[str] = mapped_column(String(30), primary_key=True)
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=1)


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"
    query_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    results: Mapped[list] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("geocode_cache_expires", "expires_at"),)


class GeocoderBudget(Base):
    __tablename__ = "geocoder_budget"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SoundingStation(Base):
    """Private IGRA station inventory used to validate and explain hunt answers."""

    __tablename__ = "sounding_hunt_stations"
    station_id: Mapped[str] = mapped_column(String(11), primary_key=True)
    name: Mapped[str] = mapped_column(String(70))
    state: Mapped[str] = mapped_column(String(2))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[float] = mapped_column(Float)
    source_version: Mapped[str] = mapped_column(String(20), default="IGRA 2.2")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SoundingObservation(Base):
    """Validated observed profile. Location and source IDs are never in public DTOs."""

    __tablename__ = "sounding_hunt_observations"
    identity: Mapped[str] = mapped_column(String(64), primary_key=True)
    station_id: Mapped[str] = mapped_column(
        ForeignKey("sounding_hunt_stations.station_id"), index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    nominal_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profile: Mapped[dict] = mapped_column(Json)
    validation: Mapped[dict] = mapped_column(Json)
    source_revision: Mapped[str | None] = mapped_column(String(64))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    eligible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("station_id", "observed_at", name="uq_hunt_station_observation"),
        Index("hunt_observation_eligible_time", "eligible", "observed_at"),
    )


class SoundingIngestionStatus(Base):
    """Latest per-station ingestion outcome and rejection reason; bounded by station count."""

    __tablename__ = "sounding_hunt_ingestion_status"
    station_id: Mapped[str] = mapped_column(
        ForeignKey("sounding_hunt_stations.station_id"), primary_key=True
    )
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    state: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    observation_identity: Mapped[str | None] = mapped_column(
        ForeignKey("sounding_hunt_observations.identity")
    )
    source_revision: Mapped[str | None] = mapped_column(String(64))


class DailyHuntChallenge(Base):
    """One idempotently published observation per Eastern calendar date."""

    __tablename__ = "sounding_hunt_daily_challenges"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    challenge_day: Mapped[date] = mapped_column(Date, unique=True)
    challenge_number: Mapped[int] = mapped_column(Integer, unique=True)
    observation_identity: Mapped[str] = mapped_column(
        ForeignKey("sounding_hunt_observations.identity"), unique=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scoring_version: Mapped[str] = mapped_column(String(32))
    score_scale_miles: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DailyHuntGuess(Base):
    __tablename__ = "sounding_hunt_daily_guesses"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sounding_hunt_daily_challenges.id"), index=True
    )
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    distance_miles: Mapped[float] = mapped_column(Float)
    score: Mapped[int] = mapped_column(Integer)
    scoring_version: Mapped[str] = mapped_column(String(32))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("user_id", "challenge_id", name="uq_hunt_daily_player_attempt"),
        CheckConstraint("latitude >= -90 AND latitude <= 90"),
        CheckConstraint("longitude >= -180 AND longitude <= 180"),
        Index(
            "hunt_daily_leaderboard",
            "challenge_id",
            "score",
            "distance_miles",
            "submitted_at",
        ),
    )


class SoundingHuntPractice(Base):
    __tablename__ = "sounding_hunt_practice"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    observation_identity: Mapped[str] = mapped_column(
        ForeignKey("sounding_hunt_observations.identity"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    distance_miles: Mapped[float | None] = mapped_column(Float)
    score: Mapped[int | None] = mapped_column(Integer)
    scoring_version: Mapped[str | None] = mapped_column(String(32))
    score_scale_miles: Mapped[float] = mapped_column(Float, default=750.0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)"),
        Index("hunt_practice_player_time", "user_id", "created_at"),
    )
