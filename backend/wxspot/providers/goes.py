"""NOAA ABI fixed-grid imagery; real scan identity, DQF masks and official GeoColor."""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from io import BytesIO
from urllib.parse import quote

import h5netcdf
import httpx
import numpy as np
from defusedxml.ElementTree import fromstring
from PIL import Image
from pyproj import CRS, Transformer

from wxspot.providers.grids import PreparedGrid
from wxspot.providers.prepared import PreparedProvider
from wxspot.providers.render import SCALES, legend_png
from wxspot.weather import SourceError
from wxspot.weather_contracts import (
    RenderDescriptor,
    WeatherFrame,
    WeatherFramesResponse,
    WeatherProduct,
)

PRODUCTS = {
    "geocolor": ("13", "GeoColor", "RGB composite", "satellite_vis"),
    "visible": ("02", "Visible · C02", "% reflectance", "satellite_vis"),
    "infrared": ("13", "Clean longwave infrared · C13", "°C", "satellite_ir"),
    "water_vapor_upper": ("08", "Upper water vapor · C08", "°C", "satellite_ir"),
    "water_vapor_mid": ("09", "Middle water vapor · C09", "°C", "satellite_ir"),
    "water_vapor_lower": ("10", "Lower water vapor · C10", "°C", "satellite_ir"),
}
IDENTITY = re.compile(r"^goes:(\d{2}):([a-z_]+):(\d{14}):v1$")
OBJECT = re.compile(r"_G(\d{2})_s(\d{14})_e(\d{14})_c\d{14}\.nc$")
MAX_INPUT = 128 * 1024 * 1024
CAPABILITIES = "https://nowcoast.noaa.gov/geoserver/satellite/wms"


def scan_time(code):
    return datetime.strptime(code[:13], "%Y%j%H%M%S").replace(tzinfo=UTC) + timedelta(
        microseconds=int(code[13]) * 100000
    )


def text_value(value):
    return value.decode() if isinstance(value, bytes) else str(value)


def decode_abi(content, product, satellite, start, end):
    with h5netcdf.File(BytesIO(content), "r") as dataset:
        if dataset.attrs["platform_ID"] != f"G{satellite}":
            raise SourceError("source_unavailable", "ABI satellite identity did not match.")
        for attribute, expected in (("time_coverage_start", start), ("time_coverage_end", end)):
            actual = datetime.fromisoformat(
                text_value(dataset.attrs[attribute]).replace("Z", "+00:00")
            )
            if abs((actual - expected).total_seconds()) > 0.2:
                raise SourceError("source_unavailable", "ABI scan timestamp did not match.")
        variable = dataset.variables["CMI"]
        if int(np.asarray(dataset.variables["band_id"][()]).item()) != int(PRODUCTS[product][0]):
            raise SourceError("source_unavailable", "ABI channel did not match.")
        if np.prod(variable.shape) * 2 > 192 * 1024 * 1024:
            raise SourceError("source_unavailable", "ABI grid exceeds its memory budget.")
        values = np.empty(variable.shape, dtype=np.uint16)
        for first in range(0, variable.shape[0], 256):
            rows = slice(first, min(first + 256, variable.shape[0]))
            raw = variable[rows, :]
            values[rows, :] = raw.view(np.uint16)
            values[rows, :][
                (raw == variable.attrs["_FillValue"]) | (dataset.variables["DQF"][rows, :] > 1)
            ] = 65535
        visible = product == "visible"
        actual_units = text_value(variable.attrs["units"])
        if (visible and actual_units != "1") or (not visible and actual_units != "K"):
            raise SourceError("source_unavailable", "ABI physical units did not match.")
        projection = dataset.variables["goes_imager_projection"].attrs
        height = float(projection["perspective_point_height"])
        crs = CRS.from_proj4(
            f"+proj=geos +h={height} +lon_0={projection['longitude_of_projection_origin']} "
            f"+a={projection['semi_major_axis']} +b={projection['semi_minor_axis']} "
            f"+sweep={text_value(projection['sweep_angle_axis'])} +units=m"
        ).to_wkt()
        x, y = dataset.variables["x"], dataset.variables["y"]
        dx = float(x.attrs["scale_factor"]) * height
        dy = float(y.attrs["scale_factor"]) * height
        x0 = (float(x[0]) * float(x.attrs["scale_factor"]) + float(x.attrs["add_offset"])) * height
        y0 = (float(y[0]) * float(y.attrs["scale_factor"]) + float(y.attrs["add_offset"])) * height
        metadata = {
            "satellite": f"GOES-{satellite}",
            "orbital_slot": dataset.attrs["orbital_slot"],
            "scan_start": start.isoformat(),
            "scan_end": end.isoformat(),
            "native_resolution": dataset.attrs["spatial_resolution"],
            "units": PRODUCTS[product][2],
            "packed_fill": 65535,
            "sampling_scale": float(variable.attrs["scale_factor"]) * (100 if visible else 1),
            "sampling_offset": float(variable.attrs["add_offset"]) * (100 if visible else 1)
            - (0 if visible else 273.15),
            "quality": "DQF 0/1 retained; out-of-range/no-value pixels masked",
        }
        return PreparedGrid(values, crs, x0, y0, dx, dy, PRODUCTS[product][3], metadata)


