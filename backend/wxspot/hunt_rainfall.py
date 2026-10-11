"""Archived NOAA MRMS rainfall evidence for Sounding Hunt.

Each raster is verified against an actual dated IEM PNG and its WGS84 world
file. The 3-hour product sums three consecutive real hourly accumulations,
not radar colors or reflectivity. Never silently substitute current rainfall.
"""

import asyncio
import math
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from io import BytesIO

import httpx
import numpy as np
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from wxspot.hunt_radar import MERCATOR, mercator_tile_bbox

ARCHIVE = "https://mesonet.agron.iastate.edu/archive/data"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RAIN_PRODUCTS = {
    "rain_rate": {"label": "2-minute derived rain rate", "unit": "mm/h"},
    "rain_1h": {"label": "1-hour MRMS accumulation", "unit": "mm"},
    "rain_3h": {"label": "3-hour MRMS accumulation", "unit": "mm"},
    "rain_24h": {"label": "24-hour MRMS accumulation", "unit": "mm"},
}


def rain_anchor(observed: datetime, product: str) -> datetime:
    if observed.tzinfo is None or product not in RAIN_PRODUCTS:
        raise ValueError("Invalid observation or precipitation product")
    when = observed.astimezone(UTC).replace(second=0, microsecond=0)
    return when.replace(minute=when.minute // 2 * 2 if product == "rain_rate" else 0)


def rain_sources(product: str, frame: datetime) -> list[tuple[str, datetime]]:
    if product not in RAIN_PRODUCTS or rain_anchor(frame, product) != frame:
        raise ValueError("Invalid historical precipitation time")
    if product == "rain_3h":
        return [("p1h", frame - timedelta(hours=n)) for n in range(3)]
    kind = {"rain_rate": "a2m", "rain_1h": "p1h", "rain_24h": "p24h"}[product]
    return [(kind, frame)]


def archive_url(kind: str, when: datetime, ext: str = "png") -> str:
    if kind not in {"a2m", "p1h", "p24h"} or ext not in {"png", "wld"}:
        raise ValueError("Unknown precipitation archive resource")
    return f"{ARCHIVE}/{when:%Y/%m/%d}/GIS/mrms/{kind}_{when:%Y%m%d%H%M}.{ext}"


def palette_mm(index: np.ndarray, kind: str) -> np.ndarray:
    """Use published IEM PNG palette index units; 255 indicates missing."""
    values = index.astype(np.float32)
    if kind == "a2m":
        return np.minimum(values, 254.0) * 0.02
    return np.select(
        [values <= 100, values <= 180],
        [values * 0.25, 25.0 + (values - 100.0) * 1.25],
        default=125.0 + (values - 180.0) * 5.0,
    ).astype(np.float32)


def encode_accumulation(mm: np.ndarray) -> np.ndarray:
    # 0..254 inclusive are actual IEM precipitation bins; 255 is missing.
    bins = palette_mm(np.arange(255, dtype=np.uint8), "p1h")
    return np.searchsorted(bins, np.maximum(0, mm), side="left").clip(0, 254).astype(np.uint8)


def parse_raster(png: bytes, world: bytes):
    if not png.startswith(PNG_SIGNATURE) or len(png) > 10_000_000 or len(world) > 200:
        raise ValueError("Invalid historical MRMS raster payload")
    wld = tuple(float(item) for item in world.decode("ascii").split())
    if len(wld) != 6 or not all(math.isfinite(value) for value in wld):
        raise ValueError("MRMS world file is incomplete")
    a, d, b, e, c, f = wld
    if not (0 < a <= 0.1 and -0.1 <= e < 0 and abs(d) < 1e-10 and abs(b) < 1e-10):
        raise ValueError("MRMS archive is not a north-up WGS84 raster")
    with Image.open(BytesIO(png)) as img:
        if img.mode != "P" or img.width > 13000 or img.height > 7000:
            raise ValueError("Unrecognized MRMS palette or raster dimensions")
        palette = np.asarray(img.getpalette()[:768], dtype=np.uint8).reshape(256, 3)
        grid = np.asarray(img, dtype=np.uint8).copy()
    return grid, palette, (a, e, c, f)


def raster_tile(scans: list, product: str, z: int, x: int, y: int) -> bytes:
    mercator_tile_bbox(z, x, y)
    source, palette, geo = scans[0]
    if any(scan[0].shape != source.shape or scan[2] != geo for scan in scans):
        raise ValueError("MRMS source rasters have incompatible georeferencing")
    a, e, c, f = geo
    delta = 2 * MERCATOR / (2**z)
    dx = (np.arange(256, dtype=np.float64) + 0.5) * delta / 256
    gx = -MERCATOR + x * delta + dx
    gy = MERCATOR - y * delta - dx
    lon = np.degrees(gx / (MERCATOR / math.pi))
    lat = np.degrees(np.arctan(np.sinh(gy / (MERCATOR / math.pi))))
    col = np.floor((lon - c) / a + 0.5).astype(np.int64)
    row = np.floor((lat - f) / e + 0.5).astype(np.int64)
    valid = ((row >= 0) & (row < source.shape[0]))[:, None] & (
        (col >= 0) & (col < source.shape[1])
    )[None, :]
    yy = row.clip(0, source.shape[0] - 1)
    xx = col.clip(0, source.shape[1] - 1)
    values = [grid[yy[:, None], xx[None, :]] for grid, _, _ in scans]
    for pixel in values:
        valid &= pixel != 255
    if product == "rain_3h":
        summed = sum(
            (palette_mm(arr, "p1h") for arr in values),
            np.zeros((256, 256), dtype=np.float32),
        )
        indexed = encode_accumulation(summed)
    else:
        indexed = values[0]
    color = palette[indexed]
    alpha = np.where(valid & (indexed >= 4) & (indexed != 255), 215, 0).astype(np.uint8)
    output = BytesIO()
    Image.fromarray(np.dstack((color, alpha)), "RGBA").save(output, format="PNG")
    return output.getvalue()


class HistoricalRainfall:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.cache: OrderedDict[tuple[str, str], tuple] = OrderedDict()
        self.available: OrderedDict[str, bool] = OrderedDict()
        self.limit = asyncio.Semaphore(4)

    async def exists(self, kind: str, when: datetime) -> bool:
        key = archive_url(kind, when)
        if key in self.available:
            return self.available[key]
        async with self.limit:
            try:
                response = await self.client.head(key, timeout=12)
                present = response.status_code == 200 and (
                    "image" in response.headers.get("content-type", "")
                )
            except httpx.HTTPError:
                present = False
        self.available[key] = present
        while len(self.available) > 150:
            self.available.popitem(last=False)
        return present

    async def frames(self, observed: datetime, product: str, path: str) -> dict:
        frame = rain_anchor(observed, product)
        required = rain_sources(product, frame)
        files = await asyncio.gather(*(self.exists(kind, when) for kind, when in required))
        ready = all(files)
        stamp = frame.strftime("%Y%m%d%H%M")
        row = {
            "time": frame.isoformat().replace("+00:00", "Z"),
            "stamp": stamp,
            "tile_template": f"{path}/rain/{product}/tiles/{stamp}/{{z}}/{{x}}/{{y}}.png",
        }
        return {
            "state": "ready" if ready else "unavailable",
            "source": "NOAA MRMS precipitation via Iowa Environmental Mesonet historic rasters",
            "attribution": "NOAA MRMS / Iowa Environmental Mesonet",
            "product": product,
            "observation_time": observed.isoformat(),
            "anchor_time": frame.isoformat().replace("+00:00", "Z"),
            "frames": [row] if ready else [],
            "initial_index": 0,
            "message": None if ready else "Verified MRMS precipitation archive unavailable.",
        }

    async def _raster(self, kind: str, frame: datetime):
        key = kind, frame.isoformat()
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if not await self.exists(kind, frame):
            raise HTTPException(404, "Archived MRMS rainfall is unavailable")
        async with self.limit:
            try:
                png, world = await asyncio.gather(
                    self.client.get(archive_url(kind, frame), timeout=25),
                    self.client.get(archive_url(kind, frame, "wld"), timeout=15),
                )
                png.raise_for_status()
                world.raise_for_status()
                result = await asyncio.to_thread(parse_raster, png.content, world.content)
            except (httpx.HTTPError, ValueError, OSError, UnidentifiedImageError) as error:
                raise HTTPException(503, "MRMS archive raster could not be decoded") from error
        self.cache[key] = result
        while len(self.cache) > 4:
            self.cache.popitem(last=False)
        return result

    async def tile(self, observed: datetime, product: str, stamp: str, z: int, x: int, y: int):
        try:
            frame = datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=UTC)
            allowed = rain_anchor(observed, product)
            mercator_tile_bbox(z, x, y)
        except ValueError as error:
            raise HTTPException(404, "Invalid archived rainfall tile") from error
        if frame != allowed:
            raise HTTPException(404, "Rainfall timestamp is outside sounding observation")
        scans = await asyncio.gather(
            *(self._raster(kind, when) for kind, when in rain_sources(product, frame))
        )
        try:
            return await asyncio.to_thread(raster_tile, scans, product, z, x, y)
        except ValueError as error:
            raise HTTPException(503, "MRMS raster georeferencing could not be verified") from error
