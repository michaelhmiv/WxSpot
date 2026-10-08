"""Bounded NWS point data with independent sections and explicit accumulation intervals."""

import asyncio
import json
import math
import re
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx

from wxspot.config import settings
from wxspot.geocoding import _distance_km
from wxspot.location_weather_contracts import (
    ForecastPeriod,
    LocationWeatherResponse,
    Observation,
    PrecipitationInterval,
    WeatherSection,
)
from wxspot.weather import SourceError
from wxspot.weather_cache import read_cache, write_bounded_json_cache
from wxspot.weather_jobs import content_key

BASE = "https://api.weather.gov"


def source_url(address):
    parsed = urlparse(address)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.weather.gov"
        or not re.fullmatch(r"/(points|gridpoints|stations)/[A-Za-z0-9.,_/-]+", parsed.path)
    ):
        raise SourceError("source_unavailable", "Invalid NWS source link")
    return address


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def quantity(item, target):
    if not isinstance(item, dict):
        return None
    value = number(item.get("value"))
    if value is None:
        return None
    unit = str(item.get("unitCode", item.get("uom", "")) or "").split(":")[-1]
    if target == "c":
        return (
            value
            if unit == "degC"
            else (value - 32) * 5 / 9
            if unit == "degF"
            else value - 273.15
            if unit == "K"
            else None
        )
    if target == "ms":
        if value < 0:
            return None
        factor = {"m_s-1": 1, "km_h-1": 1 / 3.6, "mi_h-1": 0.44704, "kt": 0.5144444444}.get(unit)
        return value * factor if factor is not None else None
    if target == "mm":
        if value < 0:
            return None
        factor = {"mm": 1, "m": 1000, "cm": 10, "in": 25.4}.get(unit)
        return value * factor if factor is not None else None
    if target == "percent":
        return value if unit == "percent" and 0 <= value <= 100 else None
    return value if unit == "degree_(angle)" and 0 <= value <= 360 else None


def wind_range(value):
    if isinstance(value, dict):
        speed = quantity(value, "ms")
        return speed, speed
    if value == "Calm":
        return 0.0, 0.0
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(?: to (\d+(?:\.\d+)?))? (mph|km/h|m/s|kt)", str(value))
    if not match:
        return None, None
    factor = {"mph": 0.44704, "km/h": 1 / 3.6, "m/s": 1, "kt": 0.5144444444}[match[3]]
    return float(match[1]) * factor, float(match[2] or match[1]) * factor


def interval(value):
    start, length = value.split("/", 1)
    start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if start.tzinfo is None:
        raise ValueError("Missing source timezone")
    if not length.startswith("P"):
        return start, datetime.fromisoformat(length.replace("Z", "+00:00"))
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", length)
    if not match or not any(match.groups()):
        raise ValueError("Unsupported duration")
    days, hours, minutes, seconds = [int(v or 0) for v in match.groups()]
    return start, start + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def timeline(field, target):
    rows = []
    for item in field.get("values", [])[:2000]:
        try:
            start, end = interval(item["validTime"])
            if end > start:
                rows.append(
                    (
                        start,
                        end,
                        quantity({"value": item["value"], "uom": field.get("uom")}, target),
                    )
                )
        except (KeyError, ValueError, TypeError):
            continue
    return rows


