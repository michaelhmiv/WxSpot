import asyncio
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel, Field

from wxspot.config import settings

OSM_ATTRIBUTION = "© OpenStreetMap contributors"
RADAR_STATIONS_URL = "https://coast.noaa.gov/arcgis/rest/services/Hosted/WeatherRadarStations/FeatureServer/0/query"


class PlaceSearchResult(BaseModel):
    id: str
    name: str
    lat: float
    lon: float


class LocationSearchResponse(BaseModel):
    state: str
    results: list[PlaceSearchResult] = Field(default_factory=list)
    message: str | None = None
    retry_after_seconds: int | None = None
    attribution: str = OSM_ATTRIBUTION


class RadarStation(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    distance_km: float


class RadarStationResponse(BaseModel):
    state: str
    stations: list[RadarStation] = Field(default_factory=list)
    fetched_at: datetime | None = None
    message: str | None = None
    attribution: str = "NOAA Office for Coastal Management"


class ProviderUnavailable(Exception):
    pass


class NominatimProvider:
    """Explicit, server-proxied user searches with a replaceable upstream endpoint."""

    def __init__(self, client: httpx.AsyncClient, base_url: str | None = None):
        self.client = client
        self.base_url = (base_url or settings().geocoder_base_url).rstrip("/")

    async def search(
        self, query: str, latitude: float | None = None, longitude: float | None = None
    ) -> list[PlaceSearchResult]:
        params: dict[str, str | int] = {
            "q": query,
            "format": "jsonv2",
            "limit": 8,
            "addressdetails": 0,
        }
        if latitude is not None and longitude is not None:
            params["viewbox"] = ",".join(
                str(value)
                for value in (
                    max(-180.0, longitude - 1.0),
                    min(90.0, latitude + 0.7),
                    min(180.0, longitude + 1.0),
                    max(-90.0, latitude - 0.7),
                )
            )
            params["bounded"] = 0
        try:
            response = await self.client.get(
                self.base_url + "/search",
                params=params,
                headers={"User-Agent": settings().geocoder_user_agent},
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable("Place search is unavailable. Try again shortly.") from exc
        results: list[PlaceSearchResult] = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, Mapping):
                continue
            try:
                lat, lon = float(item["lat"]), float(item["lon"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                osm_type = str(item.get("osm_type", "place"))
                osm_id = str(item.get("osm_id", item.get("place_id", "")))
                name = str(item.get("display_name", item.get("name", ""))).strip()[:250]
                if not osm_id or not name:
                    continue
                results.append(
                    PlaceSearchResult(id=f"{osm_type}:{osm_id}"[:120], name=name, lat=lat, lon=lon)
                )
            except (KeyError, TypeError, ValueError):
                continue
        return results


class RadarStationProvider:
    """Cached NOAA station coordinates for a geographic nearby-station picker."""

    def __init__(self, client: httpx.AsyncClient, endpoint: str | None = None):
        self.client = client
        self.endpoint = endpoint or settings().radar_station_catalog_url or RADAR_STATIONS_URL
        self._cached_at: datetime | None = None
        self._stations: list[tuple[str, str, float, float]] = []
        self._lock = asyncio.Lock()

    async def nearby(self, latitude: float, longitude: float, limit: int = 12):
        async with self._lock:
            now = datetime.now(UTC)
            if self._cached_at is None or now - self._cached_at > timedelta(hours=24):
                self._stations = await self._load()
                self._cached_at = now
            stations = self._stations
            fetched_at = self._cached_at
        ranked = sorted(
            (
                RadarStation(
                    id=site,
                    name=name,
                    lat=lat,
                    lon=lon,
                    distance_km=round(_distance_km(latitude, longitude, lat, lon), 1),
                )
                for site, name, lat, lon in stations
            ),
            key=lambda station: station.distance_km,
        )
        ranked = [station for station in ranked if station.distance_km <= 600]
        return RadarStationResponse(
            state="ready" if ranked else "no_data",
            stations=ranked[: max(1, min(limit, 30))],
            fetched_at=fetched_at,
        )

    async def _load(self) -> list[tuple[str, str, float, float]]:
        try:
            response = await self.client.get(
                self.endpoint,
                params={
                    "where": "1=1",
                    "outFields": "siteidentifier,sitename,radartype",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "resultRecordCount": 2000,
                    "f": "json",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable("NOAA radar station inventory is unavailable.") from exc
        if payload.get("error"):
            raise ProviderUnavailable("NOAA radar station inventory is unavailable.")
        result = []
        for feature in payload.get("features", []):
            attributes = feature.get("attributes") or {}
            geometry = feature.get("geometry") or {}
            site = str(attributes.get("siteidentifier", "")).upper()
            radar_type = str(attributes.get("radartype", "")).upper()
            if not re.fullmatch(r"[KPT][A-Z0-9]{3}", site) or "TDWR" in radar_type:
                continue
            try:
                lon, lat = float(geometry["x"]), float(geometry["y"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            name = str(attributes.get("sitename") or site).strip()
            result.append((site, name, lat, lon))
        if not result:
            raise ProviderUnavailable("NOAA radar station inventory returned no usable sites.")
        return result


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radians = math.pi / 180
    delta_lat = (lat2 - lat1) * radians
    delta_lon = (lon2 - lon1) * radians
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1 * radians) * math.cos(lat2 * radians) * math.sin(delta_lon / 2) ** 2
    )
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
