import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from wxspot.providers.location_weather import (
    BASE,
    LocationWeatherProvider,
    interval,
    quantity,
    source_url,
    wind_range,
)
from wxspot.weather import SourceError


def documents():
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    grid = BASE + "/gridpoints/CHS/76,86"
    period = {
        "startTime": now.isoformat(),
        "endTime": (now + timedelta(hours=1)).isoformat(),
        "isDaytime": True,
        "temperature": 68,
        "temperatureUnit": "F",
        "windSpeed": "5 to 10 mph",
        "windDirection": "NE",
        "dewpoint": {"value": 10, "unitCode": "wmoUnit:degC"},
        "relativeHumidity": {"value": 50, "unitCode": "wmoUnit:percent"},
        "probabilityOfPrecipitation": {"value": None, "unitCode": "wmoUnit:percent"},
    }
    points = {
        "properties": {
            "gridId": "CHS",
            "gridX": 76,
            "gridY": 86,
            "timeZone": "America/New_York",
            "forecast": grid + "/forecast",
            "forecastHourly": grid + "/forecast/hourly",
            "forecastGridData": grid,
            "observationStations": grid + "/stations",
        }
    }
    forecast = {"properties": {"updateTime": now.isoformat(), "periods": [period]}}
    data = {
        "properties": {
            "updateTime": now.isoformat(),
            "windGust": {
                "uom": "wmoUnit:km_h-1",
                "values": [{"validTime": now.isoformat() + "/PT6H", "value": 36}],
            },
            "quantitativePrecipitation": {
                "uom": "wmoUnit:mm",
                "values": [{"validTime": now.isoformat() + "/PT6H", "value": 25.4}],
            },
        }
    }
    station = {
        "features": [
            {
                "geometry": {"coordinates": [-80.2, 33.0]},
                "properties": {"stationIdentifier": "KDYB", "name": "Summerville Airport"},
            }
        ]
    }
    observation = {
        "properties": {
            "timestamp": (now - timedelta(minutes=130)).isoformat(),
            "temperature": {"unitCode": "wmoUnit:degC", "value": 20},
            "windSpeed": {"unitCode": "wmoUnit:km_h-1", "value": 36},
        }
    }
    return {
        "/points/33.0200,-80.1800": points,
        "/gridpoints/CHS/76,86/forecast": forecast,
        "/gridpoints/CHS/76,86/forecast/hourly": forecast,
        "/gridpoints/CHS/76,86": data,
        "/gridpoints/CHS/76,86/stations": station,
        "/stations/KDYB/observations/latest": observation,
    }


def test_units_nulls_durations_and_source_links_are_explicit():
    assert quantity({"value": 68, "unitCode": "wmoUnit:degF"}, "c") == 20
    assert quantity({"value": 36, "unitCode": "wmoUnit:km_h-1"}, "ms") == 10
    assert quantity({"value": 0.0254, "unitCode": "wmoUnit:m"}, "mm") == pytest.approx(25.4)
    assert quantity({"value": None, "unitCode": "wmoUnit:percent"}, "percent") is None
    assert quantity({"value": float("nan"), "unitCode": "wmoUnit:mm"}, "mm") is None
    assert wind_range("5 to 10 mph") == pytest.approx((2.2352, 4.4704))
    assert wind_range("Calm") == (0, 0)
    assert wind_range("Variable") == (None, None)
    start, end = interval("2026-10-08T00:00:00Z/P1DT6H")
    assert (end - start).total_seconds() == 30 * 3600
    for link in [
        "http://api.weather.gov/points/1,2",
        "https://evil.example/points/1,2",
        "https://api.weather.gov@evil.example/points/1,2",
    ]:
        with pytest.raises(SourceError):
            source_url(link)


@pytest.mark.asyncio
async def test_partial_failure_retains_forecasts_and_full_rainfall_interval():
    docs = documents()

    async def handler(request):
        if request.url.path.endswith("/observations/latest"):
            return httpx.Response(503)
        return httpx.Response(200, json=docs[request.url.path])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        provider = LocationWeatherProvider(http, shared_cache=False)
        result = await provider.get([-80.18, 33.02])
    assert result.state == "partial"
    assert result.observation.observation is None
    assert result.hourly.state == result.daily.state == result.amounts.state == "ready"
    period = result.hourly.periods[0]
    assert period.temperature_c == 20 and period.gust_ms == 10
    assert period.precipitation_chance_percent is None
    assert result.amounts.precipitation[0].amount_mm == 25.4
    assert result.amounts.precipitation[0].end_time - result.amounts.precipitation[
        0
    ].start_time == timedelta(hours=6)


@pytest.mark.asyncio
async def test_old_observation_is_labeled_and_failed_refresh_keeps_issued_data():
    docs = documents()
    fail = False
    calls = []

    async def handler(request):
        calls.append(request.url.path)
        return httpx.Response(503) if fail else httpx.Response(200, json=docs[request.url.path])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        provider = LocationWeatherProvider(http, shared_cache=False)
        first = await provider.get([-80.18, 33.02])
        assert first.observation.state == "stale"
        assert first.observation.observation.age_minutes >= 130
        assert first.observation.observation.station == "KDYB"
        for manifest in provider.cache.values():
            manifest["fetched_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        fail = True
        second = await provider.get([-80.18, 33.02])
        assert second.hourly.state == "stale"
        assert second.hourly.updated_at == first.hourly.updated_at
        assert second.hourly.periods == first.hourly.periods


@pytest.mark.asyncio
async def test_duplicate_requests_coalesce_and_distinct_inflight_work_is_bounded():
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return httpx.Response(200, json={"properties": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        provider = LocationWeatherProvider(http, shared_cache=False)
        tasks = [asyncio.create_task(provider.document(BASE + "/points/33,-80")) for _ in range(8)]
        await started.wait()
        assert calls == 1
        release.set()
        await asyncio.gather(*tasks)
        assert calls == 1


def test_api_validates_points_and_uses_public_cache(client, monkeypatch):
    from wxspot.main import app

    async def result(point):
        async def handler(request):
            return httpx.Response(200, json=documents()[request.url.path])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await LocationWeatherProvider(http, shared_cache=False).get(point)

    monkeypatch.setattr(app.state.location_weather, "get", result)
    assert client.get("/weather/locations/forecast?lat=91&lon=0").status_code == 422
    response = client.get("/weather/locations/forecast?lat=33.02&lon=-80.18")
    assert response.status_code == 200 and response.headers["Cache-Control"].startswith("public")
    assert response.json()["hourly"]["periods"][0]["temperature_c"] == 20
