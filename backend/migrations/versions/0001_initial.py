"""Initial immutable social, identity, and spatial schema."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA = (
    """
CREATE TABLE posting_quotas (
    actor VARCHAR(100) NOT NULL,
    action VARCHAR(30) NOT NULL,
    bucket TIMESTAMP WITH TIME ZONE NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (actor, action, bucket)
)
    """,
    """
CREATE TABLE "user" (
    display_name VARCHAR(60) NOT NULL,
    self_role VARCHAR(30) NOT NULL,
    verified_role VARCHAR(30),
    is_moderator BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    id UUID NOT NULL,
    email VARCHAR(320) NOT NULL,
    hashed_password VARCHAR(1024) NOT NULL,
    is_active BOOLEAN NOT NULL,
    is_superuser BOOLEAN NOT NULL,
    is_verified BOOLEAN NOT NULL,
    PRIMARY KEY (id)
)
    """,
    """
CREATE TABLE accesstoken (
    user_id UUID NOT NULL,
    token VARCHAR(43) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (token),
    FOREIGN KEY(user_id) REFERENCES "user" (id) ON DELETE cascade
)
    """,
    """
CREATE TABLE blocks (
    blocker_id UUID NOT NULL,
    blocked_id UUID NOT NULL,
    PRIMARY KEY (blocker_id, blocked_id),
    FOREIGN KEY(blocker_id) REFERENCES "user" (id),
    FOREIGN KEY(blocked_id) REFERENCES "user" (id)
)
    """,
    """
CREATE TABLE follows (
    follower_id UUID NOT NULL,
    target_type VARCHAR(20) NOT NULL,
    target_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (follower_id, target_type, target_id),
    FOREIGN KEY(follower_id) REFERENCES "user" (id)
)
    """,
    """
CREATE TABLE moderation_actions (
    id UUID NOT NULL,
    moderator_id UUID NOT NULL,
    target_type VARCHAR(20) NOT NULL,
    target_id UUID NOT NULL,
    previous_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(moderator_id) REFERENCES "user" (id)
)
    """,
    """
CREATE TABLE posts (
    id UUID NOT NULL,
    author_id UUID NOT NULL,
    content_type VARCHAR(20) NOT NULL,
    title VARCHAR(120),
    description TEXT NOT NULL,
    why_it_matters TEXT,
    watch_next TEXT,
    topics JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,
    moderation_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    footprint geometry(GEOMETRYCOLLECTION,4326) NOT NULL,
    PRIMARY KEY (id),
    CHECK (status IN ('active','hidden','removed','under_review')),
    CHECK (content_type IN ('analysis','observation','question','photo_report')),
    FOREIGN KEY(author_id) REFERENCES "user" (id)
)
    """,
    """
CREATE TABLE reports (
    id UUID NOT NULL,
    reporter_id UUID NOT NULL,
    target_type VARCHAR(20) NOT NULL,
    target_id UUID NOT NULL,
    reason TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (reporter_id, target_type, target_id),
    FOREIGN KEY(reporter_id) REFERENCES "user" (id)
)
    """,
    """
CREATE TABLE annotation_elements (
    id UUID NOT NULL,
    post_id UUID NOT NULL,
    position INTEGER NOT NULL,
    data JSONB NOT NULL,
    PRIMARY KEY (id, post_id),
    FOREIGN KEY(post_id) REFERENCES posts (id)
)
    """,
    """
CREATE TABLE comments (
    id UUID NOT NULL,
    post_id UUID NOT NULL,
    author_id UUID NOT NULL,
    parent_id UUID,
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CHECK (status IN ('active','hidden','removed','under_review')),
    FOREIGN KEY(post_id) REFERENCES posts (id),
    FOREIGN KEY(author_id) REFERENCES "user" (id),
    FOREIGN KEY(parent_id) REFERENCES comments (id)
)
    """,
    """
CREATE TABLE layer_archives (
    id UUID NOT NULL,
    post_id UUID NOT NULL,
    layer_id VARCHAR(60) NOT NULL,
    object_key VARCHAR(240) NOT NULL,
    bounds JSONB NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(post_id) REFERENCES posts (id)
)
    """,
    """
