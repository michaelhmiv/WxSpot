"""Validated GRIB geometry, physical units, accumulation semantics and earth-relative winds."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
from pyproj import CRS, Proj, Transformer

from wxspot.providers.grib_client import isolated_grib
from wxspot.providers.grids import PreparedGrid
from wxspot.weather import SourceError


def normalize_longitude(value):
    return (value + 180) % 360 - 180


def decode_model_message(content, run, hour, mnemonic, level):
    values, fields = isolated_grib(content)
    get = lambda key: fields[key]  # noqa: E731
    actual_run = datetime.strptime(
        f"{get('dataDate'):08d}{get('dataTime'):04d}", "%Y%m%d%H%M"
    ).replace(tzinfo=UTC)
    if actual_run != run or get("endStep") != hour or get("stepUnits") != 1:
        raise SourceError("source_unavailable", "Model run/hour/step units did not match.")
    expected = {
        "REFC": ("atmosphere", 0, "dB"),
        "GUST": ("surface", 0, "m s**-1"),
        "TMP": ("heightAboveGround", 2, "K"),
        "DPT": ("heightAboveGround", 2, "K"),
        "UGRD": ("heightAboveGround", 10, "m s**-1"),
        "VGRD": ("heightAboveGround", 10, "m s**-1"),
        "APCP": ("surface", 0, "kg m**-2"),
        "CAPE": ("surface", 0, "J kg**-1"),
        "CIN": ("surface", 0, "J kg**-1"),
        "PWAT": ("atmosphereSingleLayer", 0, "kg m**-2"),
    }
    short_names = {
        "REFC": "refc",
        "GUST": "gust",
        "TMP": "2t",
        "DPT": "2d",
        "UGRD": "10u",
        "VGRD": "10v",
        "APCP": "tp",
        "CAPE": "cape",
        "CIN": "cin",
        "PWAT": "pwat",
    }
    if mnemonic in short_names and get("shortName") != short_names[mnemonic]:
        raise SourceError("source_unavailable", "GRIB variable does not match its requested field.")
    if (
        mnemonic in expected
        and (get("typeOfLevel"), get("level"), get("units")) != expected[mnemonic]
    ):
        raise SourceError(
            "source_unavailable", "Model field level or physical units did not match."
        )
    nx, ny = int(get("Nx")), int(get("Ny"))
    if nx * ny > 4_000_000 or get("alternativeRowScanning") or get("jPointsAreConsecutive"):
        raise SourceError("source_unavailable", "Model geometry exceeds supported bounds.")
    values[values == get("missingValue")] = np.nan
    lon0, lat0 = (
        normalize_longitude(get("longitudeOfFirstGridPointInDegrees")),
        get("latitudeOfFirstGridPointInDegrees"),
    )
    i_sign = -1 if get("iScansNegatively") else 1
    j_sign = 1 if get("jScansPositively") else -1
    if get("gridType") == "regular_ll":
        crs = CRS.from_epsg(4326)
        dx = i_sign * get("iDirectionIncrementInDegrees")
        dy = j_sign * get("jDirectionIncrementInDegrees")
        # Normalize and sort the published 0..360 global grid before the CONUS subset.
        lons = normalize_longitude(lon0 + np.arange(nx) * dx)
        order = np.argsort(lons)
        values, lons = values[:, order], lons[order]
        lats = lat0 + np.arange(ny) * dy
        cols = np.flatnonzero((lons >= -130) & (lons <= -60))
        rows = np.flatnonzero((lats >= 20) & (lats <= 55))
        if not len(cols) or not len(rows):
            raise SourceError("source_unavailable", "Model grid has no CONUS coverage.")
        values = values[np.ix_(rows, cols)].copy()
        x0, y0, dx = float(lons[cols[0]]), float(lats[rows[0]]), abs(dx)
    elif get("gridType") == "lambert":
        if get("shapeOfTheEarth") != 6:
            raise SourceError("source_unavailable", "Unverified model earth shape.")
        crs = CRS.from_proj4(
            f"+proj=lcc +lat_1={get('Latin1InDegrees')} +lat_2={get('Latin2InDegrees')} "
            f"+lat_0={get('LaDInDegrees')} +lon_0={get('LoVInDegrees')} +R=6371229 +units=m"
        )
        x0, y0 = Transformer.from_crs(4326, crs, always_xy=True).transform(lon0, lat0)
        dx, dy = i_sign * get("DxInMetres"), j_sign * get("DyInMetres")
    else:
        raise SourceError("source_unavailable", "Unsupported model projection.")
    metadata = {
        "run_time": run.isoformat(),
        "forecast_hour": hour,
        "valid_time": (run + timedelta(hours=hour)).isoformat(),
        "mnemonic": mnemonic,
        "level": level,
        "input_units": get("units"),
        "step_type": get("stepType"),
        "start_step": int(get("startStep")),
        "end_step": int(get("endStep")),
        "grid_relative_winds": bool(get("uvRelativeToGrid")),
        "native_resolution": "0.25 degrees" if get("gridType") == "regular_ll" else "3 km",
    }
    if mnemonic == "APCP":
        if get("stepType") != "accum" or get("typeOfStatisticalProcessing") != 1:
            raise SourceError("source_unavailable", "Precipitation message is not an accumulation.")
        metadata["statistical_process"] = 1
    elif get("stepType") != "instant":
        raise SourceError(
            "source_unavailable", "Model instantaneous field has unexpected statistics."
        )
    if mnemonic in {"TMP", "DPT"}:
        values -= 273.15
    return PreparedGrid(values, crs.to_wkt(), x0, y0, dx, dy, "", metadata)


def earth_winds(u_grid, v_grid):
    if (u_grid.crs, u_grid.x0, u_grid.y0, u_grid.dx, u_grid.dy, u_grid.values.shape) != (
        v_grid.crs,
        v_grid.x0,
        v_grid.y0,
        v_grid.dx,
        v_grid.dy,
        v_grid.values.shape,
    ):
        raise SourceError("source_unavailable", "Wind components have different geometry.")
    u, v = u_grid.values, v_grid.values
    if u_grid.metadata["grid_relative_winds"]:
        if not v_grid.metadata["grid_relative_winds"]:
            raise SourceError("source_unavailable", "Wind component rotation flags disagree.")
        ny, nx = u.shape
        x, y = np.meshgrid(
            u_grid.x0 + np.arange(nx) * u_grid.dx, u_grid.y0 + np.arange(ny) * u_grid.dy
        )
        lon, lat = Transformer.from_crs(u_grid.crs, 4326, always_xy=True).transform(x, y)
        angle = np.radians(Proj(u_grid.crs).get_factors(lon, lat).meridian_convergence)
        u, v = u * np.cos(angle) + v * np.sin(angle), -u * np.sin(angle) + v * np.cos(angle)
    return u.astype(np.float32), v.astype(np.float32)


def accumulate_nonoverlapping(grids, hour):
    cursor = 0
    total = None
    intervals = []
    for grid in sorted(grids, key=lambda g: g.metadata["end_step"]):
        start, end = grid.metadata["start_step"], grid.metadata["end_step"]
        if start != cursor or end <= start:
            raise SourceError(
                "no_data", "Run-total precipitation has missing or overlapping intervals."
            )
        if total is not None and (grid.crs, grid.x0, grid.y0, grid.values.shape) != (
            total.crs,
            total.x0,
            total.y0,
            total.values.shape,
        ):
            raise SourceError("source_unavailable", "Precipitation intervals use different grids.")
        if np.any(grid.values < 0):
            raise SourceError(
                "source_unavailable", "Negative precipitation is not a valid run total."
            )
        if total is None:
            total = replace(grid, values=grid.values.copy(), metadata=dict(grid.metadata))
        else:
            total.values += grid.values
        intervals.append([start, end])
        cursor = end
    if cursor != hour or total is None:
        raise SourceError("no_data", "Run-total precipitation is incomplete.")
    total.metadata = {
        **total.metadata,
        "start_step": 0,
        "end_step": hour,
        "intervals": intervals,
        "complete": True,
    }
    return total
