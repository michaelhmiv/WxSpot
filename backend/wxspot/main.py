from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, text

from wxspot.auth import UserCreate, UserRead, backend, required_user, users
from wxspot.auth import router as identity_router
from wxspot.config import settings
from wxspot.database import sessions
from wxspot.models import AccessToken, Quota, User
from wxspot.social import quota, router
from wxspot.storage import storage
from wxspot.weather import AlertProvider, RadarProvider, SourceError


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(25, connect=10),
        headers={"User-Agent": settings().nws_user_agent},
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        follow_redirects=True,
    ) as client:
        app.state.radar = RadarProvider(client)
        app.state.alerts = AlertProvider(client)
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
            await db.commit()
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
    site: str = Query(default="KCLX", pattern=r"^[KPT][A-Z0-9]{3}$"),
    product: str = Query(default="reflectivity", max_length=30),
):
    try:
        return await request.app.state.radar.frames(site, product)
    except SourceError as exc:
        return {"state": exc.state, "message": exc.message, "frames": [], "fetched_at": None}


@app.get("/weather/alerts", tags=["official weather"])
async def alerts(request: Request):
    return await request.app.state.alerts.active()


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
