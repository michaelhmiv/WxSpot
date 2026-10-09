import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from wxspot.database import sessions
from wxspot.models import (
    DailyHuntChallenge,
    DailyHuntGuess,
    SoundingHuntPractice,
    SoundingIngestionStatus,
    SoundingObservation,
    SoundingStation,
)
from wxspot.providers.soundings import station_catalog
from wxspot.sounding_hunt import (
    _public_sounding,
    challenge_window,
    current_challenge_day,
    distance_miles,
    score_for_distance,
    streak_lengths,
)
from wxspot.sounding_hunt_ingestion import (
    is_conus_station,
    replenish_challenge_queue,
    sounding_distance,
    validate_candidate,
)


def guest(client, resume_key=None):
    response = client.post(
        "/auth/guest", json={} if resume_key is None else {"resume_key": resume_key}
    )
    assert response.status_code in (200, 201), response.text
    account = response.json()
    return account, {"Authorization": "Bearer " + account["access_token"]}


def test_wgs84_distance_scoring_and_numeric_boundaries():
    assert distance_miles(-80.0275, 32.895, -80.0275, 32.895) == 0
    assert distance_miles(180, 90, 180, 90) == 0
    assert distance_miles(0, 0, 1, 0) == pytest.approx(69.1707, abs=0.001)
    assert score_for_distance(0) == 5000
    assert score_for_distance(750) == 1839
    assert score_for_distance(100000) == 0
    with pytest.raises(ValueError):
        distance_miles(float("nan"), 0, 0, 0)
    with pytest.raises(ValueError):
        score_for_distance(-1)
    with pytest.raises(ValueError):
        score_for_distance(0, float("inf"))


def test_eastern_daily_identity_and_dst_windows():
    assert current_challenge_day(datetime(2026, 3, 8, 11, tzinfo=UTC)) == date(2026, 3, 7)
    assert current_challenge_day(datetime(2026, 3, 8, 12, 1, tzinfo=UTC)) == date(2026, 3, 8)
    assert current_challenge_day(datetime(2026, 11, 1, 12, 30, tzinfo=UTC)) == date(2026, 10, 31)
    assert current_challenge_day(datetime(2026, 11, 1, 13, tzinfo=UTC)) == date(2026, 11, 1)
    spring = challenge_window(date(2026, 3, 7))
    fall = challenge_window(date(2026, 10, 31))
    assert spring[1] - spring[0] == timedelta(hours=23)
    assert fall[1] - fall[0] == timedelta(hours=25)


def test_streaks_follow_challenge_dates_not_device_dates():
    completed = {date(2026, 10, 6), date(2026, 10, 7)}
    current, longest = streak_lengths(completed, datetime(2026, 10, 8, 13, tzinfo=UTC))
    assert (current, longest) == (2, 2)
    assert streak_lengths(set(), datetime(2026, 10, 8, 13, tzinfo=UTC)) == (0, 0)


def test_igra_station_state_and_contiguous_us_filter():
    row = list(" " * 90)
    for start, value in (
        (0, "USM00072208"),
        (12, " 32.8950"),
        (21, " -80.0275"),
        (31, "  13.3"),
        (38, "SC"),
        (41, "Charleston".ljust(30)),
        (72, "1973"),
        (77, "2026"),
        (82, " 01234"),
    ):
        row[start : start + len(value)] = value
    station = station_catalog("".join(row))[0]
    assert station["state"] == "SC"
    assert is_conus_station(station)
    assert not is_conus_station({**station, "state": "AK"})
    assert not is_conus_station({**station, "lat": 61.2})


