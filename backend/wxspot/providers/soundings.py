"""Worker-only native forecast columns and QC-preserving NOAA IGRA launches."""

import asyncio
import hashlib
import json
import math
import re
import time
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO, TextIOWrapper
from zipfile import ZipFile

import httpx
import numpy as np
from metpy.calc import dewpoint_from_relative_humidity
from metpy.units import units
from pyproj import Geod, Transformer

from wxspot.providers.forecast import ModelProvider, forecast_hours, model_object
from wxspot.providers.grib_client import isolated_grib
from wxspot.providers.model_grids import decode_model_message, earth_winds
from wxspot.sounding_contracts import SoundingLevel, SoundingProfile
from wxspot.weather import SourceError
from wxspot.weather_cache import read_cache, write_bounded_raw_cache
from wxspot.weather_jobs import content_key, reserve_artifact

IGRA_ROOT = "https://www.ncei.noaa.gov/pub/data/igra"
PRESSURES = list(range(1000, 49, -25))
GEOD = Geod(ellps="WGS84")


def distance_km(point, sample):
    return abs(GEOD.inv(*point, *sample)[2]) / 1000


def nearest_column(grid, point):
    x, y = Transformer.from_crs(4326, grid.crs, always_xy=True).transform(*point)
    col, row = round((x - grid.x0) / grid.dx), round((y - grid.y0) / grid.dy)
    ny, nx = grid.values.shape
    if not (0 <= col < nx and 0 <= row < ny):
        raise SourceError("no_data", "This point lies outside the actual model grid.")
    x, y = grid.x0 + col * grid.dx, grid.y0 + row * grid.dy
    sample = list(Transformer.from_crs(grid.crs, 4326, always_xy=True).transform(x, y))
    return row, col, sample


def scalar(value):
    return float(value) if np.isfinite(value) else None


def geometry(grid):
    return grid.crs, grid.x0, grid.y0, grid.dx, grid.dy, grid.values.shape


