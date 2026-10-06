import math
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from shapely.geometry import shape

ContentType = Literal["analysis", "observation", "question", "photo_report"]
Status = Literal["active", "hidden", "removed", "under_review"]


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone is required")
    return value


def position(value: list[float]) -> list[float]:
    if len(value) != 2 or not all(math.isfinite(v) for v in value):
        raise ValueError("Use finite [longitude, latitude]")
    if not -180 <= value[0] <= 180 or not -85.051129 <= value[1] <= 85.051129:
        raise ValueError("Coordinates exceed Web Mercator coverage")
    return value


class Camera(BaseModel):
    center: list[float]
    zoom: float = Field(ge=0, le=22)
    bearing: float = Field(default=0, ge=0, lt=360)
    pitch: float = Field(default=0, ge=0, le=60)
    _center = field_validator("center")(position)


class WeatherLayer(BaseModel):
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")
    provider: str = Field(max_length=60)
    source_type: Literal["radar", "satellite", "model", "observation", "official"]
    product: str = Field(max_length=80)
    frame_id: str = Field(max_length=200)
    valid_time: datetime
    opacity: float = Field(default=0.8, ge=0, le=1)
    radar_site: str | None = Field(default=None, pattern=r"^[KPT][A-Z0-9]{3}$")
    elevation: float | None = None
    model: str | None = None
    run_time: datetime | None = None
    forecast_hour: int | None = Field(default=None, ge=0)
    vertical_level: str | None = None
    satellite: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    _valid = field_validator("valid_time")(aware)

    @field_validator("run_time")
    @classmethod
    def run_aware(cls, value):
        return aware(value) if value else None


class WeatherContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    captured_at: datetime
    camera: Camera
    bounds: list[float]
    layers: list[WeatherLayer] = Field(min_length=1, max_length=8)
    _captured = field_validator("captured_at")(aware)

    @field_validator("bounds")
    @classmethod
    def bounds_valid(cls, bounds):
        if len(bounds) != 4:
            raise ValueError("Use [west, south, east, north]")
        position(bounds[:2])
        position(bounds[2:])
        if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            raise ValueError("Capture a non-crossing viewport with positive area")
        return bounds

    @model_validator(mode="after")
    def unique_layers(self):
        if len({layer.id for layer in self.layers}) != len(self.layers):
            raise ValueError("Layer IDs must be unique")
        return self


class AnnotationElement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tool: Literal["pin", "ellipse", "arrow", "line", "polygon", "freehand", "text"]
    geometry: dict
    color: Literal["#67E8F9", "#FDE68A", "#F9A8D4", "#FFFFFF"] = "#67E8F9"
    stroke: float = Field(default=3, ge=1, le=8)
    label: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def valid_geometry(self):
        expected = {
            "pin": "Point",
            "text": "Point",
            "ellipse": "Polygon",
            "polygon": "Polygon",
            "arrow": "LineString",
            "line": "LineString",
            "freehand": "LineString",
        }
        if set(self.geometry) != {"type", "coordinates"}:
            raise ValueError("Geometry must contain only type and coordinates")
        if self.geometry["type"] != expected[self.tool]:
            raise ValueError("Geometry type does not match annotation tool")
        count = 0

        def check(coords):
            nonlocal count
            if not isinstance(coords, list) or not coords:
                raise ValueError("Empty geometry")
            if isinstance(coords[0], (float, int)):
                position(coords)
                count += 1
            else:
                for coord in coords:
                    check(coord)

        check(self.geometry["coordinates"])
        if count > 1600:
            raise ValueError("Too many vertices")
        try:
            geometry = shape(self.geometry)
        except Exception as exc:
            raise ValueError("Invalid geographic geometry") from exc
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("Invalid geographic geometry")
        if geometry.geom_type == "Polygon" and geometry.area == 0:
            raise ValueError("Polygon has no area")
        if self.tool == "text" and not (self.label or "").strip():
            raise ValueError("Text annotations need a label")
        return self


class PostCreate(BaseModel):
    content_type: ContentType
    title: str | None = Field(default=None, max_length=120)
    description: str = Field(min_length=1, max_length=6000)
    why_it_matters: str | None = Field(default=None, max_length=2000)
    watch_next: str | None = Field(default=None, max_length=2000)
    topics: list[str] = Field(default_factory=list, max_length=8)
    context: WeatherContext
    elements: list[AnnotationElement] = Field(min_length=1, max_length=40)
    photo_ids: list[uuid.UUID] = Field(default_factory=list, max_length=4)

    @field_validator("description")
    @classmethod
    def description_nonblank(cls, value):
        if not value.strip():
            raise ValueError("Explain what you marked")
        return value.strip()

    @field_validator("topics")
    @classmethod
    def topic_names(cls, values):
        import re

        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", value) for value in values):
            raise ValueError("Use short lowercase topic names")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def unique_elements(self):
        if len({e.id for e in self.elements}) != len(self.elements):
            raise ValueError("Element IDs must be unique")
        return self


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: uuid.UUID | None = None

    @field_validator("body")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Comment cannot be blank")
        return value.strip()


class ReportCreate(BaseModel):
    target_type: Literal["post", "comment"]
    target_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=1000)


class ModerationCreate(ReportCreate):
    status: Status
