"""Contract and archive safety checks for historical Sounding Hunt radar."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException

from wxspot.hunt_radar import (
    HistoricalRadar,
    archive_url,
    frame_stamp,
    launch_frames,
    mercator_tile_bbox,
    parse_frame_stamp,
    rounded_frame,
)


def test_launch_window_crosses_midnight_and_is_utc():
    observed = datetime(2026, 5, 19, 23, 58, 16, tzinfo=UTC)
    center = rounded_frame(observed)
    assert center == datetime(2026, 5, 19, 23, 55, tzinfo=UTC)
    frames = launch_frames(observed)
    assert len(frames) == 13
    assert frames[0] == center - timedelta(minutes=30)
    assert frames[-1] == center + timedelta(minutes=30)
    assert frame_stamp(frames[-1]) == "202605200025"
    assert archive_url(center).endswith("2026/05/19/GIS/uscomp/n0q_202605192355.png")
    assert parse_frame_stamp("202605192355") == center
    for timestamp in ("202605192357", "202605", "202613011000", "../../../etc/passwd"):
        with pytest.raises(ValueError):
            parse_frame_stamp(timestamp)
    with pytest.raises(ValueError):
        rounded_frame(datetime(2026, 5, 19, 12))


def test_radar_tile_bounds_and_security_budget():
    assert mercator_tile_bbox(0, 0, 0).startswith("-20037508.")
    for z, x, y in ((-1, 0, 0), (10, 0, 0), (3, 8, 0), (3, -1, 0), (3, 0, 8)):
        with pytest.raises(ValueError):
            mercator_tile_bbox(z, x, y)


@pytest.mark.asyncio
async def test_radar_metadata_verifies_real_archive_files_and_does_not_leak_station():
    stamp = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    middle = frame_stamp(stamp)

    def respond(request):
        if request.method == "HEAD":
            return httpx.Response(
                200 if middle in str(request.url) else 404,
                headers={"content-type": "image/png"},
            )
        return httpx.Response(
            200, headers={"content-type": "image/png"}, content=b"\x89PNG\r\n\x1a\n123"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        radar = HistoricalRadar(client)
        manifest = await radar.frames(stamp, "/game/sounding-hunt/radar/daily/2026-05-20")
        assert manifest["state"] == "ready"
        assert len(manifest["frames"]) == 1
        assert manifest["initial_index"] == 0
        assert manifest["frames"][0]["stamp"] == middle
        assert manifest["frames"][0]["tile_template"].endswith(middle + "/{z}/{x}/{y}.png")
        assert "station_id" not in str(manifest)
        assert "latitude" not in str(manifest)
        tile = await radar.tile(stamp, 2, 1, 1)
        assert tile.startswith(b"\x89PNG")
        with pytest.raises(HTTPException) as error:
            await radar.tile(stamp + timedelta(minutes=5), 2, 1, 1)
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_archive_timeout_has_no_false_ready_frames():
    def fail(_):
        raise httpx.ConnectError("offline")

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        result = await HistoricalRadar(client).frames(
            datetime(2026, 5, 20, 12, tzinfo=UTC),
            "/game/sounding-hunt/radar/daily/2026-05-20",
        )
        assert result["state"] == "unavailable"
        assert result["frames"] == []
        assert "Live radar is never substituted" in result["message"]


@pytest.mark.asyncio
async def test_historical_site_radar_uses_actual_level3_scans_and_scoped_tiles():
    observed = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)

    class FakeGrid:
        def tile(self, z, x, y):
            assert (z, x, y) == (3, 2, 3)
            return b"\\x89PNG\\r\\n\\x1a\\nsite"

    class FakeLevel3:
        def __init__(self):
            self.calls = []

        async def _list_day(self, site, code, day):
            assert site == "KTLX" and code == "N0U"
            self.calls.append(("list", day))
            return [
                (observed + timedelta(minutes=3), "TLX_N0U_2026_10_09_12_03_00"),
                (observed + timedelta(hours=5), "TLX_N0U_outside"),
            ]

        async def _load(self, site, product, code, scan):
            assert (site, product, code) == ("KTLX", "velocity", "N0U")
            assert scan == observed + timedelta(minutes=3)
            self.calls.append(("load", scan))
            return FakeGrid()

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as client:
        level3 = FakeLevel3()
        radar = HistoricalRadar(client, level3)
        path = "/game/sounding-hunt/radar/daily/2026-10-09"
        meta = await radar.site_frames(observed, "KTLX", "velocity", 0, path)
        assert meta["state"] == "ready"
        assert len(meta["frames"]) == 1
        frame = meta["frames"][0]
        assert frame["stamp"] == "20261009T120300Z"
        assert "/site/KTLX/velocity/0/tiles/" in frame["tile_template"]
        assert "station_name" not in str(meta)
        assert "latitude" not in str(meta)
        assert await radar.site_tile(
            observed, "KTLX", "velocity", 0, frame["stamp"], 3, 2, 3
        ) == b"\\x89PNG\\r\\n\\x1a\\nsite"
        assert len(level3.calls) == 2
        for site, product, tilt in [
            ("BAD!", "velocity", 0),
            ("KTLX", "invalid", 0),
            ("KTLX", "velocity", 4),
        ]:
            with pytest.raises(HTTPException) as error:
                await radar.site_frames(observed, site, product, tilt, path)
            assert error.value.status_code == 404
        with pytest.raises(HTTPException) as error:
            await radar.site_tile(
                observed, "KTLX", "velocity", 0, "20261009T183000Z", 3, 2, 3
            )
        assert error.value.status_code == 404
