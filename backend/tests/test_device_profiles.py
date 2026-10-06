import asyncio
import hashlib
import uuid
from datetime import timedelta

from conftest import payload
from sqlalchemy import func, select

from wxspot.database import sessions
from wxspot.models import AccessToken, DeviceProfile, User, now


def guest(client, resume_key=None):
    response = client.post(
        "/auth/guest", json={} if resume_key is None else {"resume_key": resume_key}
    )
    assert response.status_code in (200, 201), response.text
    data = response.json()
    return data, {"Authorization": "Bearer " + data["access_token"]}


def test_guest_creation_resume_and_device_isolation(client):
    first, first_headers = guest(client)
    second, second_headers = guest(client)
    assert first["user_id"] != second["user_id"]
    assert first["resume_key"] != second["resume_key"]
    resumed, headers = guest(client, first["resume_key"])
    assert resumed["user_id"] == first["user_id"]
    assert resumed["access_token"] != first["access_token"]
    assert client.get("/account", headers=headers).json()["id"] == first["user_id"]
    assert client.get("/account", headers=second_headers).json()["id"] == second["user_id"]
    assert not client.get("/account", headers=first_headers).json()["is_moderator"]

    async def stored():
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(DeviceProfile)) == 2
            credential = await db.get(
                DeviceProfile, hashlib.sha256(first["resume_key"].encode()).hexdigest()
            )
            assert credential.user_id == uuid.UUID(first["user_id"])
            assert await db.get(DeviceProfile, first["resume_key"]) is None
            user = await db.get(User, credential.user_id)
            assert not user.is_superuser and not user.is_moderator and not user.is_verified
            assert user.verified_role is None

    asyncio.run(stored())


def test_guest_renewal_after_expiry_keeps_posts_and_social_ownership(client):
    author, headers = guest(client)
    post = client.post("/posts", headers=headers, json=payload()).json()
    assert client.put(f"/posts/{post['id']}/like", headers=headers).status_code == 204

    async def expire():
        async with sessions() as db:
            token = await db.get(AccessToken, author["access_token"])
            token.created_at = now() - timedelta(days=8)
            await db.commit()

    asyncio.run(expire())
    assert client.get("/account", headers=headers).status_code == 401
    resumed, headers = guest(client, author["resume_key"])
    assert resumed["user_id"] == author["user_id"]
    assert client.get(f"/posts/{post['id']}", headers=headers).json()["liked"]
    assert client.delete(f"/posts/{post['id']}", headers=headers).status_code == 204


def test_invalid_or_disabled_device_cannot_create_replacement_or_escalate(client):
    identity, _ = guest(client)
    assert client.post("/auth/guest", json={"resume_key": "X" * 43}).status_code == 401
    assert client.post("/auth/guest", json={"resume_key": "short"}).status_code == 422
    assert client.post("/auth/guest", json={"is_moderator": True}).status_code == 422

    async def disable():
        async with sessions() as db:
            user = await db.get(User, uuid.UUID(identity["user_id"]))
            user.is_active = False
            await db.commit()

    asyncio.run(disable())
    assert (
        client.post("/auth/guest", json={"resume_key": identity["resume_key"]}).status_code == 401
    )

    async def no_replacement():
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(DeviceProfile)) == 1

    asyncio.run(no_replacement())


def test_two_guests_publish_restore_like_comment_follow_and_report(client):
    author, author_headers = guest(client)
    viewer, viewer_headers = guest(client)
    original = payload()
    response = client.post("/posts", headers=author_headers, json=original)
    assert response.status_code == 201, response.text
    post = response.json()
    restored = client.get(f"/posts/{post['id']}", headers=viewer_headers).json()
    assert restored["elements"] == original["elements"]
    assert (
        restored["context"]["layers"][0]["frame_id"] == original["context"]["layers"][0]["frame_id"]
    )
    assert client.delete(f"/posts/{post['id']}", headers=viewer_headers).status_code == 404
    assert client.put(f"/posts/{post['id']}/like", headers=viewer_headers).status_code == 204
    assert (
        client.put(f"/profiles/{author['user_id']}/follow", headers=viewer_headers).status_code
        == 204
    )
    comment = client.post(
        f"/posts/{post['id']}/comments",
        headers=viewer_headers,
        json={"body": "What should I watch next?"},
    )
    assert comment.status_code == 201
    assert comment.json()["author"]["id"] == viewer["user_id"]
    assert (
        client.get("/posts?sort=following", headers=viewer_headers).json()["items"][0]["id"]
        == post["id"]
    )
    report = {"target_type": "post", "target_id": post["id"], "reason": "Please review"}
    assert client.post("/reports", headers=viewer_headers, json=report).status_code == 201
    assert client.get("/moderation/reports", headers=viewer_headers).status_code == 403
    assert (
        client.post(
            "/moderation/actions", headers=viewer_headers, json={**report, "status": "removed"}
        ).status_code
        == 403
    )


def test_profile_edit_and_block_controls_are_private_and_resume_persists_name(client):
    owner, headers = guest(client)
    other, other_headers = guest(client)
    assert client.patch("/account", json={"display_name": "Name"}).status_code == 401
    update = client.patch("/account", headers=headers, json={"display_name": "  Weather learner  "})
    assert update.status_code == 200
    assert update.json()["display_name"] == "Weather learner"
    assert client.patch("/account", headers=headers, json={"display_name": "  "}).status_code == 422
    assert (
        client.patch(
            "/account",
            headers=headers,
            json={"display_name": "Name", "verified_role": "meteorologist"},
        ).status_code
        == 422
    )
    resumed, _ = guest(client, owner["resume_key"])
    assert resumed["display_name"] == "Weather learner"
    assert client.put(f"/profiles/{other['user_id']}/block", headers=headers).status_code == 204
    assert client.get("/account/blocks", headers=headers).json()[0]["id"] == other["user_id"]
    assert client.get("/account/blocks", headers=other_headers).json() == []
    assert client.delete(f"/profiles/{other['user_id']}/block", headers=headers).status_code == 204
    assert client.get("/account/blocks", headers=headers).json() == []
