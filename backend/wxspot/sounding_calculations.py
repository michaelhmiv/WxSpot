"""Unit-aware profile diagnostics; incomplete inputs return reasons, never fake zeros."""

import warnings

import metpy.calc as calc
import numpy as np
from metpy.units import units

from wxspot.sounding_contracts import SoundingDiagnostics, SoundingMetric, SoundingProfile
from wxspot.weather_jobs import content_key

METHOD = (
    "MetPy 1.7.1; SB, pressure-depth ML100 and MU300; bottom LFC/top EL; "
    "log-pressure height interpolation; 10 m forecast wind is a disclosed surface anchor."
)


def finite(value):
    value = float(getattr(value, "m", value))
    return value if np.isfinite(value) else None


def calculate(profile: SoundingProfile, parcel="sb", motion="rm", storm_u=None, storm_v=None):
    if parcel not in {"sb", "ml100", "mu300"} or motion not in {"rm", "lm", "custom"}:
        raise ValueError("Unsupported parcel or motion")
    if motion == "custom" and (storm_u is None or storm_v is None):
        raise ValueError("Custom motion needs east/north components")
    identity = content_key(
        {
            "profile": profile.identity,
            "calculation": "metpy-1.7.1-v1",
            "parcel": parcel,
            "motion": motion,
            "u": storm_u,
            "v": storm_v,
        }
    )
    result = SoundingDiagnostics(
        identity=identity, parcel=parcel, motion=motion, metrics={}, vectors={}, method=METHOD
    )

    def metric(name, value=None, unit="J/kg", reason=None, method=METHOD):
        number = finite(value) if value is not None else None
        if number is not None and (name.endswith("_cape") and number < -1e-6):
            reason = "Parcel integration returned a negative CAPE; positive buoyancy is undefined"
            number = None
        result.metrics[name] = SoundingMetric(
            value=number,
            units=unit,
            reason=reason or ("Undefined for this profile" if number is None else None),
            quality="valid" if number is not None else "unavailable",
            method=method,
        )

    # Wind-only radiosonde records need not have thermodynamics. Missing moisture at
    # a reported temperature level within the usable troposphere is never bridged.
    thermo = [x for x in profile.levels if x.temperature_c is not None]
    moist = [x for x in thermo if x.dewpoint_c is not None]
    reason = None
    if len(moist) < 8:
        reason = "Too few temperature/moisture levels"
    elif moist[0] != profile.levels[0]:
        reason = "Surface thermodynamics are missing"
    elif moist[-1].pressure_hpa > 200:
        reason = "Moisture/temperature profile does not reach 200 hPa"
    elif any(x.dewpoint_c is None for x in thermo if x.pressure_hpa >= moist[-1].pressure_hpa):
        reason = "Moisture is missing inside the thermodynamic profile"
    elif any(a.pressure_hpa - b.pressure_hpa > 150 for a, b in zip(moist, moist[1:], strict=False)):
        reason = "Thermodynamic pressure gaps exceed 150 hPa"

    if reason:
        for name in (
            "sb_cape",
            "sb_cin",
            "ml100_cape",
            "ml100_cin",
            "mu300_cape",
            "mu300_cin",
            "dcape",
        ):
            metric(name, reason=reason)
        metric("pwat", unit="mm", reason=reason)
        result.quality.append(reason)
    else:
        p = np.array([x.pressure_hpa for x in moist]) * units.hPa
        t = np.array([x.temperature_c for x in moist]) * units.degC
        td = np.array([min(x.dewpoint_c, x.temperature_c) for x in moist]) * units.degC
        if any(x.dewpoint_c > x.temperature_c for x in moist):
            result.quality.append(
                "Supersaturated dew points limited to temperature for calculation"
            )
        selections = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for name in ("sb", "ml100", "mu300"):
                try:
                    if name == "sb":
                        cape, cin = calc.surface_based_cape_cin(p, t, td)
                        pp, tt, dd = p, t, td
                    elif name == "ml100":
                        cape, cin = calc.mixed_layer_cape_cin(p, t, td, depth=100 * units.hPa)
                        mp, mt, md = calc.mixed_parcel(p, t, td, depth=100 * units.hPa)
                        mask = p < p[0] - 100 * units.hPa
                        pp = np.concatenate(([mp.m], p[mask].m)) * units.hPa
                        tt = np.concatenate(([mt.to("degC").m], t[mask].m)) * units.degC
                        dd = np.concatenate(([md.to("degC").m], td[mask].m)) * units.degC
                    else:
                        cape, cin = calc.most_unstable_cape_cin(p, t, td, depth=300 * units.hPa)
                        *_, index = calc.most_unstable_parcel(p, t, td, depth=300 * units.hPa)
                        pp, tt, dd = p[index:], t[index:], td[index:]
                    metric(name + "_cape", cape.to("J/kg"))
                    metric(name + "_cin", cin.to("J/kg"))
                    selections[name] = pp, tt, dd
                except (ValueError, IndexError, RuntimeError) as exc:
                    metric(name + "_cape", reason=str(exc)[:160])
                    metric(name + "_cin", reason=str(exc)[:160])
            try:
                metric(
                    "pwat",
                    calc.precipitable_water(p, td).to("mm"),
                    unit="mm",
                    method=f"MetPy Td integration from {p[0].m:g} to {p[-1].m:g} hPa",
                )
            except (ValueError, IndexError):
                metric("pwat", unit="mm", reason="Profile water integration unavailable")
            try:
                if p[0].m < 700 or p[-1].m > 500:
                    raise ValueError("DCAPE needs the full 700–500 hPa initiation layer")
                dcape, _, _ = calc.downdraft_cape(p, t, td)
                metric(
                    "dcape", dcape.to("J/kg"), method="MetPy minimum theta-e parcel in 700–500 hPa"
                )
            except (ValueError, IndexError, RuntimeError) as exc:
                metric("dcape", reason=str(exc)[:160])

            if parcel in selections:
                pp, tt, dd = selections[parcel]
                pp, tt, dd, trace = calc.parcel_profile_with_lcl(pp, tt, dd)
                lcl_p, lcl_t = calc.lcl(pp[0], tt[0], dd[0])
                lfc_p, lfc_t = calc.lfc(
                    pp, tt, dd, parcel_temperature_profile=trace, which="bottom"
                )
                el_p, el_t = calc.el(pp, tt, dd, parcel_temperature_profile=trace, which="top")
                heights = [x for x in moist if x.height_m_msl is not None]
                for name, pressure, temperature in (
                    ("lcl", lcl_p, lcl_t),
                    ("lfc", lfc_p, lfc_t),
                    ("el", el_p, el_t),
                ):
                    pressure = finite(pressure.to("hPa"))
                    height = None
                    if (
                        pressure
                        and len(heights) >= 2
                        and heights[-1].pressure_hpa <= pressure <= heights[0].pressure_hpa
                    ):
                        xp = np.log([x.pressure_hpa for x in heights][::-1])
                        zz = np.array([x.height_m_msl for x in heights][::-1])
                        if np.all(np.diff(zz) < 0):
                            height = float(
                                np.interp(np.log(pressure), xp, zz) - profile.terrain_m_msl
                            )
                    marker_reason = (
                        "Undefined or outside sampled profile" if pressure is None else None
                    )
                    result.markers[name] = {
                        "pressure_hpa": pressure,
                        "temperature_c": finite(temperature.to("degC")),
                        "height_m_agl": height,
                    }
                    metric(name + "_pressure", pressure, unit="hPa", reason=marker_reason)
                    metric(
                        name + "_height",
                        height,
                        unit="m AGL",
                        reason="Height unavailable at parcel marker" if height is None else None,
                    )
                if finite(el_p) is None and result.metrics[parcel + "_cape"].value:
                    result.quality.append(
                        "EL is above profile top or undefined; CAPE uses sampled top"
                    )
                env_mix = calc.saturation_mixing_ratio(pp, dd)
                origin_mix = calc.saturation_mixing_ratio(pp[0], dd[0])
                parcel_mix = (
                    np.where(pp >= lcl_p, origin_mix.m, calc.saturation_mixing_ratio(pp, trace).m)
                    * units.dimensionless
                )
                env_tv = calc.virtual_temperature(tt, env_mix).to("K").m
                parcel_tv = calc.virtual_temperature(trace, parcel_mix).to("K").m
                lower, upper = finite(lfc_p.to("hPa")), finite(el_p.to("hPa"))
                result.parcel_trace = [
                    {
                        "pressure_hpa": float(q),
                        "temperature_c": float(tp),
                        "environment_c": float(te),
                        "virtual_difference_k": float(dv),
                        "environment_virtual_c": float(ev - 273.15),
                        "parcel_virtual_c": float(pv - 273.15),
                        "shade": (
                            "cape"
                            if lower is not None
                            and q <= lower
                            and (upper is None or q >= upper)
                            and dv > 0
                            else "cin"
                            if lower is not None and q >= lower and dv < 0
                            else None
                        ),
                    }
                    for q, tp, te, dv, ev, pv in zip(
                        pp.m,
                        trace.to("degC").m,
                        tt.m,
                        parcel_tv - env_tv,
                        env_tv,
                        parcel_tv,
                        strict=True,
                    )
                ]

    wind = [
        x
        for x in profile.levels
        if all(getattr(x, k) is not None for k in ("height_m_msl", "u_ms", "v_ms"))
    ]
    # Pressure is already descending; do not sort heights and hide a corrupt inversion.
    adequate = len(wind) >= 2 and wind[0].height_m_msl - profile.terrain_m_msl <= 50
    if adequate:
        z = np.array([x.height_m_msl - profile.terrain_m_msl for x in wind])
        adequate = bool(np.all(np.diff(z) > 0))
    if adequate:
        z[0] = 0.0  # Explicit near-surface anchor, not a new measured wind.
        u = np.array([x.u_ms for x in wind])
        v = np.array([x.v_ms for x in wind])
        p_wind = np.array([x.pressure_hpa for x in wind]) * units.hPa

    def covers(depth):
        if not adequate or z[-1] < depth:
            return False
        gaps = np.diff(z)
        return bool(np.all(gaps[z[:-1] < depth] <= 1500))

    if covers(6000):
        try:
            right, left, mean = calc.bunkers_storm_motion(
                p_wind, u * units("m/s"), v * units("m/s"), z * units.m
            )
            for name, vector in (("rm", right), ("lm", left), ("mean_0_6km", mean)):
                components = [finite(x) for x in vector.to("m/s")]
                result.vectors[name] = (
                    components if all(x is not None for x in components) else None
                )
        except (ValueError, IndexError, RuntimeError):
            pass
    for name in ("rm", "lm", "mean_0_6km"):
        result.vectors.setdefault(name, None)
    chosen = [storm_u, storm_v] if motion == "custom" else result.vectors.get(motion)
    result.vectors["selected"] = chosen
    for depth in (1000, 3000, 6000):
        suffix = str(depth // 1000) + "km"
        if covers(depth):
            shear = np.hypot(np.interp(depth, z, u) - u[0], np.interp(depth, z, v) - v[0])
            metric(
                "shear_0_" + suffix,
                shear,
                unit="m/s",
                method="Vector difference; height interpolation and near-surface anchor",
            )
        else:
            metric(
                "shear_0_" + suffix,
                unit="m/s",
                reason="Wind layer lacks surface/top coverage or has >1.5 km gaps",
            )
        if depth <= 3000:
            if covers(depth) and chosen and all(x is not None for x in chosen):
                helicity = calc.storm_relative_helicity(
                    z * units.m,
                    u * units("m/s"),
                    v * units("m/s"),
                    depth * units.m,
                    storm_u=chosen[0] * units("m/s"),
                    storm_v=chosen[1] * units("m/s"),
                )[2]
                metric(
                    "srh_0_" + suffix,
                    helicity,
                    unit="m²/s²",
                    method=f"MetPy total SRH with explicit {motion} motion",
                )
            else:
                metric(
                    "srh_0_" + suffix,
                    unit="m²/s²",
                    reason="Wind layer or selected storm motion is unavailable",
                )
    result.guides = thermodynamic_guides()
    return result


_guides = None


def thermodynamic_guides():
    global _guides
    if _guides is not None:
        return _guides
    p = np.geomspace(1050, 100, 45) * units.hPa

    def line(temperature):
        return [
            [float(q), float(t)]
            for q, t in zip(p.m, temperature.to("degC").m, strict=True)
            if np.isfinite(t)
        ]

    _guides = {
        "dry": [
            line(calc.dry_lapse(p, t * units.degC, reference_pressure=1000 * units.hPa))
            for t in range(-30, 91, 20)
        ],
        "moist": [
            line(calc.moist_lapse(p, t * units.degC, reference_pressure=1000 * units.hPa))
            for t in range(-20, 41, 10)
        ],
        "mixing": [
            line(calc.dewpoint(calc.vapor_pressure(p, r * units("g/kg"))))
            for r in (1, 2, 4, 8, 16, 24)
        ],
    }
    return _guides
