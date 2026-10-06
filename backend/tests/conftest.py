import asyncio
import io
import os
from datetime import UTC, datetime

os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from wxspot.database import Base, engine
from wxspot.main import app
from wxspot.storage import LocalStorage
from wxspot.weather import SourceError


class FixtureRadar:
    """Explicit test provider. Never used by production."""

    time = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
    id = "KCLX:reflectivity:2026-10-06T15:00:00.000Z"

    async def frames(self, site="KCLX", product="reflectivity"):
        return {
            "state": "ready",
            "frames": [
                {
                    "id": self.id,
                    "valid_time": self.time.isoformat(),
                    "site": site,
                    "product": product,
                },
                {
                    "id": "KCLX:reflectivity:2026-10-06T15:06:00.000Z",
                    "valid_time": "2026-10-06T15:06:00+00:00",
                    "site": site,
                    "product": product,
                },
            ],
        }

    async def capture(self, layer, bounds):
        if layer.frame_id != self.id or layer.valid_time != self.time:
            raise SourceError("no_data", "Expired scan")
        image = Image.new("RGBA", (16, 16), (0, 200, 100, 128))
        data = io.BytesIO()
        image.save(data, "PNG")
        return data.getvalue()


@pytest.fixture
def client(tmp_path):
    async def reset():
        async with engine.begin() as db:
            names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            await db.execute(text(f"TRUNCATE {names} CASCADE"))
        await engine.dispose()

    asyncio.run(reset())
    with TestClient(app) as test_client:
        app.state.radar = FixtureRadar()
        app.state.storage = LocalStorage(tmp_path)
        yield test_client


def register(client, email="first@example.com", display="First"):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "A reasonably strong passphrase!",
            "display_name": display,
        },
    )
    assert response.status_code == 201, response.text
    account = response.json()
    login = client.post(
        "/auth/login",
        data={
            "username": email,
            "password": "A reasonably strong passphrase!",
        },
    )
    assert login.status_code == 200, login.text
    return account, {"Authorization": "Bearer " + login.json()["access_token"]}


def payload():
    import uuid

    return {
        "content_type": "analysis",
        "title": "Watch this boundary",
        "description": "The leading edge is worth following through the next scans.",
        "why_it_matters": "It may initiate new convection.",
        "watch_next": "Look for new returns on the eastern edge.",
        "topics": ["boundary"],
        "context": {
            "version": 1,
            "captured_at": "2026-10-06T15:02:00Z",
            "camera": {"center": [-80.18, 33.02], "zoom": 8, "bearing": 24, "pitch": 10},
            "bounds": [-81, 32, -79, 34],
            "layers": [
                {
                    "id": "radar",
                    "provider": "nws-ridge2",
                    "source_type": "radar",
                    "product": "reflectivity",
                    "frame_id": FixtureRadar.id,
                    "valid_time": "2026-10-06T15:00:00Z",
                    "radar_site": "KCLX",
                    "opacity": 0.8,
                }
            ],
        },
        "elements": [
            {
                "id": str(uuid.uuid4()),
                "tool": "arrow",
                "geometry": {"type": "LineString", "coordinates": [[-80.18, 33.02], [-80.1, 33.1]]},
                "color": "#67E8F9",
                "stroke": 3,
                "label": None,
            }
        ],
    }
