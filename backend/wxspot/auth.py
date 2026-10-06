import hashlib
import secrets
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, exceptions, schemas
from fastapi_users.authentication import AuthenticationBackend, BearerTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wxspot.config import settings
from wxspot.database import session
from wxspot.models import AccessToken, Block, DeviceProfile, User

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

router = APIRouter()


class DeviceSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resume_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{43}$")


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str = Field(min_length=1, max_length=60)


@router.post("/auth/guest", tags=["authentication"])
async def device_session(
    body: DeviceSessionRequest,
    response: Response,
    db: AsyncSession = Depends(session),
    user_manager: Manager = Depends(manager),
    token_strategy: DatabaseStrategy = Depends(strategy),
):
    """Create or resume an ordinary profile without asking for email or a password."""
    key = body.resume_key
    if key is None:
        key = secrets.token_urlsafe(32)
        user = await user_manager.create(
            UserCreate(
                email=f"guest-{uuid.uuid4()}@guest.example.com",
                password=secrets.token_urlsafe(48),
                display_name="Weather explorer",
            ),
            safe=True,
        )
        db.add(DeviceProfile(key_hash=hashlib.sha256(key.encode()).hexdigest(), user_id=user.id))
        await db.commit()
        response.status_code = 201
    else:
        credential = await db.get(DeviceProfile, hashlib.sha256(key.encode()).hexdigest())
        user = await db.get(User, credential.user_id) if credential else None
        if user is None or not user.is_active:
            raise HTTPException(401, "Could not restore this device profile")
    token = await token_strategy.write_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "resume_key": key,
        "user_id": str(user.id),
        "display_name": user.display_name,
    }


@router.patch("/account", tags=["profiles"])
async def update_profile(
    body: ProfileUpdate, db: AsyncSession = Depends(session), user: User = Depends(required_user)
):
    user.display_name = body.display_name
    db.add(user)
    await db.commit()
    return {"id": str(user.id), "display_name": user.display_name}


@router.get("/account/blocks", tags=["profiles"])
async def blocked_profiles(
    db: AsyncSession = Depends(session), user: User = Depends(required_user)
):
    people = await db.scalars(
        select(User)
        .join(Block, Block.blocked_id == User.id)
        .where(Block.blocker_id == user.id)
        .order_by(User.display_name, User.id)
    )
    return [{"id": str(person.id), "display_name": person.display_name} for person in people]
