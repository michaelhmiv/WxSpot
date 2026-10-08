from datetime import UTC, datetime

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from wxspot.database import sessions
from wxspot.models import WeatherArtifact, WeatherCache


async def read_cache(key):
    async with sessions() as db:
        row = await db.get(WeatherCache, key)
        return row.manifest if row and row.expires_at > datetime.now(UTC) else None


async def write_cache(key, kind, manifest, expires_at):
    async with sessions() as db:
        statement = insert(WeatherCache).values(
            content_key=key, kind=kind, manifest=manifest, expires_at=expires_at
        )
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=[WeatherCache.content_key],
                set_={"kind": kind, "manifest": manifest, "expires_at": expires_at},
            )
        )
        await db.commit()


async def write_bounded_raw_cache(key, manifest, expires_at):
    """Shared immutable GRIB reuse with an explicit total byte/entry budget."""
    retired = []
    now = datetime.now(UTC)
    async with sessions() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(1179991123927)"))
        rows = list(
            (
                await db.scalars(
                    select(WeatherCache)
                    .where(WeatherCache.kind == "sounding_grib")
                    .order_by(WeatherCache.expires_at, WeatherCache.content_key)
                    .with_for_update()
                )
            ).all()
        )
        used = sum(row.manifest["bytes"] for row in rows)
        while rows and (len(rows) >= 512 or used + manifest["bytes"] > 768 * 1024 * 1024):
            old = rows.pop(0)
            used -= old.manifest["bytes"]
            retired.append(old.manifest["object_key"])
            await db.delete(old)
        if retired:
            await db.execute(
                update(WeatherArtifact)
                .where(WeatherArtifact.object_key.in_(retired))
                .values(expires_at=now)
            )
        statement = insert(WeatherCache).values(
            content_key=key, kind="sounding_grib", manifest=manifest, expires_at=expires_at
        )
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=[WeatherCache.content_key],
                set_={"manifest": manifest, "expires_at": expires_at},
            )
        )
        await db.commit()
    return retired
