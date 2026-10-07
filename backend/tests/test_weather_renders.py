from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pyproj import Geod

from wxspot.providers.mrms import MRMS_PRODUCTS, _frame_time, _freshness_state
from wxspot.providers.nexrad import PRODUCTS, PolarGrid, _key_time
from wxspot.providers.render import RANGE_FOLD_COLOR, SRM_LEVEL_COLORS, colorize, legend_png
from wxspot.weather_contracts import WeatherSelection


def test_mrms_zero_is_valid_and_sentinels_are_transparent():
    rgba = colorize(
        np.asarray([[0.0, -1.0, -3.0]], dtype=np.float32),
        "precip_rate",
        missing=(-1.0, -3.0),
    )

    assert rgba[0, 0, 3] == 255
    assert rgba[0, 1, 3] == 0
    assert rgba[0, 2, 3] == 0


def test_range_fold_is_distinct_from_missing_data():
    rgba = colorize(
        np.asarray([[np.nan, np.nan, 8.0]], dtype=np.float32),
        "velocity",
        range_fold=np.asarray([[False, True, False]]),
    )

    assert rgba[0, 0, 3] == 0
    assert tuple(rgba[0, 1]) == (*RANGE_FOLD_COLOR, 255)
    assert rgba[0, 2, 3] == 255


def test_storm_relative_velocity_uses_official_discrete_levels_and_knots():
    rgba = colorize(
        np.asarray([[1.0, 8.0, 14.0, 15.0, np.nan]], dtype=np.float32),
        "storm_relative_velocity",
        range_fold=np.asarray([[False, False, False, True, False]]),
    )

    assert PRODUCTS["storm_relative_velocity"]["units"] == "kt"
    assert tuple(rgba[0, 0]) == (*SRM_LEVEL_COLORS[1], 255)
    assert tuple(rgba[0, 1]) == (*SRM_LEVEL_COLORS[8], 255)
    assert tuple(rgba[0, 2]) == (*SRM_LEVEL_COLORS[14], 255)
    assert tuple(rgba[0, 3]) == (*RANGE_FOLD_COLOR, 255)
    assert rgba[0, 4, 3] == 0
    assert legend_png("storm_relative_velocity").startswith(b"\x89PNG\r\n\x1a\n")
    dynamic_legend = legend_png(
        "storm_relative_velocity",
        levels_kt=(-64, -50, -36, -26, -20, -10, -1, 0, 10, 20, 26, 36, 50, 64),
    )
    assert Image.open(BytesIO(dynamic_legend)).size == (512, 58)


@pytest.mark.parametrize(
    (
        "filename",
        "product",
        "tilt",
        "units",
        "max_range_km",
        "gate_spacing_km",
        "valid_time",
        "expected_range",
    ),
    [
        (
            "KOUN_SDUS54_N0QTLX_201305202016",
            "reflectivity",
            "N0Q",
            "dBZ",
            460.0,
            0.999,
            datetime(2013, 5, 20, 20, 16, 49, tzinfo=UTC),
            (-20.0, 68.0),
        ),
        (
            "KOUN_SDUS54_N0UTLX_201305202016",
            "velocity",
            "N0U",
            "m/s",
            300.0,
            0.999 * 0.25,
            datetime(2013, 5, 20, 20, 17, 18, tzinfo=UTC),
            (-45.0, 46.5),
        ),
        (
            "KOUN_SDUS54_N0STLX_201305202016",
            "storm_relative_velocity",
            "N0S",
            "kt",
            230.0,
            0.999,
            datetime(2013, 5, 20, 20, 17, 19, tzinfo=UTC),
            (1.0, 14.0),
        ),
        (
            "KOUN_SDUS84_N0CTLX_201305202016",
            "correlation_coefficient",
            "N0C",
            "unitless",
            300.0,
            0.999 * 0.25,
            datetime(2013, 5, 20, 20, 17, 22, tzinfo=UTC),
            (0.2083333333, 1.0516666667),
        ),
        (
            "KOUN_SDUS84_N0XTLX_201305202016",
            "differential_reflectivity",
            "N0X",
            "dB",
            300.0,
            0.999 * 0.25,
            datetime(2013, 5, 20, 20, 17, 22, tzinfo=UTC),
            (-7.875, 7.9375),
        ),
        (
            "KOUN_SDUS84_N0KTLX_201305202016",
            "specific_differential_phase",
            "N0K",
            "degrees/km",
            300.0,
            0.999 * 0.25,
            datetime(2013, 5, 20, 20, 17, 22, tzinfo=UTC),
            (-2.05, 6.35),
        ),
    ],
)
def test_real_level3_product_samples_decode_units_ranges_and_renders(
    filename,
    product,
    tilt,
    units,
    max_range_km,
    gate_spacing_km,
    valid_time,
    expected_range,
):
    fixture = Path(__file__).parent / "fixtures" / "nexrad_level3" / filename
    key_time = datetime(2013, 5, 20, 20, 16, tzinfo=UTC)

    grid = PolarGrid.decode(fixture.read_bytes(), "KTLX", product, tilt, key_time)

    assert PRODUCTS[product]["units"] == units
    assert grid.valid_time == valid_time
    assert grid.max_range_km == max_range_km
    assert grid.gate_scale_km == pytest.approx(gate_spacing_km)
    assert grid.azimuth_centers.size == 360
    assert grid.values.shape[0] == 360
    assert grid.site == "KTLX"
    assert grid.longitude == pytest.approx(-97.278)
    assert grid.latitude == pytest.approx(35.333)
    valid_values = grid.values[np.isfinite(grid.values)]
    assert float(valid_values.min()) == pytest.approx(expected_range[0])
    assert float(valid_values.max()) == pytest.approx(expected_range[1])

    image = Image.open(BytesIO(grid.image([-98.5, 34.3, -96.0, 36.3], 64, 64)))
    assert image.size == (64, 64)
    assert image.getchannel("A").getbbox() is not None

    if product == "storm_relative_velocity":
        assert grid.storm_relative_levels_kt == (
            -64.0,
            -50.0,
            -36.0,
            -26.0,
            -20.0,
            -10.0,
            -1.0,
            0.0,
            10.0,
            20.0,
            26.0,
            36.0,
            50.0,
            64.0,
        )
        assert grid.storm_motion_speed_kt == pytest.approx(27.1)
        assert grid.storm_motion_direction_deg == pytest.approx(236.1)


