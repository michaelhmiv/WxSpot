"""Postgres coalescing, capacity limits and fenced leases shared by API/worker replicas."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import func, or_, select, text, update

from wxspot.config import settings
from wxspot.database import sessions
from wxspot.models import WeatherArtifact, WeatherJob
from wxspot.weather import SourceError

PROCESSING_VERSION = "weather-grid-v1"


def content_key(payload: dict) -> str:
    canonical = json.dumps({**payload, "version": PROCESSING_VERSION}, sort_keys=True)
    return sha256(canonical.encode()).hexdigest()


async def enqueue(payload: dict, *, retry_failed=False) -> WeatherJob:
    now = datetime.now(UTC)
    key = content_key(payload)
    async with sessions() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(1179991123926)"))
        job = await db.get(WeatherJob, key)
        if job is not None:
            job.requested_at = now
            if (
                job.expires_at < now
                and job.state != "running"
                or (
                    retry_failed
                    and job.state == "failed"
                    and now - job.available_at > timedelta(minutes=1)
                )
            ):
                await check_capacity(db)
                job.state, job.manifest, job.attempts = "queued", None, 0
                job.created_at = now
                job.available_at = now
                job.expires_at = now + timedelta(hours=settings().weather_live_hours)
            await db.commit()
            return job
        await check_capacity(db)
        job = WeatherJob(
            content_key=key,
            payload=payload,
            state="queued",
            created_at=now,
            requested_at=now,
            available_at=now,
            attempts=0,
            expires_at=now + timedelta(hours=settings().weather_live_hours),
        )
        db.add(job)
        await db.commit()
        return job


async def check_capacity(db):
    pending = await db.scalar(
        select(func.count())
        .select_from(WeatherJob)
        .where(WeatherJob.state.in_(["queued", "running"]))
    )
    if pending >= settings().weather_queue_limit:
        raise SourceError("source_unavailable", "Weather preparation is busy. Retry shortly.")


async def reserve_artifact(job, key):
    # Record an upload before writing it, so crashed or fenced-out uploads are reclaimable.
    if not key.startswith(f"weather-live/{job.content_key}/{job.lease_token}."):
        raise ValueError("Artifact does not belong to this lease")
    async with sessions() as db:
        db.add(WeatherArtifact(object_key=key, expires_at=job.expires_at))
        await db.commit()


async def claim() -> WeatherJob | None:
    now = datetime.now(UTC)
    async with sessions() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(1179991123926)"))
        active = await db.scalar(
            select(func.count())
            .select_from(WeatherJob)
            .where(WeatherJob.state == "running", WeatherJob.lease_until > now)
        )
        if active:
            return None
        job = await db.scalar(
            select(WeatherJob)
            .where(
                or_(
                    (WeatherJob.state == "queued") & (WeatherJob.available_at <= now),
                    (WeatherJob.state == "running") & (WeatherJob.lease_until < now),
                )
            )
            .order_by((WeatherJob.state == "running").desc(), WeatherJob.requested_at.desc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        if job.attempts >= 3:
            job.state, job.error = (
                "failed",
                "Weather preparation did not finish after three attempts.",
            )
            await db.commit()
            return None
        job.state, job.lease_token = "running", str(uuid.uuid4())
        job.lease_until = now + timedelta(seconds=settings().weather_lease_seconds)
        job.attempts += 1
        await db.commit()
        return job


async def heartbeat(job: WeatherJob):
    async with sessions() as db:
        await db.execute(
            update(WeatherJob)
            .where(
                WeatherJob.content_key == job.content_key,
                WeatherJob.lease_token == job.lease_token,
                WeatherJob.state == "running",
            )
            .values(
                lease_until=datetime.now(UTC) + timedelta(seconds=settings().weather_lease_seconds)
            )
        )
        await db.commit()


async def finish(job: WeatherJob, manifest: dict | None, error: str | None = None) -> bool:
    now = datetime.now(UTC)
    async with sessions() as db:
        result = await db.execute(
            update(WeatherJob)
            .where(
                WeatherJob.content_key == job.content_key,
                WeatherJob.lease_token == job.lease_token,
                WeatherJob.state == "running",
            )
            .values(
                state="ready" if manifest else ("queued" if job.attempts < 3 else "failed"),
                manifest=manifest,
                error=error,
                lease_until=None,
                available_at=now + timedelta(seconds=30 * job.attempts),
            )
        )
        await db.commit()
        return result.rowcount == 1


async def prepared(payload: dict) -> dict:
    job = await enqueue(payload)
    if job.state == "ready" and job.manifest:
        return job.manifest
    if job.state == "failed":
        raise SourceError("source_unavailable", job.error or "Weather preparation failed.")
    if datetime.now(UTC) - job.created_at > timedelta(minutes=8):
        raise SourceError("source_unavailable", "Weather preparation is delayed. Retry shortly.")
    raise SourceError("preparing", "Preparing this weather frame.")
