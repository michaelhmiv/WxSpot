"""Bounded NOAA NEXRAD Level III product access and polar-grid rendering."""

import asyncio
import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from urllib.parse import quote

import httpx
import numpy as np
from defusedxml.ElementTree import fromstring
from pyproj import Geod

from wxspot.providers.render import SCALES, colorize, legend_png, png_bytes
from wxspot.weather import SourceError
from wxspot.weather_contracts import (
    RenderDescriptor,
    WeatherFrame,
    WeatherFramesResponse,
    WeatherProduct,
    WeatherSelection,
)

NEXRAD_SOURCE = "noaa-nexrad-level3"
NEXRAD_BUCKET = "https://unidata-nexrad-level3.s3.amazonaws.com"
MAX_LEVEL3_BYTES = 8 * 1024 * 1024
MAX_LISTED_OBJECTS = 1000
MAX_HISTORY = timedelta(hours=3)
MAX_FRAMES = 90
MAX_DECODED_FRAMES = 12
MAX_CONCURRENT_LOADS = 3
MAX_RENDERED_TILES = 48
MAX_ZOOM = 12
RADAR_RANGE_KM = 460.0
# Product 94 and 56 use 1 km range bins. Product 99 and the dual-pol
# products use 250 m bins; the packet scale factor adjusts those resolutions.
RANGE_RESOLUTION_KM = {
    56: 1.0,
    94: 1.0,
    99: 0.25,
    153: 0.25,  # Super-resolution digital reflectivity (N0B).
    154: 0.25,  # Super-resolution digital velocity (N0G).
    159: 0.25,
    161: 0.25,
    163: 0.25,
}

PRODUCTS = {
    "reflectivity": {
        "suffix": "Q",
        "code": 94,
        "modern_suffix": "B",
        "modern_code": 153,
        "title": "Digital reflectivity",
        "units": "dBZ",
        "scale": "reflectivity",
    },
    "velocity": {
        "suffix": "U",
        "code": 99,
        "modern_suffix": "G",
        "modern_code": 154,
        "title": "Base radial velocity",
        "units": "m/s",
        "scale": "velocity",
    },
    "storm_relative_velocity": {
        "suffix": "S",
        "code": 56,
        "title": "Storm-relative velocity",
        "units": "kt",
        "scale": "storm_relative_velocity",
    },
    "correlation_coefficient": {
        "suffix": "C",
        "code": 161,
        "title": "Correlation coefficient",
        "units": "unitless",
        "scale": "correlation_coefficient",
    },
    "differential_reflectivity": {
        "suffix": "X",
        "code": 159,
        "title": "Differential reflectivity",
        "units": "dB",
        "scale": "differential_reflectivity",
    },
    "specific_differential_phase": {
        "suffix": "K",
        "code": 163,
        "title": "Specific differential phase",
        "units": "degrees/km",
        "scale": "specific_differential_phase",
    },
}
TILT_CODES = tuple(f"N{i}{product['suffix']}" for product in PRODUCTS.values() for i in range(4))
_SITE_RE = re.compile(r"^[KPT][A-Z0-9]{3}$")
_KEY_RE = re.compile(
    r"^(?P<site>[A-Z0-9]{3})_(?P<code>N[0-3][A-Z])_"
    r"(?P<year>\d{4})_(?P<month>\d{2})_(?P<day>\d{2})_"
    r"(?P<hour>\d{2})_(?P<minute>\d{2})_(?P<second>\d{2})(?:\.gz)?$"
)
_FRAME_RE = re.compile(
    r"^nexrad3:(?P<site>[KPT][A-Z0-9]{3}):(?P<product>[a-z_]+):"
    r"(?P<code>N[0-3][A-Z]):(?P<stamp>\d{8}T\d{6}Z)$"
)
_GEOD = Geod(ellps="WGS84")
_MERCATOR_RADIUS = 6378137.0


