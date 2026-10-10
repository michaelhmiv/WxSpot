import math
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import delete, text

from wxspot.auth import UserCreate, UserRead, backend, required_user, users
from wxspot.auth import router as identity_router
from wxspot.config import settings
from wxspot.database import sessions
from wxspot.geocoding import (
    LocationSearchResponse,
    NominatimProvider,
    ProviderUnavailable,
    RadarStationProvider,
)
from wxspot.hunt_radar import HistoricalRadar
from wxspot.location_weather_contracts import LocationWeatherResponse
from wxspot.models import AccessToken, GeocodeCache, GeocoderBudget, Quota, User
from wxspot.providers.forecast import ModelProvider
from wxspot.providers.goes import GoesProvider
from wxspot.providers.location_weather import LocationWeatherProvider
from wxspot.providers.mrms import MrmsProvider
from wxspot.providers.nexrad import NexradLevel3Provider
from wxspot.providers.soundings import SoundingProvider
from wxspot.social import quota, router
from wxspot.sounding_contracts import SoundingResponse, SoundingSelection
from wxspot.sounding_hunt import router as sounding_hunt_router
from wxspot.sounding_service import SoundingService
from wxspot.storage import storage
from wxspot.weather import (
    AlertProvider,
    RadarProvider,
    RadarWeatherAdapter,
    SourceError,
    WeatherProviderRegistry,
)
from wxspot.weather_contracts import WeatherFramesQuery, WeatherFramesResponse


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(25, connect=10),
        headers={"User-Agent": settings().nws_user_agent},
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        follow_redirects=True,
    ) as client:
        app.state.radar = RadarProvider(client)
        app.state.historical_radar = HistoricalRadar(client)
        app.state.mrms = MrmsProvider(client)
        app.state.nexrad = NexradLevel3Provider(client)
        app.state.storage = storage()
        app.state.goes = GoesProvider(client, app.state.storage)
        app.state.models = ModelProvider(client, app.state.storage)
        app.state.sounding_sources = SoundingProvider(client, app.state.storage)
        app.state.soundings = SoundingService(app.state.storage)
        app.state.weather = WeatherProviderRegistry(
            [
                RadarWeatherAdapter(app.state.radar),
                app.state.mrms,
                app.state.nexrad,
                app.state.goes,
                app.state.models,
            ]
        )
        app.state.alerts = AlertProvider(client)
        app.state.geocoder = NominatimProvider(client)
        app.state.radar_stations = RadarStationProvider(client)
        app.state.location_weather = LocationWeatherProvider(client)
        async with sessions() as db:
            await db.execute(
                delete(Quota).where(Quota.bucket < datetime.now(UTC) - timedelta(days=1))
            )
            await db.execute(
                delete(AccessToken).where(
                    AccessToken.created_at
                    < datetime.now(UTC) - timedelta(seconds=settings().session_seconds),
                )
            )
            await db.execute(
                delete(GeocodeCache).where(GeocodeCache.expires_at < datetime.now(UTC))
            )
            await db.commit()
        app.state.geocode_pruned_at = datetime.now(UTC)
        yield


app = FastAPI(title="WxSpot API", version="0.1.0", lifespan=lifespan)
app.include_router(users.get_auth_router(backend), prefix="/auth", tags=["authentication"])
app.include_router(
    users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["authentication"]
)
app.include_router(router)
app.include_router(identity_router)
app.include_router(sounding_hunt_router)


@app.get("/account", tags=["authentication"])
async def account(user: User = Depends(required_user)):
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "self_role": user.self_role,
        "verified_role": user.verified_role,
        "is_moderator": user.is_moderator or user.is_superuser,
    }


