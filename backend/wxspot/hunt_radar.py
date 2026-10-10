"""Historical, time-verified CONUS NEXRAD mosaic evidence for Sounding Hunt.

Every advertised frame is first checked against a dated IEM archive object.
Never substitute live radar, infer station coordinates, or report an
unverified timestamp as a radar observation.
"""
import asyncio
import math
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException

ARCHIVE = "https://mesonet.agron.iastate.edu/archive/data"
WMS = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q-t.cgi"
ATTRIBUTION = "Iowa Environmental Mesonet / NOAA NEXRAD (historical composite)"
MERCATOR = 20037508.342789244
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SUPPORTED_PRODUCTS = {
    "reflectivity": {"label": "CONUS reflectivity", "unit": "dBZ", "scope": "national"},
    "velocity": {"label": "Radial velocity", "scope": "single_site", "available": False},
    "storm_relative_velocity": {"label": "Storm-relative velocity", "scope": "single_site", "available": False},
    "correlation_coefficient": {"label": "Correlation coefficient", "scope": "single_site", "available": False},
    "differential_reflectivity": {"label": "Differential reflectivity", "scope": "single_site", "available": False},
    "specific_differential_phase": {"label": "Specific differential phase", "scope": "single_site", "available": False},
    "rain_1h": {"label": "1-hour rainfall", "scope": "national", "available": False},
    "rain_3h": {"label": "3-hour rainfall", "scope": "national", "available": False},
    "rain_24h": {"label": "24-hour rainfall", "scope": "national", "available": False},
}


def rounded_frame(observed: datetime) -> datetime:
    """Nearest preceding actual five-minute archive slot in UTC."""
    if observed.tzinfo is None:
        raise ValueError("An explicit UTC/offset-aware sounding time is required")
    stamp = observed.astimezone(UTC)
    return stamp.replace(minute=(stamp.minute // 5) * 5, second=0, microsecond=0)


def launch_frames(observed: datetime) -> list[datetime]:
    """30 min before launch through 30 min after, including nominal launch."""
    center = rounded_frame(observed)
    return [center + timedelta(minutes=offset) for offset in range(-30, 31, 5)]


def frame_stamp(frame: datetime) -> str:
    return frame.astimezone(UTC).strftime("%Y%m%d%H%M")


def archive_url(frame: datetime) -> str:
    when = rounded_frame(frame)
    return (
        f"{ARCHIVE}/{when:%Y/%m/%d}/GIS/uscomp/"
        f"n0q_{frame_stamp(when)}.png"
    )


def parse_frame_stamp(stamp: str) -> datetime:
    if len(stamp) != 12 or not stamp.isascii() or not stamp.isdigit():
        raise ValueError("Invalid radar timestamp")
    when = datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=UTC)
    if when.minute % 5:
        raise ValueError("Radar timestamps must be aligned to five-minute slots")
    return when


def mercator_tile_bbox(z: int, x: int, y: int) -> str:
    if z not in range(0, 10) or x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        raise ValueError("Invalid or excessive radar tile")
    size = 2 * MERCATOR / (2**z)
    left = -MERCATOR + x * size
    right = left + size
    top = MERCATOR - y * size
    bottom = top - size
    return f"{left:.3f},{bottom:.3f},{right:.3f},{top:.3f}"


class HistoricalRadar:
    """Bounded archive verification and tile gateway; no station-location queries."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.presence: OrderedDict[str, bool] = OrderedDict()
        self.limit = asyncio.Semaphore(4)

    async def exists(self, when: datetime) -> bool:
        key = frame_stamp(when)
        if key in self.presence:
            self.presence.move_to_end(key)
            return self.presence[key]
        async with self.limit:
            try:
                response = await self.client.head(archive_url(when), timeout=12)
                present = response.status_code == 200 and (
                    "image" in response.headers.get("content-type", "").lower()
                    or "content-length" in response.headers
                )
            except httpx.HTTPError:
                present = False
        self.presence[key] = present
        if len(self.presence) > 300:
            self.presence.popitem(last=False)
        return present

    async def frames(self, observation_time: datetime, path_prefix: str) -> dict:
        candidates = launch_frames(observation_time)
        available = await asyncio.gather(*(self.exists(frame) for frame in candidates))
        rows = [
            {
                "time": stamp.isoformat().replace("+00:00", "Z"),
                "stamp": frame_stamp(stamp),
                "tile_template": (
                    f"{path_prefix}/tiles/{frame_stamp(stamp)}/{{z}}/{{x}}/{{y}}.png"
                ),
            }
            for stamp, valid in zip(candidates, available, strict=True)
            if valid
        ]
        anchor = rounded_frame(observation_time)
        initial = (
            min(range(len(rows)), key=lambda i: abs(
                (parse_frame_stamp(rows[i]["stamp"]) - anchor).total_seconds()
            ))
            if rows else 0
        )
        return {
            "state": "ready" if rows else "unavailable",
            "source": "Iowa Environmental Mesonet historical CONUS N0Q",
            "attribution": ATTRIBUTION,
            "product": "reflectivity",
            "products": SUPPORTED_PRODUCTS,
            "observation_time": observation_time.isoformat(),
            "anchor_time": anchor.isoformat().replace("+00:00", "Z"),
            "frames": rows,
            "initial_index": initial,
            "message": (
                None if rows else
                "No verified archived radar frames for this launch. Live radar is never substituted."
            ),
        }

    async def tile(self, when: datetime, z: int, x: int, y: int) -> bytes:
        bbox = mercator_tile_bbox(z, x, y)
        if not await self.exists(when):
            raise HTTPException(404, "Archived radar frame is unavailable")
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "LAYERS": "nexrad-n0q-wmst",
            "STYLES": "",
            "FORMAT": "image/png",
            "TRANSPARENT": "TRUE",
            "SRS": "EPSG:3857",
            "BBOX": bbox,
            "WIDTH": 256,
            "HEIGHT": 256,
            "TIME": rounded_frame(when).isoformat().replace("+00:00", "Z"),
        }
        async with self.limit:
            try:
                response = await self.client.get(WMS, params=params, timeout=20)
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise HTTPException(503, "Historical radar source unavailable") from error
        data = response.content
        if not data.startswith(PNG_SIGNATURE) or len(data) > 1_500_000:
            raise HTTPException(503, "Archive did not return a valid radar image")
        return data