def assemble_column(fields, payload, byte_count, origin_count):
    base = fields.get(("PRES", "surface"))
    terrain = fields.get(("HGT", "surface"))
    if base is None or terrain is None:
        raise SourceError("no_data", "The exact profile is missing surface pressure/terrain.")
    row, col, sample = nearest_column(base, [payload["lon"], payload["lat"]])
    if any(geometry(grid) != geometry(base) for grid in fields.values()):
        raise SourceError("source_unavailable", "Profile fields do not share one native grid.")
    surface_p = scalar(base.values[row, col] / 100)
    terrain_z = scalar(terrain.values[row, col])
    if surface_p is None or terrain_z is None:
        raise SourceError("no_data", "Surface pressure or terrain is masked at this point.")

    def value(mnemonic, level):
        grid = fields.get((mnemonic, level))
        return scalar(grid.values[row, col]) if grid else None

    def winds(level):
        u, v = fields.get(("UGRD", level)), fields.get(("VGRD", level))
        if u is None or v is None:
            return None, None
        x, y = base.x0 + col * base.dx, base.y0 + row * base.dy
        u = replace(u, values=u.values[row : row + 1, col : col + 1], x0=x, y0=y)
        v = replace(v, values=v.values[row : row + 1, col : col + 1], x0=x, y0=y)
        u, v = earth_winds(u, v)
        return scalar(u[0, 0]), scalar(v[0, 0])

    u, v = winds("10 m above ground")
    levels = [
        SoundingLevel(
            pressure_hpa=surface_p,
            temperature_c=value("TMP", "2 m above ground"),
            dewpoint_c=value("DPT", "2 m above ground"),
            height_m_msl=terrain_z + 10,
            u_ms=u,
            v_ms=v,
            quality=["2 m thermodynamics; 10 m wind near-surface anchor"],
        )
    ]
    below = 0
    pressures = sorted(
        {int(level[:-3]) for _, level in fields if level.endswith(" mb")}, reverse=True
    )
    for pressure in pressures:
        if pressure >= surface_p:
            below += 1
            continue
        level = f"{pressure} mb"
        temperature, dewpoint = value("TMP", level), value("DPT", level)
        rh = value("RH", level)
        if dewpoint is None and temperature is not None and rh is not None and 0 < rh <= 200:
            dewpoint = scalar(
                dewpoint_from_relative_humidity(temperature * units.degC, rh * units.percent).m
            )
        height = value("HGT", level)
        if height is not None and height < terrain_z:
            below += 1
            continue
        u, v = winds(level)
        levels.append(
            SoundingLevel(
                pressure_hpa=pressure,
                temperature_c=temperature,
                dewpoint_c=dewpoint,
                height_m_msl=height,
                u_ms=u,
                v_ms=v,
                quality=(
                    ["dew point derived from RH"]
                    + (["Published supersaturated RH"] if rh is not None and rh > 100 else [])
                    if ("DPT", level) not in fields
                    else []
                ),
            )
        )
    run = datetime.fromisoformat(payload["run_time"])
    return SoundingProfile(
        identity=content_key(payload),
        kind="forecast",
        source="NOAA / NCEP",
        model=payload["model"],
        domain="CONUS",
        run_time=run,
        forecast_hour=payload["forecast_hour"],
        valid_time=run + timedelta(hours=payload["forecast_hour"]),
        sampled_point=sample,
        terrain_m_msl=terrain_z,
        surface_pressure_hpa=surface_p,
        method="One nearest native grid column; isobaric levels, 2 m T/Td, 10 m wind anchor.",
        fetched_at=datetime.now(UTC),
        levels=levels,
        quality=[f"{below} below-surface levels excluded", "Isobaric, not native hybrid levels"],
        metadata={
            "input_bytes": byte_count,
            "origin_requests": origin_count,
            "pressure_levels": len(pressures),
            "wind_rotation": "earth-relative east/north",
            "height_reference": "Published geopotential height and terrain in metres MSL",
        },
    )


def split_grib(content):
    offset, count = 0, 0
    while offset < len(content):
        if (
            len(content) - offset < 20
            or content[offset : offset + 4] != b"GRIB"
            or content[offset + 7] != 2
        ):
            raise SourceError("source_unavailable", "Malformed profile GRIB stream.")
        size = int.from_bytes(content[offset + 8 : offset + 16], "big")
        if not 20 <= size <= 16 * 1024 * 1024 or offset + size > len(content):
            raise SourceError("source_unavailable", "Invalid bounded GRIB message length.")
        count += 1
        if count > 350:
            raise SourceError("source_unavailable", "Profile has too many GRIB messages.")
        yield content[offset : offset + size]
        offset += size


def decode_subset(content, run, hour):
    fields = {}
    mapping = {"t": "TMP", "dpt": "DPT", "r": "RH", "gh": "HGT", "u": "UGRD", "v": "VGRD"}
    surface = {
        "sp": ("PRES", "surface"),
        "orog": ("HGT", "surface"),
        "2t": ("TMP", "2 m above ground"),
        "2d": ("DPT", "2 m above ground"),
        "10u": ("UGRD", "10 m above ground"),
        "10v": ("VGRD", "10 m above ground"),
    }
    for message in split_grib(content):
        values, meta = isolated_grib(message)
        if values.size > 2048:
            raise SourceError("source_unavailable", "NOMADS did not honor the small subset.")
        if (
            meta["typeOfLevel"] == "isobaricInhPa"
            and 50 <= meta["level"] <= 1000
            and meta["shortName"] in mapping
        ):
            key = mapping[meta["shortName"]], f"{meta['level']} mb"
        else:
            key = surface.get(meta["shortName"])
        if key:
            if key in fields:
                raise SourceError("source_unavailable", "Duplicate selected profile field.")
            fields[key] = decode_model_message(message, run, hour, *key)
    return fields


