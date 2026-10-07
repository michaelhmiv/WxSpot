import asyncio
import gzip
import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from urllib.parse import quote

import eccodes
import httpx
import numpy as np
from defusedxml.ElementTree import fromstring
from pyproj import CRS, Transformer

from wxspot.providers.render import MRMS_SENTINELS, colorize, png_bytes
from wxspot.weather import SourceError
from wxspot.weather_contracts import (
    RenderDescriptor,
    WeatherFrame,
    WeatherFramesResponse,
    WeatherProduct,
    WeatherSelection,
)


MRMS_SOURCE = "noaa-mrms"
MRMS_BUCKET = "https://noaa-mrms-pds.s3.amazonaws.com"
MRMS_PRODUCTS = {
    "reflectivity": (
        "MergedReflectivityQCComposite_00.50",
        "National composite reflectivity",
        "dBZ",
    ),
    "precip_rate": ("PrecipRate_00.00", "Estimated precipitation rate", "mm/h"),
    "precip_1h": ("RadarOnly_QPE_01H_00.00", "1-hour radar-only accumulation", "mm"),
    "precip_3h": ("RadarOnly_QPE_03H_00.00", "3-hour radar-only accumulation", "mm"),
    "precip_24h": ("RadarOnly_QPE_24H_00.00", "24-hour radar-only accumulation", "mm"),
}
MRMS_STALE_AFTER = {
    "reflectivity": timedelta(minutes=15),
    "precip_rate": timedelta(minutes=15),
    "precip_1h": timedelta(minutes=15),
    "precip_3h": timedelta(hours=2),
    "precip_24h": timedelta(hours=2),
}
MRMS_BOUNDS = [-130.0, 20.0, -60.0, 55.0]
MERCATOR_RADIUS = 6378137.0
MAX_GRIB_COMPRESSED = 32 * 1024 * 1024
MAX_GRIB_EXPANDED = 384 * 1024 * 1024
MAX_INVENTORY_OBJECTS = 1000
FRAME_ID_RE = re.compile(
    r"^mrms:(reflectivity|precip_rate|precip_1h|precip_3h|precip_24h):"
    r"(\d{8}T\d{6}Z)$"
)


def _timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def _frame_time(key: str) -> datetime | None:
    match = re.search(r"_(\d{8})-(\d{6})\.grib2(?:\.gz)?$", key)
    if match is None:
        return None
    return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _freshness_state(product: str, latest: datetime, now: datetime) -> str:
    return "source_delayed" if now - latest > MRMS_STALE_AFTER[product] else "ready"


def _xml_text(node, name: str) -> str:
    child = node.find(f"{{*}}{name}")
    return child.text if child is not None and child.text else ""


def _key_float(handle, name: str, default: float | None = None) -> float:
    try:
        return float(eccodes.codes_get(handle, name))
    except (KeyError, eccodes.CodesInternalError) as exc:
        if default is None:
            raise SourceError(
                "source_unavailable", "MRMS grid metadata is incomplete"
            ) from exc
        return default


def _inflate(data: bytes) -> bytes:
    if len(data) > MAX_GRIB_COMPRESSED:
        raise SourceError("source_unavailable", "MRMS object exceeded the processing limit")
    if data[:2] != b"\x1f\x8b":
        if len(data) > MAX_GRIB_EXPANDED:
            raise SourceError("source_unavailable", "MRMS grid exceeded the processing limit")
        return data
    try:
        with gzip.GzipFile(fileobj=BytesIO(data)) as stream:
            expanded = stream.read(MAX_GRIB_EXPANDED + 1)
    except OSError as exc:
        raise SourceError("source_unavailable", "MRMS grid could not be decompressed") from exc
    if len(expanded) > MAX_GRIB_EXPANDED:
        raise SourceError("source_unavailable", "MRMS grid exceeded the processing limit")
    return expanded


