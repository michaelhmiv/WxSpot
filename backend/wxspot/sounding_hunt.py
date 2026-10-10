"""Server-authoritative daily and practice play for the Sounding Hunt game."""

import math
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pyproj import Geod
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from wxspot.auth import required_user
from wxspot.database import session
from wxspot.hunt_radar import launch_frames, parse_frame_stamp
from wxspot.models import (
    DailyHuntChallenge,
    DailyHuntGuess,
    SoundingHuntPractice,
    SoundingIngestionStatus,
    SoundingObservation,
    SoundingStation,
    User,
)
from wxspot.social import quota
from wxspot.sounding_calculations import calculate
from wxspot.sounding_contracts import SoundingDiagnostics, SoundingProfile

router = APIRouter(prefix="/game/sounding-hunt", tags=["sounding hunt"])
EASTERN = ZoneInfo("America/New_York")
GEOD = Geod(ellps="WGS84")
SCORE_VERSION = "exp-distance-v1"
SCORE_SCALE_MILES = 750.0
DAILY_QUEUE_DAYS = 14


class HuntLevel(BaseModel):
    pressure_hpa: float
    temperature_c: float | None = None
    dewpoint_c: float | None = None
    height_m_agl: float | None = None
    u_ms: float | None = None
    v_ms: float | None = None


class PublicSounding(BaseModel):
    diagnostics: SoundingDiagnostics | None = None
    observation_time: datetime
    observation_time_basis: str = "launch"
    surface_pressure_hpa: float | None = None
    levels: list[HuntLevel]


class DailyChallengeResponse(PublicSounding):
    challenge_day: date
    challenge_number: int
    starts_at: datetime
    ends_at: datetime
    completed: bool
    current_streak: int


class GuessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=24, le=50)
    longitude: float = Field(ge=-125, le=-66)


class RevealAnswer(BaseModel):
    station_id: str
    station_name: str
    state: str
    latitude: float
    longitude: float
    elevation_m: float
    source: str
    source_version: str
    source_revision: str | None = None
    nominal_time: datetime | None = None


class ChallengeResult(BaseModel):
    challenge_day: date | None = None
    challenge_number: int | None = None
    observation_time: datetime
    selected_latitude: float | None = None
    selected_longitude: float | None = None
    answer: RevealAnswer
    distance_miles: float | None = None
    score: int | None = None
    scoring_version: str | None = None
    insights: list[str]
    historical: bool = False


class PracticeResponse(PublicSounding):
    practice_id: uuid.UUID


class LeaderboardRow(BaseModel):
    rank: int
    display_name: str
    score: int
    distance_miles: float
    submitted_at: datetime
    is_you: bool


class LeaderboardResponse(BaseModel):
    challenge_day: date
    challenge_number: int
    rows: list[LeaderboardRow]
    player_rank: int | None
    total_players: int
    page: int


class HistoryItem(BaseModel):
    challenge_day: date
    challenge_number: int
    score: int
    distance_miles: float
    submitted_at: datetime


class PlayerProfile(BaseModel):
    display_name: str
    daily_challenges_played: int
    average_score: float | None
    best_score: int | None
    average_error_miles: float | None
    current_streak: int
    longest_streak: int
    history: list[HistoryItem]


class ExclusionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    excluded: bool
    reason: str | None = Field(default=None, max_length=500)


class HuntQueueStatus(BaseModel):
    validated_candidates: int
    upcoming_challenges: int
    most_recent_ingestion: datetime | None
    failed_stations: int


class CandidateAdminRow(BaseModel):
    identity: str
    station_id: str
    station_name: str
    state: str
    observation_time: datetime
    validation: dict
    eligible: bool
    exclusion_reason: str | None


def current_challenge_day(now: datetime | None = None) -> date:
    """Return the Eastern calendar identity active under the 08:00 local reset."""
    local = (now or datetime.now(UTC)).astimezone(EASTERN)
    return local.date() if local.time() >= time(8) else local.date() - timedelta(days=1)