@app.middleware("http")
async def boundaries(request: Request, call_next):
    if int(request.headers.get("content-length", "0")) > 6 * 1024 * 1024:
        return JSONResponse({"detail": "Request is too large"}, status_code=413)
    if request.url.path in ("/auth/login", "/auth/register", "/auth/guest"):
        from fastapi import HTTPException

        try:
            await quota(request.client.host if request.client else "unknown", "auth", 30)
        except HTTPException as exc:
            return JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path not in ("/weather/style", "/health"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/health", tags=["operations"])
async def health():
    try:
        async with sessions() as db:
            await db.execute(text("SELECT PostGIS_Version()"))
        return {"status": "ok", "version": "0.1.0"}
    except Exception:
        return JSONResponse({"status": "database_unavailable"}, status_code=503)


@app.get("/weather/radar/frames", tags=["weather"])
async def radar_frames(
    request: Request,
    response: Response,
    site: str = Query(default="KCLX", pattern=r"^[KPT][A-Z0-9]{3}$"),
    product: str = Query(default="reflectivity", max_length=30),
):
    response.headers["Cache-Control"] = "public, max-age=15, stale-while-revalidate=30"
    try:
        return await request.app.state.radar.frames(site, product)
    except SourceError as exc:
        response.headers["Cache-Control"] = "public, max-age=5"
        return {"state": exc.state, "message": exc.message, "frames": [], "fetched_at": None}


@app.get("/weather/catalog", tags=["weather"])
async def weather_catalog(request: Request, response: Response):
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=120"
    return request.app.state.weather.catalog()


@app.get("/weather/frames", tags=["weather"])
async def weather_frames(
    request: Request,
    response: Response,
    source_type: str = Query(default="radar", max_length=30),
    source_id: str = Query(default="nws-ridge2", max_length=80),
    product: str = Query(default="reflectivity", max_length=100),
    site: str | None = Query(default=None, pattern=r"^[KPT][A-Z0-9]{3}$"),
    elevation: float | None = Query(default=None, ge=0, le=90),
    domain: str | None = Query(default=None, max_length=40),
    model: str | None = Query(default=None, max_length=30),
    run_time: datetime | None = None,
    forecast_hour: int | None = Query(default=None, ge=0, le=240),
    vertical_level: str | None = Query(default=None, max_length=40),
    channel: str | None = Query(default=None, max_length=40),
):
    response.headers["Cache-Control"] = "public, max-age=15, stale-while-revalidate=30"
    try:
        selection = WeatherFramesQuery(
            source_type=source_type,
            source_id=source_id,
            product_id=product,
            site=site
            or (
                "KCLX"
                if source_type == "radar" and source_id in {"nws-ridge2", "noaa-nexrad-level3"}
                else None
            ),
            domain=domain,
            model=model,
            run_time=run_time,
            forecast_hour=forecast_hour,
            vertical_level=vertical_level,
            channel=channel,
            elevation=elevation,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_context=False, include_input=False, include_url=False),
        ) from exc
    try:
        return await request.app.state.weather.frames(selection)
    except SourceError as exc:
        response.headers["Cache-Control"] = "public, max-age=5"
        return WeatherFramesResponse(state=exc.state, frames=[], message=exc.message)


