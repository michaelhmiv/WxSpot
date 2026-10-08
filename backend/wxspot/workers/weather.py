import asyncio
import json
import logging
import resource
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from wxspot.config import settings
from wxspot.database import sessions
from wxspot.models import WeatherArtifact, WeatherCache, WeatherJob
from wxspot.providers.forecast import ModelProvider
from wxspot.providers.goes import GoesProvider
from wxspot.providers.soundings import SoundingProvider
from wxspot.storage import storage
from wxspot.weather import SourceError
from wxspot.weather_jobs import claim, finish, heartbeat, reserve_artifact

logger = logging.getLogger("wxspot.weather.worker")


async def renew_lease(job):
    while True:
        await asyncio.sleep(30)
        await heartbeat(job)


async def process(job, providers, objects):
    started = time.monotonic()
    provider = None
    renewal = asyncio.create_task(renew_lease(job))
    try:
        payload = job.payload
        provider = providers.get((payload.get("source_type"), payload.get("source_id")))
        if provider is None:
            raise SourceError("unsupported_product", "Unregistered weather preparation source.")
        if hasattr(provider, "job"):
            provider.job = job
        async with asyncio.timeout(settings().weather_job_seconds):
            grid = None
            if payload.get("source_type") == "sounding":
                document = await provider.prepare_document(payload)
                data = json.dumps(document, allow_nan=False).encode()
                metadata = {"kind": "sounding", "stage": payload.get("stage", "profile")}
                extension = "json"
            else:
                grid = await provider.prepare_artifact(payload["frame_id"])
                data = await asyncio.to_thread(grid.encode)
                metadata, extension = grid.metadata, "npz"
            if len(data) > settings().weather_artifact_limit_mb * 1024 * 1024:
                raise SourceError(
                    "source_unavailable", "Prepared artifact exceeds its size budget."
                )
            # A stale lease can only write an orphan; it cannot overwrite another lease's artifact.
            key = f"weather-live/{job.content_key}/{job.lease_token}.{extension}"
            await reserve_artifact(job, key)
            await objects.put(key, data, "application/octet-stream")
            published = await finish(job, {"object_key": key, "metadata": metadata})
            logger.info(
                json.dumps(
                    {
                        "event": "prepared",
                        "key": job.content_key,
                        "published": published,
                        "output_bytes": len(data),
                        "grid_bytes": grid.values.nbytes if grid else 0,
                        "seconds": round(time.monotonic() - started, 3),
                        "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    }
                )
            )
    except Exception as exc:
        message = exc.message if isinstance(exc, SourceError) else "Weather preparation failed."
        await finish(job, None, message[:300])
        logger.exception("Weather job %s failed", job.content_key)
    finally:
        if provider is not None and hasattr(provider, "job"):
            provider.job = None
        renewal.cancel()
        with suppress(asyncio.CancelledError):
            await renewal


async def cleanup(objects):
    # Published post archives have a different prefix and are never touched by live cleanup.
    async with sessions() as db:
        jobs = (
            await db.scalars(
                select(WeatherJob)
                .where(
                    WeatherJob.expires_at < datetime.now(UTC),
                    WeatherJob.state.in_(["ready", "failed"]),
                )
                .with_for_update(skip_locked=True)
                .limit(32)
            )
        ).all()
        for job in jobs:
            await db.delete(job)
        artifacts = (
            await db.scalars(
                select(WeatherArtifact)
                .where(WeatherArtifact.expires_at < datetime.now(UTC))
                .with_for_update(skip_locked=True)
                .limit(32)
            )
        ).all()
        for artifact in artifacts:
            await objects.delete_live(artifact.object_key)
            await db.delete(artifact)
        cached = (
            await db.scalars(
                select(WeatherCache)
                .where(WeatherCache.expires_at < datetime.now(UTC))
                .with_for_update(skip_locked=True)
                .limit(64)
            )
        ).all()
        for entry in cached:
            await db.delete(entry)
        await db.commit()


async def run():
    logging.basicConfig(level=logging.INFO)
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
    objects = storage()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60, connect=10),
        follow_redirects=True,
        headers={"User-Agent": settings().nws_user_agent},
        limits=httpx.Limits(max_connections=3, max_keepalive_connections=2),
    ) as client:
        goes = GoesProvider(client, objects)
        models = ModelProvider(client, objects)
        soundings = SoundingProvider(client, objects)
        providers = {
            ("satellite", goes.provider_id): goes,
            ("model", models.provider_id): models,
            ("sounding", soundings.provider_id): soundings,
        }
        last_cleanup = 0.0
        while True:
            try:
                if time.monotonic() - last_cleanup > 300:
                    await cleanup(objects)
                    last_cleanup = time.monotonic()
                job = await claim()
                if job:
                    await process(job, providers, objects)
                else:
                    await asyncio.sleep(1)
            except Exception:
                logger.exception("Weather worker cycle failed; retrying")
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run())
