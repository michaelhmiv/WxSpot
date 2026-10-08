from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from wxspot.database import sessions
from wxspot.models import WeatherCache


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
