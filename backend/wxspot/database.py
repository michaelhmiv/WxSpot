from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from wxspot.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings().database_url,
    **(
        {"poolclass": NullPool}
        if settings().environment == "test"
        else {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 5}
    ),
)
sessions = async_sessionmaker(engine, expire_on_commit=False)


async def session() -> AsyncGenerator[AsyncSession]:
    async with sessions() as db:
        yield db
