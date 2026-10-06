from pathlib import Path

import httpx
import pytest

from wxspot.weather import AlertProvider, RadarProvider, SourceError


@pytest.mark.asyncio
async def test_weather_outage_never_invents_frames():
    def unavailable(request):
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        with pytest.raises(SourceError) as caught:
            await RadarProvider(client).frames()
        assert caught.value.state == "source_unavailable"


@pytest.mark.asyncio
async def test_provider_exposes_explicit_time_tiles_and_official_legend():
    xml = (Path(__file__).parent / "fixtures/kclx-capabilities.xml").read_bytes()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=xml))
    ) as client:
        result = await RadarProvider(client).frames()
    frame = result["frames"][-1]
    assert frame["id"].startswith("KCLX:reflectivity:")
    assert "TIME=" in frame["tile_url"]
    assert "{bbox-epsg-3857}" in frame["tile_url"]
    assert "GetLegendGraphic" in frame["legend_url"]
    assert frame["units"] == "dBZ"


@pytest.mark.asyncio
async def test_alert_outage_is_distinct_from_an_empty_success():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503))
    ) as client:
        result = await AlertProvider(client).active()
    assert result["state"] == "source_unavailable"
    assert result["collection"]["features"] == []


@pytest.mark.asyncio
async def test_expired_alerts_are_removed_but_null_geometry_is_not_fabricated():
    features = [
        {
            "geometry": None,
            "properties": {
                "id": "active",
                "expires": "2099-01-01T00:00:00Z",
                "event": "Flood Advisory",
            },
        },
        {"geometry": None, "properties": {"id": "expired", "expires": "2000-01-01T00:00:00Z"}},
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"features": features}))
    ) as client:
        result = await AlertProvider(client).active()
    assert len(result["collection"]["features"]) == 1
    assert result["collection"]["features"][0]["geometry"] is None
    assert result["collection"]["features"][0]["properties"]["official"] is True