@app.get("/weather/render/tile/{z}/{x}/{y}.png", tags=["weather"])
async def weather_tile(
    request: Request,
    z: int,
    x: int,
    y: int,
    source_id: str = Query(min_length=1, max_length=80),
    frame_id: str = Query(min_length=1, max_length=200),
    source_type: str = Query(default="radar", max_length=30),
):
    try:
        provider = request.app.state.weather.adapter(source_type, source_id)
        render_tile = getattr(provider, "render_tile", None)
        if render_tile is None:
            raise SourceError("unsupported_product", "This provider does not render map tiles")
        image = await render_tile(frame_id, z, x, y)
    except SourceError as exc:
        status_code = 404 if exc.state in {"no_data", "unsupported_product"} else 503
        return JSONResponse(
            {"state": exc.state, "message": exc.message},
            status_code=status_code,
            headers={"Cache-Control": "public, max-age=5"},
        )
    return Response(
        image,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get("/weather/prepare", tags=["weather"])
async def prepare_weather(
    request: Request,
    source_type: str = Query(max_length=30),
    source_id: str = Query(max_length=80),
    frame_id: str = Query(min_length=1, max_length=200),
):
    try:
        provider = request.app.state.weather.adapter(source_type, source_id)
        prepare = getattr(provider, "prepare", None)
        return await prepare(frame_id) if prepare else {"state": "ready"}
    except SourceError as exc:
        return {"state": exc.state, "message": exc.message}


@app.get("/weather/render/legend/{source_id}/{product}.png", tags=["weather"])
async def weather_legend(
    request: Request,
    source_id: str,
    product: str,
    frame_id: str | None = Query(default=None, min_length=1, max_length=200),
    source_type: str = Query(default="radar", max_length=30),
):
    try:
        provider = request.app.state.weather.adapter(source_type, source_id)
        render_legend = getattr(provider, "render_legend", None)
        if render_legend is None:
            raise SourceError("unsupported_product", "This provider does not render legends")
        image = await render_legend(product, frame_id)
    except SourceError as exc:
        return JSONResponse(
            {"state": exc.state, "message": exc.message},
            status_code=404,
            headers={"Cache-Control": "public, max-age=60"},
        )
    return Response(
        image,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get("/weather/alerts", tags=["official weather"])
async def alerts(request: Request):
    return await request.app.state.alerts.active()


@app.get("/weather/soundings", response_model=SoundingResponse, tags=["soundings"])
async def sounding(
    request: Request, response: Response, selection: Annotated[SoundingSelection, Query()]
):
    response.headers["Cache-Control"] = "public, max-age=3"
    try:
        return await request.app.state.soundings.get(selection)
    except SourceError as exc:
        return SoundingResponse(
            state=exc.state,
            requested_point=[selection.lon, selection.lat],
            message=exc.message,
        )


@app.get("/weather/soundings/stations", tags=["soundings"])
async def sounding_stations(
    request: Request,
    response: Response,
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    response.headers["Cache-Control"] = "public, max-age=3600"
    try:
        return {
            "state": "ready",
            "stations": await request.app.state.sounding_sources.stations([lon, lat]),
        }
    except SourceError as exc:
        return {"state": exc.state, "stations": [], "message": exc.message}


@app.get("/weather/locations/forecast", response_model=LocationWeatherResponse, tags=["locations"])
async def location_weather(
    request: Request,
    response: Response,
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=120"
    return await request.app.state.location_weather.get([lon, lat])


@app.get("/weather/locations/search", tags=["locations"])
async def location_search(
    request: Request,
    response: Response,
    q: str = Query(min_length=3, max_length=120),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
):
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    query = " ".join(q.split())
    if len(query) < 3:
        raise HTTPException(status_code=422, detail="Enter at least three characters.")
    provider_name = settings().geocoder_provider.casefold()
    if provider_name != "nominatim":
        return LocationSearchResponse(
            state="source_unavailable",
            message="The configured place search provider is unavailable.",
        )
    cache_key = sha256(
        "|".join(
            (
                provider_name,
                settings().geocoder_base_url.rstrip("/").casefold(),
                query.casefold(),
                f"{lat:.2f}" if lat is not None else "",
                f"{lon:.2f}" if lon is not None else "",
            )
        ).encode()
    ).hexdigest()
    now = datetime.now(UTC)
    async with sessions() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(1179991123925)"))
        budget_now = await db.scalar(text("SELECT clock_timestamp()"))
        last_prune = getattr(request.app.state, "geocode_pruned_at", None)
        if last_prune is None or now - last_prune >= timedelta(hours=1):
            await db.execute(delete(GeocodeCache).where(GeocodeCache.expires_at < now))
            request.app.state.geocode_pruned_at = now
        cached = await db.get(GeocodeCache, cache_key)
        if cached and cached.expires_at > now:
            return LocationSearchResponse(
                state="ready",
                results=cached.results,
                attribution="© OpenStreetMap contributors",
            )
        budget = await db.get(GeocoderBudget, 1)
        if budget and budget.last_requested_at:
            elapsed = (budget_now - budget.last_requested_at).total_seconds()
            if elapsed < 1.0:
                return LocationSearchResponse(
                    state="busy",
                    message="Place search is busy. Retry shortly.",
                    retry_after_seconds=max(1, math.ceil(1.0 - elapsed)),
                )
        if budget is None:
            budget = GeocoderBudget(id=1)
            db.add(budget)
        budget.last_requested_at = budget_now
        await db.commit()
    try:
        results = await request.app.state.geocoder.search(query, lat, lon)
    except ProviderUnavailable as exc:
        return LocationSearchResponse(state="source_unavailable", message=str(exc))
    async with sessions() as db:
        await db.merge(
            GeocodeCache(
                query_key=cache_key,
                results=[item.model_dump(mode="json") for item in results],
                created_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
        await db.commit()
    return LocationSearchResponse(state="ready" if results else "no_results", results=results)


@app.get("/weather/radar/stations/nearby", tags=["weather"])
async def nearby_radar_stations(
    request: Request,
    response: Response,
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    try:
        return await request.app.state.radar_stations.nearby(lat, lon)
    except ProviderUnavailable as exc:
        response.headers["Cache-Control"] = "public, max-age=30"
        return {"state": "source_unavailable", "stations": [], "message": str(exc)}


@app.get("/weather/style", tags=["weather"])
async def style():
    return {
        "version": 8,
        "name": "WxSpot",
        "sources": {
            "basemap": {
                "type": "raster",
                "tiles": [settings().basemap_tiles],
                "tileSize": 256,
                "attribution": "© OpenStreetMap contributors",
                "maxzoom": 19,
            },
        },
        "layers": [
            {"id": "background", "type": "background", "paint": {"background-color": "#0B1220"}},
            {
                "id": "basemap",
                "type": "raster",
                "source": "basemap",
                "paint": {"raster-saturation": -0.75, "raster-brightness-max": 0.42},
            },
        ],
    }


@app.get("/weather/style/game", tags=["weather"])
async def game_map_style():
    """A geographic game board; keep the analytical weather style unchanged."""
    game = await style()
    game["name"] = "WXspot Sounding Hunt light map"
    game["layers"] = [
        {
            "id": "background",
            "type": "background",
            "paint": {"background-color": "#D8F1FA"},
        },
        {
            "id": "basemap",
            "type": "raster",
            "source": "basemap",
            "paint": {
                "raster-saturation": 0.12,
                "raster-brightness-min": 0.16,
                "raster-brightness-max": 0.99,
                "raster-contrast": 0.03,
            },
        },
    ]
    return game
