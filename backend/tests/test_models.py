from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest
from pyproj import CRS, Geod, Transformer

from wxspot.providers.forecast import ModelProvider, forecast_hours, parse_index
from wxspot.providers.grids import PreparedGrid
from wxspot.providers.model_grids import accumulate_nonoverlapping, earth_winds
from wxspot.weather import SourceError


def test_model_horizon_never_inserts_gfs_hours_or_extends_ordinary_hrrr():
    ordinary = datetime(2026, 10, 7, 17, tzinfo=UTC)
    extended = ordinary.replace(hour=18)
    assert forecast_hours("hrrr", ordinary) == list(range(19))
    assert forecast_hours("hrrr", extended) == list(range(49))
    gfs = forecast_hours("gfs", extended)
    assert gfs[-1] == 168 and 120 in gfs and 121 not in gfs and 122 not in gfs and 123 in gfs
    provider = ModelProvider(None, None)
    with pytest.raises(SourceError):
        provider.parse_identity("model:gfs:20261007T1800Z:121:temperature:v1")
    with pytest.raises(SourceError):
        provider.parse_identity("model:hrrr:20261007T1700Z:048:temperature:v1")


def test_precipitation_totals_reject_gaps_overlaps_and_negative_values():
    def grid(start, end, value):
        return PreparedGrid(
            np.array([[value, np.nan]], dtype=np.float32),
            "EPSG:4326",
            -80,
            33,
            1,
            -1,
            "precip_1h",
            {"start_step": start, "end_step": end},
        )

    first, last = grid(0, 6, 1.5), grid(6, 9, 2.5)
    total = accumulate_nonoverlapping([last, first], 9)
    assert total.values[0, 0] == 4 and np.isnan(total.values[0, 1])
    assert first.metadata["end_step"] == 6 and first.values[0, 0] == 1.5
    for invalid in ([first, grid(7, 9, 2)], [first, grid(3, 9, 2)], [first, grid(6, 9, -1)]):
        with pytest.raises(SourceError):
            accumulate_nonoverlapping(invalid, 9)


def test_rotated_hrrr_wind_matches_independent_geodesic_basis():
    crs = CRS.from_proj4(
        "+proj=lcc +lat_1=38.5 +lat_2=38.5 +lat_0=38.5 +lon_0=-97.5 +R=6371229 +units=m"
    )
    lon, lat = -79.94, 32.78
    x, y = Transformer.from_crs(4326, crs, always_xy=True).transform(lon, lat)
    grid = PreparedGrid(
        np.ones((1, 1), dtype=np.float32),
        crs.to_wkt(),
        x,
        y,
        3000,
        3000,
        "wind",
        {"grid_relative_winds": True},
    )
    u, v = earth_winds(replace(grid, values=np.zeros((1, 1), dtype=np.float32)), grid)
    north_lon, north_lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(x, y + 1)
    bearing, _, _ = Geod(a=6371229, b=6371229).inv(lon, lat, north_lon, north_lat)
    assert u[0, 0] == pytest.approx(np.sin(np.radians(bearing)), abs=1e-5)
    assert v[0, 0] == pytest.approx(np.cos(np.radians(bearing)), abs=1e-5)


def test_index_offsets_are_exact_and_never_select_a_record_number_as_a_variable():
    rows = parse_index(
        "1:0:d=2026100718:TMP:2 m above ground:3 hour fcst:\n"
        "2:100:d=2026100718:APCP:surface:0-3 hour acc fcst:\n"
        "3:200:d=2026100718:CAPE:surface:3 hour fcst:\n"
    )
    assert rows[0]["end"] == 99 and rows[1]["end"] == 199 and rows[2]["end"] is None
    assert rows[1]["mnemonic"] == "APCP" and rows[1]["description"] == "0-3 hour acc fcst"