def test_candidate_validation_requires_real_thermal_and_moisture_coverage():
    levels = [
        SimpleNamespace(
            pressure_hpa=1000 - index * 50,
            temperature_c=20 - index * 3 if index < 10 else None,
            dewpoint_c=15 - index * 3 if index < 6 else None,
            u_ms=5 if index < 4 else None,
            v_ms=2 if index < 4 else None,
        )
        for index in range(12)
    ]
    profile = SimpleNamespace(
        levels=levels,
        sampled_point=[-80, 33],
        valid_time=datetime(2026, 10, 8, 12, tzinfo=UTC),
        surface_pressure_hpa=1000,
    )
    accepted, report, reason = validate_candidate(profile)
    assert accepted and reason is None
    assert report["temperature_count"] == 10 and report["humidity_count"] == 6
    profile.levels[0].dewpoint_c = None
    profile.levels[1].dewpoint_c = None
    accepted, _, reason = validate_candidate(profile)
    assert not accepted and reason == "Fewer than 6 usable humidity observations"
    profile.levels[0].dewpoint_c = 30
    profile.levels[1].dewpoint_c = 15
    accepted, _, reason = validate_candidate(profile)
    assert not accepted and reason == "Dew point measurements are physically implausible"


def test_profile_diversity_compares_measured_thermodynamic_layers():
    ordinary = {
        "levels": [
            {
                "pressure_hpa": pressure,
                "temperature_c": 20 - index * 8,
                "dewpoint_c": 15 - index * 9,
            }
            for index, pressure in enumerate((1000, 850, 700, 500, 300))
        ]
    }
    similar = {"levels": [dict(level) for level in ordinary["levels"]]}
    different = {
        "levels": [
            {"pressure_hpa": pressure, "temperature_c": -20, "dewpoint_c": -35}
            for pressure in (1000, 850, 700, 500, 300)
        ]
    }
    assert sounding_distance(ordinary, similar) == 0
    assert sounding_distance(ordinary, different) > 0.8


def test_public_chart_projection_does_not_serialize_private_answer_fields():
    private_profile = {
        "identity": "candidate-hash",
        "station": "USM00072208",
        "station_name": "Charleston International Airport",
        "sampled_point": [-80.0275, 32.895],
        "terrain_m_msl": 13.3,
        "source": "NOAA / NCEI IGRA 2.2",
        "metadata": {"source_url": "https://example.invalid/USM00072208"},
        "surface_pressure_hpa": 1006.2,
        "levels": [
            {
                "pressure_hpa": 1000,
                "temperature_c": 24,
                "dewpoint_c": 20,
                "height_m_msl": 20,
                "u_ms": 4,
                "v_ms": -2,
                "quality": ["temperature QC retained"],
            }
        ],
    }
    observation = SimpleNamespace(
        profile=private_profile,
        observed_at=datetime(2026, 10, 8, 12, tzinfo=UTC),
    )
    public = _public_sounding(observation)
    serialized = str(public)
    assert set(public) == {"observation_time", "surface_pressure_hpa", "levels"}
    assert "USM00072208" not in serialized
    assert "Charleston" not in serialized
    assert "sampled_point" not in serialized
    assert "source_url" not in serialized
    assert "quality" not in public["levels"][0]
    assert public["levels"][0]["height_m_agl"] == pytest.approx(6.7)
    assert "height_m_msl" not in public["levels"][0]


