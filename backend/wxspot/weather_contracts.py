from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceType = Literal["radar", "satellite", "model", "observation"]
FrameState = Literal[
    "ready",
    "preparing",
    "source_delayed",
    "no_data",
    "source_unavailable",
    "unsupported_product",
    "render_error",
]


def aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("Weather timestamps must include a timezone")
    return value


def valid_bounds(value: list[float] | None) -> list[float] | None:
    if value is None:
        return None
    if len(value) != 4:
        raise ValueError("Coverage bounds must be [west, south, east, north]")
    west, south, east, north = value
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Coverage bounds are invalid")
    return value


class WeatherSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType
    source_id: str = Field(min_length=1, max_length=80)
    product_id: str = Field(min_length=1, max_length=100)
    site: str | None = Field(default=None, max_length=12)
    domain: str | None = Field(default=None, max_length=40)
    elevation: float | None = Field(default=None, ge=0, le=90)
    channel: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=30)
    run_time: datetime | None = None
    forecast_hour: int | None = Field(default=None, ge=0, le=240)
    vertical_level: str | None = Field(default=None, max_length=40)
    selection_generation: int = Field(default=0, ge=0)

    _run_aware = field_validator("run_time")(aware)

    @model_validator(mode="after")
    def selected_source_fields(self):
        if self.source_type == "radar" and self.source_id in {
            "nws-ridge2",
            "noaa-nexrad-level3",
        } and self.site is None:
            raise ValueError("This radar source requires an explicit site")
        if self.source_type == "model":
            if self.model is None or self.run_time is None:
                raise ValueError("Model selections require a model and explicit run")
            if self.forecast_hour is None:
                raise ValueError("Model selections require an explicit forecast hour")
        return self


class RenderDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["xyz", "image"]
    url_template: str | None = Field(default=None, max_length=2048)
    image_url: str | None = Field(default=None, max_length=2048)
    tile_size: int | None = Field(default=256, ge=1, le=2048)
    min_zoom: int | None = Field(default=None, ge=0, le=24)
    max_zoom: int | None = Field(default=None, ge=0, le=24)
    bounds: list[float] | None = None
    content_version: str = Field(min_length=1, max_length=200)

    _bounds = field_validator("bounds")(valid_bounds)

    @model_validator(mode="after")
    def usable_descriptor(self):
        if self.kind == "xyz" and not self.url_template:
            raise ValueError("XYZ render descriptors require a URL template")
        if self.kind == "image" and not self.image_url:
            raise ValueError("Image render descriptors require an image URL")
        if self.min_zoom is not None and self.max_zoom is not None:
            if self.min_zoom > self.max_zoom:
                raise ValueError("Minimum zoom must not exceed maximum zoom")
        return self


class WeatherFrame(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    provider: str = Field(min_length=1, max_length=80)
    product: str = Field(min_length=1, max_length=100)
    valid_time: datetime
    render: RenderDescriptor | None = None
    coverage_bounds: list[float] | None = None
    attribution: str = Field(min_length=1, max_length=400)
    units: str | None = Field(default=None, max_length=40)
    legend_url: str | None = Field(default=None, max_length=2048)
    state: FrameState = "ready"
    site: str | None = Field(default=None, max_length=12)
    elevation: float | None = Field(default=None, ge=0, le=90)
    model: str | None = Field(default=None, max_length=30)
    domain: str | None = Field(default=None, max_length=40)
    run_time: datetime | None = None
    forecast_hour: int | None = Field(default=None, ge=0, le=240)
    vertical_level: str | None = Field(default=None, max_length=40)
    satellite: str | None = Field(default=None, max_length=40)
    channel: str | None = Field(default=None, max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _valid = field_validator("valid_time")(aware)
    _run_aware = field_validator("run_time")(aware)
    _coverage = field_validator("coverage_bounds")(valid_bounds)

    @model_validator(mode="after")
    def ready_frame_has_renderer(self):
        if self.state == "ready" and self.render is None:
            raise ValueError("A ready weather frame needs a render descriptor")
        if self.source_type == "model" and self.run_time is not None:
            if self.forecast_hour is None:
                raise ValueError("Model frames require a forecast hour")
            if self.valid_time != self.run_time + timedelta(hours=self.forecast_hour):
                raise ValueError("Model valid time must match run time plus forecast hour")
        return self


class WeatherProduct(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType
    provider: str
    source_id: str
    product_id: str
    display_name: str
    units: str | None = None
    attribution: str
    legend_url: str | None = None
    coverage_bounds: list[float] | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


class WeatherCatalogResponse(BaseModel):
    state: Literal["ready", "source_unavailable"] = "ready"
    products: list[WeatherProduct]
    fetched_at: datetime | None = None

    _fetched = field_validator("fetched_at")(aware)


class WeatherFramesResponse(BaseModel):
    state: FrameState
    frames: list[WeatherFrame]
    fetched_at: datetime | None = None
    message: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    _fetched = field_validator("fetched_at")(aware)

    @model_validator(mode="after")
    def consistent_frames(self):
        if len({frame.id for frame in self.frames}) != len(self.frames):
            raise ValueError("Weather frame IDs must be unique")
        if self.frames:
            first = self.frames[0]
            if any(
                (frame.source_type, frame.provider, frame.product)
                != (first.source_type, first.provider, first.product)
                for frame in self.frames
            ):
                raise ValueError("A frame response must contain one source and product")
            if [frame.valid_time for frame in self.frames] != sorted(
                frame.valid_time for frame in self.frames
            ):
                raise ValueError("Weather frames must be ordered by valid time")
        return self


class FrameReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    frame_id: str
    selection_generation: int = Field(ge=0)
    viewport_generation: int = Field(ge=0)
    state: Literal["loading", "ready", "error"]
    error: str | None = None
