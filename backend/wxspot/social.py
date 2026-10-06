import base64
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from geoalchemy2.shape import from_shape, to_shape
from PIL import Image, UnidentifiedImageError
from shapely.geometry import GeometryCollection, shape
from sqlalchemy import and_, delete, exists, func, literal, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from wxspot.auth import optional_user, required_user
from wxspot.database import session, sessions
from wxspot.models import (
    Block,
    Comment,
    ContextRecord,
    ElementRecord,
    Follow,
    LayerArchive,
    Like,
    Media,
    ModerationAction,
    Notification,
    Post,
    Quota,
    Report,
    User,
)
from wxspot.ranking import top_score
from wxspot.schemas import CommentCreate, ModerationCreate, PostCreate, ReportCreate
from wxspot.weather import SourceError

router = APIRouter()
Db = Depends(session)
OptionalUser = Depends(optional_user)
RequiredUser = Depends(required_user)
Image.MAX_IMAGE_PIXELS = 20_000_000


async def quota(actor: str, action: str, limit: int):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    async with sessions() as db:
        stmt = insert(Quota).values(actor=actor, action=action, bucket=bucket, count=1)
        result = await db.scalar(
            stmt.on_conflict_do_update(
                index_elements=[Quota.actor, Quota.action, Quota.bucket],
                set_={"count": Quota.count + 1},
            ).returning(Quota.count)
        )
        await db.commit()
    if result > limit:
        raise HTTPException(
            429, "Please wait a minute before trying again", headers={"Retry-After": "60"}
        )


def blocked_author(user):
    if not user:
        return literal(False)
    return exists(
        select(Block.blocker_id).where(
            or_(
                and_(Block.blocker_id == user.id, Block.blocked_id == Post.author_id),
                and_(Block.blocked_id == user.id, Block.blocker_id == Post.author_id),
            )
        )
    )


async def users_blocked(db, first, second):
    return await db.scalar(
        select(
            exists().where(
                or_(
                    and_(Block.blocker_id == first, Block.blocked_id == second),
                    and_(Block.blocker_id == second, Block.blocked_id == first),
                )
            )
        )
    )


async def visible_post(db, post_id, user):
    post = await db.scalar(
        select(Post).where(
            Post.id == post_id,
            Post.status == "active",
            ~blocked_author(user),
        )
    )
    if not post:
        raise HTTPException(404, "Annotation not found")
    return post


def profile(user):
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "self_role": user.self_role,
        "verified_role": user.verified_role,
        "created_at": user.created_at,
    }


async def posts_json(db, posts, user):
    if not posts:
        return []
    ids = [post.id for post in posts]
    likes = dict(
        (
            await db.execute(
                select(Like.post_id, func.count())
                .where(Like.post_id.in_(ids))
                .group_by(Like.post_id)
            )
        ).all()
    )
    comments = dict(
        (
            await db.execute(
                select(Comment.post_id, func.count())
                .where(Comment.post_id.in_(ids), Comment.status == "active")
                .group_by(Comment.post_id)
            )
        ).all()
    )
    liked, followed = set(), set()
    if user:
        liked = set(
            (
                await db.scalars(
                    select(Like.post_id).where(Like.post_id.in_(ids), Like.user_id == user.id)
                )
            ).all()
        )
        followed = set(
            (
                await db.scalars(
                    select(Follow.target_id).where(
                        Follow.follower_id == user.id,
                        Follow.target_type == "person",
                        Follow.target_id.in_({post.author_id for post in posts}),
                    )
                )
            ).all()
        )
    photos = {}
    for post_id, media_id in (
        await db.execute(select(Media.post_id, Media.id).where(Media.post_id.in_(ids)))
    ).all():
        photos.setdefault(post_id, []).append(f"/media/{media_id}")
    result = []
    for post in posts:
        point = to_shape(post.footprint).representative_point()
        result.append(
            {
                "id": str(post.id),
                "author": profile(post.author),
                "content_type": post.content_type,
                "title": post.title,
                "description": post.description,
                "why_it_matters": post.why_it_matters,
                "watch_next": post.watch_next,
                "topics": post.topics,
                "created_at": post.created_at,
                "status": post.status,
                "context": post.context.data,
                "elements": [e.data for e in post.elements],
                "location": [point.x, point.y],
                "like_count": likes.get(post.id, 0),
                "comment_count": comments.get(post.id, 0),
                "liked": post.id in liked,
                "following_author": post.author_id in followed,
                "archives": [
                    {
                        "layer_id": a.layer_id,
                        "url": f"/posts/{post.id}/archives/{a.layer_id}",
                        "bounds": a.bounds,
                        "state": "preserved",
                    }
                    for a in post.archives
                ],
                "photos": photos.get(post.id, []),
            }
        )
    return result