def station_catalog(content):
    rows = []
    year = datetime.now(UTC).year
    for line in content.splitlines():
        if len(line) < 88:
            continue
        try:
            station = {
                "id": line[:11],
                "lat": float(line[12:20]),
                "lon": float(line[21:30]),
                "elevation_m": float(line[31:37]),
                "state": line[38:40].strip(),
                "name": line[41:71].strip(),
                "last_year": int(line[77:81]),
            }
            if (
                station["last_year"] >= year - 1
                and abs(station["lat"]) <= 90
                and abs(station["lon"]) <= 180
                and station["elevation_m"] > -999
            ):
                rows.append(station)
        except ValueError:
            continue
    return rows


def igra_launch(header):
    date = datetime(int(header[13:17]), int(header[18:20]), int(header[21:23]), tzinfo=UTC)
    hour = int(header[24:26])
    nominal = date + timedelta(hours=hour) if hour != 99 else None
    release = int(header[27:31])
    quality = []
    if release == 9999:
        if nominal is None:
            return None, nominal, ["Launch time unavailable"]
        return nominal, nominal, ["Release time missing; nominal observation time shown"]
    release_hour, minute = divmod(release, 100)
    if minute == 99:
        minute = 0
        quality.append("Release minute unknown; release hour shown")
    if release_hour > 23 or minute > 59:
        return None, nominal, ["Invalid launch time"]
    launch = date + timedelta(hours=release_hour, minutes=minute)
    if nominal:
        if launch - nominal > timedelta(hours=12):
            launch -= timedelta(days=1)
        elif nominal - launch > timedelta(hours=12):
            launch += timedelta(days=1)
    return launch, nominal, quality


def parse_igra(content, station):
    launches = deque(maxlen=32)
    with ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        if len(entries) != 1 or entries[0].file_size > 64 * 1024 * 1024:
            raise SourceError("source_unavailable", "IGRA archive exceeds its size budget.")
        with TextIOWrapper(archive.open(entries[0]), encoding="ascii") as stream:
            for header in stream:
                if not header.startswith("#") or header[1:12] != station["id"]:
                    raise SourceError("source_unavailable", "Unexpected IGRA station record.")
                count = int(header[32:36])
                if not 0 <= count <= 1500:
                    raise SourceError("source_unavailable", "IGRA launch exceeds its level budget.")
                launch, nominal, quality = igra_launch(header)
                levels = {}
                surface_p = None
                for _ in range(count):
                    line = stream.readline()
                    if len(line.rstrip("\n")) < 51:
                        raise SourceError("source_unavailable", "Truncated IGRA level record.")
                    flags = []

                    def read(start, end, scale=1, line=line, flags=flags):
                        raw = int(line[start:end])
                        if raw in {-9999, -8888}:
                            flags.append(
                                f"{start + 1}:{'QC removed' if raw == -8888 else 'missing'}"
                            )
                            return None
                        return raw / scale

                    pressure = read(9, 15, 100)
                    if pressure is None or not 0 < pressure <= 1100:
                        continue
                    z, t = read(16, 21), read(22, 27, 10)
                    rh, depression = read(28, 33, 10), read(34, 39, 10)
                    direction, speed = read(40, 45), read(46, 51, 10)
                    td = (
                        t - depression
                        if t is not None and depression is not None and depression >= 0
                        else None
                    )
                    if td is None and t is not None and rh is not None and 0 < rh <= 100:
                        td = scalar(
                            dewpoint_from_relative_humidity(t * units.degC, rh * units.percent).m
                        )
                    u = v = None
                    if (
                        direction is not None
                        and speed is not None
                        and 0 <= direction <= 360
                        and speed >= 0
                    ):
                        u = -speed * math.sin(math.radians(direction))
                        v = -speed * math.cos(math.radians(direction))
                    if line[1] == "1":
                        surface_p = pressure
                        if z is None:
                            z = station["elevation_m"]
                            flags.append("Station elevation supplies surface height")
                    flags.extend(
                        [
                            f"{field} climatology tier {line[flag_index]}"
                            for field, flag_index, value in [
                                ("pressure", 15, pressure),
                                ("height", 21, z),
                                ("temperature", 27, t),
                            ]
                            if value is not None and line[flag_index] in "AB"
                        ]
                    )
                    level = SoundingLevel(
                        pressure_hpa=pressure,
                        temperature_c=t,
                        dewpoint_c=td,
                        height_m_msl=z,
                        u_ms=u,
                        v_ms=v,
                        quality=flags,
                    )
                    if pressure in levels:
                        previous = levels[pressure]
                        for field in [
                            "temperature_c",
                            "dewpoint_c",
                            "height_m_msl",
                            "u_ms",
                            "v_ms",
                        ]:
                            if getattr(previous, field) is None:
                                setattr(previous, field, getattr(level, field))
                        previous.quality.extend(["Duplicate pressure combined", *flags])
                    else:
                        levels[pressure] = level
                if launch and len(levels) >= 2:
                    payload = {
                        "kind": "observed",
                        "station": station["id"],
                        "launch": launch.isoformat(),
                        "nominal_time": nominal.isoformat() if nominal else None,
                    }
                    launches.append(
                        SoundingProfile(
                            identity=content_key(payload),
                            kind="observed",
                            source="NOAA / NCEI IGRA 2.2",
                            valid_time=launch,
                            nominal_time=nominal,
                            station=station["id"],
                            station_name=station["name"],
                            sampled_point=[
                                float(header[63:71]) / 10000,
                                float(header[55:62]) / 10000,
                            ],
                            terrain_m_msl=station["elevation_m"],
                            surface_pressure_hpa=surface_p,
                            method="Observed launch; missing/QC-removed IGRA values stay null.",
                            fetched_at=datetime.now(UTC),
                            levels=sorted(
                                levels.values(), key=lambda x: x.pressure_hpa, reverse=True
                            ),
                            quality=quality,
                            metadata={
                                "input_bytes": len(content),
                                "origin_requests": 1,
                                "nominal_time": payload["nominal_time"],
                            },
                        )
                    )
    return sorted(launches, key=lambda x: x.valid_time)