def apply_geocolor(grid, image):
    ny, nx = grid.values.shape
    with Image.open(BytesIO(image)) as source:
        # Preserve the fixed grid and trim any separately appended timestamp strip.
        if source.width != nx or source.height not in {ny, ny + 30}:
            raise SourceError(
                "source_unavailable", "GeoColor dimensions do not match the ABI grid."
            )
        rgba = np.asarray(source.crop((0, 0, nx, ny)).convert("RGBA")).copy()
    x = grid.x0 + np.arange(nx) * grid.dx
    y = grid.y0 + np.arange(ny) * grid.dy
    transform = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
    for first in range(0, ny, 256):
        rows = slice(first, first + 256)
        lon, lat = transform.transform(*np.meshgrid(x, y[rows]))
        rgba[rows, :, 3][~(np.isfinite(lon) & np.isfinite(lat))] = 0
    # The upstream logo occupies this corner of the derivative; keep it out of geospatial data.
    rgba[-170:, :170, 3] = 0
    rgba[-30:, :, 3] = 0
    metadata = {
        k: v for k, v in grid.metadata.items() if not k.startswith(("packed_", "sampling_"))
    }
    metadata.update(
        {
            "units": "RGB composite",
            "method": "NOAA STAR/CIRA GeoColor; ABI fixed grid; static city lights and borders",
        }
    )
    return PreparedGrid(rgba, grid.crs, grid.x0, grid.y0, grid.dx, grid.dy, "geocolor", metadata)


