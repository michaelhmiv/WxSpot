"""Bounded IGRA candidate ingestion and idempotent daily challenge publication."""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from wxspot.database import sessions
from wxspot.models import (
    DailyHuntChallenge,
    SoundingIngestionStatus,
    SoundingObservation,
    SoundingStation,
)
from wxspot.sounding_hunt import (
    DAILY_QUEUE_DAYS,
    SCORE_SCALE_MILES,
    SCORE_VERSION,
    challenge_window,
    current_challenge_day,
)
from wxspot.weather import SourceError

logger = logging.getLogger("wxspot.sounding_hunt.ingestion")
CONUS_STATES = frozenset(
    "AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV "
    "NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
INGESTION_BATCH_SIZE = 3
MAX_STATION_LAUNCHES = 32
SOUNDING_QUEUE_LOCK = asyncio.Lock()


def is_conus_station(station: dict) -> bool:
    """Use the official U.S. station state code and coordinates, not ID heuristics alone."""
    return (
        station.get("id", "").startswith("US")
        and station.get("state") in CONUS_STATES
        and 24 <= station.get("lat", 0) <= 50
        and -125 <= station.get("lon", 0) <= -66
        and -150 <= station.get("elevation_m", -1000) <= 5000
    )


def validate_candidate(profile) -> tuple[bool, dict, str | None]:
    levels = profile.levels
    temperatures = [level for level in levels if level.temperature_c is not None]
    humidity = [level for level in levels if level.dewpoint_c is not None]
    winds = [level for level in levels if level.u_ms is not None and level.v_ms is not None]
    top_pressure = min((level.pressure_hpa for level in levels), default=1100)
    lat, lon = profile.sampled_point[1], profile.sampled_point[0]
    validation = {
        "level_count": len(levels),
        "temperature_count": len(temperatures),
        "humidity_count": len(humidity),
        "wind_count": len(winds),
        "top_pressure_hpa": top_pressure,
        "launch_hour_utc": profile.valid_time.hour,
        "location_in_conus": 24 <= lat <= 50 and -125 <= lon <= -66,
        "pressure_ordered": all(
            first.pressure_hpa > second.pressure_hpa
            for first, second in zip(levels, levels[1:], strict=False)
        ),
        "temperature_plausible": all(-120 <= level.temperature_c <= 60 for level in temperatures),
        "dewpoint_plausible": all(
            -120 <= level.dewpoint_c <= 40
            and (level.temperature_c is None or level.dewpoint_c <= level.temperature_c + 2)
            for level in humidity
        ),
        "wind_plausible": all(abs(level.u_ms) <= 200 and abs(level.v_ms) <= 200 for level in winds),
    }
    reason = None
    if len(levels) < 12:
        reason = "Fewer than 12 usable pressure levels"
    elif len(temperatures) < 10:
        reason = "Fewer than 10 usable temperature observations"
    elif len(humidity) < 6:
        reason = "Fewer than 6 usable humidity observations"
    elif top_pressure > 500:
        reason = "Profile does not reach 500 hPa"
    elif not validation["location_in_conus"]:
        reason = "Launch coordinates are outside the contiguous United States"
    elif not validation["pressure_ordered"]:
        reason = "Pressure levels are not strictly ordered"
    elif not validation["temperature_plausible"]:
        reason = "Temperature measurements are physically implausible"
    elif not validation["dewpoint_plausible"]:
        reason = "Dew point measurements are physically implausible"
    elif not validation["wind_plausible"]:
        reason = "Wind measurements are physically implausible"
    elif profile.surface_pressure_hpa is None:
        reason = "Surface pressure is unavailable"
    elif not (300 <= profile.surface_pressure_hpa <= 1100):
        reason = "Surface pressure is physically implausible"
    return reason is None, validation, reason


def _region(latitude: float, longitude: float) -> str:
    if longitude < -115:
        return "west"
    if longitude < -100:
        return "mountain" if latitude >= 37 else "southwest"
    if longitude < -90:
        return "plains"
    if latitude < 37:
        return "southeast"
    if latitude >= 40:
        return "northeast"
    return "mid-atlantic"


def _quality_penalty(observation: SoundingObservation) -> tuple[int, int, int]:
    validation = observation.validation
    nominal = observation.nominal_time
    return (
        0 if validation.get("wind_count", 0) >= 4 else 1,
        0 if nominal is not None and nominal.hour in (0, 12) else 1,
        -min(validation.get("level_count", 0), 200),
    )


def sounding_distance(left: dict, right: dict) -> float:
    """Compare measured thermodynamic structure; 0 is identical, 1 is very different."""
    targets = (1000, 850, 700, 500, 300)

    def signature(profile: dict) -> dict[tuple[int, str], float]:
        levels = profile.get("levels", [])
        result = {}
        for target in targets:
            level = min(
                levels,
                key=lambda item: abs(item.get("pressure_hpa", 1100) - target),
                default=None,
            )
            if level is None or abs(level.get("pressure_hpa", 1100) - target) > target * 0.08:
                continue
            for field in ("temperature_c", "dewpoint_c"):
                value = level.get(field)
                if value is not None:
                    result[target, field] = value
        return result

    first, second = signature(left), signature(right)
    shared = first.keys() & second.keys()
    if not shared:
        return 0.0
    normalized = [min(abs(first[key] - second[key]) / 20, 1) for key in shared]
    return sum(normalized) / len(normalized)


def _diversity_score(profile: dict, recent_profiles: list[dict]) -> float:
    if not recent_profiles:
        return 0.0
    distances = [sounding_distance(profile, other) for other in recent_profiles]
    return min(distances)


async def _persist_station_attempt(station: dict, provider, revision: str | None) -> str:
    attempted_at = datetime.now(UTC)
    state = "failed"
    reason = None
    observation_identity = None
    try:
        profile, source_info = await provider.observed({"station": station["id"], "launch": None})
        revision = source_info.get("source_revision") or revision
        launch_times = set()
        for value in source_info.get("launches", []):
            try:
                launch_time = datetime.fromisoformat(value).astimezone(UTC)
            except (TypeError, ValueError):
                continue
            if launch_time <= attempted_at:
                launch_times.add(launch_time)
        launch_times.add(profile.valid_time.astimezone(UTC))
        selected_launches = sorted(launch_times)[-MAX_STATION_LAUNCHES:]
        accepted_profiles = []
        rejected_launches = []
        for launch_time in selected_launches:
            if launch_time == profile.valid_time.astimezone(UTC):
                candidate, candidate_source = profile, source_info
            else:
                try:
                    candidate, candidate_source = await provider.observed(
                        {"station": station["id"], "launch": launch_time.isoformat()}
                    )
                except Exception as exc:
                    launch_reason = (
                        exc.message if isinstance(exc, SourceError) else "IGRA launch unavailable"
                    )
                    rejected_launches.append(f"{launch_time.isoformat()}: {launch_reason}")
                    continue
            revision = candidate_source.get("source_revision") or revision
            accepted, validation, launch_reason = validate_candidate(candidate)
            if accepted:
                accepted_profiles.append((candidate, validation))
            else:
                rejected_launches.append(f"{launch_time.isoformat()}: {launch_reason}")
        state = "accepted" if accepted_profiles else "rejected"
        observation_identity = accepted_profiles[-1][0].identity if accepted_profiles else None
        reason = "; ".join(rejected_launches)[:4000] if rejected_launches else None
        async with sessions() as db:
            row = await db.get(SoundingStation, station["id"])
            values = {
                "station_id": station["id"],
                "name": station["name"],
                "state": station["state"],
                "latitude": station["lat"],
                "longitude": station["lon"],
                "elevation_m": station["elevation_m"],
                "source_version": "IGRA 2.2",
                "updated_at": attempted_at,
            }
            if row is None:
                db.add(SoundingStation(**values))
            else:
                for name, value in values.items():
                    setattr(row, name, value)
            await db.flush()
            for candidate, validation in accepted_profiles:
                stored = await db.get(SoundingObservation, candidate.identity)
                if stored is None:
                    db.add(
                        SoundingObservation(
                            identity=candidate.identity,
                            station_id=station["id"],
                            observed_at=candidate.valid_time,
                            nominal_time=candidate.nominal_time,
                            profile=candidate.model_dump(mode="json"),
                            validation=validation,
                            source_revision=revision,
                            ingested_at=attempted_at,
                            eligible=True,
                        )
                    )
            status_row = await db.get(SoundingIngestionStatus, station["id"])
            values = {
                "station_id": station["id"],
                "last_attempt_at": attempted_at,
                "state": state,
                "reason": reason,
                "observation_identity": observation_identity,
                "source_revision": revision,
            }
            if status_row is None:
                db.add(SoundingIngestionStatus(**values))
            else:
                for name, value in values.items():
                    setattr(status_row, name, value)
            await db.commit()
        return state
    except Exception as exc:
        reason = exc.message if isinstance(exc, SourceError) else "IGRA candidate processing failed"
        async with sessions() as db:
            row = await db.get(SoundingStation, station["id"])
            if row is None:
                db.add(
                    SoundingStation(
                        station_id=station["id"],
                        name=station["name"],
                        state=station["state"],
                        latitude=station["lat"],
                        longitude=station["lon"],
                        elevation_m=station["elevation_m"],
                        source_version="IGRA 2.2",
                        updated_at=attempted_at,
                    )
                )
                await db.flush()
            status_row = await db.get(SoundingIngestionStatus, station["id"])
            values = {
                "station_id": station["id"],
                "last_attempt_at": attempted_at,
                "state": state,
                "reason": reason[:500],
                "observation_identity": None,
                "source_revision": revision,
            }
            if status_row is None:
                db.add(SoundingIngestionStatus(**values))
            else:
                for name, value in values.items():
                    setattr(status_row, name, value)
            await db.commit()
        logger.info("IGRA station %s was not ingested: %s", station["id"], reason)
        return state


async def _ingest_batch(provider) -> int:
    stations = [station for station in await provider.stations() if is_conus_station(station)]
    async with sessions() as db:
        # Older attempts are revisited first. Successful profiles stay usable during outages.
        attempts = {
            row.station_id: row.last_attempt_at
            for row in (await db.scalars(select(SoundingIngestionStatus))).all()
        }
    cutoff = datetime.now(UTC) - timedelta(hours=4)
    pending = [
        station
        for station in stations
        if attempts.get(station["id"], datetime.min.replace(tzinfo=UTC)) < cutoff
    ]
    pending.sort(
        key=lambda station: (
            attempts.get(station["id"], datetime.min.replace(tzinfo=UTC)),
            station["id"],
        )
    )
    outcomes = []
    for station in pending[:INGESTION_BATCH_SIZE]:
        outcomes.append(await _persist_station_attempt(station, provider, None))
    return sum(outcome == "accepted" for outcome in outcomes)


async def replenish_challenge_queue() -> int:
    """Publish only pre-validated profiles, one unique calendar slot per transaction."""
    created = 0
    today = current_challenge_day()
    for _ in range(DAILY_QUEUE_DAYS):
        async with sessions() as db:
            existing_days = set(
                (
                    await db.scalars(
                        select(DailyHuntChallenge.challenge_day).where(
                            DailyHuntChallenge.challenge_day >= today
                        )
                    )
                ).all()
            )
            next_day = next(
                (
                    today + timedelta(days=offset)
                    for offset in range(DAILY_QUEUE_DAYS)
                    if today + timedelta(days=offset) not in existing_days
                ),
                None,
            )
            if next_day is None:
                break
            used_observations = select(DailyHuntChallenge.observation_identity)
            observations = list(
                (
                    await db.scalars(
                        select(SoundingObservation)
                        .where(
                            SoundingObservation.eligible.is_(True),
                            SoundingObservation.identity.not_in(used_observations),
                            SoundingObservation.observed_at < challenge_window(next_day)[0],
                        )
                        .order_by(SoundingObservation.observed_at.desc())
                        .limit(500)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            if not observations:
                break
            station_ids = {item.station_id for item in observations}
            stations = {
                station.station_id: station
                for station in (
                    await db.scalars(
                        select(SoundingStation).where(SoundingStation.station_id.in_(station_ids))
                    )
                ).all()
            }
            recent_station_ids = set(
                (
                    await db.scalars(
                        select(SoundingObservation.station_id)
                        .join(
                            DailyHuntChallenge,
                            DailyHuntChallenge.observation_identity == SoundingObservation.identity,
                        )
                        .where(
                            DailyHuntChallenge.challenge_day < next_day,
                            DailyHuntChallenge.challenge_day >= next_day - timedelta(days=30),
                        )
                    )
                ).all()
            )
            prior = await db.scalar(
                select(DailyHuntChallenge)
                .where(DailyHuntChallenge.challenge_day < next_day)
                .order_by(DailyHuntChallenge.challenge_day.desc())
                .limit(1)
            )
            prior_region = None
            if prior:
                prior_observation = await db.get(SoundingObservation, prior.observation_identity)
                prior_station = (
                    stations.get(prior_observation.station_id) if prior_observation else None
                )
                if prior_station is None and prior_observation:
                    prior_station = await db.get(SoundingStation, prior_observation.station_id)
                if prior_station:
                    prior_region = _region(prior_station.latitude, prior_station.longitude)
            recent_profiles = list(
                (
                    await db.scalars(
                        select(SoundingObservation.profile)
                        .join(
                            DailyHuntChallenge,
                            DailyHuntChallenge.observation_identity == SoundingObservation.identity,
                        )
                        .where(
                            DailyHuntChallenge.challenge_day < next_day,
                            DailyHuntChallenge.challenge_day >= next_day - timedelta(days=14),
                        )
                    )
                ).all()
            )
            candidates = [
                item for item in observations if item.station_id not in recent_station_ids
            ]
            if not candidates:
                candidates = observations
            candidates.sort(
                key=lambda item: (
                    1
                    if prior_region
                    and _region(
                        stations[item.station_id].latitude, stations[item.station_id].longitude
                    )
                    == prior_region
                    else 0,
                    -_diversity_score(item.profile, recent_profiles),
                    *_quality_penalty(item),
                    -item.observed_at.timestamp(),
                    hashlib.sha256(f"{next_day}:{item.identity}".encode()).hexdigest(),
                )
            )
            selected = candidates[0]
            challenge_start, challenge_end = challenge_window(next_day)
            next_number = (
                int(
                    await db.scalar(
                        select(func.coalesce(func.max(DailyHuntChallenge.challenge_number), 0))
                    )
                    or 0
                )
                + 1
            )
            db.add(
                DailyHuntChallenge(
                    challenge_day=next_day,
                    challenge_number=next_number,
                    observation_identity=selected.identity,
                    starts_at=challenge_start,
                    ends_at=challenge_end,
                    scoring_version=SCORE_VERSION,
                    score_scale_miles=SCORE_SCALE_MILES,
                )
            )
            try:
                await db.commit()
                created += 1
            except IntegrityError:
                await db.rollback()
                # Another worker published first; the unique constraints make this safe to retry.
                continue
    return created


async def maintain_sounding_hunt(provider) -> None:
    if SOUNDING_QUEUE_LOCK.locked():
        return
    async with SOUNDING_QUEUE_LOCK:
        published = await replenish_challenge_queue()
        async with sessions() as db:
            upcoming = await db.scalar(
                select(func.count())
                .select_from(DailyHuntChallenge)
                .where(DailyHuntChallenge.challenge_day >= current_challenge_day())
            )
            candidates = await db.scalar(
                select(func.count())
                .select_from(SoundingObservation)
                .where(SoundingObservation.eligible.is_(True))
            )
        if int(upcoming or 0) < DAILY_QUEUE_DAYS:
            added = await _ingest_batch(provider)
            published += await replenish_challenge_queue()
            async with sessions() as db:
                upcoming = await db.scalar(
                    select(func.count())
                    .select_from(DailyHuntChallenge)
                    .where(DailyHuntChallenge.challenge_day >= current_challenge_day())
                )
                candidates = await db.scalar(
                    select(func.count())
                    .select_from(SoundingObservation)
                    .where(SoundingObservation.eligible.is_(True))
                )
            logger.info(
                "Sounding Hunt maintenance: ingested=%s candidates=%s published=%s queued=%s",
                added,
                int(candidates or 0),
                published,
                int(upcoming or 0),
            )
        if int(upcoming or 0) < 3 or int(candidates or 0) < 5:
            logger.warning(
                "Sounding Hunt verified pool is low: candidates=%s upcoming=%s",
                int(candidates or 0),
                int(upcoming or 0),
            )
