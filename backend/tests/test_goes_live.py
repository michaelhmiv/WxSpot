import gc
import json
import resource
import time
from io import BytesIO

import httpx
import numpy as np
import pytest
from PIL import Image

from wxspot.providers.goes import PRODUCTS, GoesProvider
from wxspot.storage import LocalStorage
from wxspot.weather_contracts import WeatherSelection


@pytest.mark.asyncio
async def test_operational_east_west_all_required_abi_products(tmp_path):
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        provider = GoesProvider(client, LocalStorage(tmp_path))
        satellites = await provider.satellites()
        assert satellites["east"] != satellites["west"]
        for sector in ("east", "west"):
            for product, (_, _, units, _) in PRODUCTS.items():
                started = time.monotonic()
                response = await provider.frames(
                    WeatherSelection(
                        source_type="satellite",
                        source_id="noaa-goes",
                        product_id=product,
                        domain=sector,
                    )
                )
                assert response.frames, f"No real {sector}/{product} frames"
                frame = response.frames[-1]
                grid = await provider.prepare_artifact(frame.id)
                assert frame.satellite == "GOES-" + satellites[sector]
                assert frame.units == grid.metadata["units"] == units
                assert grid.metadata["scan_start"] == frame.metadata["scan_start"]
                assert grid.metadata["scan_end"] == frame.metadata["scan_end"]
                assert frame.channel == (
                    "GeoColor" if product == "geocolor" else "C" + PRODUCTS[product][0]
                )
                assert grid.values.nbytes <= 192 * 1024 * 1024
                tile = Image.open(BytesIO(grid.tile(4, 4 if sector == "east" else 2, 6)))
                assert tile.size == (256, 256)
                assert np.asarray(tile)[..., 3].any()
                assert Image.open(BytesIO(await provider.render_legend(product))).width == 512
                print(
                    json.dumps(
                        {
                            "product": product,
                            "sector": sector,
                            "frame": frame.id,
                            "seconds": round(time.monotonic() - started, 2),
                            "grid_bytes": grid.values.nbytes,
                            "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        }
                    )
                )
                del grid, tile
                gc.collect()
