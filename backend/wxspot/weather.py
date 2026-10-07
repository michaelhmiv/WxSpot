import asyncio
import math
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode

import httpx
from defusedxml.ElementTree import fromstring
from pydantic import BaseModel

from wxspot.config import settings
from wxspot.weather_contracts import (
    RenderDescriptor,
    WeatherCatalogResponse,
    WeatherFrame,
    WeatherFramesResponse,
    WeatherProduct,
    WeatherSelection,
)

WMS = "{http://www.opengis.net/wms}"
PRODUCTS = {
    "reflectivity": ("sr_bref", "Base reflectivity", "dBZ"),
    "velocity": ("sr_bvel", "Base radial velocity", "provider scale"),
}


class SourceError(Exception):
    def __init__(self, state: str, message: str):
        self.state, self.message = state, message
        super().__init__(message)


class RadarFrame(BaseModel):
    id: str
    valid_time: datetime
    provider: str = "nws-ridge2"
    site: str
    product: str
    title: str
    tile_url: str
    attribution: str = "NOAA / National Weather Service"
    units: str
    legend_url: str


class WeatherRasterProvider(Protocol):
    """Replaceable weather boundary consumed by the social publishing workflow."""

    async def frames(self, site: str, product: str) -> dict: ...
    async def capture(self, layer, bounds: list[float]) -> bytes: ...


class WeatherProviderAdapter(Protocol):
    source_type: str
    provider_id: str

    def products(self) -> list[WeatherProduct]: ...
    async def frames(self, selection: WeatherSelection) -> WeatherFramesResponse: ...
    async def capture(self, layer, bounds: list[float]) -> bytes: ...


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise SourceError("source_unavailable", "Provider supplied a time without a timezone")
    return result.astimezone(UTC)


def parse_times(value: str) -> list[datetime]:
    result = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "/" not in item:
            result.add(timestamp(item))
            continue
        # WMS may advertise a regular interval rather than enumerated frames.
        import re

        parts = item.split("/")
        if len(parts) != 3:
            raise SourceError("source_unavailable", "Unsupported WMS time interval")
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", parts[2])
        if not match:
            raise SourceError("source_unavailable", "Unsupported WMS interval duration")
        hours, minutes, seconds = (int(v or 0) for v in match.groups())
        step = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        start, end = timestamp(parts[0]), timestamp(parts[1])
        if step.total_seconds() <= 0 or (end - start) / step > 1000:
            raise SourceError("source_unavailable", "Invalid WMS interval")
        while start <= end:
            result.add(start)
            start += step
    return sorted(result)


def parse_capabilities(data: bytes, site: str, product: str) -> list[datetime]:
    layer_name = f"{site.lower()}_{PRODUCTS[product][0]}"
    root = fromstring(data)
    for layer in root.iter(f"{WMS}Layer"):
        if layer.findtext(f"{WMS}Name") not in (layer_name, f"{site.lower()}:{layer_name}"):
            continue
        dimension = next(
            (d for d in layer.findall(f"{WMS}Dimension") if d.attrib.get("name") == "time"),
            None,
        )
        if dimension is None or not dimension.text:
            raise SourceError("no_data", "Radar layer has no advertised scans")
        return parse_times(dimension.text)
    raise SourceError("unsupported_product", "This radar site does not advertise this product")


def iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def mercator_bounds(bounds: list[float]) -> list[float]:
    def project(lon, lat):
        radius = 6378137
        return radius * math.radians(lon), radius * math.log(
            math.tan(math.pi / 4 + math.radians(lat) / 2)
        )

    west, south = project(bounds[0], bounds[1])
    east, north = project(bounds[2], bounds[3])
    return [west, south, east, north]