async def post_json(db, post, user):
    return (await posts_json(db, [post], user))[0]


def bbox_filter(bounds):
    west, south, east, north = bounds

    def intersects(w, e):
        return func.ST_Intersects(Post.footprint, func.ST_MakeEnvelope(w, south, e, north, 4326))

    return (
        intersects(west, east)
        if west <= east
        else or_(intersects(west, 180), intersects(-180, east))
    )


def parse_bbox(value):
    import math

    try:
        bounds = [float(v) for v in value.split(",")]
    except ValueError as exc:
        raise HTTPException(422, "Use west,south,east,north") from exc
    if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
        raise HTTPException(422, "Use four finite bounds")
    w, s, e, n = bounds
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -85.051129 <= s < n <= 85.051129):
        raise HTTPException(422, "Bounds are out of range")
    return bounds


def encode_cursor(post):
    return base64.urlsafe_b64encode(f"{post.created_at.isoformat()}|{post.id}".encode()).decode()


def decode_cursor(value):
    try:
        date, identifier = base64.urlsafe_b64decode(value.encode()).decode().split("|")
        date = datetime.fromisoformat(date)
        if date.tzinfo is None:
            raise ValueError()
        return date, uuid.UUID(identifier)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, "Invalid cursor") from exc


@router.get("/posts", tags=["discovery"])
async def discover(
    bbox: str | None = None,
    sort: Literal["recent", "top", "following", "most_followed"] = "recent",
    content_type: Literal["analysis", "observation", "question", "photo_report"] | None = None,
    topic: str | None = Query(default=None, max_length=40),
    verified_only: bool = False,
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=10, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Db,
    user: User | None = OptionalUser,
):
    if cursor and sort not in ("recent", "following"):
        raise HTTPException(422, "Cursor pages require Recent or Following")
    likes = select(func.count()).where(Like.post_id == Post.id).correlate(Post).scalar_subquery()
    comments = (
        select(func.count())
        .where(
            Comment.post_id == Post.id,
            Comment.status == "active",
        )
        .correlate(Post)
        .scalar_subquery()
    )
    stmt = select(Post).where(
        Post.status == "active",
        ~blocked_author(user),
        Post.created_at >= datetime.now(UTC) - timedelta(hours=hours),
    )
    if bbox:
        stmt = stmt.where(bbox_filter(parse_bbox(bbox)))
    if content_type:
        stmt = stmt.where(Post.content_type == content_type)
    if topic:
        stmt = stmt.where(Post.topics.contains([topic]))
    if verified_only:
        stmt = stmt.join(User, Post.author_id == User.id).where(User.verified_role.is_not(None))
    if sort == "following":
        if user is None:
            raise HTTPException(401, "Sign in to see people you follow")
        stmt = stmt.where(
            exists(
                select(Follow.target_id).where(
                    Follow.follower_id == user.id,
                    Follow.target_type == "person",
                    Follow.target_id == Post.author_id,
                )
            )
        )
    if cursor:
        date, identifier = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Post.created_at, Post.id) < tuple_(date, identifier))
    if sort == "top":
        stmt = stmt.order_by(top_score(likes, comments, func.now()).desc())
    if sort == "most_followed":
        followers = (
            select(func.count())
            .where(
                Follow.target_type == "person",
                Follow.target_id == Post.author_id,
            )
            .correlate(Post)
            .scalar_subquery()
        )
        stmt = stmt.order_by(followers.desc())
    stmt = stmt.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit + 1)
    rows = (await db.scalars(stmt)).all()
    selected = rows[:limit]
    return {
        "items": await posts_json(db, selected, user),
        "next_cursor": encode_cursor(selected[-1])
        if len(rows) > limit and sort in ("recent", "following")
        else None,
    }


