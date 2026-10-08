from io import BytesIO

import httpx
import numpy as np
import pytest
from PIL import Image

from wxspot.providers.forecast import MODEL_PRODUCTS, ModelProvider
from wxspot.storage import LocalStorage


@pytest.mark.asyncio
async def test_real_hrrr_gfs_all_core_fields_and_accumulation_intervals(tmp_path):
    async with httpx.AsyncClient(timeout=60) as client:
        provider = ModelProvider(client, LocalStorage(tmp_path))
        for model in ("hrrr", "gfs"):
            runs = await provider.available_runs(model)
            run = next((r for r in runs if 3 in provider._inventories[(model, r)][1]), None)
            assert run is not None
            for product in MODEL_PRODUCTS:
                frame = provider.frame(model, run, 3, product)
                grid = await provider.prepare_artifact(frame.id)
                assert (
                    grid.metadata["forecast_hour"] == 3
                    and grid.metadata["run_time"] == run.isoformat()
                )
                assert grid.metadata["units"] == MODEL_PRODUCTS[product][1]
                assert np.isfinite(grid.values).any()
                tile = Image.open(BytesIO(grid.tile(5, 8, 12)))
                assert tile.size == (256, 256) and np.asarray(tile)[..., 3].any()
                if product.startswith("precip_"):
                    assert (
                        grid.metadata["step_type"] == "accum"
                        and grid.metadata["statistical_process"] == 1
                    )
                    assert 0 <= grid.metadata["start_step"] < grid.metadata["end_step"] == 3
                if product == "precip_total":
                    assert grid.metadata["complete"] is True
                if product == "wind":
                    assert grid.metadata["vector_wind"] and grid.values.shape[-1] == 3
                print(model, product, frame.id, grid.values.nbytes)
            # Exercise a long available run-total, including GFS accumulation resets.
            long_run = max(runs, key=lambda r: max(provider._inventories[(model, r)][1], default=0))
            hour = max(provider._inventories[(model, long_run)][1])
            total = await provider.prepare_artifact(
                provider.frame(model, long_run, hour, "precip_total").id
            )
            assert total.metadata["start_step"] == 0 and total.metadata["end_step"] == hour
            assert total.metadata["complete"] and total.metadata["intervals"][0][0] == 0
