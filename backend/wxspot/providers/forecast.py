"""NCEP HRRR/GFS immutable model frames; ranged GRIB ingestion runs only in the worker."""

import asyncio
import re
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
import numpy as np
from defusedxml.ElementTree import fromstring

from wxspot.providers.grids import PreparedGrid
from wxspot.providers.model_grids import (
    accumulate_nonoverlapping,
    decode_model_message,
    earth_winds,
)
from wxspot.providers.prepared import PreparedProvider
from wxspot.weather import SourceError
from wxspot.weather_cache import read_cache, write_cache
from wxspot.weather_contracts import (
    RenderDescriptor,
    WeatherFrame,
    WeatherFramesResponse,
    WeatherProduct,
)
from wxspot.weather_jobs import content_key, reserve_artifact

MODEL_BUCKETS = {
    "hrrr": "https://noaa-hrrr-bdp-pds.s3.amazonaws.com",
    "gfs": "https://noaa-gfs-bdp-pds.s3.amazonaws.com",
}
MODEL_PRODUCTS = {
    "reflectivity": (
        "Forecast composite reflectivity",
        "dBZ",
        "REFC",
        "entire atmosphere",
        "reflectivity",
    ),
    "temperature": ("2 m temperature", "°C", "TMP", "2 m above ground", "temperature"),
    "dew_point": ("2 m dew point", "°C", "DPT", "2 m above ground", "dew_point"),
    "wind": ("10 m wind speed and direction", "m/s", "UGRD", "10 m above ground", "wind"),
    "gust": ("Forecast surface gust", "m/s", "GUST", "surface", "wind"),
    "precip_interval": (
        "Precipitation · actual accumulation interval",
        "mm",
        "APCP",
        "surface",
        "precip_1h",
    ),
    "precip_total": ("Precipitation · complete run total", "mm", "APCP", "surface", "precip_24h"),
    "cape": ("Surface-based CAPE", "J/kg", "CAPE", "surface", "cape"),
    "cin": ("Surface-based CIN", "J/kg", "CIN", "surface", "cin"),
    "pwat": (
        "Entire-atmosphere precipitable water",
        "mm",
        "PWAT",
        "entire atmosphere (considered as a single layer)",
        "pwat",
    ),
}
IDENTITY = re.compile(r"^model:(hrrr|gfs):(\d{8}T\d{4}Z):(\d{3}):([a-z_]+):v1$")


def forecast_hours(model, run):
    if model == "hrrr":
        return list(range(49 if run.hour in {0, 6, 12, 18} else 19))
    return list(range(121)) + list(range(123, 169, 3))


def model_object(model, run, hour, pressure=False):
    if model == "hrrr":
        product = "prs" if pressure else "sfc"
        return f"hrrr.{run:%Y%m%d}/conus/hrrr.t{run:%H}z.wrf{product}f{hour:02d}.grib2"
    return f"gfs.{run:%Y%m%d}/{run:%H}/atmos/gfs.t{run:%H}z.pgrb2.0p25.f{hour:03d}"


def parse_index(content):
    entries = []
    for line in content.splitlines():
        parts = line.split(":")
        if len(parts) < 7 or not parts[1].isdigit():
            raise SourceError("source_unavailable", "Model index contains an invalid record.")
        entries.append(
            {
                "offset": int(parts[1]),
                "mnemonic": parts[3],
                "level": parts[4],
                "description": parts[5],
            }
        )
    if len(entries) > 1500:
        raise SourceError("source_unavailable", "Model index exceeds its record budget.")
    for index, entry in enumerate(entries):
        next_offset = next(
            (e["offset"] for e in entries[index + 1 :] if e["offset"] > entry["offset"]), None
        )
        entry["end"] = None if next_offset is None else next_offset - 1
    return entries


