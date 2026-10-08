"""Replay/access audit with isolated providers; real sources run in device acceptance."""

import asyncio
import io
from datetime import UTC, datetime, timedelta

import pytest
from conftest import app, payload, register
from PIL import Image

from wxspot.database import engine, sessions
from wxspot.models import WeatherArtifact, WeatherCache
from wxspot.weather import SourceError, WeatherProviderRegistry
from wxspot.workers.weather import cleanup

CASES = [
    ("radar", "nws-ridge2", "reflectivity", {}),
    ("radar", "noaa-mrms", "precip_1h", {"metadata": {"units": "mm", "period": "PT1H"}}),
    (
        "satellite",
        "noaa-goes",
        "infrared",
        {"satellite": "G19", "metadata": {"channel": "C13"}},
    ),
    (
        "model",
        "noaa-models",
        "temperature",
        {"model": "hrrr", "run_time": "2026-10-06T12:00:00Z", "forecast_hour": 3},
    ),
    (
        "model",
        "noaa-models",
        "wind",
        {"model": "gfs", "run_time": "2026-10-06T12:00:00Z", "forecast_hour": 3},
    ),
]


class AuditProvider:
    """Only checks the publishing boundary, never supplies app or live weather."""

    def __init__(self, layer):
        self.source_type, self.provider_id = layer["source_type"], layer["provider"]
        self.layer = layer
        self.expired = False
        self.calls = 0
        data = io.BytesIO()
        Image.new("RGBA", (16, 16), (40, 180, 220, 128)).save(data, "PNG")
        self.png = data.getvalue()

    async def capture(self, layer, bounds):
        self.calls += 1
        assert layer.frame_id == self.layer["frame_id"]
        assert layer.model == self.layer.get("model")
        assert layer.forecast_hour == self.layer.get("forecast_hour")
        assert layer.satellite == self.layer.get("satellite")
        assert layer.metadata == self.layer.get("metadata", {})
        assert bounds == [-81, 32, -79, 34]
        if self.expired:
            raise SourceError("no_data", "Live source expired; preserved posts remain available")
        return self.png


@pytest.mark.parametrize("source,provider,product,extra", CASES)
def test_exact_archives_survive_live_expiry_and_enforce_current_access(
    client, source, provider, product, extra
):
    body = payload()
    layer = body["context"]["layers"][0]
    layer.update(source_type=source, provider=provider, product=product, **extra)
    if source != "radar" or provider != "nws-ridge2":
        layer["frame_id"] = f"{source}:{provider}:{extra.get('model', product)}:exact-1500"
        layer["radar_site"] = None
    adapter = AuditProvider(layer)
    app.state.weather = WeatherProviderRegistry([adapter])
    author, headers = register(client)
    _, viewer = register(client, "viewer@example.com")
    created = client.post("/posts", headers=headers, json=body)
    assert created.status_code == 201, created.text
    post = created.json()
    assert post["context"]["camera"] == body["context"]["camera"]
    assert post["context"]["layers"][0]["frame_id"] == layer["frame_id"]
    assert post["elements"] == body["elements"]
    assert "object_key" not in str(post) and "weather-live/" not in str(post)
    archive_url = post["archives"][0]["url"]
    original = client.get(archive_url, headers=viewer)
    assert original.status_code == 200 and original.content == adapter.png
    assert original.headers["cache-control"] == "private, no-store"
    assert original.headers["vary"] == "Authorization"

    adapter.expired = True
    calls = adapter.calls
    assert client.get(archive_url, headers=viewer).content == original.content
    reopened = client.get(f"/posts/{post['id']}", headers=viewer).json()
    assert reopened["context"] == post["context"] and reopened["elements"] == post["elements"]
    assert adapter.calls == calls  # No new upstream access for a preserved post.
    assert client.post("/posts", headers=headers, json=body).status_code == 503
    assert len(client.get("/posts", headers=headers).json()["items"]) == 1

    async def expire_live_objects():
        expired = datetime.now(UTC) - timedelta(minutes=1)
        live_key = "weather-live/audit-expired.png"
        try:
            await app.state.storage.put(live_key, b"temporary", "image/png")
            async with sessions() as db:
                db.add(WeatherArtifact(object_key=live_key, expires_at=expired))
                db.add(
                    WeatherCache(
                        content_key="audit-expired", kind="audit", manifest={}, expires_at=expired
                    )
                )
                await db.commit()
            await cleanup(app.state.storage)
            with pytest.raises(FileNotFoundError):
                await app.state.storage.get(live_key)
        finally:
            await engine.dispose()

    asyncio.run(expire_live_objects())
    assert client.get(archive_url, headers=viewer).content == original.content
    blocked = f"/profiles/{author['id']}/block"
    assert client.put(blocked, headers=viewer).status_code == 204
    assert client.get(archive_url, headers=viewer).status_code == 404
    assert client.get(f"/posts/{post['id']}", headers=viewer).status_code == 404
    assert client.get(archive_url, headers=headers).status_code == 200
    assert client.delete(blocked, headers=viewer).status_code == 204
    assert client.get(archive_url, headers=viewer).content == original.content
    assert client.delete(f"/posts/{post['id']}", headers=headers).status_code == 204
    assert client.get(archive_url).status_code == 404
    assert client.get(archive_url, headers=headers).status_code == 404


def test_original_v1_radar_post_remains_readable_without_optional_phase2_fields(client):
    _, headers = register(client)
    body = payload()
    assert body["context"]["layers"][0]["frame_id"].startswith("KCLX:")
    response = client.post("/posts", headers=headers, json=body)
    assert response.status_code == 201, response.text
    post = response.json()
    assert post["context"]["version"] == 1
    assert post["context"]["layers"][0]["source_type"] == "radar"
    assert client.get(post["archives"][0]["url"]).status_code == 200