def challenge_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(8), tzinfo=EASTERN)
    end = datetime.combine(day + timedelta(days=1), time(8), tzinfo=EASTERN)
    return start.astimezone(UTC), end.astimezone(UTC)


def distance_miles(
    guess_lon: float, guess_lat: float, answer_lon: float, answer_lat: float
) -> float:
    values = (guess_lon, guess_lat, answer_lon, answer_lat)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Coordinates must be finite")
    if not (-180 <= guess_lon <= 180 and -90 <= guess_lat <= 90):
        raise ValueError("Guess coordinates are outside WGS84 bounds")
    if not (-180 <= answer_lon <= 180 and -90 <= answer_lat <= 90):
        raise ValueError("Answer coordinates are outside WGS84 bounds")
    return abs(GEOD.inv(guess_lon, guess_lat, answer_lon, answer_lat)[2]) / 1609.344


def score_for_distance(distance: float, scale_miles: float = SCORE_SCALE_MILES) -> int:
    if not math.isfinite(distance) or distance < 0:
        raise ValueError("Distance must be a finite non-negative number")
    if not math.isfinite(scale_miles) or scale_miles <= 0:
        raise ValueError("Scoring scale must be positive and finite")
    raw = 5000 * math.exp(-distance / scale_miles)
    return max(0, min(5000, math.floor(raw + 0.5)))


def streak_lengths(completed_days: set[date], now: datetime | None = None) -> tuple[int, int]:
    if not completed_days:
        return 0, 0
    today = current_challenge_day(now)
    anchor = today if today in completed_days else today - timedelta(days=1)
    current = 0
    cursor = anchor
    while cursor in completed_days:
        current += 1
        cursor -= timedelta(days=1)
    longest = run = 0
    previous = None
    for day in sorted(completed_days):
        run = run + 1 if previous == day - timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    return current, longest


def _public_diagnostics(observation: SoundingObservation) -> dict | None:
    """Run the existing verified MetPy engine; never leak station metadata."""
    try:
        source = SoundingProfile.model_validate(observation.profile)
        details = calculate(source)
    except (ValueError, TypeError, ArithmeticError, IndexError):
        return None
    public = details.model_dump(mode="json")
    # Diagnostics identity is computed from a private station-bearing profile key.
    # Replace it rather than exposing a hash that could be used to enumerate sites.
    public["identity"] = "hunt:observation"
    return public


def _public_sounding(observation: SoundingObservation) -> dict:
    profile = observation.profile
    # Explicit projection: do not include identity, station, coordinates, source URLs,
    # terrain, profile metadata, QC provenance, or other private ORM fields.
    levels = [
        {
            "pressure_hpa": level["pressure_hpa"],
            "temperature_c": level.get("temperature_c"),
            "dewpoint_c": level.get("dewpoint_c"),
            "height_m_agl": (
                level.get("height_m_msl") - profile.get("terrain_m_msl", 0)
                if level.get("height_m_msl") is not None
                else None
            ),
            "u_ms": level.get("u_ms"),
            "v_ms": level.get("v_ms"),
        }
        for level in profile.get("levels", [])
    ]
    return {
        "diagnostics": _public_diagnostics(observation),
        "observation_time": observation.observed_at,
        "observation_time_basis": (
            "nominal"
            if "Release time missing; nominal observation time shown" in profile.get("quality", [])
            else "launch"
        ),
        "surface_pressure_hpa": profile.get("surface_pressure_hpa"),
        "levels": levels,
    }