@router.post("/posts", status_code=201, tags=["annotations"])
async def create_post(
    body: PostCreate, request: Request, db: AsyncSession = Db, user: User = RequiredUser
):
    await quota(str(user.id), "post", 6)
    photos = []
    for identifier in body.photo_ids:
        media = await db.get(Media, identifier)
        if media is None or media.owner_id != user.id or media.post_id is not None:
            raise HTTPException(422, "A photo is unavailable or belongs to another account")
        photos.append(media)
    post_id = uuid.uuid4()
    archives = []
    for layer in body.context.layers:
        if layer.opacity == 0:
            continue
        try:
            raster = await request.app.state.radar.capture(layer, body.context.bounds)
            key = f"radar/{post_id}/{layer.id}.png"
            await request.app.state.storage.put(key, raster, "image/png")
        except SourceError as exc:
            raise HTTPException(503, {"state": exc.state, "message": exc.message}) from exc
        except Exception as exc:
            raise HTTPException(
                503, "Could not preserve the radar layer; your draft is still available"
            ) from exc
        archives.append(
            LayerArchive(
                post_id=post_id,
                layer_id=layer.id,
                object_key=key,
                bounds=body.context.bounds,
            )
        )
    if not archives:
        raise HTTPException(422, "At least one visible weather layer is required")
    footprint = GeometryCollection([shape(element.geometry) for element in body.elements])
    post = Post(
        id=post_id,
        author_id=user.id,
        content_type=body.content_type,
        title=body.title,
        description=body.description,
        why_it_matters=body.why_it_matters,
        watch_next=body.watch_next,
        topics=body.topics,
        footprint=from_shape(footprint, srid=4326),
        context=ContextRecord(data=body.context.model_dump(mode="json")),
        elements=[
            ElementRecord(id=e.id, position=i, data=e.model_dump(mode="json"))
            for i, e in enumerate(body.elements)
        ],
        archives=archives,
    )
    db.add(post)
    await db.flush()
    for media in photos:
        media.post_id = post_id
    # Fanout uses INSERT SELECT; no in-memory follower list or invented emergency alert type.
    follower_query = select(
        func.gen_random_uuid(),
        Follow.follower_id,
        literal(user.id),
        literal("followed_post"),
        literal(post_id),
        func.now(),
    ).where(
        Follow.target_type == "person",
        Follow.target_id == user.id,
        ~exists(
            select(Block.blocker_id).where(
                or_(
                    and_(Block.blocker_id == user.id, Block.blocked_id == Follow.follower_id),
                    and_(Block.blocked_id == user.id, Block.blocker_id == Follow.follower_id),
                )
            )
        ),
    )
    await db.execute(
        insert(Notification).from_select(
            ["id", "recipient_id", "actor_id", "kind", "post_id", "created_at"],
            follower_query,
        )
    )
    await db.commit()
    loaded = await visible_post(db, post_id, user)
    return await post_json(db, loaded, user)


@router.get("/posts/{post_id}", tags=["annotations"])
async def get_post(post_id: uuid.UUID, db: AsyncSession = Db, user: User | None = OptionalUser):
    return await post_json(db, await visible_post(db, post_id, user), user)


@router.delete("/posts/{post_id}", status_code=204, tags=["annotations"])
async def remove_post(post_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser):
    post = await db.get(Post, post_id)
    if not post or post.author_id != user.id:
        raise HTTPException(404, "Your annotation was not found")
    post.status, post.moderation_reason = "removed", "Deleted by author"
    await db.commit()


