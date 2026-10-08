import asyncio
from collections import OrderedDict

from wxspot.providers.grids import PreparedGrid
from wxspot.providers.render import legend_png
from wxspot.weather import SourceError
from wxspot.weather_jobs import enqueue, prepared


class PreparedProvider:
    """API side of shared worker artifacts; never downloads/decodes raw datasets."""

    def __init__(self, client, storage):
        self.client, self.storage = client, storage
        self._cache = OrderedDict()
        self._tiles = OrderedDict()
        self._load_lock = asyncio.Lock()
        self._render_lock = asyncio.Lock()

    def payload(self, frame_id):
        self.parse_identity(frame_id)
        return {
            "source_type": self.source_type,
            "source_id": self.provider_id,
            "frame_id": frame_id,
        }

    async def prepare(self, frame_id):
        job = await enqueue(self.payload(frame_id))
        return {
            "state": "ready"
            if job.state == "ready"
            else ("source_unavailable" if job.state == "failed" else "preparing"),
            "message": job.error,
            "retry_after_seconds": 3,
            "metadata": job.manifest.get("metadata", {}) if job.manifest else {},
        }

    async def _grid(self, frame_id):
        async with self._load_lock:
            if frame_id in self._cache:
                self._cache.move_to_end(frame_id)
                return self._cache[frame_id]
            manifest = await prepared(self.payload(frame_id))
            data = await self.storage.get(manifest["object_key"])
            grid = await asyncio.to_thread(PreparedGrid.decode, data)
            self._cache[frame_id] = grid
            while len(self._cache) > 1:
                self._cache.popitem(last=False)
            return grid

    async def render_tile(self, frame_id, zoom, x, y):
        key = (frame_id, zoom, x, y)
        async with self._render_lock:
            if key in self._tiles:
                self._tiles.move_to_end(key)
                return self._tiles[key]
            grid = await self._grid(frame_id)
            result = await asyncio.to_thread(grid.tile, zoom, x, y)
            self._tiles[key] = result
            while len(self._tiles) > 96:
                self._tiles.popitem(last=False)
            return result

    async def capture(self, layer, bounds):
        frame = await self.resolve_frame(layer.frame_id)
        if (layer.source_type, layer.provider, layer.product, layer.valid_time) != (
            frame.source_type,
            frame.provider,
            frame.product,
            frame.valid_time,
        ):
            raise SourceError(
                "unsupported_product", "Weather layer does not match its exact frame."
            )
        if frame.source_type == "model" and (layer.model, layer.run_time, layer.forecast_hour) != (
            frame.model,
            frame.run_time,
            frame.forecast_hour,
        ):
            raise SourceError("unsupported_product", "Model layer does not match its run and hour.")
        if frame.source_type == "model" and layer.vertical_level != frame.vertical_level:
            raise SourceError(
                "unsupported_product", "Model layer does not match its vertical level."
            )
        if frame.source_type == "satellite" and layer.satellite != frame.satellite:
            raise SourceError(
                "unsupported_product", "Satellite layer does not match its spacecraft."
            )
        grid = await self._grid(layer.frame_id)
        return await asyncio.to_thread(grid.image, bounds)

    async def render_legend(self, product, frame_id=None):
        return await asyncio.to_thread(legend_png, self.scale_product(product))