def _insights(profile: dict) -> list[str]:
    levels = profile.get("levels", [])
    results = []
    surface_pressure = profile.get("surface_pressure_hpa")
    if surface_pressure is not None and surface_pressure < 950:
        results.append(
            f"The launch surface pressure was {surface_pressure:.0f} hPa, "
            "strong evidence of elevated terrain."
        )

    low = [level for level in levels if level.get("temperature_c") is not None][:4]
    moist = [level for level in low if level.get("dewpoint_c") is not None]
    if len(moist) >= 2:
        spreads = [level["temperature_c"] - level["dewpoint_c"] for level in moist]
        average_spread = sum(spreads) / len(spreads)
        if average_spread <= 5:
            results.append(
                "The lowest measured layers were moist, with temperature and dew point "
                "close together."
            )
        elif average_spread >= 18:
            results.append(
                "A wide low-level temperature–dew point spread showed a dry near-surface layer."
            )

    if len(low) >= 2:
        first, second = low[0], low[1]
        if second["temperature_c"] - first["temperature_c"] >= 3:
            results.append(
                "Temperature increased above the surface, showing a low-level inversion."
            )
        elif first["temperature_c"] - second["temperature_c"] >= 8:
            results.append(
                "Temperature fell quickly just above the surface, indicating a steep "
                "low-level lapse rate."
            )

    winds = [
        level for level in levels if level.get("u_ms") is not None and level.get("v_ms") is not None
    ]
    if len(winds) >= 2:
        shear = math.hypot(
            winds[-1]["u_ms"] - winds[0]["u_ms"],
            winds[-1]["v_ms"] - winds[0]["v_ms"],
        )
        if shear >= 20:
            results.append(f"Wind changed by about {shear:.0f} m/s through the observed profile.")
    if not results:
        results.append("The profile offers clues from moisture, temperature, pressure, and winds.")
    results.append(
        "Similar soundings can occur far apart; these clues narrow possibilities but do not "
        "identify one place by themselves."
    )
    return results[:4]


async def _profile_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[list[DailyHuntGuess], set[date]]:
    rows = list(
        (
            await db.scalars(
                select(DailyHuntGuess)
                .where(DailyHuntGuess.user_id == user_id)
                .order_by(DailyHuntGuess.submitted_at.desc())
            )
        ).all()
    )
    day_rows = await db.execute(
        select(DailyHuntChallenge.challenge_day)
        .join(DailyHuntGuess, DailyHuntGuess.challenge_id == DailyHuntChallenge.id)
        .where(DailyHuntGuess.user_id == user_id)
    )
    return rows, set(day_rows.scalars().all())


async def _challenge(db: AsyncSession, day: date) -> DailyHuntChallenge:
    challenge = await db.scalar(
        select(DailyHuntChallenge).where(DailyHuntChallenge.challenge_day == day)
    )
    if challenge is None:
        raise HTTPException(503, "Today's verified sounding is not available yet")
    return challenge


async def _observation(db: AsyncSession, identity: str) -> SoundingObservation:
    value = await db.get(SoundingObservation, identity)
    if value is None:
        raise HTTPException(503, "The verified sounding is temporarily unavailable")
    return value


def _answer_payload(observation: SoundingObservation, station: SoundingStation) -> dict:
    point = observation.profile["sampled_point"]
    return {
        "station_id": observation.station_id,
        "station_name": station.name,
        "state": station.state,
        "latitude": point[1],
        "longitude": point[0],
        "elevation_m": station.elevation_m,
        "source": "NOAA / NCEI Integrated Global Radiosonde Archive",
        "source_version": "IGRA 2.2",
        "source_revision": observation.source_revision,
        "nominal_time": observation.nominal_time,
    }


