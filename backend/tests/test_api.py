import asyncio
import io
import uuid
from datetime import UTC, datetime, timedelta

from conftest import app, payload, register
from PIL import Image
from sqlalchemy import select

from wxspot.database import sessions
from wxspot.models import ModerationAction, Post, User, now
from wxspot.providers.mrms import MrmsProvider
from wxspot.providers.nexrad import NexradLevel3Provider
from wxspot.weather import RadarWeatherAdapter, WeatherProviderRegistry
from wxspot.weather_contracts import WeatherFramesResponse


def create(client, headers, body=None):
    response = client.post("/posts", headers=headers, json=body or payload())
    assert response.status_code == 201, response.text
    return response.json()


def test_two_account_capture_persist_retrieve_archive(client):
    assert client.get("/weather/radar/frames").status_code == 200
    assert client.get("/posts?bbox=-81,32,-79,34").json()["items"] == []
    author, token = register(client)
    post = create(client, token)
    viewer, viewer_token = register(client, "second@example.com", "Second")
    reopened = client.get(f"/posts/{post['id']}", headers=viewer_token).json()
    assert reopened["context"] == post["context"]
    assert reopened["elements"] == post["elements"]
    assert reopened["context"]["camera"] == payload()["context"]["camera"]
    frames = client.get("/weather/radar/frames").json()["frames"]
    assert frames[0]["id"] == reopened["context"]["layers"][0]["frame_id"]
    assert frames[1]["id"] != frames[0]["id"]
    # Source archive remains independently available while the client scrubs another scan.
    archive = client.get(reopened["archives"][0]["url"], headers=viewer_token)
    assert archive.status_code == 200 and archive.content.startswith(b"\x89PNG")
    assert client.get(f"/posts/{post['id']}").json()["elements"] == reopened["elements"]
    assert author["id"] != viewer["id"]


def test_anonymous_account_actions_require_auth(client):
    assert client.post("/posts", json=payload()).status_code == 401
    identifier = uuid.uuid4()
    for path in (f"/posts/{identifier}/like", f"/profiles/{identifier}/follow"):
        assert client.put(path).status_code == 401
    assert client.post(f"/posts/{identifier}/comments", json={"body": "test"}).status_code == 401
    assert (
        client.post(
            "/reports",
            json={
                "target_type": "post",
                "target_id": str(identifier),
                "reason": "Misleading",
            },
        ).status_code
        == 401
    )


def test_like_idempotency_and_unlike(client):
    _, headers = register(client)
    post = create(client, headers)
    path = f"/posts/{post['id']}/like"
    assert client.put(path, headers=headers).status_code == 204
    assert client.put(path, headers=headers).status_code == 204
    assert client.get(f"/posts/{post['id']}", headers=headers).json()["like_count"] == 1
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(f"/posts/{post['id']}").json()["like_count"] == 0


def test_follow_and_notifications(client):
    author, author_headers = register(client)
    follower, follower_headers = register(client, "follower@example.com")
    path = f"/profiles/{author['id']}/follow"
    assert client.put(path, headers=follower_headers).status_code == 204
    assert client.put(path, headers=follower_headers).status_code == 204
    assert client.get(f"/profiles/{author['id']}").json()["followers"] == 1
    post = create(client, author_headers)
    assert (
        client.get("/posts?sort=following", headers=follower_headers).json()["items"][0]["id"]
        == post["id"]
    )
    assert (
        client.get("/notifications", headers=follower_headers).json()[0]["kind"] == "followed_post"
    )
    assert (
        client.put(f"/profiles/{follower['id']}/follow", headers=follower_headers).status_code
        == 422
    )
    assert client.delete(path, headers=follower_headers).status_code == 204