@router.get("/posts/{post_id}/archives/{layer_id}", tags=["replay"])
async def archive(
    post_id: uuid.UUID,
    layer_id: str,
    request: Request,
    db: AsyncSession = Db,
    user: User | None = OptionalUser,
):
    post = await visible_post(db, post_id, user)
    stored = next((a for a in post.archives if a.layer_id == layer_id), None)
    if not stored:
        raise HTTPException(404, "Preserved radar layer not found")
    try:
        data = await request.app.state.storage.get(stored.object_key)
    except Exception as exc:
        raise HTTPException(503, "Preserved layer temporarily unavailable") from exc
    return Response(data, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.put("/posts/{post_id}/like", status_code=204, tags=["social"])
async def like(post_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser):
    await quota(str(user.id), "like", 60)
    await visible_post(db, post_id, user)
    await db.execute(insert(Like).values(post_id=post_id, user_id=user.id).on_conflict_do_nothing())
    await db.commit()


@router.delete("/posts/{post_id}/like", status_code=204, tags=["social"])
async def unlike(post_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser):
    await visible_post(db, post_id, user)
    await db.execute(delete(Like).where(Like.post_id == post_id, Like.user_id == user.id))
    await db.commit()


def comment_json(comment):
    return {
        "id": str(comment.id),
        "post_id": str(comment.post_id),
        "parent_id": str(comment.parent_id) if comment.parent_id else None,
        "author": profile(comment.author),
        "body": comment.body,
        "created_at": comment.created_at,
    }


@router.get("/posts/{post_id}/comments", tags=["discussion"])
async def comments(
    post_id: uuid.UUID,
    db: AsyncSession = Db,
    user: User | None = OptionalUser,
    cursor: str | None = Query(default=None, max_length=200),
):
    await visible_post(db, post_id, user)
    stmt = select(Comment).where(Comment.post_id == post_id, Comment.status == "active")
    if user:
        stmt = stmt.where(
            ~exists(
                select(Block.blocker_id).where(
                    or_(
                        and_(Block.blocker_id == user.id, Block.blocked_id == Comment.author_id),
                        and_(Block.blocked_id == user.id, Block.blocker_id == Comment.author_id),
                    )
                )
            )
        )
    if cursor:
        time, identifier = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Comment.created_at, Comment.id) < tuple_(time, identifier))
    rows = (
        await db.scalars(stmt.order_by(Comment.created_at.desc(), Comment.id.desc()).limit(51))
    ).all()
    return {
        "items": [comment_json(c) for c in rows[:50]],
        "next_cursor": encode_cursor(rows[49]) if len(rows) > 50 else None,
    }


@router.post("/posts/{post_id}/comments", status_code=201, tags=["discussion"])
async def add_comment(
    post_id: uuid.UUID, body: CommentCreate, db: AsyncSession = Db, user: User = RequiredUser
):
    await quota(str(user.id), "comment", 20)
    post = await visible_post(db, post_id, user)
    parent = await db.get(Comment, body.parent_id) if body.parent_id else None
    if body.parent_id and (
        parent is None
        or parent.post_id != post_id
        or parent.parent_id is not None
        or parent.status != "active"
        or await users_blocked(db, user.id, parent.author_id)
    ):
        raise HTTPException(422, "Reply to a visible top-level comment on this post")
    comment = Comment(post_id=post_id, author_id=user.id, body=body.body, parent_id=body.parent_id)
    db.add(comment)
    await db.flush()
    for recipient in {post.author_id, parent.author_id if parent else post.author_id} - {user.id}:
        if not await users_blocked(db, user.id, recipient):
            db.add(
                Notification(
                    recipient_id=recipient,
                    actor_id=user.id,
                    kind="reply",
                    post_id=post_id,
                    comment_id=comment.id,
                )
            )
    await db.commit()
    await db.refresh(comment, ["author"])
    return comment_json(comment)