CREATE TABLE likes (
    post_id UUID NOT NULL,
    user_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (post_id, user_id),
    FOREIGN KEY(post_id) REFERENCES posts (id),
    FOREIGN KEY(user_id) REFERENCES "user" (id)
)
    """,
    """
CREATE TABLE media (
    id UUID NOT NULL,
    owner_id UUID NOT NULL,
    post_id UUID,
    object_key VARCHAR(240) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(owner_id) REFERENCES "user" (id),
    FOREIGN KEY(post_id) REFERENCES posts (id)
)
    """,
    """
CREATE TABLE weather_contexts (
    id UUID NOT NULL,
    post_id UUID NOT NULL,
    data JSONB NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (post_id),
    FOREIGN KEY(post_id) REFERENCES posts (id)
)
    """,
    """
CREATE TABLE notifications (
    id UUID NOT NULL,
    recipient_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    kind VARCHAR(30) NOT NULL,
    post_id UUID NOT NULL,
    comment_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    read_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    FOREIGN KEY(recipient_id) REFERENCES "user" (id),
    FOREIGN KEY(actor_id) REFERENCES "user" (id),
    FOREIGN KEY(post_id) REFERENCES posts (id),
    FOREIGN KEY(comment_id) REFERENCES comments (id)
)
    """,
    """
CREATE UNIQUE INDEX ix_user_email ON "user" (email)
    """,
    """
CREATE INDEX ix_accesstoken_created_at ON accesstoken (created_at)
    """,
    """
CREATE INDEX follow_target ON follows (target_type, target_id)
    """,
    """
CREATE INDEX ix_moderation_actions_target_id ON moderation_actions (target_id)
    """,
    """
CREATE INDEX idx_posts_footprint ON posts USING gist (footprint)
    """,
    """
CREATE INDEX ix_posts_author_id ON posts (author_id)
    """,
    """
CREATE INDEX posts_status_time ON posts (status, created_at)
    """,
    """
CREATE INDEX posts_time_id ON posts (created_at, id)
    """,
    """
CREATE INDEX posts_topics ON posts USING gin (topics)
    """,
    """
CREATE INDEX posts_type_time ON posts (content_type, created_at)
    """,
    """
CREATE INDEX ix_reports_target_id ON reports (target_id)
    """,
    """
CREATE INDEX ix_annotation_elements_post_id ON annotation_elements (post_id)
    """,
    """
CREATE INDEX ix_comments_author_id ON comments (author_id)
    """,
    """
CREATE INDEX ix_comments_post_id ON comments (post_id)
    """,
    """
CREATE INDEX ix_layer_archives_post_id ON layer_archives (post_id)
    """,
    """
CREATE INDEX ix_likes_user_id ON likes (user_id)
    """,
    """
CREATE INDEX ix_media_owner_id ON media (owner_id)
    """,
    """
CREATE INDEX ix_media_post_id ON media (post_id)
    """,
    """
CREATE INDEX ix_notifications_recipient_id ON notifications (recipient_id)
    """,
)


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    for statement in SCHEMA:
        op.execute(statement)


def downgrade():
    op.execute('DROP TABLE "notifications"')
    op.execute('DROP TABLE "weather_contexts"')
    op.execute('DROP TABLE "media"')
    op.execute('DROP TABLE "likes"')
    op.execute('DROP TABLE "layer_archives"')
    op.execute('DROP TABLE "comments"')
    op.execute('DROP TABLE "annotation_elements"')
    op.execute('DROP TABLE "reports"')
    op.execute('DROP TABLE "posts"')
    op.execute('DROP TABLE "moderation_actions"')
    op.execute('DROP TABLE "follows"')
    op.execute('DROP TABLE "blocks"')
    op.execute('DROP TABLE "accesstoken"')
    op.execute('DROP TABLE "user"')
    op.execute('DROP TABLE "posting_quotas"')