def _seed_game(client):
    today = current_challenge_day()
    starts_at, ends_at = challenge_window(today)
    profile = {
        "identity": "a" * 64,
        "kind": "observed",
        "source": "NOAA / NCEI IGRA 2.2",
        "valid_time": datetime.now(UTC).isoformat(),
        "nominal_time": datetime.now(UTC).isoformat(),
        "station": "USM00072208",
        "station_name": "Charleston International Airport",
        "sampled_point": [-80.0275, 32.895],
        "terrain_m_msl": 13.3,
        "surface_pressure_hpa": 1006.2,
        "levels": [
            {
                "pressure_hpa": 1000 - i * 100,
                "temperature_c": 24 - i * 5,
                "dewpoint_c": 20 - i * 6,
                "height_m_msl": 20 + i * 1000,
                "u_ms": 4 + i,
                "v_ms": -2 + i,
                "quality": [],
            }
            for i in range(5)
        ],
        "metadata": {"source_url": "https://example.invalid/USM00072208"},
    }
    practice_profile = {
        **profile,
        "identity": "b" * 64,
        "valid_time": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
        "sampled_point": [-97.44, 35.22],
        "station": "USM00072357",
        "station_name": "Norman",
    }

    async def seed():
        async with sessions() as db:
            station = SoundingStation(
                station_id="USM00072208",
                name="Charleston International Airport",
                state="SC",
                latitude=32.895,
                longitude=-80.0275,
                elevation_m=13.3,
                source_version="IGRA 2.2",
            )
            practice_station = SoundingStation(
                station_id="USM00072357",
                name="Norman",
                state="OK",
                latitude=35.22,
                longitude=-97.44,
                elevation_m=345,
                source_version="IGRA 2.2",
            )
            db.add_all([station, practice_station])
            await db.flush()
            challenge_obs = SoundingObservation(
                identity="a" * 64,
                station_id=station.station_id,
                observed_at=datetime.fromisoformat(profile["valid_time"]),
                nominal_time=datetime.fromisoformat(profile["nominal_time"]),
                profile=profile,
                validation={"wind_count": 5, "level_count": 5},
                source_revision="revision-a",
                eligible=True,
            )
            practice_obs = SoundingObservation(
                identity="b" * 64,
                station_id=practice_station.station_id,
                observed_at=datetime.fromisoformat(practice_profile["valid_time"]),
                nominal_time=None,
                profile=practice_profile,
                validation={"wind_count": 5, "level_count": 5},
                source_revision="revision-b",
                eligible=True,
            )
            db.add_all([challenge_obs, practice_obs])
            await db.flush()
            db.add(
                DailyHuntChallenge(
                    challenge_day=today,
                    challenge_number=1,
                    observation_identity=challenge_obs.identity,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    scoring_version="exp-distance-v1",
                    score_scale_miles=750,
                )
            )
            await db.commit()

    asyncio.run(seed())


def test_daily_publication_uses_unused_verified_profiles_and_is_idempotent(client):
    observed = datetime.now(UTC) - timedelta(days=2)

    async def seed_candidates():
        async with sessions() as db:
            for index, (station_id, name, state, latitude, longitude) in enumerate(
                (
                    ("USM00072208", "Charleston", "SC", 32.895, -80.0275),
                    ("USM00072357", "Norman", "OK", 35.22, -97.44),
                )
            ):
                station = SoundingStation(
                    station_id=station_id,
                    name=name,
                    state=state,
                    latitude=latitude,
                    longitude=longitude,
                    elevation_m=13.3 + index,
                    source_version="IGRA 2.2",
                )
                db.add(station)
                await db.flush()
                profile = {
                    "sampled_point": [longitude, latitude],
                    "terrain_m_msl": 13.3 + index,
                    "surface_pressure_hpa": 1000,
                    "levels": [],
                }
                db.add(
                    SoundingObservation(
                        identity=chr(97 + index) * 64,
                        station_id=station_id,
                        observed_at=observed - timedelta(hours=index),
                        nominal_time=observed,
                        profile=profile,
                        validation={"wind_count": 4, "level_count": 20},
                        source_revision=f"revision-{index}",
                        eligible=True,
                    )
                )
            await db.commit()

    asyncio.run(seed_candidates())
    assert asyncio.run(replenish_challenge_queue()) == 2
    assert asyncio.run(replenish_challenge_queue()) == 0

    async def verify():
        async with sessions() as db:
            rows = list((await db.scalars(select(DailyHuntChallenge))).all())
            assert len(rows) == 2
            assert len({row.observation_identity for row in rows}) == 2
            assert {row.scoring_version for row in rows} == {"exp-distance-v1"}
            assert all(row.score_scale_miles == 750 for row in rows)
            assert len({row.challenge_day for row in rows}) == 2

    asyncio.run(verify())


