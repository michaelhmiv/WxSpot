"""Published MetPy references and independently computed geometry/kinematics/QC."""

import math
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from pydantic import ValidationError

from wxspot.providers.grids import PreparedGrid
from wxspot.providers.soundings import assemble_column, igra_launch, parse_igra
from wxspot.sounding_calculations import calculate
from wxspot.sounding_contracts import SoundingLevel, SoundingProfile, SoundingSelection


def reference_profile():
    rows = []
    path = Path(__file__).parent / "fixtures/sounding_reference.txt"
    for line in path.read_text().splitlines()[7:]:
        if not line.strip():
            break
        try:
            p, z, t, td = [float(line[i : i + 7]) for i in (0, 7, 14, 21)]
            direction, speed = [float(line[i : i + 7]) for i in (42, 49)]
        except ValueError:
            continue
        rows.append(
            SoundingLevel(
                pressure_hpa=p,
                height_m_msl=z,
                temperature_c=t,
                dewpoint_c=td,
                u_ms=-speed * 0.5144444444 * math.sin(math.radians(direction)),
                v_ms=-speed * 0.5144444444 * math.cos(math.radians(direction)),
            )
        )
    now = datetime(2011, 5, 22, 12, tzinfo=UTC)
    return SoundingProfile(
        identity="metpy-OUN-20110522",
        kind="observed",
        source="MetPy v1.7.1 reference",
        valid_time=now,
        fetched_at=now,
        sampled_point=[-97.44, 35.22],
        terrain_m_msl=345,
        surface_pressure_hpa=966,
        method="Official OUN reference",
        levels=rows,
    )


def test_published_norman_reference_values_and_real_plot_guides():
    # MetPy official Sounding_Calculations.html independently publishes these values.
    # Its display CIN uses an older parcel helper; accept a 1 J/kg numerical tolerance.
    result = calculate(reference_profile())
    for name, expected, tolerance in (
        ("sb_cape", 3297.18, 2),
        ("sb_cin", -128.30, 1),
        ("lcl_pressure", 949.00, 1),
        ("lfc_pressure", 735.84, 1),
        ("el_pressure", 194.83, 1),
    ):
        assert result.metrics[name].value == pytest.approx(expected, abs=tolerance)
    assert result.vectors["rm"][0] * 1.943844 == pytest.approx(21.85, abs=0.1)
    assert result.vectors["rm"][1] * 1.943844 == pytest.approx(4.55, abs=0.1)
    assert set(result.guides) == {"dry", "moist", "mixing"}
    assert len(result.parcel_trace) > 50
    assert result.metrics["lcl_height"].value > 0
    for parcel in ("ml100", "mu300"):
        selected = calculate(reference_profile(), parcel)
        assert selected.parcel == parcel and selected.parcel_trace != result.parcel_trace
        assert selected.metrics[parcel + "_cape"].value > 0


def test_missing_moisture_is_null_but_valid_wind_diagnostics_survive():
    profile = reference_profile()
    profile.levels[10].dewpoint_c = None
    result = calculate(profile)
    assert result.metrics["sb_cape"].value is None
    assert "Moisture" in result.metrics["sb_cape"].reason
    assert result.metrics["shear_0_1km"].value is not None
    assert not result.parcel_trace
    assert "NaN" not in result.model_dump_json()


def test_stable_complete_profile_can_legitimately_have_zero_cape():
    profile = reference_profile()
    for level in profile.levels:
        level.temperature_c = 20 + 30 * math.log(level.pressure_hpa / 966)
        level.dewpoint_c = level.temperature_c - 10
    result = calculate(profile)
    assert result.metrics["sb_cape"].value == 0
    assert result.metrics["sb_cape"].quality == "valid"
    assert result.markers["lfc"]["pressure_hpa"] is None


def test_custom_motion_srh_and_shear_match_hodograph_area_by_hand():
    profile = reference_profile()
    profile.levels = [
        SoundingLevel(
            pressure_hpa=1000 - i * 65,
            temperature_c=25 - i * 6,
            dewpoint_c=20 - i * 6,
            height_m_msl=345 + i * 1000,
            u_ms=float(np.interp(i, [0, 1, 3, 6, 12], [0, 10, 10, 20, 30])),
            v_ms=float(np.interp(i, [0, 1, 3, 6, 12], [0, 0, 10, 10, 10])),
        )
        for i in range(14)
    ]
    profile.surface_pressure_hpa = 1000
    result = calculate(profile, motion="custom", storm_u=5, storm_v=5)
    assert result.metrics["shear_0_1km"].value == pytest.approx(10)
    assert result.metrics["shear_0_3km"].value == pytest.approx(math.sqrt(200))
    # Polygon contribution (u1-cx)(v0-cy) - (u0-cx)(v1-cy).
    assert result.metrics["srh_0_1km"].value == pytest.approx(-50)
    assert result.metrics["srh_0_3km"].value == pytest.approx(-100)
    changed = calculate(profile, motion="custom", storm_u=0, storm_v=5)
    assert result.identity != changed.identity
    assert changed.metrics["srh_0_3km"].value != result.metrics["srh_0_3km"].value


