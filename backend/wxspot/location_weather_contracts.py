from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WeatherValues(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    temperature_c: float | None = None
    dewpoint_c: float | None = None
    humidity_percent: float | None = None
    wind_low_ms: float | None = None
    wind_high_ms: float | None = None
    wind_direction: str | None = None
    gust_ms: float | None = None
    precipitation_chance_percent: float | None = None


class Observation(WeatherValues):
    station: str
    station_name: str
    sampled_point: list[float]
    distance_km: float
    observed_at: datetime
    age_minutes: int
    description: str = ""
    precipitation_last_hour_mm: float | None = None


class ForecastPeriod(WeatherValues):
    start_time: datetime
    end_time: datetime
    name: str = ""
    daytime: bool
    summary: str = ""
    detail: str = ""


class PrecipitationInterval(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    start_time: datetime
    end_time: datetime
    amount_mm: float | None = None


class WeatherSection(BaseModel):
    state: Literal["ready", "stale", "no_data", "source_unavailable"]
    source: str = "National Weather Service"
    source_url: str | None = None
    fetched_at: datetime | None = None
    updated_at: datetime | None = None
    message: str | None = None
    observation: Observation | None = None
    periods: list[ForecastPeriod] = Field(default_factory=list)
    precipitation: list[PrecipitationInterval] = Field(default_factory=list)


class LocationWeatherResponse(BaseModel):
    state: str
    requested_point: list[float]
    timezone: str | None = None
    place_name: str | None = None
    grid: str | None = None
    message: str | None = None
    observation: WeatherSection
    hourly: WeatherSection
    daily: WeatherSection
    amounts: WeatherSection