@router.delete("/comments/{comment_id}", status_code=204, tags=["discussion"])
async def remove_comment(comment_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser):
    comment = await db.get(Comment, comment_id)
    if comment is None or comment.author_id != user.id:
        raise HTTPException(404, "Your comment was not found")
    comment.status = "removed"
    await db.commit()


@router.get("/profiles/{user_id}", tags=["profiles"])
async def get_profile(user_id: uuid.UUID, db: AsyncSession = Db, user: User | None = OptionalUser):
    author = await db.get(User, user_id)
    if (
        author is None
        or not author.is_active
        or (user and await users_blocked(db, user.id, user_id))
    ):
        raise HTTPException(404, "Profile not found")
    return {
        **profile(author),
        "followers": await db.scalar(
            select(func.count())
            .select_from(Follow)
            .where(
                Follow.target_type == "person",
                Follow.target_id == user_id,
            )
        ),
        "following": bool(user and await db.get(Follow, (user.id, "person", user_id))),
    }


@router.put("/profiles/{user_id}/follow", status_code=204, tags=["social"])
async def follow(user_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser):
    await quota(str(user.id), "follow", 30)
    if user_id == user.id:
        raise HTTPException(422, "You cannot follow yourself")
    await get_profile(user_id, db, user)
    await db.execute(
        insert(Follow)
        .values(
            follower_id=user.id,
            target_type="person",
            target_id=user_id,
        )
        .on_conflict_do_nothing()
    )
    await db.commit()


@router.delete("/profiles/{user_id}/follow", status_code=204, tags=["social"])
async def unfollow(user_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser):
    await db.execute(
        delete(Follow).where(
            Follow.follower_id == user.id,
            Follow.target_type == "person",
            Follow.target_id == user_id,
        )
    )
    await db.commit()


@router.put("/profiles/{user_id}/block", status_code=204, tags=["moderation"])
async def block(user_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser):
    if user_id == user.id or await db.get(User, user_id) is None:
        raise HTTPException(422, "Choose another account")
    await db.execute(
        insert(Block).values(blocker_id=user.id, blocked_id=user_id).on_conflict_do_nothing()
    )
    await db.execute(
        delete(Follow).where(
            Follow.target_type == "person",
            or_(
                and_(Follow.follower_id == user.id, Follow.target_id == user_id),
                and_(Follow.follower_id == user_id, Follow.target_id == user.id),
            ),
        )
    )
    await db.commit()


@router.delete("/profiles/{user_id}/block", status_code=204, tags=["moderation"])
async def unblock(user_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser):
    await db.execute(delete(Block).where(Block.blocker_id == user.id, Block.blocked_id == user_id))
    await db.commit()


@router.post("/reports", status_code=201, tags=["moderation"])
async def report(body: ReportCreate, db: AsyncSession = Db, user: User = RequiredUser):
    await quota(str(user.id), "report", 10)
    if body.target_type == "post":
        await visible_post(db, body.target_id, user)
    else:
        comment = await db.get(Comment, body.target_id)
        if (
            comment is None
            or comment.status != "active"
            or await users_blocked(db, user.id, comment.author_id)
        ):
            raise HTTPException(404, "Comment not found")
        await visible_post(db, comment.post_id, user)
    await db.execute(
        insert(Report)
        .values(
            reporter_id=user.id,
            target_type=body.target_type,
            target_id=body.target_id,
            reason=body.reason,
        )
        .on_conflict_do_nothing(index_elements=["reporter_id", "target_type", "target_id"])
    )
    await db.commit()
    return {"status": "reported"}


async def moderator(user: User = RequiredUser):
    if not (user.is_moderator or user.is_superuser):
        raise HTTPException(403, "Moderator access required")
    return user


