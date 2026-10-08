import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from test_soundings import reference_profile

from wxspot.database import engine, sessions
from wxspot.models import WeatherArtifact, WeatherCache, WeatherJob
from wxspot.providers.soundings import SoundingProvider
from wxspot.sounding_contracts import SoundingSelection
from wxspot.sounding_service import SoundingService
from wxspot.storage import LocalStorage
from wxspot.weather_cache import write_bounded_raw_cache
from wxspot.weather_jobs import claim
from wxspot.workers.weather import process


@pytest.mark.asyncio
async def test_profile_and_derived_worker_jobs_round_trip_without_redownloading(client, tmp_path):
    objects = LocalStorage(tmp_path)
    service = SoundingService(objects)
    selection = SoundingSelection(kind="observed", station="USM00072357", lat=35.22, lon=-97.44)
    profile = reference_profile()
    async with httpx.AsyncClient() as http:
        provider = SoundingProvider(http, objects)
        prepare = AsyncMock(return_value=(profile, {"launches": [profile.valid_time.isoformat()]}))
        provider.prepare_profile = prepare
        providers = {("sounding", "noaa-soundings"): provider}
        try:
            assert (await service.get(selection)).state == "preparing"
            job = await claim()
            await process(job, providers, objects)
            partial = await service.get(selection)
            assert partial.state == "preparing" and partial.profile.identity == profile.identity
            assert partial.diagnostics is None
            await process(await claim(), providers, objects)
            ready = await service.get(selection)
            assert ready.state == "ready" and ready.diagnostics.metrics["sb_cape"].value > 3000
            assert ready.distance_km < 0.001
            custom = selection.model_copy(
                update={"parcel": "ml100", "motion": "custom", "storm_u": 5, "storm_v": 5}
            )
            assert (await service.get(custom)).profile.identity == ready.profile.identity
            await process(await claim(), providers, objects)
            changed = await service.get(custom)
            assert changed.state == "ready"
            assert changed.diagnostics.identity != ready.diagnostics.identity
            assert changed.diagnostics.vectors["selected"] == [5, 5]
            assert prepare.await_count == 1
            assert "NaN" not in json.dumps(changed.model_dump(mode="json"), allow_nan=False)
            async with sessions() as db:
                jobs = (await db.scalars(select(WeatherJob))).all()
                assert len(jobs) == 3 and all(j.state == "ready" for j in jobs)
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_shared_raw_cache_bounds_retire_live_objects_and_preserve_archives(client):
    expiry = datetime.now(UTC) + timedelta(hours=1)
    try:
        async with sessions() as db:
            db.add_all(
                WeatherCache(
                    content_key=f"field-{i:04}",
                    kind="sounding_grib",
                    manifest={"object_key": f"weather-live/{i}.grib", "bytes": 1},
                    expires_at=expiry,
                )
                for i in range(512)
            )
            db.add(WeatherArtifact(object_key="weather-live/0.grib", expires_at=expiry))
            db.add(WeatherArtifact(object_key="archives/post/image.png", expires_at=expiry))
            await db.commit()
        retired = await write_bounded_raw_cache(
            "extra-field", {"object_key": "weather-live/new.grib", "bytes": 1}, expiry
        )
        assert retired == ["weather-live/0.grib"]
        async with sessions() as db:
            assert len((await db.scalars(select(WeatherCache))).all()) == 512
            assert (await db.get(WeatherArtifact, "weather-live/0.grib")).expires_at < expiry
            assert (await db.get(WeatherArtifact, "archives/post/image.png")).expires_at == expiry
        large = {"object_key": "weather-live/large.grib", "bytes": 400 * 1024 * 1024}
        await write_bounded_raw_cache("large-one", large, expiry)
        await write_bounded_raw_cache(
            "large-two", {**large, "object_key": "weather-live/other.grib"}, expiry
        )
        async with sessions() as db:
            rows = (await db.scalars(select(WeatherCache))).all()
            assert sum(r.manifest["bytes"] for r in rows) <= 768 * 1024 * 1024
    finally:
        await engine.dispose()