def forecast_section(manifest, hourly, grid=None):
    doc = manifest["document"]["properties"]
    now = datetime.now(UTC)
    periods = []
    gusts = timeline((grid or {}).get("windGust", {}), "ms")
    for item in doc.get("periods", [])[:200]:
        try:
            start, end = (
                datetime.fromisoformat(item["startTime"]),
                datetime.fromisoformat(item["endTime"]),
            )
            if end <= now or start >= now + timedelta(hours=48 if hourly else 168):
                continue
            temperature = item.get("temperature")
            if not isinstance(temperature, dict):
                temperature = {
                    "value": temperature,
                    "unitCode": "deg" + item.get("temperatureUnit", ""),
                }
            low, high = wind_range(item.get("windSpeed"))
            valid_gusts = [v for a, b, v in gusts if a < end and b > start and v is not None]
            periods.append(
                ForecastPeriod(
                    start_time=start,
                    end_time=end,
                    name=item.get("name", ""),
                    daytime=item["isDaytime"],
                    temperature_c=quantity(temperature, "c"),
                    dewpoint_c=quantity(item.get("dewpoint"), "c"),
                    humidity_percent=quantity(item.get("relativeHumidity"), "percent"),
                    wind_low_ms=low,
                    wind_high_ms=high,
                    wind_direction=item.get("windDirection"),
                    gust_ms=max(valid_gusts) if valid_gusts else None,
                    precipitation_chance_percent=quantity(
                        item.get("probabilityOfPrecipitation"), "percent"
                    ),
                    summary=item.get("shortForecast", ""),
                    detail=item.get("detailedForecast", ""),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    updated = doc.get("updateTime")
    old = (
        manifest.get("stale", False)
        or updated is not None
        and now - datetime.fromisoformat(updated) > timedelta(hours=18)
    )
    return WeatherSection(
        state="stale" if old and periods else "ready" if periods else "no_data",
        source_url=manifest["url"],
        fetched_at=manifest["fetched_at"],
        updated_at=updated,
        periods=periods,
        message="Cached/older forecast; refresh when connected." if old else None,
    )


class LocationWeatherProvider:
    def __init__(self, client, *, shared_cache=True):
        self.client, self.shared_cache = client, shared_cache
        self.cache = OrderedDict()
        self.inflight = {}
        self.semaphore = asyncio.Semaphore(3)

    async def document(self, url, ttl=300):
        url = source_url(url)
        key = content_key({"kind": "nws_json", "url": url})
        cached = self.cache.get(key)
        if cached is None and self.shared_cache:
            cached = await read_cache(key)
        if cached and datetime.now(UTC) - datetime.fromisoformat(cached["fetched_at"]) < timedelta(
            seconds=ttl
        ):
            return cached
        task = self.inflight.get(key)
        if task is None:
            if len(self.inflight) >= 8:
                if cached:
                    return {**cached, "stale": True}
                raise SourceError("source_unavailable", "Location weather is busy. Retry shortly.")
            task = asyncio.create_task(self.download(url, key, cached))
            self.inflight[key] = task
            task.add_done_callback(lambda _, key=key: self.inflight.pop(key, None))
        return await asyncio.shield(task)

    async def download(self, url, key, cached):
        try:
            async with self.semaphore, asyncio.timeout(25):
                async with self.client.stream(
                    "GET",
                    url,
                    headers={
                        "User-Agent": settings().nws_user_agent,
                        "Accept": "application/geo+json",
                    },
                    follow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for block in response.aiter_bytes():
                        if len(data) + len(block) > 2 * 1024 * 1024:
                            raise ValueError("NWS document exceeds byte budget")
                        data.extend(block)
                    document = json.loads(data)
            manifest = {
                "document": document,
                "fetched_at": datetime.now(UTC).isoformat(),
                "url": url,
                "bytes": len(data),
            }
            if self.shared_cache:
                await write_bounded_json_cache(
                    key, manifest, datetime.now(UTC) + timedelta(hours=12)
                )
            self.cache[key] = manifest
            self.cache.move_to_end(key)
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
            return manifest
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            if cached and datetime.now(UTC) - datetime.fromisoformat(
                cached["fetched_at"]
            ) < timedelta(hours=12):
                return {**cached, "stale": True}
            state = (
                "no_data"
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {404, 400}
                else "source_unavailable"
            )
            raise SourceError(
                state, "NWS data is unavailable for this section. Retry shortly."
            ) from exc

    async def observation(self, point, stations_url):
        inventory = await self.document(stations_url, 3600)
        candidates = []
        for feature in inventory["document"].get("features", [])[:200]:
            p, coordinates = (
                feature.get("properties", {}),
                feature.get("geometry", {}).get("coordinates", []),
            )
            station = p.get("stationIdentifier", "")
            if re.fullmatch(r"[A-Z0-9]{3,8}", station) and len(coordinates) == 2:
                distance = _distance_km(point[1], point[0], coordinates[1], coordinates[0])
                candidates.append((distance, station, p.get("name", station), coordinates))
        older = None
        for distance, station, name, coordinates in sorted(candidates)[:3]:
            try:
                manifest = await self.document(
                    f"{BASE}/stations/{station}/observations/latest?require_qc=true", 120
                )
                p = manifest["document"]["properties"]
                observed = datetime.fromisoformat(p["timestamp"])
                age = max(0, int((datetime.now(UTC) - observed).total_seconds() / 60))
                temperature = quantity(p.get("temperature"), "c")
                if temperature is None:
                    continue
                speed = quantity(p.get("windSpeed"), "ms")
                direction = quantity(p.get("windDirection"), "degree")
                observation = Observation(
                    station=station,
                    station_name=name,
                    sampled_point=coordinates,
                    distance_km=round(distance, 1),
                    observed_at=observed,
                    age_minutes=age,
                    temperature_c=temperature,
                    dewpoint_c=quantity(p.get("dewpoint"), "c"),
                    humidity_percent=quantity(p.get("relativeHumidity"), "percent"),
                    wind_low_ms=speed,
                    wind_high_ms=speed,
                    wind_direction=f"{direction:g}°" if direction is not None else None,
                    gust_ms=quantity(p.get("windGust"), "ms"),
                    description=p.get("textDescription", ""),
                    precipitation_last_hour_mm=quantity(p.get("precipitationLastHour"), "mm"),
                )
                section = WeatherSection(
                    state="stale" if age > 90 or manifest.get("stale") else "ready",
                    source_url=manifest["url"],
                    fetched_at=manifest["fetched_at"],
                    updated_at=observed,
                    observation=observation,
                    message="Station observation is older than 90 minutes." if age > 90 else None,
                )
                if section.state == "ready":
                    return section
                if older is None or age < older.observation.age_minutes:
                    older = section
            except (SourceError, KeyError, ValueError, TypeError):
                continue
        return older or WeatherSection(
            state="no_data", message="No usable current observation at the three nearest stations."
        )

    async def get(self, point):
        blank = WeatherSection(state="source_unavailable", message="NWS point lookup unavailable.")
        result = LocationWeatherResponse(
            state="source_unavailable",
            requested_point=point,
            observation=blank,
            hourly=blank,
            daily=blank,
            amounts=blank,
        )
        try:
            mapped = await self.document(f"{BASE}/points/{point[1]:.4f},{point[0]:.4f}", 86400)
            p = mapped["document"]["properties"]
            result.timezone = p.get("timeZone")
            place = p.get("relativeLocation", {}).get("properties", {})
            result.place_name = ", ".join(v for v in [place.get("city"), place.get("state")] if v)
            result.grid = f"{p['gridId']}/{p['gridX']},{p['gridY']}"
            fetched = await asyncio.gather(
                self.observation(point, p["observationStations"]),
                self.document(p["forecastHourly"]),
                self.document(p["forecast"]),
                self.document(p["forecastGridData"]),
                return_exceptions=True,
            )
            observation, hourly, daily, grid = fetched
            result.observation = (
                observation
                if isinstance(observation, WeatherSection)
                else self.failure(observation)
            )
            grid_properties = (
                grid.get("document", {}).get("properties") if isinstance(grid, dict) else None
            )
            for name, document in (("hourly", hourly), ("daily", daily)):
                try:
                    section = (
                        forecast_section(document, name == "hourly", grid_properties)
                        if isinstance(document, dict)
                        else self.failure(document)
                    )
                except (KeyError, TypeError, ValueError):
                    section = self.failure(None)
                setattr(result, name, section)
            if isinstance(grid, dict) and isinstance(grid_properties, dict):
                now = datetime.now(UTC)
                intervals = [
                    PrecipitationInterval(start_time=a, end_time=b, amount_mm=v)
                    for a, b, v in timeline(
                        grid_properties.get("quantitativePrecipitation", {}), "mm"
                    )
                    if b > now and a < now + timedelta(days=7)
                ]
                result.amounts = WeatherSection(
                    state="stale" if grid.get("stale") else "ready" if intervals else "no_data",
                    source_url=grid["url"],
                    fetched_at=grid["fetched_at"],
                    updated_at=grid_properties.get("updateTime"),
                    precipitation=intervals,
                    message="Rainfall totals apply to the labeled source intervals.",
                )
            else:
                result.amounts = self.failure(grid)
            states = [
                result.observation.state,
                result.hourly.state,
                result.daily.state,
                result.amounts.state,
            ]
            result.state = (
                "ready"
                if all(s == "ready" for s in states)
                else "partial"
                if any(s in {"ready", "stale"} for s in states)
                else "no_data"
                if all(s == "no_data" for s in states)
                else "source_unavailable"
            )
        except (SourceError, KeyError, ValueError, TypeError) as exc:
            result.message = (
                exc.message
                if isinstance(exc, SourceError)
                else "NWS point mapping is unavailable for this location."
            )
            if isinstance(exc, SourceError):
                result.state = exc.state
        return result

    @staticmethod
    def failure(exc):
        return WeatherSection(
            state=exc.state
            if isinstance(exc, SourceError) and exc.state == "no_data"
            else "source_unavailable",
            message="This section is unavailable. Other weather sections remain usable.",
        )
