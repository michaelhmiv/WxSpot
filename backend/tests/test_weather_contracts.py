import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from wxspot.weather_contracts import WeatherFramesResponse, WeatherSelection

CONTRACT_FIXTURE = Path(__file__).parents[2] / "contracts/weather-frames-response-v1.json"


def test_shared_weather_frames_fixture_matches_backend_contract():
    response = WeatherFramesResponse.model_validate_json(CONTRACT_FIXTURE.read_text())
    assert response.state == "ready"
    frame = response.frames[0]
    assert frame.id.startswith("radar:nws-ridge2:KCLX:reflectivity:")
    assert frame.valid_time == datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
    assert frame.render is not None
    assert frame.render.kind == "xyz"
    assert frame.coverage_bounds is None
    assert json.loads(response.model_dump_json())["frames"][0]["source_type"] == "radar"


def test_model_frame_valid_time_is_run_plus_forecast_hour():
    fixture = json.loads(CONTRACT_FIXTURE.read_text())
    frame = fixture["frames"][0]
    frame.update(
        {
            "id": "model:hrrr:run:2026-10-06T12:00:00Z:f03:reflectivity",
            "source_type": "model",
            "provider": "ncep-nomads",
            "product": "simulated-reflectivity",
            "run_time": "2026-10-06T12:00:00Z",
            "forecast_hour": 3,
            "valid_time": "2026-10-06T15:00:00Z",
        }
    )
    WeatherFramesResponse.model_validate({"state": "ready", "frames": [frame]})
    frame["valid_time"] = "2026-10-06T16:00:00Z"
    with pytest.raises(ValidationError, match="run time plus forecast hour"):
        WeatherFramesResponse.model_validate({"state": "ready", "frames": [frame]})


def test_weather_selection_rejects_ambiguous_model_run():
    with pytest.raises(ValidationError, match="explicit run"):
        WeatherSelection(
            source_type="model",
            source_id="ncep-nomads",
            product_id="temperature-2m",
            model="HRRR",
            forecast_hour=3,
        )
