"""Historical, time-verified CONUS NEXRAD mosaic evidence for Sounding Hunt.

Every advertised frame is first checked against a dated IEM archive object.
Never substitute live radar, infer station coordinates, or report an
unverified timestamp as a radar observation.
"""

import asyncio
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException

from wxspot.providers.nexrad import _SITE_RE as NEXRAD_SITE_RE
from wxspot.providers.nexrad import PRODUCTS as LEVEL3_PRODUCTS
from wxspot.weather import SourceError

ARCHIVE = "https://mesonet.agron.iastate.edu/archive/data"
WMS = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q-t.cgi"
ATTRIBUTION = "Iowa Environmental Mesonet / NOAA NEXRAD (historical composite)"
MERCATOR = 20037508.342789244
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SUPPORTED_PRODUCTS = {
    "reflectivity": {"label": "CONUS reflectivity", "unit": "dBZ", "scope": "national"},
    "velocity": {"label": "Radial velocity", "scope": "single_site"},
    "storm_relative_velocity": {
        "label": "Storm-relative velocity",
        "scope": "single_site",
    },
    "correlation_coefficient": {
        "label": "Correlation coefficient",
        "scope": "single_site",
    },
    "differential_reflectivity": {
        "label": "Differential reflectivity",
        "scope": "single_site",
    },
    "specific_differential_phase": {
        "label": "Specific differential phase",
        "scope": "single_site",
    },
    "rain_rate": {"label": "2-minute derived rain rate", "scope": "national", "unit": "mm/h"},
    "rain_1h": {"label": "1-hour MRMS rainfall", "scope": "national", "unit": "mm"},
    "rain_3h": {"label": "3-hour derived MRMS rainfall", "scope": "national", "unit": "mm"},
    "rain_24h": {"label": "24-hour MRMS rainfall", "scope": "national", "unit": "mm"},
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
    return f"{ARCHIVE}/{when:%Y/%m/%d}/GIS/uscomp/n0q_{frame_stamp(when)}.png"


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

    def __init__(self, client: httpx.AsyncClient, level3=None):
        self.client = client
        self.level3 = level3
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
            min(
                range(len(rows)),
                key=lambda i: abs((parse_frame_stamp(rows[i]["stamp"]) - anchor).total_seconds()),
            )
            if rows
            else 0
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
                None
                if rows
                else (
                    "No verified archived radar frames for this launch. "
                    "Live radar is never substituted."
                )
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

    def _site_codes(self, site: str, product: str, tilt: int) -> list[str]:
        if (
            NEXRAD_SITE_RE.fullmatch(site) is None
            or product not in LEVEL3_PRODUCTS
            or tilt not in range(4)
        ):
            raise HTTPException(404, "Invalid radar site, product, or elevation")
        definition = LEVEL3_PRODUCTS[product]
        codes = [f"N{tilt}{definition['suffix']}"]
        modern = definition.get("modern_suffix")
        if modern:
            codes.insert(0, f"N{tilt}{modern}")
        return codes

    async def site_frames(
        self,
        observed: datetime,
        site: str,
        product: str,
        tilt: int,
        path_prefix: str,
    ) -> dict:
        """Inventory real historic site scans; never fall back to recent scans."""
        codes = self._site_codes(site, product, tilt)
        if self.level3 is None:
            raise HTTPException(503, "Historical single-site radar is unavailable")
        anchor = rounded_frame(observed)
        start, end = anchor - timedelta(minutes=30), anchor + timedelta(minutes=30)
        try:
            days = sorted({start.date(), end.date()})
            day_data = await asyncio.gather(
                *(self.level3._list_day(site, code, day) for code in codes for day in days)
            )
        except SourceError:
            day_data = []
        available = sorted(
            {
                (time, code, key)
                for code, collection in zip(
                    [code for code in codes for _ in days],
                    day_data,
                    strict=True,
                )
                for time, key in collection
                if start <= time <= end
            }
        )[:40]
        rows = [
            {
                "time": time.isoformat().replace("+00:00", "Z"),
                "stamp": time.strftime("%Y%m%dT%H%M%SZ"),
                "tile_template": (
                    f"{path_prefix}/site/{site}/{product}/{tilt}/"
                    f"tiles/{code}/{time:%Y%m%dT%H%M%SZ}/{{z}}/{{x}}/{{y}}.png"
                ),
            }
            for time, code, _ in available
        ]
        initial = (
            min(
                range(len(available)),
                key=lambda i: abs((available[i][0] - observed).total_seconds()),
            )
            if available
            else 0
        )
        return {
            "state": "ready" if rows else "unavailable",
            "source": "NOAA / NEXRAD historical Level III",
            "attribution": "NOAA / NEXRAD Level III via NSF Unidata archive",
            "product": product,
            "products": SUPPORTED_PRODUCTS,
            "observation_time": observed.isoformat(),
            "anchor_time": anchor.isoformat().replace("+00:00", "Z"),
            "frames": rows,
            "initial_index": initial,
            "message": (
                None if rows else "No archived scans for this site/product near the balloon launch."
            ),
        }

    async def site_tile(
        self,
        observed: datetime,
        site: str,
        product: str,
        tilt: int,
        code: str,
        stamp: str,
        z: int,
        x: int,
        y: int,
    ) -> bytes:
        """Decode an exact authenticated historic Level III scan into a map tile."""
        if code not in self._site_codes(site, product, tilt):
            raise HTTPException(404, "Unsupported historical radar product code")
        mercator_tile_bbox(z, x, y)
        try:
            when = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError as error:
            raise HTTPException(404, "Invalid historical scan identity") from error
        anchor = rounded_frame(observed)
        if not anchor - timedelta(minutes=30) <= when <= anchor + timedelta(minutes=30):
            raise HTTPException(404, "Historical scan lies outside the challenge window")
        if self.level3 is None:
            raise HTTPException(503, "Historical single-site radar is unavailable")
        try:
            grid = await self.level3._load(site, product, code, when)
            return await asyncio.to_thread(grid.tile, z, x, y)
        except SourceError as error:
            raise HTTPException(404, "Historical site radar scan unavailable") from error