def test_comments_thread_scope_and_deletion(client):
    author, headers = register(client)
    _, second = register(client, "second@example.com")
    post, other = create(client, headers), create(client, headers)
    path = f"/posts/{post['id']}/comments"
    parent = client.post(path, headers=headers, json={"body": "What should I watch?"}).json()
    reply = client.post(
        path, headers=second, json={"body": "The eastern edge.", "parent_id": parent["id"]}
    )
    assert reply.status_code == 201
    assert (
        client.post(
            path,
            headers=second,
            json={
                "body": "Too deep",
                "parent_id": reply.json()["id"],
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/posts/{other['id']}/comments",
            headers=headers,
            json={
                "body": "Wrong post",
                "parent_id": parent["id"],
            },
        ).status_code
        == 422
    )
    assert client.delete(f"/comments/{parent['id']}", headers=second).status_code == 404
    assert client.delete(f"/comments/{parent['id']}", headers=headers).status_code == 204
    assert len(client.get(path).json()["items"]) == 1


def test_viewport_filters_cursor_and_dateline(client):
    _, headers = register(client)
    post = create(client, headers)
    assert (
        len(
            client.get("/posts?bbox=-81,32,-79,34&topic=boundary&content_type=analysis").json()[
                "items"
            ]
        )
        == 1
    )
    assert client.get("/posts?bbox=-100,20,-90,30").json()["items"] == []
    assert client.get("/posts?bbox=170,-10,-170,10").json()["items"] == []
    assert client.get("/posts?verified_only=true").json()["items"] == []
    newer = create(client, headers)
    page = client.get("/posts?limit=1").json()
    assert page["items"][0]["id"] == newer["id"] and page["next_cursor"]
    next_page = client.get("/posts", params={"limit": 1, "cursor": page["next_cursor"]}).json()
    assert next_page["items"][0]["id"] == post["id"]


def test_top_time_decay_and_most_followed(client):
    author, headers = register(client)
    other, other_headers = register(client, "other@example.com")
    older, newer = create(client, headers), create(client, other_headers)

    async def age():
        async with sessions() as db:
            old = await db.get(Post, uuid.UUID(older["id"]))
            old.created_at = now() - timedelta(hours=23)
            await db.commit()

    asyncio.run(age())
    client.put(f"/posts/{older['id']}/like", headers=headers)
    client.put(f"/profiles/{author['id']}/follow", headers=other_headers)
    assert client.get("/posts?sort=top").json()["items"][0]["id"] == newer["id"]
    assert client.get("/posts?sort=most_followed").json()["items"][0]["id"] == older["id"]


def test_block_bidirectional_visibility(client):
    author, headers = register(client)
    viewer, second = register(client, "viewer@example.com")
    post = create(client, headers)
    client.put(f"/profiles/{author['id']}/follow", headers=second)
    assert client.put(f"/profiles/{author['id']}/block", headers=second).status_code == 204
    assert client.get("/posts", headers=second).json()["items"] == []
    assert client.get(f"/posts/{post['id']}", headers=second).status_code == 404
    assert client.get(f"/profiles/{viewer['id']}", headers=headers).status_code == 404
    assert client.get(f"/profiles/{author['id']}").json()["followers"] == 0
    assert client.delete(f"/profiles/{author['id']}/block", headers=second).status_code == 204
    assert len(client.get("/posts", headers=second).json()["items"]) == 1


def test_moderation_permissions_and_preserved_evidence(client):
    account, headers = register(client)
    post = create(client, headers)
    body = {"target_type": "post", "target_id": post["id"], "reason": "Misleading analysis"}
    assert client.post("/reports", headers=headers, json=body).status_code == 201
    assert (
        client.post(
            "/moderation/actions", headers=headers, json={**body, "status": "removed"}
        ).status_code
        == 403
    )

    async def grant():
        async with sessions() as db:
            user = await db.get(User, uuid.UUID(account["id"]))
            user.is_moderator = True
            await db.commit()

    asyncio.run(grant())
    assert len(client.get("/moderation/reports", headers=headers).json()) == 1
    assert (
        client.post(
            "/moderation/actions", headers=headers, json={**body, "status": "removed"}
        ).status_code
        == 201
    )
    assert client.get(f"/posts/{post['id']}").status_code == 404

    async def preserved():
        async with sessions() as db:
            assert await db.get(Post, uuid.UUID(post["id"])) is not None
            assert await db.scalar(select(ModerationAction.id)) is not None

    asyncio.run(preserved())


def test_registration_cannot_escalate_or_verify_role(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "Another long test passphrase",
            "display_name": "Fake official",
            "self_role": "meteorologist",
            "is_superuser": True,
            "is_moderator": True,
            "verified_role": "meteorologist",
        },
    )
    assert response.status_code == 201
    assert response.json()["is_superuser"] is False and response.json()["verified_role"] is None


def test_logout_revokes_session(client):
    _, headers = register(client)
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.post("/posts", headers=headers, json=payload()).status_code == 401