class RadarProvider:
    """Provider boundary: no social-domain dependencies."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.cache: OrderedDict[str, tuple[datetime, bytes]] = OrderedDict()
        self.lock = asyncio.Lock()

    def endpoint(self, site: str) -> str:
        import re

        if not re.fullmatch(r"[KPT][A-Z0-9]{3}", site):
            raise SourceError("unsupported_product", "Choose a NEXRAD radar site")
        return f"{settings().radar_base_url}/{site.lower()}/ows"

    async def frames(self, site="KCLX", product="reflectivity", force=False) -> dict:
        if product not in PRODUCTS:
            raise SourceError("unsupported_product", "This radar product is not supported")
        endpoint = self.endpoint(site)
        async with self.lock:
            cached = self.cache.get(site)
            if not cached or force or (datetime.now(UTC) - cached[0]).total_seconds() > 45:
                try:
                    response = await self.client.get(
                        endpoint,
                        params={"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"},
                    )
                    response.raise_for_status()
                    cached = (datetime.now(UTC), response.content)
                    self.cache[site] = cached
                    if len(self.cache) > 160:
                        self.cache.popitem(last=False)
                except httpx.HTTPError as exc:
                    raise SourceError(
                        "source_unavailable", "NOAA radar source is unavailable"
                    ) from exc
        try:
            times = parse_capabilities(cached[1], site, product)
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError(
                "source_unavailable", "NOAA radar metadata could not be read"
            ) from exc
        frames = [
            RadarFrame(
                id=f"{site}:{product}:{iso(t)}",
                valid_time=t,
                site=site,
                product=product,
                title=PRODUCTS[product][1],
                units=PRODUCTS[product][2],
                legend_url=endpoint
                + "?"
                + urlencode(
                    {
                        "SERVICE": "WMS",
                        "REQUEST": "GetLegendGraphic",
                        "VERSION": "1.1.1",
                        "FORMAT": "image/png",
                        "LAYER": f"{site.lower()}_{PRODUCTS[product][0]}",
                    }
                ),
                tile_url=self.map_url(site, product, t, "{bbox-epsg-3857}", 256),
            ).model_dump(mode="json")
            for t in times[-60:]
        ]
        state = (
            "no_data"
            if not times
            else (
                "source_delayed"
                if (datetime.now(UTC) - times[-1]).total_seconds() > 900
                else "ready"
            )
        )
        return {"state": state, "fetched_at": cached[0], "frames": frames}

    def map_url(self, site, product, valid_time, bbox, size=1024):
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "LAYERS": f"{site.lower()}_{PRODUCTS[product][0]}",
            "STYLES": "",
            "FORMAT": "image/png",
            "TRANSPARENT": "true",
            "SRS": "EPSG:3857",
            "TIME": iso(valid_time),
            "WIDTH": str(size),
            "HEIGHT": str(size),
            "BBOX": bbox if isinstance(bbox, str) else ",".join(str(v) for v in bbox),
        }
        return self.endpoint(site) + "?" + urlencode(params, safe="{},-:")

    async def capture(self, layer, bounds):
        if layer.provider != "nws-ridge2" or layer.source_type != "radar" or not layer.radar_site:
            raise SourceError(
                "unsupported_product", "Only NOAA radar can be published in this slice"
            )
        data = await self.frames(layer.radar_site, layer.product, force=True)
        frame_id = legacy_radar_frame_id(layer.frame_id)
        exact = next((f for f in data["frames"] if f["id"] == frame_id), None)
        if not exact or timestamp(exact["valid_time"]) != layer.valid_time:
            raise SourceError(
                "no_data", "That scan has expired. Select an available scan and mark it again."
            )
        try:
            response = await self.client.get(
                self.map_url(
                    layer.radar_site,
                    layer.product,
                    layer.valid_time,
                    mercator_bounds(bounds),
                )
            )
            response.raise_for_status()
            if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise SourceError(
                    "source_unavailable", "NOAA did not return the requested radar raster"
                )
            # Recheck membership: nearestValue could select a later scan at eviction.
            refreshed = await self.frames(layer.radar_site, layer.product, force=True)
            if not any(f["id"] == frame_id for f in refreshed["frames"]):
                raise SourceError(
                    "no_data", "The marked scan expired during capture; please select another."
                )
            return response.content
        except httpx.HTTPError as exc:
            raise SourceError(
                "source_unavailable", "Could not preserve the marked radar scan"
            ) from exc


def legacy_radar_frame_id(frame_id: str) -> str:
    """Accept v1 frame IDs and the namespaced v2 radar identity."""
    prefix = "radar:nws-ridge2:"
    return frame_id.removeprefix(prefix)


class RadarWeatherAdapter:
    """Maps the existing RIDGE2 provider into the versioned weather contract."""

    source_type = "radar"
    provider_id = "nws-ridge2"

    def __init__(self, radar: WeatherRasterProvider):
        self.radar = radar

    def products(self) -> list[WeatherProduct]:
        return [
            WeatherProduct(
                source_type="radar",
                provider=self.provider_id,
                source_id=self.provider_id,
                product_id=product_id,
                display_name=title,
                units=units,
                attribution="NOAA / National Weather Service",
                capabilities={"timeline": True, "exact_capture": True, "site_selection": True},
            )
            for product_id, (_, title, units) in PRODUCTS.items()
        ]

    async def frames(self, selection: WeatherSelection) -> WeatherFramesResponse:
        if selection.source_type != self.source_type or selection.source_id != self.provider_id:
            raise SourceError("unsupported_product", "This weather source is not supported")
        result = await self.radar.frames(selection.site or "KCLX", selection.product_id)
        frames = [
            WeatherFrame(
                id=f"{self.source_type}:{self.provider_id}:{frame['id']}",
                source_type=self.source_type,
                provider=self.provider_id,
                product=frame["product"],
                valid_time=timestamp(frame["valid_time"]),
                render=RenderDescriptor(
                    kind="xyz",
                    url_template=frame["tile_url"],
                    tile_size=256,
                    content_version=frame["id"],
                ),
                coverage_bounds=None,
                attribution=frame.get("attribution", "NOAA / National Weather Service"),
                units=frame.get("units"),
                legend_url=frame.get("legend_url"),
                state="ready",
                site=frame.get("site"),
                metadata={"legacy_frame_id": frame["id"]},
            )
            for frame in result.get("frames", [])
        ]
        return WeatherFramesResponse(
            state=result["state"],
            frames=frames,
            fetched_at=result.get("fetched_at"),
            message=result.get("message"),
        )

    async def capture(self, layer, bounds: list[float]) -> bytes:
        return await self.radar.capture(layer, bounds)


class WeatherProviderRegistry:
    """Source-aware dispatch for weather discovery and exact frame capture."""

    def __init__(self, adapters: list[WeatherProviderAdapter] | None = None):
        self._adapters: dict[tuple[str, str], WeatherProviderAdapter] = {}
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: WeatherProviderAdapter) -> None:
        key = (adapter.source_type, adapter.provider_id)
        if key in self._adapters:
            raise ValueError(f"A provider is already registered for {key}")
        self._adapters[key] = adapter

    def catalog(self) -> WeatherCatalogResponse:
        return WeatherCatalogResponse(
            products=[
                product for adapter in self._adapters.values() for product in adapter.products()
            ],
            fetched_at=datetime.now(UTC),
        )

    def adapter(self, source_type: str, provider_id: str) -> WeatherProviderAdapter:
        adapter = self._adapters.get((source_type, provider_id))
        if adapter is None:
            raise SourceError("unsupported_product", "This weather source is not supported")
        return adapter

    async def frames(self, selection: WeatherSelection) -> WeatherFramesResponse:
        return await self.adapter(selection.source_type, selection.source_id).frames(selection)

    async def capture(self, layer, bounds: list[float]) -> bytes:
        return await self.adapter(layer.source_type, layer.provider).capture(layer, bounds)


class AlertProvider:
    def __init__(self, client: httpx.AsyncClient):
        self.client, self.cached, self.fetched_at = client, [], None
        self.lock = asyncio.Lock()

    async def active(self):
        state = "ready"
        async with self.lock:
            if (
                self.fetched_at is None
                or (datetime.now(UTC) - self.fetched_at).total_seconds() > 45
            ):
                try:
                    response = await self.client.get(
                        settings().alerts_url,
                        headers={"Accept": "application/geo+json"},
                    )
                    response.raise_for_status()
                    self.cached = response.json()["features"]
                    self.fetched_at = datetime.now(UTC)
                except (httpx.HTTPError, ValueError, KeyError):
                    state = "source_unavailable"
        features = []
        for feature in self.cached:
            p = feature.get("properties", {})
            try:
                if p.get("expires") and timestamp(p["expires"]) <= datetime.now(UTC):
                    continue
            except ValueError:
                continue
            features.append(
                {
                    "type": "Feature",
                    "id": p.get("id", feature.get("id")),
                    "geometry": feature.get("geometry"),
                    "properties": {
                        "nws_id": p.get("id"),
                        "event": p.get("event"),
                        "severity": p.get("severity"),
                        "headline": p.get("headline"),
                        "issued": p.get("sent"),
                        "expires": p.get("expires"),
                        "issuing_office": p.get("senderName"),
                        "description": p.get("description"),
                        "instruction": p.get("instruction"),
                        "source": "National Weather Service",
                        "official": True,
                    },
                }
            )
        return {
            "state": state,
            "fetched_at": self.fetched_at,
            "collection": {"type": "FeatureCollection", "features": features},
        }