@dataclass
class Grid:
    values: np.ndarray
    nx: int
    ny: int
    x0: float
    y0: float
    dx: float
    dy: float
    transform: Transformer
    product: str
    valid_time: datetime

    @classmethod
    def decode(cls, content: bytes, product: str) -> "Grid":
        payload = _inflate(content)
        try:
            handle = eccodes.codes_grib_new_from_message(payload)
        except Exception as exc:
            raise SourceError("source_unavailable", "MRMS GRIB2 data could not be decoded") from exc
        if handle is None:
            raise SourceError("source_unavailable", "MRMS GRIB2 object was empty")
        try:
            nx = int(eccodes.codes_get(handle, "Nx"))
            ny = int(eccodes.codes_get(handle, "Ny"))
            raw = np.asarray(eccodes.codes_get_values(handle), dtype=np.float32)
            if nx < 2 or ny < 2 or raw.size != nx * ny:
                raise SourceError(
                    "source_unavailable", "MRMS grid dimensions do not match its data"
                )
            grid_type = str(eccodes.codes_get(handle, "gridType"))
            valid_date = int(eccodes.codes_get(handle, "validityDate"))
            valid_hhmm = int(eccodes.codes_get(handle, "validityTime"))
            valid_time = datetime.strptime(
                f"{valid_date:08d}{valid_hhmm:04d}", "%Y%m%d%H%M"
            ).replace(tzinfo=UTC)
            first_lon = _key_float(handle, "longitudeOfFirstGridPointInDegrees")
            first_lat = _key_float(handle, "latitudeOfFirstGridPointInDegrees")
            i_sign = -1.0 if int(eccodes.codes_get(handle, "iScansNegatively")) else 1.0
            j_sign = 1.0 if int(eccodes.codes_get(handle, "jScansPositively")) else -1.0
            j_consecutive = bool(eccodes.codes_get(handle, "jPointsAreConsecutive"))
            alternating = bool(eccodes.codes_get(handle, "alternativeRowScanning"))
            if alternating:
                raise SourceError(
                    "unsupported_product",
                    "MRMS alternate-row scan order is not supported",
                )
            if j_consecutive:
                values = raw.reshape(nx, ny).T
            else:
                values = raw.reshape(ny, nx)
            if grid_type == "regular_ll":
                dx = i_sign * _key_float(handle, "iDirectionIncrementInDegrees")
                dy = j_sign * _key_float(handle, "jDirectionIncrementInDegrees")
                return cls(
                    values,
                    nx,
                    ny,
                    first_lon,
                    first_lat,
                    dx,
                    dy,
                    Transformer.from_crs("EPSG:4326", "EPSG:4326", always_xy=True),
                    product,
                    valid_time,
                )
            if grid_type != "lambert":
                raise SourceError(
                    "unsupported_product", f"MRMS grid projection is unsupported: {grid_type}"
                )
            lon0 = _key_float(handle, "LoVInDegrees")
            lat0 = _key_float(handle, "LaDInDegrees")
            lat1 = _key_float(handle, "Latin1InDegrees")
            lat2 = _key_float(handle, "Latin2InDegrees", lat1)
            radius = _key_float(handle, "radiusInMetres", 6_371_229.0)
            projection = CRS.from_proj4(
                f"+proj=lcc +lat_1={lat1} +lat_2={lat2} +lat_0={lat0} +lon_0={lon0} "
                f"+R={radius} +units=m +no_defs"
            )
            transformer = Transformer.from_crs("EPSG:4326", projection, always_xy=True)
            x0, y0 = transformer.transform(first_lon, first_lat)
            dx = i_sign * _key_float(handle, "DxInMetres")
            dy = j_sign * _key_float(handle, "DyInMetres")
            return cls(values, nx, ny, x0, y0, dx, dy, transformer, product, valid_time)
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError("source_unavailable", "MRMS grid metadata could not be read") from exc
        finally:
            eccodes.codes_release(handle)

    def sample(self, longitude: np.ndarray, latitude: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, y = self.transform.transform(longitude, latitude)
        col = np.rint((np.asarray(x) - self.x0) / self.dx).astype(np.int64)
        row = np.rint((np.asarray(y) - self.y0) / self.dy).astype(np.int64)
        inside = (col >= 0) & (col < self.nx) & (row >= 0) & (row < self.ny)
        sampled = np.full(col.shape, np.nan, dtype=np.float32)
        sampled[inside] = self.values[row[inside], col[inside]]
        missing = np.zeros(sampled.shape, dtype=bool)
        missing |= ~np.isfinite(sampled)
        for sentinel in MRMS_SENTINELS[self.product]:
            missing |= sampled == sentinel
        return sampled, inside & ~missing

    def image(self, bounds: list[float], width: int = 1024, height: int = 768) -> bytes:
        if len(bounds) != 4 or not (
            -180 <= bounds[0] < bounds[2] <= 180 and -90 < bounds[1] < bounds[3] < 90
        ):
            raise SourceError("unsupported_product", "Weather image bounds are invalid")
        west, south, east, north = bounds
        lon = west + (np.arange(width, dtype=np.float64) + .5) * (east - west) / width
        lat = north - (np.arange(height, dtype=np.float64) + .5) * (north - south) / height
        longitude, latitude = np.meshgrid(lon, lat)
        values, valid = self.sample(longitude, latitude)
        rgba = colorize(values, self.product, missing=MRMS_SENTINELS[self.product])
        rgba[~valid, 3] = 0
        return png_bytes(rgba)

    def tile(self, zoom: int, x: int, y: int) -> bytes:
        if not (0 <= zoom <= 12 and 0 <= x < 2**zoom and 0 <= y < 2**zoom):
            raise SourceError("unsupported_product", "Map tile coordinates are invalid")
        world = math.pi * MERCATOR_RADIUS
        span = (world * 2) / (2**zoom)
        left = -world + x * span
        top = world - y * span
        pixels = np.arange(256, dtype=np.float64) + .5
        xs = left + pixels * span / 256
        ys = top - pixels * span / 256
        xm, ym = np.meshgrid(xs, ys)
        longitude = np.degrees(xm / MERCATOR_RADIUS)
        latitude = np.degrees(2 * np.arctan(np.exp(ym / MERCATOR_RADIUS)) - math.pi / 2)
        values, valid = self.sample(longitude, latitude)
        rgba = colorize(values, self.product, missing=MRMS_SENTINELS[self.product])
        rgba[~valid, 3] = 0
        return png_bytes(rgba)


class MrmsProvider:
    source_type = "radar"
    provider_id = MRMS_SOURCE

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self._inventory: OrderedDict[
            tuple[str, str], tuple[datetime, list[tuple[datetime, str]]]
        ] = OrderedDict()
        self._grid_cache: OrderedDict[str, Grid] = OrderedDict()
        self._grid_lock = asyncio.Lock()
        self._network_slots = asyncio.Semaphore(3)
        self._render_lock = asyncio.Lock()
        self._render_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()

    def products(self) -> list[WeatherProduct]:
        return [
            WeatherProduct(
                source_type="radar",
                provider=self.provider_id,
                source_id=self.provider_id,
                product_id=product,
                display_name=title,
                units=units,
                attribution="NOAA Multi-Radar/Multi-Sensor System",
                coverage_bounds=MRMS_BOUNDS,
                legend_url=f"/weather/render/legend/{self.provider_id}/{product}.png",
                capabilities={
                    "timeline": True,
                    "exact_capture": True,
                    "coverage": "CONUS",
                    "history_hours": 3,
                    "native_grid": True,
                },
            )
            for product, (_, title, units) in MRMS_PRODUCTS.items()
        ]

    async def _list_day(self, upstream_product: str, day: datetime) -> list[tuple[datetime, str]]:
        date = day.strftime("%Y%m%d")
        cache_key = (upstream_product, date)
        now = datetime.now(UTC)
        cached = self._inventory.get(cache_key)
        if cached and (now - cached[0]).total_seconds() < 60:
            self._inventory.move_to_end(cache_key)
            return cached[1]
        prefixes = [
            f"CONUS/{upstream_product}/{date}/",
            f"CONUS/{upstream_product}/{day:%Y/%m/%d}/",
        ]
        keys: list[tuple[datetime, str]] = []
        for prefix in prefixes:
            params = {"list-type": "2", "prefix": prefix, "max-keys": str(MAX_INVENTORY_OBJECTS)}
            try:
                async with self._network_slots:
                    response = await self.client.get(MRMS_BUCKET + "/", params=params)
                response.raise_for_status()
                root = fromstring(response.content)
                for item in root.iter():
                    if item.tag.rsplit("}", 1)[-1] != "Contents":
                        continue
                    key = _xml_text(item, "Key")
                    stamp = _frame_time(key)
                    if stamp is not None:
                        keys.append((stamp, key))
                if keys:
                    break
            except (httpx.HTTPError, ValueError, OSError) as exc:
                raise SourceError(
                    "source_unavailable", "NOAA MRMS inventory is unavailable"
                ) from exc
        keys.sort(key=lambda item: item[0])
        self._inventory[cache_key] = (now, keys)
        self._inventory.move_to_end(cache_key)
        while len(self._inventory) > 32:
            self._inventory.popitem(last=False)
        return keys

    async def _frames(self, product: str) -> list[tuple[datetime, str]]:
        upstream_product = MRMS_PRODUCTS[product][0]
        now = datetime.now(UTC)
        start = now - timedelta(hours=3)
        days = {start.date(), now.date()}
        found = []
        for day in sorted(days):
            found.extend(
                await self._list_day(
                    upstream_product, datetime.combine(day, datetime.min.time(), UTC)
                )
            )
        unique = {
            key: stamp
            for stamp, key in found
            if start <= stamp <= now + timedelta(minutes=2)
        }
        return sorted(
            ((stamp, key) for key, stamp in unique.items()), key=lambda item: item[0]
        )[-100:]

    def _frame(self, product: str, stamp: datetime, key: str) -> WeatherFrame:
        identifier = f"mrms:{product}:{stamp.strftime('%Y%m%dT%H%M%SZ')}"
        frame_id = quote(identifier, safe="")
        url = (
            f"/weather/render/tile/{{z}}/{{x}}/{{y}}.png?source_id={self.provider_id}"
            f"&frame_id={frame_id}"
        )
        hours = {"precip_1h": 1, "precip_3h": 3, "precip_24h": 24}.get(product)
        metadata = {"upstream_product": MRMS_PRODUCTS[product][0], "domain": "CONUS"}
        if hours is not None:
            metadata.update(
                {
                    "accumulation_hours": hours,
                    "accumulation_start": (
                        (stamp - timedelta(hours=hours))
                        .isoformat()
                        .replace("+00:00", "Z")
                    ),
                    "accumulation_end": stamp.isoformat().replace("+00:00", "Z"),
                }
            )
        return WeatherFrame(
            id=identifier,
            source_type="radar",
            provider=self.provider_id,
            product=product,
            valid_time=stamp,
            render=RenderDescriptor(
                kind="xyz",
                url_template=url,
                tile_size=256,
                max_zoom=12,
                content_version=identifier,
            ),
            coverage_bounds=MRMS_BOUNDS,
            attribution="NOAA Multi-Radar/Multi-Sensor System",
            units=MRMS_PRODUCTS[product][2],
            legend_url=f"/weather/render/legend/{self.provider_id}/{product}.png",
            metadata=metadata,
        )

    async def frames(self, selection: WeatherSelection) -> WeatherFramesResponse:
        if selection.source_type != self.source_type or selection.source_id != self.provider_id:
            raise SourceError("unsupported_product", "This radar source is not supported")
        if selection.product_id not in MRMS_PRODUCTS:
            raise SourceError("unsupported_product", "This MRMS product is not supported")
        frames = await self._frames(selection.product_id)
        result = [self._frame(selection.product_id, stamp, key) for stamp, key in frames]
        now = datetime.now(UTC)
        state = (
            "no_data"
            if not result
            else _freshness_state(selection.product_id, frames[-1][0], now)
        )
        return WeatherFramesResponse(
            state=state,
            frames=result,
            fetched_at=now,
            message=(
                "MRMS reports radar-estimated precipitation and CONUS radar coverage."
                if result
                else "No MRMS frames are currently available."
            ),
        )

    def _key_for(self, frame_id: str) -> tuple[str, datetime]:
        match = FRAME_ID_RE.fullmatch(frame_id)
        if match is None:
            raise SourceError("unsupported_product", "Weather frame identity is invalid")
        product, stamp = match.groups()
        return product, _timestamp(stamp)

    async def _object_for(self, frame_id: str) -> bytes:
        product, stamp = self._key_for(frame_id)
        upstream_product = MRMS_PRODUCTS[product][0]
        day = stamp.date()
        keys = await self._list_day(
            upstream_product, datetime.combine(day, datetime.min.time(), UTC)
        )
        key = next((key for time, key in keys if time == stamp), None)
        if key is None:
            raise SourceError("no_data", "That MRMS frame is no longer available upstream")
        try:
            chunks = []
            total = 0
            async with self._network_slots:
                async with self.client.stream(
                    "GET", f"{MRMS_BUCKET}/{quote(key, safe='/')}"
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_GRIB_COMPRESSED:
                            raise SourceError(
                                "source_unavailable",
                                "MRMS object exceeded the processing limit",
                            )
                        chunks.append(chunk)
            content = b"".join(chunks)
            return content
        except httpx.HTTPError as exc:
            raise SourceError(
                "source_unavailable", "Could not retrieve the exact MRMS frame"
            ) from exc

    async def _grid(self, frame_id: str) -> Grid:
        async with self._grid_lock:
            cached = self._grid_cache.get(frame_id)
            if cached is not None:
                self._grid_cache.move_to_end(frame_id)
                return cached
            product, stamp = self._key_for(frame_id)
            content = await self._object_for(frame_id)
            grid = await asyncio.to_thread(Grid.decode, content, product)
            if abs((grid.valid_time - stamp).total_seconds()) > 60:
                raise SourceError(
                    "source_unavailable",
                    "MRMS file timestamp did not match the GRIB valid time",
                )
            self._grid_cache[frame_id] = grid
            while len(self._grid_cache) > 1:
                self._grid_cache.popitem(last=False)
            return grid

    async def render_tile(self, frame_id: str, zoom: int, x: int, y: int) -> bytes:
        cache_key = (frame_id, f"{zoom}/{x}/{y}")
        cached = self._render_cache.get(cache_key)
        if cached is not None:
            self._render_cache.move_to_end(cache_key)
            return cached
        grid = await self._grid(frame_id)
        async with self._render_lock:
            cached = self._render_cache.get(cache_key)
            if cached is not None:
                return cached
            data = await asyncio.to_thread(grid.tile, zoom, x, y)
            self._render_cache[cache_key] = data
            while len(self._render_cache) > 96:
                self._render_cache.popitem(last=False)
            return data

    async def capture(self, layer, bounds: list[float]) -> bytes:
        if layer.source_type != "radar" or layer.provider != self.provider_id:
            raise SourceError(
                "unsupported_product", "Only an MRMS frame can be captured by this adapter"
            )
        product, stamp = self._key_for(layer.frame_id)
        if product != layer.product or stamp != layer.valid_time:
            raise SourceError(
                "unsupported_product", "MRMS frame identity did not match the selected layer"
            )
        grid = await self._grid(layer.frame_id)
        return await asyncio.to_thread(grid.image, bounds)

    async def render_legend(self, product: str, frame_id: str | None = None) -> bytes:
        from wxspot.providers.render import legend_png

        if product not in MRMS_PRODUCTS:
            raise SourceError("unsupported_product", "This MRMS legend is not available")
        return await asyncio.to_thread(legend_png, product)