class GoesProvider(PreparedProvider):
    source_type = "satellite"
    provider_id = "noaa-goes"

    def __init__(self, client, storage):
        super().__init__(client, storage)
        self._satellites = None
        self._discovered_at = None
        self._inventory = {}
        self._composites = {}

    async def source_request(self, url, params=None):
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceError(
                "source_unavailable", "NOAA satellite source is unavailable."
            ) from exc
        if len(response.content) > 8 * 1024 * 1024:
            raise SourceError("source_unavailable", "Satellite catalog exceeds its size budget.")
        return response

    async def composite_minutes(self, satellite):
        now = datetime.now(UTC)
        cached = self._composites.get(satellite)
        if cached and now - cached[0] < timedelta(seconds=60):
            return cached[1]
        response = await self.source_request(
            f"https://cdn.star.nesdis.noaa.gov/GOES{satellite}/ABI/CONUS/GEOCOLOR/"
        )
        minutes = set(
            re.findall(
                rf"(\d{{11}})_GOES{satellite}-ABI-CONUS-GEOCOLOR-2500x1500\.jpg", response.text
            )
        )
        self._composites[satellite] = (now, minutes)
        return minutes

    async def render_legend(self, product, frame_id=None):
        self.scale_product(product)
        return await asyncio.to_thread(
            legend_png, "geocolor" if product == "geocolor" else self.scale_product(product)
        )

    def scale_product(self, product):
        if product not in PRODUCTS:
            raise SourceError("unsupported_product", "This ABI product is not supported.")
        return PRODUCTS[product][3]

    def products(self):
        return [
            WeatherProduct(
                source_type=self.source_type,
                provider=self.provider_id,
                source_id=self.provider_id,
                product_id=product,
                display_name=values[1],
                units=values[2],
                attribution="NOAA NESDIS / STAR; GeoColor: CIRA / NOAA",
                coverage_bounds=[-180, 0, -40, 65],
                legend_url=f"/weather/render/legend/{self.provider_id}/{product}.png?source_type=satellite",
                capabilities={
                    "timeline": True,
                    "exact_capture": True,
                    "sectors": ["east", "west"],
                    "nighttime": "Visible is dark at night; GeoColor uses an IR composite.",
                },
            )
            for product, values in PRODUCTS.items()
        ]

    async def satellites(self):
        now = datetime.now(UTC)
        if self._satellites and now - self._discovered_at < timedelta(hours=6):
            return self._satellites
        response = await self.source_request(
            CAPABILITIES, params={"service": "WMS", "request": "GetCapabilities"}
        )
        match = re.search(r"GOES-(\d+) \(East\).*?GOES-(\d+) \(West\)", response.text)
        if match is None:
            raise SourceError("source_unavailable", "Operational GOES identities are unavailable.")
        self._satellites = {"east": match[1], "west": match[2]}
        self._discovered_at = now
        return self._satellites

    def parse_identity(self, frame_id):
        match = IDENTITY.fullmatch(frame_id)
        if not match or match[2] not in PRODUCTS:
            raise SourceError("unsupported_product", "Invalid ABI frame identity.")
        return match[1], match[2], match[3]

    async def inventory(self, satellite, product, hour):
        key = (satellite, product, hour)
        now = datetime.now(UTC)
        cached = self._inventory.get(key)
        if cached and now - cached[0] < timedelta(seconds=60):
            return cached[1]
        prefix = f"ABI-L2-CMIPC/{hour:%Y}/{hour:%j}/{hour:%H}/"
        response = await self.source_request(
            f"https://noaa-goes{satellite}.s3.amazonaws.com/",
            params={"list-type": "2", "prefix": prefix, "max-keys": 1000},
        )
        objects = []
        for element in fromstring(response.content).findall(".//{*}Key"):
            name = element.text or ""
            match = OBJECT.search(name)
            if (
                match
                and match[1] == satellite
                and re.search(f"M[36]C{PRODUCTS[product][0]}_", name)
            ):
                objects.append((match[2], match[3], name))
        self._inventory[key] = (now, objects)
        if len(self._inventory) > 48:
            self._inventory.pop(next(iter(self._inventory)))
        return objects

    def frame(self, satellite, product, start, end):
        identifier = f"goes:{satellite}:{product}:{start}:v1"
        start_time, end_time = scan_time(start), scan_time(end)
        valid = (
            start_time.replace(second=0, microsecond=0)
            if product == "geocolor"
            else start_time + (end_time - start_time) / 2
        )
        return WeatherFrame(
            id=identifier,
            source_type=self.source_type,
            provider=self.provider_id,
            product=product,
            valid_time=valid,
            satellite=f"GOES-{satellite}",
            channel="GeoColor" if product == "geocolor" else "C" + PRODUCTS[product][0],
            domain="CONUS",
            units=PRODUCTS[product][2],
            attribution="NOAA NESDIS / STAR; GeoColor: CIRA / NOAA",
            render=RenderDescriptor(
                kind="xyz",
                url_template=(
                    "/weather/render/tile/{z}/{x}/{y}.png?source_type=satellite"
                    f"&source_id={self.provider_id}&frame_id={quote(identifier, safe='')}"
                ),
                content_version=identifier,
                max_zoom=12,
            ),
            coverage_bounds=[-180, 0, -40, 65],
            legend_url=f"/weather/render/legend/{self.provider_id}/{product}.png?source_type=satellite",
            metadata={
                "scan_start": start_time.isoformat(),
                "scan_end": end_time.isoformat(),
                "sector": "CONUS",
                "time_method": "STAR composite filename minute"
                if product == "geocolor"
                else "ABI scan midpoint",
                "nighttime": "Visible imagery is dark at night.",
                "legend_min": None
                if product == "geocolor"
                else SCALES[PRODUCTS[product][3]].minimum,
                "legend_max": None
                if product == "geocolor"
                else SCALES[PRODUCTS[product][3]].maximum,
            },
        )

    async def frames(self, selection):
        if selection.product_id not in PRODUCTS or selection.domain not in {None, "east", "west"}:
            raise SourceError("unsupported_product", "Choose a supported ABI product and sector.")
        satellites = await self.satellites()
        satellite = satellites[selection.domain or "east"]
        composites = (
            await self.composite_minutes(satellite) if selection.product_id == "geocolor" else None
        )
        now = datetime.now(UTC)
        frames = []
        for offset in range(4):
            hour = (now - timedelta(hours=offset)).replace(minute=0, second=0, microsecond=0)
            for start, end, _ in await self.inventory(satellite, selection.product_id, hour):
                if now - timedelta(hours=3) <= scan_time(start) <= now and (
                    composites is None or start[:11] in composites
                ):
                    frame = self.frame(satellite, selection.product_id, start, end)
                    frame.metadata["satellite_sector"] = selection.domain or "east"
                    frames.append(frame)
        frames.sort(key=lambda f: f.valid_time)
        state = (
            "no_data"
            if not frames
            else (
                "source_delayed" if now - frames[-1].valid_time > timedelta(minutes=20) else "ready"
            )
        )
        return WeatherFramesResponse(state=state, frames=frames[-40:], fetched_at=now)

    async def resolve_frame(self, frame_id):
        sat, product, start = self.parse_identity(frame_id)
        for found_start, end, _ in await self.inventory(
            sat, product, scan_time(start).replace(minute=0, second=0, microsecond=0)
        ):
            if found_start == start:
                return self.frame(sat, product, start, end)
        raise SourceError("no_data", "That exact ABI scan is unavailable upstream.")

    async def download(self, url):
        data = bytearray()
        async with self.client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                if len(data) + len(chunk) > MAX_INPUT:
                    raise SourceError(
                        "source_unavailable", "ABI input exceeds its processing budget."
                    )
                data.extend(chunk)
        return bytes(data)

    async def prepare_artifact(self, frame_id):
        satellite, product, start = self.parse_identity(frame_id)
        hour = scan_time(start).replace(minute=0, second=0, microsecond=0)
        objects = await self.inventory(satellite, product, hour)
        found = next((o for o in objects if o[0] == start), None)
        if found is None:
            raise SourceError("no_data", "That exact ABI scan is unavailable upstream.")
        _, end, key = found
        raw = await self.download(f"https://noaa-goes{satellite}.s3.amazonaws.com/{key}")
        grid = await asyncio.to_thread(
            decode_abi, raw, product, satellite, scan_time(start), scan_time(end)
        )
        if product == "geocolor":
            name = f"{start[:11]}_GOES{satellite}-ABI-CONUS-GEOCOLOR-2500x1500.jpg"
            image = await self.download(
                f"https://cdn.star.nesdis.noaa.gov/GOES{satellite}/ABI/CONUS/GEOCOLOR/{name}"
            )
            grid = await asyncio.to_thread(apply_geocolor, grid, image)
        grid.metadata["valid_time"] = self.frame(
            satellite, product, start, end
        ).valid_time.isoformat()
        return grid