def test_high_terrain_column_never_exposes_below_ground_levels():
    fields = {}

    def add(name, level, value):
        fields[name, level] = PreparedGrid(
            np.array([[value]], dtype=np.float32),
            "EPSG:4326",
            -80,
            33,
            0.25,
            -0.25,
            "",
            {"grid_relative_winds": False},
        )

    for name, level, value in (
        ("PRES", "surface", 85000),
        ("HGT", "surface", 1500),
        ("TMP", "2 m above ground", 15),
        ("DPT", "2 m above ground", 8),
        ("UGRD", "10 m above ground", 3),
        ("VGRD", "10 m above ground", 4),
    ):
        add(name, level, value)
    for pressure, height in ((1000, 0), (900, 900), (800, 2000), (750, 2500)):
        for name, value in (("TMP", 10), ("DPT", 5), ("HGT", height), ("UGRD", 3), ("VGRD", 4)):
            add(name, f"{pressure} mb", value)
    profile = assemble_column(
        fields,
        {
            "model": "gfs",
            "lon": -80,
            "lat": 33,
            "run_time": "2026-10-08T06:00:00+00:00",
            "forecast_hour": 3,
        },
        100,
        1,
    )
    assert [x.pressure_hpa for x in profile.levels] == [850, 800, 750]
    assert profile.levels[0].height_m_msl == 1510
    assert profile.levels[0].u_ms == 3
    assert calculate(profile).metrics["sb_cape"].value is None


def header(count=2):
    data = list(" " * 90)
    for start, value in (
        (0, "#USM00072208"),
        (13, "2026"),
        (18, "10"),
        (21, "08"),
        (24, "00"),
        (27, "2310"),
        (32, f"{count:4d}"),
        (55, " 328950"),
        (63, " -800275"),
    ):
        data[start : start + len(value)] = value
    return "".join(data) + "\n"


def test_igra_previous_day_launch_missing_qc_and_meteorological_wind():
    record = list(" " * 51)
    for start, value in (
        (0, "11"),
        (9, "100500"),
        (16, "-9999"),
        (22, "  253"),
        (28, "-8888"),
        (34, "   50"),
        (40, "  270"),
        (46, "  100"),
        (27, "A"),
    ):
        record[start : start + len(value)] = value
    second = record.copy()
    second[0:2] = "20"
    second[9:15] = " 90000"
    second[16:21] = " 1000"
    second[22:27] = "-8888"
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("station.txt", header() + "".join(record) + "\n" + "".join(second) + "\n")
    profiles = parse_igra(
        output.getvalue(), {"id": "USM00072208", "name": "Charleston", "elevation_m": 13.3}
    )
    launch = profiles[0]
    assert launch.valid_time == datetime(2026, 10, 7, 23, 10, tzinfo=UTC)
    assert launch.nominal_time == datetime(2026, 10, 8, tzinfo=UTC)
    assert launch.sampled_point == [-80.0275, 32.895]
    assert launch.levels[0].temperature_c == 25.3 and launch.levels[0].dewpoint_c == 20.3
    assert launch.levels[0].height_m_msl == 13.3
    assert launch.levels[0].u_ms == pytest.approx(10) and abs(launch.levels[0].v_ms) < 1e-10
    assert "temperature climatology tier A" in launch.levels[0].quality
    assert launch.levels[1].temperature_c is None
    assert any("QC removed" in flag for flag in launch.levels[1].quality)
    missing = header().replace("2310", "9999")
    missing_launch, _, missing_quality = igra_launch(missing)
    assert missing_launch == datetime(2026, 10, 8, tzinfo=UTC)
    assert missing_quality == ["Release time missing; nominal observation time shown"]


def test_contract_rejects_nonfinite_profiles_duplicates_and_fake_forecast_hours():
    with pytest.raises(ValidationError):
        SoundingLevel(pressure_hpa=800, temperature_c=float("nan"))
    profile = reference_profile()
    duplicate = profile.model_dump()
    duplicate["levels"] = [duplicate["levels"][0]] * 2
    with pytest.raises(ValidationError):
        SoundingProfile.model_validate(duplicate)
    for model, hour, run in (
        ("gfs", 121, "2026-10-08T06:00:00Z"),
        ("hrrr", 48, "2026-10-08T07:00:00Z"),
    ):
        with pytest.raises(ValidationError):
            SoundingSelection(
                kind="forecast", lat=33, lon=-80, model=model, forecast_hour=hour, run_time=run
            )
