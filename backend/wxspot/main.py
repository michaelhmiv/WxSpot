import math
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256

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
from wxspot.models import AccessToken, GeocodeCache, GeocoderBudget, Quota, User
from wxspot.social import quota, router
from wxspot.storage import storage
from wxspot.weather import (
    AlertProvider,
    RadarProvider,
    RadarWeatherAdapter,
    SourceError,
    WeatherProviderRegistry,
)
from wxspot.weather_contracts import WeatherFramesResponse, WeatherSelection


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(25, connect=10),
        headers={"User-Agent": settings().nws_user_agent},
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        follow_redirects=True,
    ) as client:
        app.state.radar = RadarProvider(client)
        app.state.weather = WeatherProviderRegistry([RadarWeatherAdapter(app.state.radar)])
        app.state.alerts = AlertProvider(client)
        app.state.geocoder = NominatimProvider(client)
        app.state.radar_stations = RadarStationProvider(client)
        app.state.storage = storage()
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
    domain: str | None = Query(default=None, max_length=40),
    model: str | None = Query(default=None, max_length=30),
    run_time: datetime | None = None,
    forecast_hour: int | None = Query(default=None, ge=0, le=240),
    vertical_level: str | None = Query(default=None, max_length=40),
    channel: str | None = Query(default=None, max_length=40),
):
    response.headers["Cache-Control"] = "public, max-age=15, stale-while-revalidate=30"
    try:
        selection = WeatherSelection(
            source_type=source_type,
            source_id=source_id,
            product_id=product,
            site=site or ("KCLX" if source_type == "radar" else None),
            domain=domain,
            model=model,
            run_time=run_time,
            forecast_hour=forecast_hour,
            vertical_level=vertical_level,
            channel=channel,
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


@app.get("/weather/alerts", tags=["official weather"])
async def alerts(request: Request):
    return await request.app.state.alerts.active()


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