class ModelProvider(PreparedProvider):
    source_type = "model"
    provider_id = "noaa-models"

    def __init__(self, client, storage):
        super().__init__(client, storage)
        self._inventories = OrderedDict()
        self._indexes = OrderedDict()
        self._fields = OrderedDict()
        self.job = None

    def parse_identity(self, frame_id):
        match = IDENTITY.fullmatch(frame_id)
        if not match or match[4] not in MODEL_PRODUCTS:
            raise SourceError("unsupported_product", "Invalid model frame identity.")
        model, run, hour, product = match.groups()
        run = datetime.strptime(run, "%Y%m%dT%H%MZ").replace(tzinfo=UTC)
        hour = int(hour)
        if (
            run.minute
            or (model == "gfs" and run.hour not in {0, 6, 12, 18})
            or hour not in forecast_hours(model, run)
        ):
            raise SourceError("unsupported_product", "Unsupported model run or forecast hour.")
        return model, run, hour, product

    def scale_product(self, product):
        if product not in MODEL_PRODUCTS:
            raise SourceError("unsupported_product", "Choose a supported forecast field.")
        return MODEL_PRODUCTS[product][4]

    def products(self):
        return [
            WeatherProduct(
                source_type="model",
                provider=self.provider_id,
                source_id=self.provider_id,
                product_id=p,
                display_name=v[0],
                units=v[1],
                attribution="NOAA / NCEP HRRR and GFS forecasts",
                coverage_bounds=[-130, 20, -60, 55],
                legend_url=f"/weather/render/legend/{self.provider_id}/{p}.png?source_type=model",
                capabilities={
                    "models": ["hrrr", "gfs"],
                    "run_selection": True,
                    "exact_capture": True,
                    "native_resolution": {"hrrr": "3 km", "gfs": "0.25 degrees"},
                    "domain": "CONUS",
                },
            )
            for p, v in MODEL_PRODUCTS.items()
        ]

    async def catalog_request(self, url, params=None):
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceError("source_unavailable", "NCEP model inventory is unavailable.") from exc
        if len(response.content) > 8 * 1024 * 1024:
            raise SourceError("source_unavailable", "Model inventory exceeds its size budget.")
        return response

    async def inventory(self, model, run):
        key = model, run
        now = datetime.now(UTC)
        cached = self._inventories.get(key)
        if cached and now - cached[0] < timedelta(seconds=60):
            return cached[1]
        prefix = (
            f"hrrr.{run:%Y%m%d}/conus/hrrr.t{run:%H}z.wrfsfcf"
            if model == "hrrr"
            else f"gfs.{run:%Y%m%d}/{run:%H}/atmos/gfs.t{run:%H}z.pgrb2.0p25.f"
        )
        response = await self.catalog_request(
            MODEL_BUCKETS[model], {"list-type": "2", "prefix": prefix, "max-keys": 1000}
        )
        keys = {e.text for e in fromstring(response.content).findall(".//{*}Key")}
        hours = [
            h
            for h in forecast_hours(model, run)
            if model_object(model, run, h) in keys and model_object(model, run, h) + ".idx" in keys
        ]
        self._inventories[key] = now, hours
        while len(self._inventories) > 24:
            self._inventories.popitem(last=False)
        return hours

    async def available_runs(self, model):
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        if model == "gfs":
            now = now.replace(hour=(now.hour // 6) * 6)
        runs = []
        candidates = [
            now - timedelta(hours=offset * (1 if model == "hrrr" else 6))
            for offset in range(5 if model == "hrrr" else 4)
        ]
        if model == "hrrr":
            extended = now.replace(hour=now.hour // 6 * 6)
            candidates.extend([extended, extended - timedelta(hours=6)])
        for run in sorted(set(candidates), reverse=True):
            if await self.inventory(model, run):
                runs.append(run)
        return runs

    def frame(self, model, run, hour, product):
        identifier = f"model:{model}:{run:%Y%m%dT%H%MZ}:{hour:03d}:{product}:v1"
        return WeatherFrame(
            id=identifier,
            source_type="model",
            provider=self.provider_id,
            product=product,
            valid_time=run + timedelta(hours=hour),
            model=model,
            run_time=run,
            forecast_hour=hour,
            vertical_level="entire atmosphere" if product == "pwat" else MODEL_PRODUCTS[product][3],
            domain="CONUS",
            units=MODEL_PRODUCTS[product][1],
            attribution="NOAA / NCEP · model forecast",
            coverage_bounds=[-130, 20, -60, 55],
            legend_url=f"/weather/render/legend/{self.provider_id}/{product}.png?source_type=model",
            render=RenderDescriptor(
                kind="xyz",
                url_template="/weather/render/tile/{z}/{x}/{y}.png?source_type=model"
                + f"&source_id={self.provider_id}&frame_id={quote(identifier, safe='')}",
                content_version=identifier,
                max_zoom=12,
            ),
            metadata={
                "forecast": True,
                "native_resolution": "3 km" if model == "hrrr" else "0.25 degrees",
                "parcel": "surface-based" if product in {"cape", "cin"} else None,
                "interval": "Read from exact GRIB accumulation metadata"
                if product.startswith("precip_")
                else None,
            },
        )

    async def frames(self, selection):
        model = selection.model or "hrrr"
        if (
            model not in MODEL_BUCKETS
            or selection.product_id not in MODEL_PRODUCTS
            or selection.domain not in {None, "conus", "CONUS"}
        ):
            raise SourceError(
                "unsupported_product", "Choose HRRR or GFS and a supported CONUS field."
            )
        runs = await self.available_runs(model)
        if not runs:
            return WeatherFramesResponse(
                state="no_data", frames=[], message="No published model runs are available."
            )
        run = selection.run_time or runs[0]
        hours = await self.inventory(model, run)
        if selection.product_id.startswith("precip_"):
            hours = [h for h in hours if h > 0]
        if selection.forecast_hour is not None:
            hours = [h for h in hours if h == selection.forecast_hour]
        frames = [self.frame(model, run, h, selection.product_id) for h in hours]
        return WeatherFramesResponse(
            state="ready" if frames else "no_data",
            frames=frames,
            fetched_at=datetime.now(UTC),
            options={
                "runs": [r.isoformat() for r in runs],
                "selected_run": run.isoformat(),
                "forecast_hours": hours,
            },
        )

    async def resolve_frame(self, frame_id):
        model, run, hour, product = self.parse_identity(frame_id)
        if hour not in await self.inventory(model, run):
            raise SourceError("no_data", "That exact model run/hour is unavailable upstream.")
        return self.frame(model, run, hour, product)

    async def index(self, model, run, hour, pressure=False):
        key = model, run, hour, pressure
        if key not in self._indexes:
            response = await self.catalog_request(
                MODEL_BUCKETS[model] + "/" + model_object(model, run, hour, pressure) + ".idx"
            )
            self._indexes[key] = parse_index(response.text)
            while len(self._indexes) > 32:
                self._indexes.popitem(last=False)
        return self._indexes[key]

    async def download_message(self, model, run, hour, entry, pressure=False):
        start, end = entry["offset"], entry["end"]
        url = MODEL_BUCKETS[model] + "/" + model_object(model, run, hour, pressure)
        if end is None:
            response = await self.client.head(url)
            response.raise_for_status()
            end = int(response.headers["Content-Length"]) - 1
        if not 0 < end - start + 1 <= 16 * 1024 * 1024:
            raise SourceError("source_unavailable", "GRIB message exceeds its processing budget.")
        async with self.client.stream(
            "GET",
            url,
            headers={"Range": f"bytes={start}-{end}"},
            params={"wxspot_range": str(start)},
        ) as response:
            if response.status_code != 206 or not response.headers.get(
                "Content-Range", ""
            ).startswith(f"bytes {start}-{end}/"):
                raise SourceError(
                    "source_unavailable", "Model source did not honor the exact byte range."
                )
            data = bytearray()
            async for block in response.aiter_bytes():
                if len(data) + len(block) > end - start + 1:
                    raise SourceError("source_unavailable", "GRIB range exceeded its size.")
                data.extend(block)
        if len(data) != end - start + 1:
            raise SourceError("source_unavailable", "Incomplete model GRIB range.")
        return bytes(data)

    async def field(self, model, run, hour, mnemonic, level, preference="instant"):
        key = model, run, hour, mnemonic, level, preference
        if key in self._fields:
            self._fields.move_to_end(key)
            return self._fields[key]
        cache_key = content_key(
            {
                "kind": "model_field",
                "model": model,
                "run": run.isoformat(),
                "hour": hour,
                "mnemonic": mnemonic,
                "level": level,
                "preference": preference,
                "domain": "CONUS",
            }
        )
        cached = await read_cache(cache_key) if self.job else None
        if cached:
            grid = await asyncio.to_thread(
                PreparedGrid.decode, await self.storage.get(cached["object_key"])
            )
            self._fields[key] = grid
            self.trim_fields()
            return grid
        entries = [
            e
            for e in await self.index(model, run, hour)
            if (e["mnemonic"], e["level"]) == (mnemonic, level)
        ]
        if not entries:
            raise SourceError("no_data", "This field is missing from the exact forecast hour.")
        candidates = []
        for entry in entries:
            raw = await self.download_message(model, run, hour, entry)
            grid = await asyncio.to_thread(decode_model_message, raw, run, hour, mnemonic, level)
            candidates.append(grid)
        candidates.sort(key=lambda g: g.metadata["start_step"], reverse=preference != "total")
        grid = candidates[0]
        for other in candidates[1:]:
            if other.metadata["start_step"] == grid.metadata["start_step"] and not np.array_equal(
                other.values, grid.values, equal_nan=True
            ):
                raise SourceError(
                    "source_unavailable", "Conflicting duplicate model accumulation messages."
                )
        self._fields[key] = grid
        self.trim_fields()
        if self.job:
            artifact = f"weather-live/{self.job.content_key}/{self.job.lease_token}.{cache_key}.npz"
            await reserve_artifact(self.job, artifact)
            await self.storage.put(
                artifact, await asyncio.to_thread(grid.encode), "application/octet-stream"
            )
            await write_cache(
                cache_key, "model_field", {"object_key": artifact}, self.job.expires_at
            )
        return grid

    def trim_fields(self):
        while sum(g.values.nbytes for g in self._fields.values()) > 64 * 1024 * 1024:
            self._fields.popitem(last=False)

    async def prepare_artifact(self, frame_id):
        model, run, hour, product = self.parse_identity(frame_id)
        _, units, mnemonic, level, scale = MODEL_PRODUCTS[product]
        grid = await self.field(
            model, run, hour, mnemonic, level, "total" if product == "precip_total" else "instant"
        )
        if product == "wind":
            v = await self.field(model, run, hour, "VGRD", level)
            u, v = await asyncio.to_thread(earth_winds, grid, v)
            grid = PreparedGrid(
                np.stack([np.hypot(u, v), u, v], axis=-1),
                grid.crs,
                grid.x0,
                grid.y0,
                grid.dx,
                grid.dy,
                scale,
                {
                    **grid.metadata,
                    "vector_wind": True,
                    "wind_rotation": "earth-relative east/north",
                },
            )
        elif product == "precip_total":
            intervals = [grid]
            cursor = grid.metadata["start_step"]
            while cursor > 0:
                prior = await self.field(model, run, cursor, mnemonic, level, "total")
                if prior.metadata["end_step"] != cursor or prior.metadata["start_step"] >= cursor:
                    raise SourceError("no_data", "A required precipitation interval is missing.")
                intervals.append(prior)
                cursor = prior.metadata["start_step"]
                if len(intervals) > 137:
                    raise SourceError("source_unavailable", "Too many precipitation intervals.")
            grid = await asyncio.to_thread(accumulate_nonoverlapping, intervals, hour)
        else:
            grid = PreparedGrid(
                grid.values,
                grid.crs,
                grid.x0,
                grid.y0,
                grid.dx,
                grid.dy,
                scale,
                dict(grid.metadata),
            )
        grid.product = scale
        grid.metadata.update(
            {
                "units": units,
                "product": product,
                "model": model,
                "domain": "CONUS",
                "vertical_level": level,
                "forecast_hour": hour,
                "run_time": run.isoformat(),
                "valid_time": (run + timedelta(hours=hour)).isoformat(),
            }
        )
        if product.startswith("precip_"):
            grid.metadata["accumulation_start"] = (
                run + timedelta(hours=grid.metadata["start_step"])
            ).isoformat()
            grid.metadata["accumulation_end"] = (
                run + timedelta(hours=grid.metadata["end_step"])
            ).isoformat()
        return grid