async def _result(
    db: AsyncSession,
    observation: SoundingObservation,
    station: SoundingStation,
    *,
    challenge: DailyHuntChallenge | None = None,
    guess: DailyHuntGuess | None = None,
    practice: SoundingHuntPractice | None = None,
    historical: bool = False,
) -> dict:
    answer = _answer_payload(observation, station)
    return {
        "challenge_day": challenge.challenge_day if challenge else None,
        "challenge_number": challenge.challenge_number if challenge else None,
        "observation_time": observation.observed_at,
        "selected_latitude": guess.latitude if guess else (practice.latitude if practice else None),
        "selected_longitude": (
            guess.longitude if guess else (practice.longitude if practice else None)
        ),
        "answer": answer,
        "distance_miles": (
            guess.distance_miles if guess else (practice.distance_miles if practice else None)
        ),
        "score": guess.score if guess else (practice.score if practice else None),
        "scoring_version": (
            guess.scoring_version if guess else (practice.scoring_version if practice else None)
        ),
        "insights": _insights(observation.profile),
        "historical": historical,
    }


async def _current_streak(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> int:
    _, days = await _profile_for_user(db, user_id)
    return streak_lengths(days, now)[0]


async def _radar_target(kind: str, identifier: str, db: AsyncSession, user: User):
    """Constrain evidence strictly to a released daily or the user's practice."""
    if kind == "daily":
        try:
            challenge_day = date.fromisoformat(identifier)
        except ValueError as error:
            raise HTTPException(404, "Unknown challenge") from error
        challenge = await _challenge(db, challenge_day)
        if datetime.now(UTC) < challenge.starts_at:
            raise HTTPException(404, "Challenge not yet released")
        return await _observation(db, challenge.observation_identity)
    if kind == "practice":
        try:
            practice_id = uuid.UUID(identifier)
        except ValueError as error:
            raise HTTPException(404, "Unknown practice session") from error
        practice = await db.get(SoundingHuntPractice, practice_id)
        if practice is None or practice.user_id != user.id:
            raise HTTPException(404, "Unknown practice session")
        return await _observation(db, practice.observation_identity)
    raise HTTPException(404, "Unknown evidence type")


@router.get("/radar/{kind}/{identifier}/frames")
async def historical_radar_frames(
    kind: str,
    identifier: str,
    request: Request,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    observation = await _radar_target(kind, identifier, db, user)
    # Single scoped public account; avoid arbitrary external date/proxy selection.
    await quota(str(user.id), "radar_frames", 120)
    path = f"/game/sounding-hunt/radar/{kind}/{identifier}"
    return await request.app.state.historical_radar.frames(observation.observed_at, path)


@router.get("/radar/{kind}/{identifier}/tiles/{stamp}/{z}/{x}/{y}.png")
async def historical_radar_tile(
    kind: str,
    identifier: str,
    stamp: str,
    z: int,
    x: int,
    y: int,
    request: Request,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    observation = await _radar_target(kind, identifier, db, user)
    try:
        timestamp = parse_frame_stamp(stamp)
    except ValueError as error:
        raise HTTPException(404, "Invalid radar frame") from error
    if timestamp not in launch_frames(observation.observed_at):
        raise HTTPException(404, "Radar frame is outside this observation window")
    try:
        content = await request.app.state.historical_radar.tile(timestamp, z, x, y)
    except ValueError as error:
        raise HTTPException(404, "Unsupported radar tile") from error
    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400", "Vary": "Authorization"},
    )


@router.get("/radar/{kind}/{identifier}/site/{site}/{product}/{tilt}/frames")
async def historical_site_radar_frames(
    kind: str,
    identifier: str,
    site: str,
    product: str,
    tilt: int,
    request: Request,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    observation = await _radar_target(kind, identifier, db, user)
    await quota(str(user.id), "radar_frames", 120)
    path = f"/game/sounding-hunt/radar/{kind}/{identifier}"
    return await request.app.state.historical_radar.site_frames(
        observation.observed_at, site, product, tilt, path
    )


@router.get(
    "/radar/{kind}/{identifier}/site/{site}/{product}/{tilt}/tiles/{code}/{stamp}/{z}/{x}/{y}.png"
)
async def historical_site_radar_tile(
    kind: str,
    identifier: str,
    site: str,
    product: str,
    tilt: int,
    code: str,
    stamp: str,
    z: int,
    x: int,
    y: int,
    request: Request,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    observation = await _radar_target(kind, identifier, db, user)
    raster = await request.app.state.historical_radar.site_tile(
        observation.observed_at, site, product, tilt, code, stamp, z, x, y
    )
    return Response(
        content=raster,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400", "Vary": "Authorization"},
    )


@router.get("/radar/{kind}/{identifier}/rain/{product}/frames")
async def historical_mrms_frames(
    kind: str,
    identifier: str,
    product: str,
    request: Request,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    observation = await _radar_target(kind, identifier, db, user)
    await quota(str(user.id), "radar_frames", 120)
    path = f"/game/sounding-hunt/radar/{kind}/{identifier}"
    try:
        return await request.app.state.historical_rainfall.frames(
            observation.observed_at, product, path
        )
    except ValueError as error:
        raise HTTPException(404, "Unknown historical precipitation product") from error


@router.get("/radar/{kind}/{identifier}/rain/{product}/tiles/{stamp}/{z}/{x}/{y}.png")
async def historical_mrms_tile(
    kind: str,
    identifier: str,
    product: str,
    stamp: str,
    z: int,
    x: int,
    y: int,
    request: Request,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    observation = await _radar_target(kind, identifier, db, user)
    content = await request.app.state.historical_rainfall.tile(
        observation.observed_at, product, stamp, z, x, y
    )
    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400", "Vary": "Authorization"},
    )


@router.get("/today", response_model=DailyChallengeResponse)
async def today(db: AsyncSession = Depends(session), user: User = Depends(required_user)):
    now = datetime.now(UTC)
    day = current_challenge_day(now)
    challenge = await _challenge(db, day)
    observation = await _observation(db, challenge.observation_identity)
    guess = await db.scalar(
        select(DailyHuntGuess).where(
            DailyHuntGuess.challenge_id == challenge.id,
            DailyHuntGuess.user_id == user.id,
        )
    )
    return {
        **_public_sounding(observation),
        "challenge_day": challenge.challenge_day,
        "challenge_number": challenge.challenge_number,
        "starts_at": challenge.starts_at,
        "ends_at": challenge.ends_at,
        "completed": guess is not None,
        "current_streak": await _current_streak(db, user.id, now),
    }


@router.get("/daily/{challenge_day}", response_model=DailyChallengeResponse)
async def daily_sounding(
    challenge_day: date,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    """Return a sanitized chart profile for a known day; answer data stays private."""
    now = datetime.now(UTC)
    challenge = await _challenge(db, challenge_day)
    if now < challenge.starts_at:
        raise HTTPException(404, "This sounding has not been released")
    observation = await _observation(db, challenge.observation_identity)
    guess = await db.scalar(
        select(DailyHuntGuess).where(
            DailyHuntGuess.challenge_id == challenge.id,
            DailyHuntGuess.user_id == user.id,
        )
    )
    return {
        **_public_sounding(observation),
        "challenge_day": challenge.challenge_day,
        "challenge_number": challenge.challenge_number,
        "starts_at": challenge.starts_at,
        "ends_at": challenge.ends_at,
        "completed": guess is not None,
        "current_streak": await _current_streak(db, user.id, now),
    }


@router.post("/daily/{challenge_day}/guess", response_model=ChallengeResult, status_code=201)
async def submit_daily_guess(
    challenge_day: date,
    body: GuessRequest,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    await quota(str(user.id), "hunt_daily", 4)
    now = datetime.now(UTC)
    if challenge_day != current_challenge_day(now):
        raise HTTPException(409, "This daily challenge is no longer ranked")
    challenge = await _challenge(db, challenge_day)
    if not challenge.starts_at <= now < challenge.ends_at:
        raise HTTPException(409, "This daily challenge is outside its ranked window")
    observation = await _observation(db, challenge.observation_identity)
    point = observation.profile["sampled_point"]
    miles = distance_miles(body.longitude, body.latitude, point[0], point[1])
    guess = DailyHuntGuess(
        user_id=user.id,
        challenge_id=challenge.id,
        latitude=body.latitude,
        longitude=body.longitude,
        distance_miles=miles,
        score=score_for_distance(miles, challenge.score_scale_miles),
        scoring_version=challenge.scoring_version,
        submitted_at=now,
    )
    db.add(guess)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "You already submitted a guess for this daily challenge") from exc
    station = await db.get(SoundingStation, observation.station_id)
    return await _result(db, observation, station, challenge=challenge, guess=guess)


@router.get("/daily/{challenge_day}/result", response_model=ChallengeResult)
async def daily_result(
    challenge_day: date,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    challenge = await _challenge(db, challenge_day)
    now = datetime.now(UTC)
    guess = await db.scalar(
        select(DailyHuntGuess).where(
            DailyHuntGuess.challenge_id == challenge.id,
            DailyHuntGuess.user_id == user.id,
        )
    )
    if guess is None and now < challenge.ends_at:
        raise HTTPException(403, "Submit your guess before viewing the answer")
    observation = await _observation(db, challenge.observation_identity)
    station = await db.get(SoundingStation, observation.station_id)
    return await _result(
        db,
        observation,
        station,
        challenge=challenge,
        guess=guess,
        historical=guess is None,
    )


@router.get("/leaderboard/{challenge_day}", response_model=LeaderboardResponse)
async def leaderboard(
    challenge_day: date,
    page: int = Query(default=1, ge=1, le=10000),
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    challenge = await _challenge(db, challenge_day)
    page_size = 50
    query = (
        select(DailyHuntGuess, User)
        .join(User, User.id == DailyHuntGuess.user_id)
        .where(DailyHuntGuess.challenge_id == challenge.id)
        .order_by(
            DailyHuntGuess.score.desc(),
            DailyHuntGuess.distance_miles.asc(),
            DailyHuntGuess.submitted_at.asc(),
            DailyHuntGuess.user_id.asc(),
        )
    )
    entries = (await db.execute(query.offset((page - 1) * page_size).limit(page_size))).all()
    total = await db.scalar(
        select(func.count())
        .select_from(DailyHuntGuess)
        .where(DailyHuntGuess.challenge_id == challenge.id)
    )
    own = await db.scalar(
        select(DailyHuntGuess).where(
            DailyHuntGuess.challenge_id == challenge.id,
            DailyHuntGuess.user_id == user.id,
        )
    )
    own_rank = None
    if own:
        ahead = await db.scalar(
            select(func.count())
            .select_from(DailyHuntGuess)
            .where(
                DailyHuntGuess.challenge_id == challenge.id,
                or_(
                    DailyHuntGuess.score > own.score,
                    and_(
                        DailyHuntGuess.score == own.score,
                        DailyHuntGuess.distance_miles < own.distance_miles,
                    ),
                    and_(
                        DailyHuntGuess.score == own.score,
                        DailyHuntGuess.distance_miles == own.distance_miles,
                        DailyHuntGuess.submitted_at < own.submitted_at,
                    ),
                    and_(
                        DailyHuntGuess.score == own.score,
                        DailyHuntGuess.distance_miles == own.distance_miles,
                        DailyHuntGuess.submitted_at == own.submitted_at,
                        DailyHuntGuess.user_id < own.user_id,
                    ),
                ),
            )
        )
        own_rank = int(ahead or 0) + 1
    rows = [
        {
            "rank": (page - 1) * page_size + offset + 1,
            "display_name": profile.display_name,
            "score": guess.score,
            "distance_miles": round(guess.distance_miles, 2),
            "submitted_at": guess.submitted_at,
            "is_you": guess.user_id == user.id,
        }
        for offset, (guess, profile) in enumerate(entries)
    ]
    return {
        "challenge_day": challenge_day,
        "challenge_number": challenge.challenge_number,
        "rows": rows,
        "player_rank": own_rank,
        "total_players": int(total or 0),
        "page": page,
    }


@router.get("/profile", response_model=PlayerProfile)
async def profile(db: AsyncSession = Depends(session), user: User = Depends(required_user)):
    guesses, days = await _profile_for_user(db, user.id)
    current, longest = streak_lengths(days)
    challenge_ids = [guess.challenge_id for guess in guesses]
    challenge_rows = []
    if challenge_ids:
        results = await db.execute(
            select(DailyHuntGuess, DailyHuntChallenge)
            .join(DailyHuntChallenge, DailyHuntChallenge.id == DailyHuntGuess.challenge_id)
            .where(DailyHuntGuess.user_id == user.id)
            .order_by(DailyHuntChallenge.challenge_day.desc())
            .limit(100)
        )
        challenge_rows = results.all()
    return {
        "display_name": user.display_name,
        "daily_challenges_played": len(guesses),
        "average_score": (
            round(sum(row.score for row in guesses) / len(guesses), 1) if guesses else None
        ),
        "best_score": max((row.score for row in guesses), default=None),
        "average_error_miles": (
            round(sum(row.distance_miles for row in guesses) / len(guesses), 1) if guesses else None
        ),
        "current_streak": current,
        "longest_streak": longest,
        "history": [
            {
                "challenge_day": challenge.challenge_day,
                "challenge_number": challenge.challenge_number,
                "score": guess.score,
                "distance_miles": round(guess.distance_miles, 2),
                "submitted_at": guess.submitted_at,
            }
            for guess, challenge in challenge_rows
        ],
    }


@router.post("/practice", response_model=PracticeResponse, status_code=201)
async def create_practice(db: AsyncSession = Depends(session), user: User = Depends(required_user)):
    await quota(str(user.id), "hunt_practice", 20)
    now = datetime.now(UTC)
    used_recently = select(SoundingHuntPractice.observation_identity).where(
        SoundingHuntPractice.user_id == user.id,
        SoundingHuntPractice.created_at >= now - timedelta(days=30),
    )
    eligible = (
        SoundingObservation.eligible.is_(True),
        SoundingObservation.identity.not_in(
            select(DailyHuntChallenge.observation_identity).where(DailyHuntChallenge.ends_at > now)
        ),
    )
    observation = await db.scalar(
        select(SoundingObservation)
        .where(*eligible, SoundingObservation.identity.not_in(used_recently))
        .order_by(func.random())
        .limit(1)
    )
    if observation is None:
        observation = await db.scalar(
            select(SoundingObservation).where(*eligible).order_by(func.random()).limit(1)
        )
    if observation is None:
        raise HTTPException(503, "No unused verified practice soundings are available yet")
    practice = SoundingHuntPractice(user_id=user.id, observation_identity=observation.identity)
    db.add(practice)
    await db.commit()
    return {**_public_sounding(observation), "practice_id": practice.id}


@router.post("/practice/{practice_id}/guess", response_model=ChallengeResult, status_code=201)
async def submit_practice_guess(
    practice_id: uuid.UUID,
    body: GuessRequest,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    await quota(str(user.id), "hunt_practice_guess", 20)
    practice = await db.scalar(
        select(SoundingHuntPractice)
        .where(
            SoundingHuntPractice.id == practice_id,
            SoundingHuntPractice.user_id == user.id,
        )
        .with_for_update()
    )
    if practice is None:
        raise HTTPException(404, "Practice session not found")
    if practice.submitted_at is not None:
        raise HTTPException(409, "This practice guess has already been submitted")
    observation = await _observation(db, practice.observation_identity)
    point = observation.profile["sampled_point"]
    miles = distance_miles(body.longitude, body.latitude, point[0], point[1])
    practice.latitude = body.latitude
    practice.longitude = body.longitude
    practice.distance_miles = miles
    practice.score = score_for_distance(miles, practice.score_scale_miles)
    practice.scoring_version = SCORE_VERSION
    practice.submitted_at = datetime.now(UTC)
    await db.commit()
    station = await db.get(SoundingStation, observation.station_id)
    return await _result(db, observation, station, practice=practice)


@router.get("/practice/{practice_id}/result", response_model=ChallengeResult)
async def practice_result(
    practice_id: uuid.UUID,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    practice = await db.scalar(
        select(SoundingHuntPractice).where(
            SoundingHuntPractice.id == practice_id,
            SoundingHuntPractice.user_id == user.id,
        )
    )
    if practice is None or practice.submitted_at is None:
        raise HTTPException(404, "Completed practice result not found")
    observation = await _observation(db, practice.observation_identity)
    station = await db.get(SoundingStation, observation.station_id)
    return await _result(db, observation, station, practice=practice)


@router.patch("/admin/observations/{identity}", response_model=HuntQueueStatus)
async def exclude_observation(
    identity: str,
    body: ExclusionRequest,
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    if not (user.is_moderator or user.is_superuser):
        raise HTTPException(403, "Administrator access required")
    observation = await db.get(SoundingObservation, identity)
    if observation is None:
        raise HTTPException(404, "Candidate observation not found")
    observation.eligible = not body.excluded
    observation.exclusion_reason = body.reason if body.excluded else None
    if body.excluded:
        now = datetime.now(UTC)
        future = await db.scalars(
            select(DailyHuntChallenge).where(
                DailyHuntChallenge.observation_identity == identity,
                DailyHuntChallenge.starts_at > now,
            )
        )
        for challenge in future:
            await db.delete(challenge)
    await db.commit()
    return await _queue_status(db)


@router.get("/admin/candidates", response_model=list[CandidateAdminRow])
async def admin_candidates(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(session),
    user: User = Depends(required_user),
):
    if not (user.is_moderator or user.is_superuser):
        raise HTTPException(403, "Administrator access required")
    rows = await db.execute(
        select(SoundingObservation, SoundingStation)
        .join(SoundingStation, SoundingStation.station_id == SoundingObservation.station_id)
        .order_by(SoundingObservation.observed_at.desc())
        .limit(limit)
    )
    return [
        {
            "identity": observation.identity,
            "station_id": observation.station_id,
            "station_name": station.name,
            "state": station.state,
            "observation_time": observation.observed_at,
            "validation": observation.validation,
            "eligible": observation.eligible,
            "exclusion_reason": observation.exclusion_reason,
        }
        for observation, station in rows
    ]


@router.get("/admin/status", response_model=HuntQueueStatus)
async def admin_status(db: AsyncSession = Depends(session), user: User = Depends(required_user)):
    if not (user.is_moderator or user.is_superuser):
        raise HTTPException(403, "Administrator access required")
    return await _queue_status(db)


async def _queue_status(db: AsyncSession) -> dict:
    today = current_challenge_day()
    candidates = await db.scalar(
        select(func.count())
        .select_from(SoundingObservation)
        .where(SoundingObservation.eligible.is_(True))
    )
    upcoming = await db.scalar(
        select(func.count())
        .select_from(DailyHuntChallenge)
        .where(DailyHuntChallenge.challenge_day >= today)
    )
    latest = await db.scalar(select(func.max(SoundingIngestionStatus.last_attempt_at)))
    failures = await db.scalar(
        select(func.count())
        .select_from(SoundingIngestionStatus)
        .where(SoundingIngestionStatus.state.in_(["failed", "rejected"]))
    )
    return {
        "validated_candidates": int(candidates or 0),
        "upcoming_challenges": int(upcoming or 0),
        "most_recent_ingestion": latest,
        "failed_stations": int(failures or 0),
    }