class SoundingProvider:
    provider_id = "noaa-soundings"

    def __init__(self, client, storage):
        self.client = client
        self.storage = storage
        self.job = None
        self.origin_ranges = 0
        self.models = ModelProvider(client, storage)
        self._stations = None
        self._station_time = 0
        self._launches = {}

    async def stations(self, point=None):
        if self._stations is None or time.monotonic() - self._station_time > 3600:
            data = await self.download(IGRA_ROOT + "/igra2-station-list.txt", 1024 * 1024)
            self._stations = station_catalog(data.decode("utf-8"))
            self._station_time = time.monotonic()
        rows = self._stations
        if point:
            rows = sorted(rows, key=lambda s: distance_km(point, [s["lon"], s["lat"]]))[:20]
            return [
                {**s, "distance_km": round(distance_km(point, [s["lon"], s["lat"]]), 1)}
                for s in rows
            ]
        return rows

    async def download(self, url, limit, params=None):
        data = bytearray()
        try:
            async with self.client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                async for block in response.aiter_bytes():
                    if len(data) + len(block) > limit:
                        raise SourceError(
                            "source_unavailable", "Sounding source exceeds its byte budget."
                        )
                    data.extend(block)
        except httpx.HTTPError as exc:
            raise SourceError(
                "source_unavailable", "The exact NOAA sounding source is unavailable."
            ) from exc
        return bytes(data)

    async def observed(self, payload):
        station = next((s for s in await self.stations() if s["id"] == payload["station"]), None)
        if station is None:
            raise SourceError("no_data", "No supported recent IGRA station has this identity.")
        now = time.monotonic()
        cached = self._launches.get(station["id"])
        if not cached or now - cached[0] > 3600:
            year = datetime.now(UTC).year
            data = await self.download(
                f"{IGRA_ROOT}/data/data-y2d/{station['id']}-data-beg{year}.txt.zip",
                16 * 1024 * 1024,
            )
            launches = await asyncio.to_thread(parse_igra, data, station)
            source_revision = hashlib.sha256(data).hexdigest()
            self._launches[station["id"]] = now, launches, source_revision
            if len(self._launches) > 8:
                del self._launches[next(iter(self._launches))]
        else:
            launches, source_revision = cached[1], cached[2]
        if not launches:
            raise SourceError("no_data", "This station has no usable recent observed launches.")
        selected = (
            launches[-1]
            if payload.get("launch") is None
            else next(
                (p for p in launches if p.valid_time == datetime.fromisoformat(payload["launch"])),
                None,
            )
        )
        if selected is None:
            raise SourceError(
                "no_data", "That exact launch is not in the recent retained inventory."
            )
        return selected, {
            "launches": [p.valid_time.isoformat() for p in launches],
            "source_revision": source_revision,
        }

    async def ranged_field(self, model, run, hour, entry, pressure):
        key = content_key(
            {
                "kind": "sounding_grib",
                "model": model,
                "run_time": run.isoformat(),
                "forecast_hour": hour,
                "pressure_file": pressure,
                "entry": entry,
            }
        )
        if self.job is not None:
            cached = await read_cache(key)
            if cached:
                data = await self.storage.get(cached["object_key"])
                if len(data) == cached["bytes"]:
                    return data
                raise SourceError("source_unavailable", "Cached exact GRIB field is truncated.")
        data = await self.models.download_message(model, run, hour, entry, pressure)
        self.origin_ranges += 1
        if self.job is not None:
            object_key = f"weather-live/{self.job.content_key}/{self.job.lease_token}.{key}.grib"
            await reserve_artifact(self.job, object_key)
            await self.storage.put(object_key, data, "application/octet-stream")
            retired = await write_bounded_raw_cache(
                key, {"object_key": object_key, "bytes": len(data)}, self.job.expires_at
            )
            for old_key in retired:
                await self.storage.delete_live(old_key)
        return data

    async def forecast(self, payload):
        self.origin_ranges = 0
        model = payload["model"]
        run, hour = datetime.fromisoformat(payload["run_time"]), payload["forecast_hour"]
        if (
            hour not in forecast_hours(model, run)
            or (model == "gfs" and run.hour not in {0, 6, 12, 18})
            or run.minute
            or run.second
        ):
            raise SourceError("unsupported_product", "Unsupported immutable forecast run/hour.")
        if not (-130 <= payload["lon"] <= -60 and 20 <= payload["lat"] <= 55):
            raise SourceError("no_data", "Forecast soundings use the initial CONUS display domain.")
        if hour not in await self.models.inventory(model, run):
            raise SourceError("no_data", "The exact sounding forecast hour is unavailable.")
        if model == "gfs":
            params = {
                "file": model_object(model, run, hour).split("/")[-1],
                "dir": f"/gfs.{run:%Y%m%d}/{run:%H}/atmos",
                "subregion": "",
                "leftlon": str(payload["lon"] - 0.3),
                "rightlon": str(payload["lon"] + 0.3),
                "toplat": str(payload["lat"] + 0.3),
                "bottomlat": str(payload["lat"] - 0.3),
                "lev_surface": "on",
                "lev_2_m_above_ground": "on",
                "lev_10_m_above_ground": "on",
            }
            for entry in await self.models.index(model, run, hour):
                match = re.fullmatch(r"(\d+) mb", entry["level"])
                if match and 50 <= int(match[1]) <= 1000:
                    params["lev_" + match[1] + "_mb"] = "on"
            params.update(
                {"var_" + v: "on" for v in ["TMP", "DPT", "RH", "HGT", "UGRD", "VGRD", "PRES"]}
            )
            data = await self.download(
                "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl",
                8 * 1024 * 1024,
                params,
            )
            fields = await asyncio.to_thread(decode_subset, data, run, hour)
            byte_count, requests = len(data), 1
        else:
            fields = {}
            selected = [
                ("PRES", "surface"),
                ("HGT", "surface"),
                ("TMP", "2 m above ground"),
                ("DPT", "2 m above ground"),
                ("UGRD", "10 m above ground"),
                ("VGRD", "10 m above ground"),
            ]
            index = await self.models.index(model, run, hour, pressure=True)
            pressure_entries = [
                e
                for e in index
                if e["mnemonic"] in {"HGT", "TMP", "DPT", "UGRD", "VGRD"}
                and e["level"] in {f"{p} mb" for p in PRESSURES}
            ]
            surface_index = await self.models.index(model, run, hour)
            entries = [(e, True) for e in pressure_entries] + [
                (e, False) for e in surface_index if (e["mnemonic"], e["level"]) in selected
            ]
            if len(entries) > 210:
                raise SourceError("source_unavailable", "Profile exceeds its field/level budget.")
            byte_count, requests = 0, 0
            sample, reference = None, None
            for start in range(0, len(entries), 3):
                group = entries[start : start + 3]
                raw = await asyncio.gather(
                    *(self.ranged_field(model, run, hour, e, pressure) for e, pressure in group)
                )
                for (entry, _), message in zip(group, raw, strict=True):
                    byte_count += len(message)
                    if byte_count > 384 * 1024 * 1024:
                        raise SourceError(
                            "source_unavailable", "HRRR profile exceeds its transfer budget."
                        )
                    grid = await asyncio.to_thread(
                        decode_model_message, message, run, hour, entry["mnemonic"], entry["level"]
                    )
                    if reference is None:
                        row, col, sample = nearest_column(grid, [payload["lon"], payload["lat"]])
                        reference = geometry(grid)
                    elif geometry(grid) != reference:
                        raise SourceError("source_unavailable", "Forecast column grids disagree.")
                    key = entry["mnemonic"], entry["level"]
                    if key in fields:
                        raise SourceError("source_unavailable", "Duplicate pressure field.")
                    fields[key] = replace(
                        grid,
                        values=grid.values[row : row + 1, col : col + 1].copy(),
                        x0=grid.x0 + col * grid.dx,
                        y0=grid.y0 + row * grid.dy,
                    )
                    del grid
            if sample is None:
                raise SourceError("no_data", "No pressure fields are published for this forecast.")
            requests = self.origin_ranges
        profile = await asyncio.to_thread(assemble_column, fields, payload, byte_count, requests)
        return profile, {"forecast_hours": await self.models.inventory(model, run)}

    async def prepare_profile(self, payload):
        return await (
            self.forecast(payload) if payload["kind"] == "forecast" else self.observed(payload)
        )

    async def prepare_document(self, payload):
        if payload.get("stage") == "diagnostics":
            from wxspot.sounding_calculations import calculate

            key = payload["profile_object_key"]
            if not key.startswith("weather-live/") or not key.endswith(".json"):
                raise SourceError("unsupported_product", "Invalid prepared profile reference")
            data = await self.storage.get(key)
            if len(data) > 2 * 1024 * 1024:
                raise SourceError("source_unavailable", "Profile artifact exceeds its budget")
            profile = SoundingProfile.model_validate(json.loads(data)["profile"])
            if profile.identity != payload["profile_identity"]:
                raise SourceError("unsupported_product", "Prepared profile identity changed")
            diagnostics = await asyncio.to_thread(
                calculate,
                profile,
                payload["parcel"],
                payload["motion"],
                payload.get("storm_u"),
                payload.get("storm_v"),
            )
            return {"diagnostics": diagnostics.model_dump(mode="json")}
        profile, options = await self.prepare_profile(payload)
        return {"profile": profile.model_dump(mode="json"), "options": options}
