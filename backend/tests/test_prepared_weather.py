import asyncio
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import select, update

from wxspot.config import settings
from wxspot.database import engine, sessions
from wxspot.models import WeatherArtifact, WeatherJob
from wxspot.providers.goes import decode_abi
from wxspot.providers.grids import PreparedGrid
from wxspot.storage import LocalStorage
from wxspot.weather import SourceError
from wxspot.weather_jobs import claim, content_key, enqueue, finish, reserve_artifact
from wxspot.workers.weather import cleanup


def test_real_abi_east_west_projection_and_temperature_reference():
    directory = Path(__file__).parent / "fixtures" / "goes"
    for ref in json.loads((directory / "reference.json").read_text()):
        grid = decode_abi(
            (directory / ref["filename"]).read_bytes(),
            "infrared",
            ref["platform"],
            datetime.fromisoformat(ref["start"].replace("Z", "+00:00")),
            datetime.fromisoformat(ref["end"].replace("Z", "+00:00")),
        )
        actual = grid.sample(np.asarray([ref["point"][0]]), np.asarray([ref["point"][1]]))[0]
        assert actual == pytest.approx(ref["brightness_temperature_c"], abs=0.0001)
        assert (
            PreparedGrid.decode(grid.encode()).sample(
                np.asarray([ref["point"][0]]), np.asarray([ref["point"][1]])
            )[0]
            == actual
        )
        assert np.isnan(grid.sample(np.asarray([0.0]), np.asarray([0.0]))[0])
        image = Image.open(
            BytesIO(
                grid.image(
                    [
                        ref["point"][0] - 0.1,
                        ref["point"][1] - 0.1,
                        ref["point"][0] + 0.1,
                        ref["point"][1] + 0.1,
                    ],
                    64,
                    64,
                )
            )
        )
        assert np.asarray(image)[..., 3].any()
        with pytest.raises(SourceError, match="channel"):
            decode_abi(
                (directory / ref["filename"]).read_bytes(),
                "water_vapor_mid",
                ref["platform"],
                datetime.fromisoformat(ref["start"].replace("Z", "+00:00")),
                datetime.fromisoformat(ref["end"].replace("Z", "+00:00")),
            )


@pytest.mark.asyncio
async def test_shared_jobs_coalesce_and_expired_leases_cannot_publish(client):
    payload = {"source_type": "satellite", "source_id": "noaa-goes", "frame_id": "same-frame"}
    try:
        jobs = await asyncio.gather(*(enqueue(payload) for _ in range(6)))
        assert len({j.content_key for j in jobs}) == 1
        first = await claim()
        assert first and first.attempts == 1
        assert await claim() is None
        await enqueue({**payload, "frame_id": "another-frame"})
        assert await claim() is None, "Heavy processing is globally bounded to one active lease"
        async with sessions() as db:
            await db.execute(
                update(WeatherJob)
                .where(WeatherJob.content_key == first.content_key)
                .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
            )
            await db.commit()
        recovered = await claim()
        assert recovered.attempts == 2 and recovered.lease_token != first.lease_token
        assert not await finish(first, {"object_key": "stale-worker"})
        assert await finish(recovered, {"object_key": "current-worker"})
        assert (await enqueue(payload)).manifest == {"object_key": "current-worker"}
        assert content_key(payload) != content_key({**payload, "frame_id": "another-frame"})
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_capacity_limit_accepts_duplicates_but_rejects_new_work(client, monkeypatch):
    monkeypatch.setattr(settings(), "weather_queue_limit", 2)
    try:
        first = {"source_type": "satellite", "source_id": "noaa-goes", "frame_id": "frame-one"}
        await enqueue(first)
        await enqueue({**first, "frame_id": "frame-two"})
        assert (await enqueue(first)).content_key == content_key(first)
        with pytest.raises(SourceError, match="busy"):
            await enqueue({**first, "frame_id": "frame-three"})
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_three_retries_are_finite_and_orphan_cleanup_preserves_archives(client, tmp_path):
    objects = LocalStorage(tmp_path)
    payload = {"source_type": "satellite", "source_id": "noaa-goes", "frame_id": "retry-frame"}
    try:
        await enqueue(payload)
        for attempt in range(1, 4):
            job = await claim()
            assert job.attempts == attempt
            await finish(job, None, "upstream missing")
            async with sessions() as db:
                await db.execute(update(WeatherJob).values(available_at=datetime.now(UTC)))
                await db.commit()
        assert (await enqueue(payload)).state == "failed"
        assert await claim() is None
        orphan_key = f"weather-live/{job.content_key}/{job.lease_token}.npz"
        await reserve_artifact(job, orphan_key)
        await objects.put(orphan_key, b"orphan", "application/octet-stream")
        await objects.put("archives/post/layer.png", b"preserved", "image/png")
        async with sessions() as db:
            await db.execute(
                update(WeatherArtifact).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await db.commit()
        await cleanup(objects)
        assert not (tmp_path / orphan_key).exists()
        assert await objects.get("archives/post/layer.png") == b"preserved"
        async with sessions() as db:
            assert (await db.scalars(select(WeatherArtifact))).all() == []
        with pytest.raises(ValueError):
            await objects.delete_live("archives/post/layer.png")
    finally:
        await engine.dispose()
