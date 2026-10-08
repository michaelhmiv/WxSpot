import json
import time

import httpx
import pytest

from wxspot.providers.location_weather import LocationWeatherProvider


@pytest.mark.asyncio
async def test_real_nws_point_observation_forecasts_and_source_intervals():
    async with httpx.AsyncClient(timeout=25) as client:
        provider = LocationWeatherProvider(client, shared_cache=False)
        started = time.monotonic()
        result = await provider.get([-80.18, 33.02])
        assert result.timezone == "America/New_York"
        assert result.hourly.state in {"ready", "stale"} and len(result.hourly.periods) >= 24
        assert result.daily.state in {"ready", "stale"} and len(result.daily.periods) >= 7
        assert result.observation.observation is not None
        assert result.observation.observation.station.startswith("K")
        assert result.observation.observation.observed_at.tzinfo is not None
        assert result.amounts.precipitation
        assert all(p.end_time > p.start_time for p in result.amounts.precipitation)
        json.dumps(result.model_dump(mode="json"), allow_nan=False)
        print(
            json.dumps(
                {
                    "point": result.requested_point,
                    "grid": result.grid,
                    "observation_station": result.observation.observation.station,
                    "observation_time": result.observation.observation.observed_at.isoformat(),
                    "hourly_periods": len(result.hourly.periods),
                    "daily_periods": len(result.daily.periods),
                    "rainfall_intervals": len(result.amounts.precipitation),
                    "seconds": round(time.monotonic() - started, 2),
                }
            ),
            flush=True,
        )