def test_daily_answer_reveal_duplicate_submission_and_practice_isolation(client):
    _seed_game(client)
    account, headers = guest(client)
    today = current_challenge_day().isoformat()
    assert client.get("/game/sounding-hunt/today").status_code == 401
    challenge = client.get("/game/sounding-hunt/today", headers=headers)
    assert challenge.status_code == 200, challenge.text
    pre_guess = challenge.json()
    assert pre_guess["observation_time"].endswith("+00:00")
    assert pre_guess["completed"] is False
    assert not any(
        key in pre_guess
        for key in ("station", "station_id", "station_name", "sampled_point", "metadata")
    )
    assert "USM00072208" not in challenge.text and "-80.0275" not in challenge.text
    assert pre_guess["levels"][0]["height_m_agl"] == pytest.approx(6.7)
    assert "height_m_msl" not in challenge.text
    reviewed = client.get(f"/game/sounding-hunt/daily/{today}", headers=headers)
    assert reviewed.status_code == 200 and "USM00072208" not in reviewed.text
    assert (
        client.get(f"/game/sounding-hunt/daily/{today}/result", headers=headers).status_code
        == 403
    )

    submitted = client.post(
        f"/game/sounding-hunt/daily/{today}/guess",
        headers=headers,
        json={"latitude": 33.0, "longitude": -80.0},
    )
    assert submitted.status_code == 201, submitted.text
    result = submitted.json()
    assert result["score"] <= 5000 and result["distance_miles"] > 0
    assert result["answer"]["station_id"] == "USM00072208"
    assert result["answer"]["station_name"] == "Charleston International Airport"
    assert result["answer"]["source_version"] == "IGRA 2.2"
    assert result["insights"] and any("Similar soundings" in item for item in result["insights"])
    duplicate = client.post(
        f"/game/sounding-hunt/daily/{today}/guess",
        headers=headers,
        json={"latitude": 33.0, "longitude": -80.0},
    )
    assert duplicate.status_code == 409

    board = client.get(f"/game/sounding-hunt/leaderboard/{today}", headers=headers)
    assert board.status_code == 200 and board.json()["player_rank"] == 1
    assert "latitude" not in board.text and "longitude" not in board.text
    resumed, resumed_headers = guest(client, account["resume_key"])
    assert resumed["user_id"] == account["user_id"]
    assert client.get("/game/sounding-hunt/today", headers=resumed_headers).json()["completed"]

    practice = client.post("/game/sounding-hunt/practice", headers=headers)
    assert practice.status_code == 201, practice.text
    assert practice.json()["observation_time"] < pre_guess["observation_time"]
    practice_id = practice.json()["practice_id"]
    assert client.get(
        f"/game/sounding-hunt/practice/{practice_id}/result", headers=headers
    ).status_code == 404
    practice_result = client.post(
        f"/game/sounding-hunt/practice/{practice_id}/guess",
        headers=headers,
        json={"latitude": 35.22, "longitude": -97.44},
    )
    assert practice_result.status_code == 201 and practice_result.json()["score"] == 5000

    async def verify_practice_is_unranked():
        async with sessions() as db:
            ranked = list(
                (
                    await db.scalars(
                        select(DailyHuntGuess).where(
                            DailyHuntGuess.user_id == uuid.UUID(account["user_id"])
                        )
                    )
                ).all()
            )
            practice_rows = list(
                (
                    await db.scalars(
                        select(SoundingHuntPractice).where(
                            SoundingHuntPractice.user_id == uuid.UUID(account["user_id"])
                        )
                    )
                ).all()
            )
            assert len(ranked) == 1 and len(practice_rows) == 1
            assert practice_rows[0].score_scale_miles == 750
            assert await db.scalar(select(SoundingIngestionStatus.station_id)) is None

    asyncio.run(verify_practice_is_unranked())


def test_daily_submission_rejects_coordinates_outside_guess_bounds(client):
    _seed_game(client)
    _, headers = guest(client)
    today = current_challenge_day().isoformat()
    response = client.post(
        f"/game/sounding-hunt/daily/{today}/guess",
        headers=headers,
        json={"latitude": 61.2, "longitude": -149.9},
    )
    assert response.status_code == 422
