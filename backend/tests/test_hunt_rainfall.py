"""Archived MRMS rainfall is scientific evidence, not inferred radar colors."""

import io
from datetime import UTC, datetime

import httpx
import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image

from wxspot.hunt_rainfall import (
    HistoricalRainfall,
    encode_accumulation,
    palette_mm,
    parse_raster,
    rain_anchor,
    rain_sources,
    raster_tile,
)


def _fixture(value=18):
    image = Image.new("P", (1200, 600), color=value)
    image.putpalette([component for n in range(256) for component in (n, n, 0)])
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), b"0.1\n0\n0\n-0.1\n-129.95\n59.95\n"


def test_archive_precipitation_has_precise_time_and_physical_index_units():
    observed = datetime(2026, 10, 9, 11, 8, 55, tzinfo=UTC)
    assert rain_anchor(observed, "rain_rate") == datetime(2026, 10, 9, 11, 8, tzinfo=UTC)
    assert rain_anchor(observed, "rain_3h") == datetime(2026, 10, 9, 11, tzinfo=UTC)
    stamps = rain_sources("rain_3h", rain_anchor(observed, "rain_3h"))
    assert [t for _, t in stamps] == [
        datetime(2026, 10, 9, 11, tzinfo=UTC),
        datetime(2026, 10, 9, 10, tzinfo=UTC),
        datetime(2026, 10, 9, 9, tzinfo=UTC),
    ]
    assert all(kind == "p1h" for kind, _ in stamps)
    assert rain_sources("rain_24h", rain_anchor(observed, "rain_24h"))[0][0] == "p24h"
    assert palette_mm(np.array([0, 100, 101, 180, 181, 254], dtype=np.uint8), "p1h").tolist() == [
        0.0,
        25.0,
        26.25,
        125.0,
        130.0,
        495.0,
    ]
    assert palette_mm(np.array([50], dtype=np.uint8), "a2m").tolist() == pytest.approx([1.0])
    assert encode_accumulation(np.array([12.0], dtype=np.float32)).tolist() == [48]
    with pytest.raises(ValueError):
        rain_anchor(datetime(2026, 10, 9, 11, 8), "rain_1h")
    with pytest.raises(ValueError):
        rain_anchor(observed, "fake_product")


def test_wgs84_worldfile_is_required_and_three_hour_grid_uses_measured_values():
    png, world = _fixture(value=16)
    sample = parse_raster(png, world)
    tile = raster_tile([sample, sample, sample], "rain_3h", 5, 7, 12)
    assert tile.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(tile)) as raster:
        assert raster.size == (256, 256)
        assert raster.mode == "RGBA"
    with pytest.raises(ValueError):
        parse_raster(png, b"0.1\n0.1\n0\n-0.1\n-129.95\n59.95\n")
    bad = (sample[0], sample[1], (0.01, -0.1, -129.95, 59.95))
    with pytest.raises(ValueError):
        raster_tile([sample, bad], "rain_3h", 5, 7, 12)


@pytest.mark.asyncio
async def test_rain_archived_frame_gate_and_strict_tile_time():
    observed = datetime(2026, 10, 9, 11, 8, 55, tzinfo=UTC)
    png, world = _fixture()

    def respond(request):
        if request.method == "HEAD":
            if "p1h_202610091000" in str(request.url):
                return httpx.Response(404)
            return httpx.Response(200, headers={"content-type": "image/png"})
        return httpx.Response(200, content=world if str(request.url).endswith(".wld") else png)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        rain = HistoricalRainfall(client)
        path = "/game/sounding-hunt/radar/practice/abc-def"
        unavailable = await rain.frames(observed, "rain_3h", path)
        assert unavailable["state"] == "unavailable"
        assert unavailable["frames"] == []
        ready = await rain.frames(observed, "rain_24h", path)
        assert ready["state"] == "ready"
        assert ready["frames"][0]["stamp"] == "202610091100"
        frame = ready["frames"][0]
        assert "/rain/rain_24h/tiles/" in frame["tile_template"]
        assert "station_id" not in str(ready) and "latitude" not in str(ready)
        tile = await rain.tile(observed, "rain_24h", frame["stamp"], 5, 7, 12)
        assert tile.startswith(b"\x89PNG")
        with pytest.raises(HTTPException) as error:
            await rain.tile(observed, "rain_24h", "202610081100", 5, 7, 12)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException) as error:
            await rain.tile(observed, "rain_24h", frame["stamp"], 10, 7, 12)
        assert error.value.status_code == 404
