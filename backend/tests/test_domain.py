from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from wxspot.schemas import AnnotationElement, WeatherContext
from wxspot.social import decode_cursor, parse_bbox
from wxspot.weather import SourceError, mercator_bounds, parse_capabilities, parse_times


def test_real_ridge_capabilities():
    data = Path(__file__).with_name("fixtures").joinpath("kclx-capabilities.xml").read_bytes()
    reflectivity = parse_capabilities(data, "KCLX", "reflectivity")
    velocity = parse_capabilities(data, "KCLX", "velocity")
    assert len(reflectivity) >= 10
    assert reflectivity == sorted(set(reflectivity))
    assert velocity and all(t.tzinfo for t in velocity)


def test_unsupported_product_not_fabricated():
    data = b'<WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability/></WMS_Capabilities>'
    with pytest.raises(SourceError, match="does not advertise"):
        parse_capabilities(data, "KCLX", "reflectivity")


def test_wms_interval():
    times = parse_times("2026-10-06T12:00:00Z/2026-10-06T12:15:00Z/PT5M")
    assert len(times) == 4 and times[0] == datetime(2026, 10, 6, 12, tzinfo=UTC)
    with pytest.raises(SourceError):
        parse_times("2026-10-06T12:00:00Z/2026-10-06T12:15:00Z/PT0M")


def test_mercator_origin():
    bounds = mercator_bounds([0, 0, 1, 1])
    assert abs(bounds[1]) < 1e-6
    assert 111000 < bounds[2] < 112000


@pytest.mark.parametrize("coordinates", [[181, 20], [0, 90], [float("nan"), 0], []])
def test_invalid_coordinates(coordinates):
    with pytest.raises(ValidationError):
        AnnotationElement(tool="pin", geometry={"type": "Point", "coordinates": coordinates})


def test_tool_geometry_must_agree():
    with pytest.raises(ValidationError):
        AnnotationElement(tool="arrow", geometry={"type": "Point", "coordinates": [-80, 33]})
    with pytest.raises(ValidationError):
        AnnotationElement(tool="text", geometry={"type": "Point", "coordinates": [-80, 33]})


def test_self_intersecting_polygon():
    with pytest.raises(ValidationError):
        AnnotationElement(
            tool="polygon",
            geometry={
                "type": "Polygon",
                "coordinates": [[[-80, 33], [-79, 34], [-80, 34], [-79, 33], [-80, 33]]],
            },
        )


def test_context_is_versioned_multilayer():
    context = WeatherContext.model_validate(
        {
            "captured_at": "2026-10-06T12:00:00Z",
            "camera": {"center": [-80, 33], "zoom": 7, "bearing": 30, "pitch": 20},
            "bounds": [-81, 32, -79, 34],
            "layers": [
                {
                    "id": "radar",
                    "provider": "nws-ridge2",
                    "source_type": "radar",
                    "product": "reflectivity",
                    "frame_id": "KCLX:reflectivity:time",
                    "valid_time": "2026-10-06T12:00:00Z",
                    "radar_site": "KCLX",
                },
                {
                    "id": "model",
                    "provider": "future",
                    "source_type": "model",
                    "product": "cape",
                    "frame_id": "run:6",
                    "valid_time": "2026-10-06T18:00:00Z",
                    "model": "HRRR",
                    "run_time": "2026-10-06T12:00:00Z",
                    "forecast_hour": 6,
                },
            ],
        }
    )
    assert WeatherContext.model_validate_json(context.model_dump_json()) == context
    assert len(context.layers) == 2


@pytest.mark.parametrize("bbox", ["0,0,0", "nan,0,1,1", "181,0,1,1", "-80,34,-79,33"])
def test_invalid_viewport(bbox):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        parse_bbox(bbox)


def test_antimeridian_and_invalid_cursor():
    assert parse_bbox("170,-10,-170,10") == [170, -10, -170, 10]
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        decode_cursor("not-a-cursor")
