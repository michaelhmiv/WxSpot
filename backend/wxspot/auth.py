import uuid
from typing import Literal

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, exceptions, schemas
from fastapi_users.authentication import AuthenticationBackend, BearerTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from wxspot.config import settings
from wxspot.database import session
from wxspot.models import AccessToken, User

Role = Literal["enthusiast", "trained_spotter", "storm_chaser", "meteorologist", "organization"]


class UserRead(schemas.BaseUser[uuid.UUID]):
    display_name: str
    self_role: str
    verified_role: str | None


class UserCreate(schemas.BaseUserCreate):
    display_name: str = Field(min_length=1, max_length=60)
    self_role: Role = "enthusiast"


class Manager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def validate_password(self, password: str, user):
        if len(password) < 12 or len(password) > 200:
            raise exceptions.InvalidPasswordException(reason="Use 12–200 characters.")


async def user_db(db: AsyncSession = Depends(session)):
    yield SQLAlchemyUserDatabase(db, User)


async def manager(db=Depends(user_db)):
    yield Manager(db)


async def token_db(db: AsyncSession = Depends(session)):
    yield SQLAlchemyAccessTokenDatabase(db, AccessToken)


def strategy(db=Depends(token_db)):
    return DatabaseStrategy(db, lifetime_seconds=settings().session_seconds)


backend = AuthenticationBackend(
    name="database",
    transport=BearerTransport(tokenUrl="/auth/login"),
    get_strategy=strategy,
)
users = FastAPIUsers[User, uuid.UUID](manager, [backend])
required_user = users.current_user(active=True)
optional_user = users.current_user(active=True, optional=True)
