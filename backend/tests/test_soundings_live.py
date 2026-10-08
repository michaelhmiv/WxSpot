import json
import resource
import time
from pathlib import Path

import httpx
import pytest

from wxspot.providers.forecast import MODEL_BUCKETS, model_object
from wxspot.providers.soundings import SoundingProvider
from wxspot.sounding_calculations import calculate
from wxspot.sounding_contracts import SoundingSelection
from wxspot.storage import LocalStorage


@pytest.mark.asyncio
async def test_live_hrrr_gfs_and_actual_igra_launch(tmp_path):
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60, connect=10),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=3),
    ) as client:
        provider = SoundingProvider(client, LocalStorage(Path(tmp_path)))
        for model in ("hrrr", "gfs"):
            started = time.monotonic()
            runs = await provider.models.available_runs(model)
            assert runs, f"No real {model} runs are published"
            run = None
            for candidate in runs:
                if model == "hrrr":
                    # Surface products can arrive before this cycle's pressure file.
                    # Choose an explicitly available pressure run for this live check;
                    # the application still honors every requested run without fallback.
                    key = model_object(model, candidate, 0, pressure=True)
                    response = await client.head(f"{MODEL_BUCKETS[model]}/{key}.idx")
                    if response.status_code == 404:
                        print(f"HRRR pressure F000 not published yet: {candidate.isoformat()}")
                        continue
                    response.raise_for_status()
                run = candidate
                break
            assert run is not None, f"No real {model} sounding run is published"
            selection = SoundingSelection(
                kind="forecast", model=model, run_time=run, forecast_hour=0, lon=-80.18, lat=33.02
            )
            profile, options = await provider.prepare_profile(selection.profile_payload())
            assert profile.model == model and profile.run_time == run and profile.forecast_hour == 0
            assert len(profile.levels) >= 20 and 0 in options["forecast_hours"]
            assert all(
                level.pressure_hpa <= profile.surface_pressure_hpa for level in profile.levels
            )
            assert all(
                level.height_m_msl is None or level.height_m_msl >= profile.terrain_m_msl
                for level in profile.levels
            )
            diagnostics = calculate(profile)
            assert diagnostics.metrics["pwat"].value is not None
            assert diagnostics.metrics["shear_0_1km"].value is not None
            json.dumps(diagnostics.model_dump(mode="json"), allow_nan=False)
            print(
                json.dumps(
                    {
                        "model": model,
                        "run": run.isoformat(),
                        "levels": len(profile.levels),
                        "seconds": round(time.monotonic() - started, 2),
                        "input": profile.metadata,
                        "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    }
                ),
                flush=True,
            )
        stations = await provider.stations([-80.18, 33.02])
        assert stations and stations[0]["id"] == "USM00072208"
        profile, options = await provider.observed({"station": stations[0]["id"]})
        assert profile.kind == "observed" and profile.station == "USM00072208"
        assert profile.valid_time.isoformat() == options["launches"][-1]
        assert profile.sampled_point == [stations[0]["lon"], stations[0]["lat"]]
        assert len(profile.levels) > 20
        json.dumps(calculate(profile).model_dump(mode="json"), allow_nan=False)
        print(
            json.dumps(
                {
                    "station": profile.station,
                    "actual_launch": profile.valid_time.isoformat(),
                    "levels": len(profile.levels),
                    "input": profile.metadata,
                }
            ),
            flush=True,
        )
