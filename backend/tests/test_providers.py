from pathlib import Path

import httpx
import pytest

from wxspot.weather import (
    AlertProvider,
    RadarProvider,
    RadarWeatherAdapter,
    SourceError,
    WeatherProviderRegistry,
)
from wxspot.weather_contracts import WeatherSelection


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


@pytest.mark.asyncio
async def test_generic_frame_contract_has_source_complete_identity():
    xml = (Path(__file__).parent / "fixtures/kclx-capabilities.xml").read_bytes()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=xml))
    ) as client:
        registry = WeatherProviderRegistry([RadarWeatherAdapter(RadarProvider(client))])
        reflectivity = await registry.frames(
            WeatherSelection(
                source_type="radar",
                source_id="nws-ridge2",
                product_id="reflectivity",
                site="KCLX",
            )
        )
        velocity = await registry.frames(
            WeatherSelection(
                source_type="radar",
                source_id="nws-ridge2",
                product_id="velocity",
                site="KCLX",
            )
        )
    assert reflectivity.frames[0].valid_time == velocity.frames[0].valid_time
    assert reflectivity.frames[0].id != velocity.frames[0].id
    assert reflectivity.frames[0].source_type == "radar"
    assert reflectivity.frames[0].provider == "nws-ridge2"
    assert reflectivity.frames[0].render.url_template.endswith("{bbox-epsg-3857}")


@pytest.mark.asyncio
async def test_weather_registry_does_not_guess_an_unregistered_provider():
    async with httpx.AsyncClient() as client:
        registry = WeatherProviderRegistry([RadarWeatherAdapter(RadarProvider(client))])
        with pytest.raises(SourceError) as caught:
            await registry.frames(
                WeatherSelection(
                    source_type="radar",
                    source_id="unverified-provider",
                    product_id="reflectivity",
                    site="KCLX",
                )
            )
    assert caught.value.state == "unsupported_product"