def test_generic_weather_contract_keeps_radar_compatibility(client):
    app.state.weather = WeatherProviderRegistry(
        [
            RadarWeatherAdapter(app.state.radar),
            MrmsProvider(None),
            NexradLevel3Provider(None),
        ]
    )
    catalog = client.get("/weather/catalog")
    assert catalog.status_code == 200
    assert catalog.headers["cache-control"].startswith("public")
    products = catalog.json()["products"]
    ridge2_products = [item for item in products if item["provider"] == "nws-ridge2"]
    assert {item["product_id"] for item in ridge2_products} == {
        "reflectivity",
        "velocity",
    }
    assert {item["provider"] for item in products} >= {
        "nws-ridge2",
        "noaa-mrms",
        "noaa-nexrad-level3",
    }

    frames = client.get("/weather/frames?source_type=radar&source_id=nws-ridge2&site=KCLX")
    assert frames.status_code == 200
    assert frames.json()["frames"][0]["id"].startswith("radar:nws-ridge2:KCLX:")
    assert frames.json()["frames"][0]["render"]["kind"] == "xyz"
    assert (
        client.get("/weather/radar/frames").json()["frames"][0]["id"]
        == "KCLX:reflectivity:2026-10-06T15:00:00.000Z"
    )


def test_generic_weather_frames_reject_ambiguous_selections(client):
    response = client.get(
        "/weather/frames?source_type=model&source_id=ncep-nomads&product=temperature-2m"
    )
    assert response.status_code == 422
    assert "explicit model" in response.text

    response = client.get("/weather/frames?source_type=radar&source_id=unknown&site=KCLX")
    assert response.status_code == 200
    assert response.json()["state"] == "unsupported_product"


def test_expired_frame_does_not_publish(client):
    _, headers = register(client)
    body = payload()
    body["context"]["layers"][0]["frame_id"] = "expired"
    response = client.post("/posts", headers=headers, json=body)
    assert response.status_code == 503 and client.get("/posts").json()["items"] == []


def test_photos_are_owned_and_protected(client):
    _, headers = register(client)
    _, other = register(client, "other@example.com")
    data = io.BytesIO()
    Image.new("RGB", (16, 16)).save(data, "JPEG")
    uploaded = client.post(
        "/media", headers=headers, files={"file": ("photo.jpg", data.getvalue(), "image/jpeg")}
    )
    assert uploaded.status_code == 201
    media_id = uploaded.json()["id"]
    assert client.get(f"/media/{media_id}").status_code == 404
    body = payload()
    body["photo_ids"] = [media_id]
    assert client.post("/posts", headers=other, json=body).status_code == 422
    post = create(client, headers, body)
    assert client.get(post["photos"][0]).status_code == 200
    client.delete(f"/posts/{post['id']}", headers=headers)
    assert client.get(post["photos"][0]).status_code == 404


def test_post_rate_limit(client, monkeypatch):
    clock = now().replace(second=10, microsecond=0)

    class QuotaClock(datetime):
        @classmethod
        def now(cls, tz=UTC):
            return clock.astimezone(tz) if tz else clock.replace(tzinfo=None)

    monkeypatch.setattr("wxspot.social.datetime", QuotaClock)
    _, headers = register(client)
    for _ in range(6):
        create(client, headers)
    assert client.post("/posts", headers=headers, json=payload()).status_code == 429
    clock += timedelta(minutes=1)
    create(client, headers)


def test_official_products_separate_from_community(client):
    _, headers = register(client)
    body = payload()
    body["content_type"] = "tornado_warning"
    assert client.post("/posts", headers=headers, json=body).status_code == 422
    assert (
        "official weather"
        in client.get("/openapi.json").json()["paths"]["/weather/alerts"]["get"]["tags"]
    )


def test_model_frame_inventory_route_accepts_latest_and_pinned_runs(client, monkeypatch):
    seen = []

    async def inventory(selection):
        seen.append(selection)
        return WeatherFramesResponse(state="no_data", frames=[])

    monkeypatch.setattr(app.state.weather, "frames", inventory)
    query = "/weather/frames?source_type=model&source_id=noaa-models&product=wind&model=gfs"
    assert client.get(query).status_code == 200
    assert seen[-1].run_time is None and seen[-1].forecast_hour is None
    run = datetime(2026, 10, 6, 12, tzinfo=UTC)
    assert client.get(query, params={"run_time": run.isoformat()}).status_code == 200
    assert seen[-1].run_time == run and seen[-1].forecast_hour is None