@router.get("/moderation/reports", tags=["moderation"])
async def moderation_reports(db: AsyncSession = Db, user: User = Depends(moderator)):
    rows = (
        await db.scalars(
            select(Report).where(Report.status == "open").order_by(Report.created_at).limit(100)
        )
    ).all()
    return [
        {
            "id": r.id,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "reason": r.reason,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/moderation/actions", status_code=201, tags=["moderation"])
async def moderate(body: ModerationCreate, db: AsyncSession = Db, user: User = Depends(moderator)):
    target = await db.get(Post if body.target_type == "post" else Comment, body.target_id)
    if target is None:
        raise HTTPException(404, "Content not found")
    db.add(
        ModerationAction(
            moderator_id=user.id,
            target_type=body.target_type,
            target_id=body.target_id,
            previous_status=target.status,
            new_status=body.status,
            reason=body.reason,
        )
    )
    target.status = body.status
    if isinstance(target, Post):
        target.moderation_reason = body.reason
    for report_row in (
        await db.scalars(
            select(Report).where(
                Report.target_type == body.target_type,
                Report.target_id == body.target_id,
                Report.status == "open",
            )
        )
    ).all():
        report_row.status = "reviewed"
    await db.commit()
    return {"status": body.status}


@router.post("/media", status_code=201, tags=["media"])
async def upload_media(
    request: Request, file: UploadFile = File(), db: AsyncSession = Db, user: User = RequiredUser
):
    await quota(str(user.id), "photo", 8)
    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Photos must be 5 MB or smaller")
    try:
        image = Image.open(io.BytesIO(data))
        image.thumbnail((2048, 2048))
        output = io.BytesIO()
        image.convert("RGB").save(output, "JPEG", quality=85)  # Strip EXIF/location metadata.
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Choose a valid, reasonably sized image") from exc
    media = Media(id=uuid.uuid4(), owner_id=user.id, object_key=f"photos/{uuid.uuid4()}.jpg")
    try:
        await request.app.state.storage.put(media.object_key, output.getvalue(), "image/jpeg")
    except Exception as exc:
        raise HTTPException(503, "Photo storage temporarily unavailable") from exc
    db.add(media)
    await db.commit()
    return {"id": str(media.id)}


@router.get("/media/{media_id}", tags=["media"])
async def get_media(
    media_id: uuid.UUID, request: Request, db: AsyncSession = Db, user: User | None = OptionalUser
):
    media = await db.get(Media, media_id)
    if media is None:
        raise HTTPException(404, "Photo not found")
    if media.post_id:
        await visible_post(db, media.post_id, user)
    elif user is None or user.id != media.owner_id:
        raise HTTPException(404, "Photo not found")
    try:
        data = await request.app.state.storage.get(media.object_key)
    except Exception as exc:
        raise HTTPException(503, "Photo temporarily unavailable") from exc
    return Response(
        data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"}
    )


@router.get("/notifications", tags=["notifications"])
async def notifications(db: AsyncSession = Db, user: User = RequiredUser):
    rows = (
        await db.scalars(
            select(Notification)
            .join(Post, Notification.post_id == Post.id)
            .where(
                Notification.recipient_id == user.id,
                Post.status == "active",
                ~blocked_author(user),
                ~exists(
                    select(Block.blocker_id).where(
                        or_(
                            and_(
                                Block.blocker_id == user.id,
                                Block.blocked_id == Notification.actor_id,
                            ),
                            and_(
                                Block.blocked_id == user.id,
                                Block.blocker_id == Notification.actor_id,
                            ),
                        )
                    )
                ),
            )
            .order_by(Notification.created_at.desc())
            .limit(50)
        )
    ).all()
    return [
        {
            "id": n.id,
            "kind": n.kind,
            "actor_id": n.actor_id,
            "post_id": n.post_id,
            "comment_id": n.comment_id,
            "created_at": n.created_at,
            "read_at": n.read_at,
        }
        for n in rows
    ]


@router.put("/notifications/{notification_id}/read", status_code=204, tags=["notifications"])
async def read_notification(
    notification_id: uuid.UUID, db: AsyncSession = Db, user: User = RequiredUser
):
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.recipient_id != user.id:
        raise HTTPException(404, "Notification not found")
    notification.read_at = datetime.now(UTC)
    await db.commit()