@dataclass
class PolarGrid:
    site: str
    product: str
    code: str
    valid_time: datetime
    elevation: float
    longitude: float
    latitude: float
    max_range_km: float
    azimuth_centers: np.ndarray
    values: np.ndarray
    range_fold: np.ndarray
    first_gate_index: int = 0
    gate_scale_km: float = 1.0
    storm_motion_speed_kt: float | None = None
    storm_motion_direction_deg: float | None = None
    storm_relative_levels_kt: tuple[float, ...] = ()

    @classmethod
    def decode(cls, payload: bytes, site: str, product: str, code: str, valid_time: datetime):
        from metpy.io import Level3File

        if len(payload) > MAX_LEVEL3_BYTES:
            raise SourceError(
                "source_unavailable", "NEXRAD Level III object exceeded the processing limit"
            )
        try:
            volume = Level3File(BytesIO(payload))
            definition = PRODUCTS[product]
            modern = definition.get("modern_suffix") == code[-1]
            expected_code = definition["modern_code"] if modern else definition["code"]
            if getattr(volume.header, "code", None) != expected_code:
                raise SourceError("unsupported_product", "NEXRAD object product code did not match")
            if volume.siteID and volume.siteID.strip() != site[1:]:
                raise SourceError("unsupported_product", "NEXRAD object site did not match")
            if not volume.sym_block:
                raise SourceError("no_data", "NEXRAD object contains no radial data")
            radial_packet = next(
                (
                    packet
                    for layer in volume.sym_block
                    for packet in layer
                    if isinstance(packet, dict)
                    and "start_az" in packet
                    and "end_az" in packet
                    and "data" in packet
                ),
                None,
            )
            if radial_packet is None:
                raise SourceError("no_data", "NEXRAD object contains no supported radial packet")
            raw_rows = radial_packet["data"]
            starts = np.asarray(radial_packet["start_az"], dtype=np.float64)
            ends = np.asarray(radial_packet["end_az"], dtype=np.float64)
            if len(raw_rows) != starts.size or starts.size < 2:
                raise SourceError("source_unavailable", "NEXRAD radial metadata is inconsistent")
            max_gates = max(len(row) for row in raw_rows)
            decoded = np.full((len(raw_rows), max_gates), np.nan, dtype=np.float32)
            folded = np.zeros((len(raw_rows), max_gates), dtype=bool)
            first_gate_index = int(radial_packet.get("first", 0))
            if not 0 <= first_gate_index <= 230:
                raise SourceError("source_unavailable", "NEXRAD first range bin is invalid")
            gate_scale_km = float(radial_packet.get("gate_scale", 0.0))
            gate_scale_km *= RANGE_RESOLUTION_KM[expected_code]
            if not math.isfinite(gate_scale_km) or not 0 < gate_scale_km <= 10:
                raise SourceError("source_unavailable", "NEXRAD range-bin scale is invalid")
            mapper = volume.map_data
            labels = getattr(mapper, "labels", ())
            range_fold_codes = {index for index, label in enumerate(labels) if label == "RF"}
            storm_levels = ()
            if product == "storm_relative_velocity":
                mapped_levels = np.asarray(getattr(mapper, "lut", ()), dtype=np.float64)
                storm_levels = tuple(float(value) for value in mapped_levels[1:15])
                if (
                    len(storm_levels) != 14
                    or not all(math.isfinite(value) for value in storm_levels)
                    or any(
                        left >= right
                        for left, right in zip(storm_levels, storm_levels[1:], strict=False)
                    )
                ):
                    raise SourceError(
                        "source_unavailable",
                        "NEXRAD storm-relative velocity levels are invalid",
                    )
            for index, raw_values in enumerate(raw_rows):
                raw = np.asarray(raw_values, dtype=np.uint8)
                physical = np.asarray(mapper(raw), dtype=np.float32)
                gate_count = min(raw.size, physical.size, max_gates)
                if product == "storm_relative_velocity":
                    decoded[index, :gate_count] = raw[:gate_count].astype(np.float32)
                    decoded[index, :gate_count][~np.isfinite(physical[:gate_count])] = np.nan
                else:
                    decoded[index, :gate_count] = physical[:gate_count]
                if product == "velocity":
                    folded[index, :gate_count] = raw[:gate_count] == 1
                elif range_fold_codes:
                    folded[index, :gate_count] = np.isin(raw[:gate_count], tuple(range_fold_codes))

            centers = (starts + ends) / 2.0
            centers = np.mod(centers, 360.0)
            order = np.argsort(centers)
            centers = centers[order]
            decoded = decoded[order]
            folded = folded[order]
            if np.any(~np.isfinite(centers)) or not math.isfinite(float(volume.max_range)):
                raise SourceError("source_unavailable", "NEXRAD polar geometry is incomplete")
            if not (0 <= float(volume.metadata["el_angle"]) <= 90):
                raise SourceError("source_unavailable", "NEXRAD elevation metadata is invalid")
            if not (-180 <= float(volume.lon) <= 180 and -90 <= float(volume.lat) <= 90):
                raise SourceError("source_unavailable", "NEXRAD site coordinates are invalid")
            prod_time = volume.metadata["prod_time"]
            if prod_time.tzinfo is None or prod_time.utcoffset() is None:
                prod_time = prod_time.replace(tzinfo=UTC)
            storm_speed = volume.metadata.get("avg_speed")
            storm_direction = volume.metadata.get("avg_dir")
            if product == "storm_relative_velocity":
                if storm_speed is not None and not 0 <= float(storm_speed) <= 99.9:
                    raise SourceError("source_unavailable", "NEXRAD storm-motion speed is invalid")
                if storm_direction is not None and not 0 <= float(storm_direction) <= 359.9:
                    raise SourceError(
                        "source_unavailable", "NEXRAD storm-motion direction is invalid"
                    )
            return cls(
                site=site,
                product=product,
                code=code,
                valid_time=prod_time.astimezone(UTC),
                elevation=float(volume.metadata["el_angle"]),
                longitude=float(volume.lon),
                latitude=float(volume.lat),
                max_range_km=min(float(volume.max_range), RADAR_RANGE_KM),
                azimuth_centers=centers,
                values=decoded,
                range_fold=folded,
                first_gate_index=first_gate_index,
                gate_scale_km=gate_scale_km,
                storm_motion_speed_kt=(float(storm_speed) if storm_speed is not None else None),
                storm_motion_direction_deg=(
                    float(storm_direction) if storm_direction is not None else None
                ),
                storm_relative_levels_kt=storm_levels,
            )
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError(
                "source_unavailable", "NEXRAD Level III object could not be decoded"
            ) from exc

    def sample(
        self, longitude: np.ndarray, latitude: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        azimuth, _, distance = _GEOD.inv(
            np.full(np.shape(longitude), self.longitude),
            np.full(np.shape(latitude), self.latitude),
            longitude,
            latitude,
        )
        bearing = np.mod(np.asarray(azimuth), 360.0)
        distance_km = np.asarray(distance) / 1000.0
        next_ray = np.searchsorted(self.azimuth_centers, bearing, side="left")
        after = next_ray % self.azimuth_centers.size
        before = (next_ray - 1) % self.azimuth_centers.size
        before_delta = np.abs((bearing - self.azimuth_centers[before] + 180.0) % 360.0 - 180.0)
        after_delta = np.abs((bearing - self.azimuth_centers[after] + 180.0) % 360.0 - 180.0)
        ray = np.where(before_delta <= after_delta, before, after)
        gate = np.floor(distance_km / self.gate_scale_km).astype(np.int64)
        first_distance_km = self.first_gate_index * self.gate_scale_km
        gate -= self.first_gate_index
        inside = (
            (distance_km >= first_distance_km)
            & (distance_km <= self.max_range_km)
            & (gate >= 0)
            & (gate < self.values.shape[1])
        )
        sampled = np.full(gate.shape, np.nan, dtype=np.float32)
        folded = np.zeros(gate.shape, dtype=bool)
        sampled[inside] = self.values[ray[inside], gate[inside]]
        folded[inside] = self.range_fold[ray[inside], gate[inside]]
        valid = inside & (np.isfinite(sampled) | folded)
        return sampled, valid, folded

    def tile(self, zoom: int, x: int, y: int) -> bytes:
        if not (0 <= zoom <= MAX_ZOOM and 0 <= x < 2**zoom and 0 <= y < 2**zoom):
            raise SourceError("unsupported_product", "Map tile coordinates are invalid")
        world = math.pi * _MERCATOR_RADIUS
        span = 2 * world / (2**zoom)
        left, top = -world + x * span, world - y * span
        pixels = np.arange(256, dtype=np.float64) + 0.5
        xm, ym = np.meshgrid(left + pixels * span / 256, top - pixels * span / 256)
        longitude = np.degrees(xm / _MERCATOR_RADIUS)
        latitude = np.degrees(2 * np.arctan(np.exp(ym / _MERCATOR_RADIUS)) - math.pi / 2)
        values, valid, folded = self.sample(longitude, latitude)
        rgba = colorize(values, PRODUCTS[self.product]["scale"], range_fold=folded)
        rgba[~valid, 3] = 0
        return png_bytes(rgba)

    def image(self, bounds: list[float], width: int = 1024, height: int = 768) -> bytes:
        if len(bounds) != 4 or not (
            -180 <= bounds[0] < bounds[2] <= 180 and -85 < bounds[1] < bounds[3] < 85
        ):
            raise SourceError("unsupported_product", "Weather image bounds are invalid")
        west, south, east, north = bounds
        lon = west + (np.arange(width, dtype=np.float64) + 0.5) * (east - west) / width
        lat = north - (np.arange(height, dtype=np.float64) + 0.5) * (north - south) / height
        longitude, latitude = np.meshgrid(lon, lat)
        values, valid, folded = self.sample(longitude, latitude)
        rgba = colorize(values, PRODUCTS[self.product]["scale"], range_fold=folded)
        rgba[~valid, 3] = 0
        return png_bytes(rgba)


class NexradLevel3Provider:
    source_type = "radar"
    provider_id = NEXRAD_SOURCE

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self._inventory: OrderedDict[
            tuple[str, str, str], tuple[datetime, list[tuple[datetime, str]]]
        ] = OrderedDict()
        self._decoded: OrderedDict[str, PolarGrid] = OrderedDict()
        self._tiles: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self._lock = asyncio.Lock()
        self._network_slots = asyncio.Semaphore(MAX_CONCURRENT_LOADS)
        self._decode_slots = asyncio.Semaphore(3)

    def products(self) -> list[WeatherProduct]:
        return [
            WeatherProduct(
                source_type="radar",
                provider=self.provider_id,
                source_id=self.provider_id,
                product_id=product,
                display_name=definition["title"],
                units=definition["units"],
                attribution="NOAA / NEXRAD Level III",
                legend_url=f"/weather/render/legend/{self.provider_id}/{definition['scale']}.png",
                capabilities={
                    "timeline": True,
                    "exact_capture": True,
                    "site_selection": True,
                    "elevation_selection": True,
                    "history_hours": 3,
                    "products": ["N0", "N1", "N2", "N3"],
                },
            )
            for product, definition in PRODUCTS.items()
        ]

    async def _list_day(self, site: str, code: str, day: date) -> list[tuple[datetime, str]]:
        cache_key = (site, code, day.isoformat())
        now = datetime.now(UTC)
        cached = self._inventory.get(cache_key)
        if cached and (now - cached[0]).total_seconds() < 60:
            self._inventory.move_to_end(cache_key)
            return cached[1]
        prefix = f"{site[1:]}_{code}_{day:%Y_%m_%d}_"
        try:
            async with self._network_slots:
                response = await self.client.get(
                    NEXRAD_BUCKET + "/",
                    params={
                        "list-type": "2",
                        "prefix": prefix,
                        "max-keys": str(MAX_LISTED_OBJECTS),
                    },
                )
            response.raise_for_status()
            root = fromstring(response.content)
            objects = []
            for item in root.iter():
                if item.tag.rsplit("}", 1)[-1] != "Contents":
                    continue
                key = _xml_text(item, "Key")
                stamp = _key_time(key, site, code)
                if stamp is not None:
                    objects.append((stamp, key))
            objects.sort(key=lambda row: row[0])
        except (httpx.HTTPError, ValueError, OSError) as exc:
            raise SourceError(
                "source_unavailable", "NOAA NEXRAD Level III inventory is unavailable"
            ) from exc
        self._inventory[cache_key] = (now, objects)
        self._inventory.move_to_end(cache_key)
        while len(self._inventory) > 48:
            self._inventory.popitem(last=False)
        return objects

    async def _objects(self, site: str, code: str) -> list[tuple[datetime, str]]:
        now = datetime.now(UTC)
        cutoff = now - MAX_HISTORY
        objects = []
        for day in sorted({cutoff.date(), now.date()}):
            objects.extend(await self._list_day(site, code, day))
        unique = {
            key: stamp for stamp, key in objects if cutoff <= stamp <= now + timedelta(minutes=2)
        }
        return sorted(((stamp, key) for key, stamp in unique.items()), key=lambda row: row[0])[
            -MAX_FRAMES:
        ]

    async def _download(self, key: str) -> bytes:
        try:
            chunks = []
            total = 0
            async with self._network_slots:
                async with self.client.stream(
                    "GET", f"{NEXRAD_BUCKET}/{quote(key, safe='_')}"
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_LEVEL3_BYTES:
                            raise SourceError(
                                "source_unavailable",
                                "NEXRAD Level III object exceeded the processing limit",
                            )
                        chunks.append(chunk)
            return b"".join(chunks)
        except httpx.HTTPError as exc:
            raise SourceError(
                "source_unavailable", "NOAA NEXRAD Level III object is unavailable"
            ) from exc

    def _frame_id(self, site: str, product: str, code: str, stamp: datetime) -> str:
        return f"nexrad3:{site}:{product}:{code}:{stamp.strftime('%Y%m%dT%H%M%SZ')}"

    def _identity(self, frame_id: str) -> tuple[str, str, str, datetime]:
        match = _FRAME_RE.fullmatch(frame_id)
        if match is None:
            raise SourceError("unsupported_product", "NEXRAD frame identity is invalid")
        site, product, code, stamp = match.groups()
        if (
            not _SITE_RE.fullmatch(site)
            or product not in PRODUCTS
            or code[2]
            not in {
                PRODUCTS[product]["suffix"],
                PRODUCTS[product].get("modern_suffix"),
            }
        ):
            raise SourceError("unsupported_product", "NEXRAD frame identity is invalid")
        return site, product, code, datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)

    async def _load(
        self, site: str, product: str, code: str, stamp: datetime, key: str | None = None
    ) -> PolarGrid:
        frame_id = self._frame_id(site, product, code, stamp)
        async with self._lock:
            cached = self._decoded.get(frame_id)
            if cached:
                self._decoded.move_to_end(frame_id)
                return cached
        if key is None:
            day_objects = await self._list_day(site, code, stamp.date())
            key = next((candidate for time, candidate in day_objects if time == stamp), None)
        if key is None:
            raise SourceError("no_data", "That NEXRAD scan is no longer available upstream")
        payload = await self._download(key)
        async with self._decode_slots:
            grid = await asyncio.to_thread(PolarGrid.decode, payload, site, product, code, stamp)
        if abs((grid.valid_time - stamp).total_seconds()) > 600:
            raise SourceError(
                "source_unavailable", "NEXRAD timestamp did not match the selected scan"
            )
        async with self._lock:
            self._decoded[frame_id] = grid
            self._decoded.move_to_end(frame_id)
            while len(self._decoded) > MAX_DECODED_FRAMES:
                self._decoded.popitem(last=False)
        return grid

    async def frames(self, selection: WeatherSelection) -> WeatherFramesResponse:
        if selection.source_type != self.source_type or selection.source_id != self.provider_id:
            raise SourceError("unsupported_product", "This NEXRAD source is not supported")
        if selection.site is None or not _SITE_RE.fullmatch(selection.site):
            raise SourceError("unsupported_product", "Choose a NEXRAD station")
        if selection.product_id not in PRODUCTS:
            raise SourceError(
                "unsupported_product", "This NEXRAD Level III product is not supported"
            )
        product = selection.product_id
        site = selection.site
        definition = PRODUCTS[product]
        codes = [f"N{i}{definition['suffix']}" for i in range(4)]
        now = datetime.now(UTC)
        listings = await asyncio.gather(
            *(self._objects(site, code) for code in codes), return_exceptions=True
        )
        latest = []
        for code, items in zip(codes, listings, strict=True):
            if isinstance(items, Exception) or not items:
                continue
            stamp, key = items[-1]
            latest.append((code, stamp, key))
        if not latest:
            if any(isinstance(items, Exception) for items in listings):
                return WeatherFramesResponse(
                    state="source_unavailable",
                    frames=[],
                    fetched_at=now,
                    message="NOAA NEXRAD Level III inventory could not be read.",
                )
            return WeatherFramesResponse(
                state="no_data",
                frames=[],
                fetched_at=now,
                message="No NEXRAD scans are currently available.",
            )

        async def latest_grid(entry):
            code, stamp, key = entry
            try:
                grid = await self._load(site, product, code, stamp, key)
                return grid
            except SourceError:
                return None

        latest_grids = await asyncio.gather(*(latest_grid(entry) for entry in latest))
        elevations = sorted(
            {(grid.elevation, grid.code) for grid in latest_grids if grid is not None}
        )
        if not elevations:
            return WeatherFramesResponse(
                state="source_unavailable",
                frames=[],
                fetched_at=now,
                message="NEXRAD scan metadata could not be read.",
            )
        desired = (
            min(elevations, key=lambda item: (abs(item[0] - selection.elevation), item[0]))
            if selection.elevation is not None
            else min(elevations, key=lambda item: item[0])
        )
        if selection.elevation is not None and abs(desired[0] - selection.elevation) > 0.1:
            return WeatherFramesResponse(
                state="no_data",
                frames=[],
                fetched_at=now,
                message="This station has no recent scan at the selected elevation.",
                options={"elevations": [angle for angle, _ in elevations]},
            )
        selected_code = desired[1]
        objects = next(
            (
                items
                for code, items in zip(codes, listings, strict=True)
                if code == selected_code and not isinstance(items, Exception)
            ),
            [],
        )

        async def load_entry(item):
            stamp, key = item
            try:
                return stamp, await self._load(site, product, selected_code, stamp, key)
            except SourceError:
                return None

        frames = []
        selected_objects = objects[-MAX_FRAMES:]
        for start in range(0, len(selected_objects), MAX_CONCURRENT_LOADS):
            batch = selected_objects[start : start + MAX_CONCURRENT_LOADS]
            loaded = await asyncio.gather(*(load_entry(item) for item in batch))
            for item in loaded:
                if item is None:
                    continue
                object_time, grid = item
                if abs(grid.elevation - desired[0]) > 0.05:
                    continue
                frame_id = self._frame_id(site, product, selected_code, object_time)
                encoded_id = quote(frame_id, safe="")
                url = (
                    f"/weather/render/tile/{{z}}/{{x}}/{{y}}.png?source_id={self.provider_id}"
                    f"&frame_id={encoded_id}"
                )
                legend_url = f"/weather/render/legend/{self.provider_id}/{definition['scale']}.png"
                if product == "storm_relative_velocity":
                    legend_url += f"?frame_id={encoded_id}"
                bounds = _site_bounds(grid.longitude, grid.latitude)
                metadata = {
                    "product_code": definition["code"],
                    "tilt_code": selected_code,
                    "range_km": grid.max_range_km,
                    "range_bin_km": grid.gate_scale_km,
                    "storm_motion_speed_kt": grid.storm_motion_speed_kt,
                    "storm_motion_direction_deg": grid.storm_motion_direction_deg,
                }
                if product == "storm_relative_velocity":
                    metadata["storm_relative_levels_kt"] = list(grid.storm_relative_levels_kt)
                frames.append(
                    WeatherFrame(
                        id=frame_id,
                        source_type="radar",
                        provider=self.provider_id,
                        product=product,
                        valid_time=grid.valid_time,
                        render=RenderDescriptor(
                            kind="xyz",
                            url_template=url,
                            tile_size=256,
                            max_zoom=MAX_ZOOM,
                            content_version=frame_id,
                        ),
                        coverage_bounds=bounds,
                        attribution="NOAA / NEXRAD Level III",
                        units=definition["units"],
                        legend_url=legend_url,
                        site=site,
                        elevation=grid.elevation,
                        metadata=metadata,
                    )
                )
        frames.sort(key=lambda frame: frame.valid_time)
        state = (
            "no_data"
            if not frames
            else "source_delayed"
            if now - frames[-1].valid_time > timedelta(minutes=20)
            else "ready"
        )
        return WeatherFramesResponse(
            state=state,
            frames=frames,
            fetched_at=now,
            message=(
                "NEXRAD elevation is read from each Level III product header."
                if frames
                else "No recent scans matched this elevation."
            ),
            options={"elevations": [angle for angle, _ in elevations]},
        )

    async def render_tile(self, frame_id: str, zoom: int, x: int, y: int) -> bytes:
        site, product, code, stamp = self._identity(frame_id)
        cache_key = (frame_id, f"{zoom}/{x}/{y}")
        cached = self._tiles.get(cache_key)
        if cached is not None:
            self._tiles.move_to_end(cache_key)
            return cached
        grid = await self._load(site, product, code, stamp)
        rendered = await asyncio.to_thread(grid.tile, zoom, x, y)
        self._tiles[cache_key] = rendered
        self._tiles.move_to_end(cache_key)
        while len(self._tiles) > MAX_RENDERED_TILES:
            self._tiles.popitem(last=False)
        return rendered

    async def capture(self, layer, bounds: list[float]) -> bytes:
        if layer.source_type != "radar" or layer.provider != self.provider_id:
            raise SourceError(
                "unsupported_product", "Only a NEXRAD frame can be captured by this adapter"
            )
        site, product, code, stamp = self._identity(layer.frame_id)
        if (site, product) != (layer.radar_site, layer.product):
            raise SourceError(
                "unsupported_product", "NEXRAD frame identity did not match the selected layer"
            )
        grid = await self._load(site, product, code, stamp)
        if grid.valid_time != layer.valid_time:
            raise SourceError(
                "unsupported_product", "NEXRAD timestamp did not match the selected layer"
            )
        if layer.elevation is None or abs(grid.elevation - layer.elevation) > 0.05:
            raise SourceError(
                "unsupported_product", "NEXRAD elevation did not match the selected layer"
            )
        return await asyncio.to_thread(grid.image, bounds)

    async def render_legend(self, product: str, frame_id: str | None = None) -> bytes:
        if product not in SCALES:
            raise SourceError("unsupported_product", "This NEXRAD legend is not available")
        if product != "storm_relative_velocity" or frame_id is None:
            return await asyncio.to_thread(legend_png, product)
        site, frame_product, code, stamp = self._identity(frame_id)
        if frame_product != product:
            raise SourceError(
                "unsupported_product", "NEXRAD legend does not match the selected product"
            )
        grid = await self._load(site, product, code, stamp)
        return await asyncio.to_thread(
            legend_png,
            product,
            levels_kt=grid.storm_relative_levels_kt,
        )


def _key_time(key: str, site: str, code: str) -> datetime | None:
    match = _KEY_RE.fullmatch(key.rsplit("/", 1)[-1])
    if match is None or match.group("site") != site[1:] or match.group("code") != code:
        return None
    fields = match.groupdict()
    try:
        return datetime(
            int(fields["year"]),
            int(fields["month"]),
            int(fields["day"]),
            int(fields["hour"]),
            int(fields["minute"]),
            int(fields["second"]),
            tzinfo=UTC,
        )
    except ValueError:
        return None


def _xml_text(node, name: str) -> str:
    child = node.find(f"{{*}}{name}")
    return child.text if child is not None and child.text else ""


def _site_bounds(longitude: float, latitude: float) -> list[float]:
    lons, lats, _ = _GEOD.fwd(
        np.full(4, longitude),
        np.full(4, latitude),
        np.asarray([0.0, 90.0, 180.0, 270.0]),
        np.full(4, RADAR_RANGE_KM * 1000),
    )
    return [float(np.min(lons)), float(np.min(lats)), float(np.max(lons)), float(np.max(lats))]
