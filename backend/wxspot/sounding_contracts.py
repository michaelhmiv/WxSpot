"""Forecast and observed sounding identities, real levels, and nullable diagnostics."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wxspot.weather_contracts import FrameState, aware


class SoundingSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["forecast", "observed"]
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    model: Literal["hrrr", "gfs"] = "hrrr"
    domain: Literal["conus"] = "conus"
    run_time: datetime | None = None
    forecast_hour: int = Field(default=0, ge=0, le=168)
    station: str | None = Field(default=None, pattern=r"^[A-Z0-9]{11}$")
    launch: datetime | None = None
    parcel: Literal["sb", "ml100", "mu300"] = "sb"
    motion: Literal["rm", "lm", "custom"] = "rm"
    storm_u: float | None = Field(default=None, ge=-100, le=100)
    storm_v: float | None = Field(default=None, ge=-100, le=100)
    retry_failed: bool = False

    _run = field_validator("run_time", "launch")(aware)

    @model_validator(mode="after")
    def explicit_identity(self):
        if self.kind == "forecast" and self.run_time is None:
            raise ValueError("Forecast profiles require an explicit run")
        if self.kind == "forecast":
            run = self.run_time
            if run.minute or run.second or run.microsecond:
                raise ValueError("Forecast runs must use an exact hourly cycle")
            if self.model == "hrrr" and self.forecast_hour > (48 if run.hour % 6 == 0 else 18):
                raise ValueError("Forecast hour exceeds this HRRR cycle")
            if self.model == "gfs" and (
                run.hour % 6 or self.forecast_hour > 120 and self.forecast_hour % 3
            ):
                raise ValueError("GFS requires a six-hour cycle and actual published hour cadence")
        if self.kind == "observed" and self.station is None:
            raise ValueError("Observed profiles require an explicit station")
        if self.motion == "custom" and (self.storm_u is None or self.storm_v is None):
            raise ValueError("Custom storm motion requires east/north u/v in m/s")
        return self

    def profile_payload(self):
        common = {"source_type": "sounding", "source_id": "noaa-soundings", "kind": self.kind}
        if self.kind == "forecast":
            return {
                **common,
                "model": self.model,
                "domain": self.domain,
                "run_time": self.run_time.isoformat(),
                "forecast_hour": self.forecast_hour,
                "lat": round(self.lat, 5),
                "lon": round(self.lon, 5),
            }
        return {
            **common,
            "station": self.station,
            "launch": self.launch.isoformat() if self.launch else None,
            "refresh_hour": datetime.now(UTC).strftime("%Y%m%d%H") if self.launch is None else None,
        }


class SoundingLevel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    pressure_hpa: float = Field(gt=0, le=1100)
    temperature_c: float | None = None
    dewpoint_c: float | None = None
    height_m_msl: float | None = None
    u_ms: float | None = None
    v_ms: float | None = None
    quality: list[str] = Field(default_factory=list)


class SoundingProfile(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    identity: str
    kind: Literal["forecast", "observed"]
    source: str
    model: str | None = None
    domain: str | None = None
    run_time: datetime | None = None
    forecast_hour: int | None = None
    valid_time: datetime
    station: str | None = None
    station_name: str | None = None
    nominal_time: datetime | None = None
    sampled_point: list[float]
    terrain_m_msl: float
    surface_pressure_hpa: float | None = None
    method: str
    fetched_at: datetime
    levels: list[SoundingLevel] = Field(min_length=2, max_length=1500)
    quality: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered_levels(self):
        pressures = [level.pressure_hpa for level in self.levels]
        if any(a <= b for a, b in zip(pressures, pressures[1:], strict=False)):
            raise ValueError("Profile pressures must be unique and strictly descending")
        return self


class SoundingMetric(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    value: float | None = None
    units: str
    reason: str | None = None
    quality: str = "valid"
    method: str = ""


class SoundingDiagnostics(BaseModel):
    identity: str
    parcel: str
    motion: str
    metrics: dict[str, SoundingMetric]
    vectors: dict[str, list[float] | None]
    parcel_trace: list[dict] = Field(default_factory=list)
    markers: dict[str, dict] = Field(default_factory=dict)
    guides: dict[str, list[list[list[float]]]] = Field(default_factory=dict)
    method: str
    quality: list[str] = Field(default_factory=list)


class SoundingResponse(BaseModel):
    state: FrameState
    profile: SoundingProfile | None = None
    diagnostics: SoundingDiagnostics | None = None
    requested_point: list[float]
    distance_km: float | None = None
    retry_after_seconds: int | None = None
    message: str | None = None
    options: dict = Field(default_factory=dict)
