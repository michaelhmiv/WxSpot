import uuid
from datetime import UTC, datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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


def now() -> datetime:
    return datetime.now(UTC)


class User(SQLAlchemyBaseUserTableUUID, Base):
    display_name: Mapped[str] = mapped_column(String(60), default="Weather enthusiast")
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