def test_mrms_inventory_product_levels_and_key_timestamps():
    assert MRMS_PRODUCTS["reflectivity"][0].endswith("_00.50")
    assert MRMS_PRODUCTS["precip_rate"][0].endswith("_00.00")
    assert MRMS_PRODUCTS["precip_1h"][0].endswith("_00.00")
    assert _frame_time(
        "CONUS/PrecipRate_00.00/20261007/MRMS_PrecipRate_00.00_20261007-143012.grib2.gz"
    ) == datetime(2026, 10, 7, 14, 30, 12, tzinfo=UTC)


def test_mrms_staleness_threshold_matches_each_product_cadence():
    now = datetime(2026, 10, 7, 16, 0, tzinfo=UTC)

    assert _freshness_state("reflectivity", now - timedelta(minutes=16), now) == "source_delayed"
    assert _freshness_state("precip_1h", now - timedelta(minutes=15), now) == "ready"
    assert _freshness_state("precip_3h", now - timedelta(minutes=90), now) == "ready"
    assert _freshness_state("precip_24h", now.replace(hour=13, minute=59), now) == "source_delayed"


def test_nexrad_inventory_timestamp_requires_matching_site_and_product_code():
    key = "TLX_N0Q_2026_10_07_14_30_12"

    assert _key_time(key, "KTLX", "N0Q") == datetime(2026, 10, 7, 14, 30, 12, tzinfo=UTC)
    assert _key_time(key, "KOUN", "N0Q") is None
    assert _key_time(key, "KTLX", "N0U") is None


def test_mrms_source_does_not_require_a_station_but_local_level3_does():
    national = WeatherSelection(
        source_type="radar",
        source_id="noaa-mrms",
        product_id="reflectivity",
    )
    assert national.site is None

    try:
        WeatherSelection(
            source_type="radar",
            source_id="noaa-nexrad-level3",
            product_id="reflectivity",
        )
    except ValueError as exc:
        assert "explicit site" in str(exc)
    else:
        raise AssertionError("Level III station selections must name a site")


def test_polar_grid_uses_geographic_azimuth_and_keeps_folded_gate():
    grid = PolarGrid(
        site="KTLX",
        product="velocity",
        code="N0U",
        valid_time=datetime(2026, 10, 7, 14, 30, tzinfo=UTC),
        elevation=0.5,
        longitude=0.0,
        latitude=0.0,
        max_range_km=4.0,
        azimuth_centers=np.asarray([0.0, 90.0, 180.0, 270.0]),
        values=np.asarray(
            [[1, 2, 3, 4], [np.nan, 5, 6, 7], [8, 9, 10, 11], [12, 13, 14, 15]],
            dtype=np.float32,
        ),
        range_fold=np.asarray([[False] * 4, [True, False, False, False], [False] * 4, [False] * 4]),
    )

    values, valid, folded = grid.sample(np.asarray([0.008]), np.asarray([0.0]))

    assert valid.tolist() == [True]
    assert np.isnan(values[0])
    assert folded.tolist() == [True]


def test_polar_grid_respects_the_first_range_bin_offset():
    grid = PolarGrid(
        site="KTLX",
        product="reflectivity",
        code="N0Q",
        valid_time=datetime(2026, 10, 7, 14, 30, tzinfo=UTC),
        elevation=0.5,
        longitude=0.0,
        latitude=0.0,
        max_range_km=1.25,
        azimuth_centers=np.asarray([0.0, 90.0, 180.0, 270.0]),
        values=np.ones((4, 4), dtype=np.float32),
        range_fold=np.zeros((4, 4), dtype=bool),
        first_gate_index=1,
        gate_scale_km=0.25,
    )

    geod = Geod(ellps="WGS84")
    before_first, _, _ = geod.fwd(0.0, 0.0, 90.0, 100.0)
    first_gate, _, _ = geod.fwd(0.0, 0.0, 90.0, 400.0)
    values, valid, _ = grid.sample(np.asarray([before_first, first_gate]), np.asarray([0.0, 0.0]))

    assert valid.tolist() == [False, True]
    assert np.isnan(values[0])
    assert values[1] == 1.0
