from io import BytesIO

import httpx
import numpy as np
import pytest
from PIL import Image

from wxspot.providers.mrms import MRMS_PRODUCTS, MrmsProvider
from wxspot.providers.render import MRMS_SENTINELS
from wxspot.weather_contracts import WeatherSelection


@pytest.mark.asyncio
async def test_current_noaa_mrms_grids_decode_and_render_for_each_product():
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        provider = MrmsProvider(client)
        for product, (_, _, units) in MRMS_PRODUCTS.items():
            selection = WeatherSelection(
                source_type="radar",
                source_id="noaa-mrms",
                product_id=product,
            )
            response = await provider.frames(selection)
            assert response.frames, f"NOAA returned no {product} MRMS frames"
            frame = response.frames[-1]
            assert frame.product == product
            assert frame.units == units
            assert frame.metadata["upstream_product"] == MRMS_PRODUCTS[product][0]

            grid = await provider._grid(frame.id)
            assert grid.product == product
            assert abs((grid.valid_time - frame.valid_time).total_seconds()) <= 60
            assert grid.nx > 1000 and grid.ny > 500
            present = np.isfinite(grid.values)
            for sentinel in MRMS_SENTINELS[product]:
                present &= grid.values != sentinel
            assert present.any(), f"NOAA {product} grid contained no physical values"

            tile = await provider.render_tile(frame.id, zoom=4, x=4, y=6)
            image = Image.open(BytesIO(tile))
            assert image.format == "PNG"
            assert image.size == (256, 256)
