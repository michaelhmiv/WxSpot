"""Portable georeferenced numeric/RGBA grids and bounded rendering outside the API loop."""

import json
import math
from dataclasses import dataclass
from io import BytesIO

import numpy as np
from pyproj import Transformer

from wxspot.providers.render import colorize, png_bytes
from wxspot.weather import SourceError


@dataclass
class PreparedGrid:
    values: np.ndarray
    crs: str
    x0: float
    y0: float
    dx: float
    dy: float
    product: str
    metadata: dict

    def encode(self) -> bytes:
        output = BytesIO()
        header = {k: v for k, v in vars(self).items() if k != "values"}
        np.savez_compressed(output, values=self.values, header=json.dumps(header))
        return output.getvalue()

    @classmethod
    def decode(cls, data: bytes):
        with np.load(BytesIO(data), allow_pickle=False) as dataset:
            header = json.loads(str(dataset["header"]))
            values = dataset["values"]
            if values.nbytes > 192 * 1024 * 1024:
                raise SourceError("source_unavailable", "Prepared grid exceeds its memory budget.")
            return cls(values=values, **header)

    def sample(self, longitude, latitude):
        transform = Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)
        x, y = transform.transform(longitude, latitude)
        x, y = np.asarray(x), np.asarray(y)
        finite = np.isfinite(x) & np.isfinite(y)
        col = np.rint(np.where(finite, (x - self.x0) / self.dx, -1)).astype(np.int64)
        row = np.rint(np.where(finite, (y - self.y0) / self.dy, -1)).astype(np.int64)
        ny, nx = self.values.shape[:2]
        inside = finite & (col >= 0) & (col < nx) & (row >= 0) & (row < ny)
        if self.values.ndim == 3:
            result = np.zeros((*col.shape, 4), dtype=np.uint8)
            result[inside] = self.values[row[inside], col[inside]]
        else:
            result = np.full(col.shape, np.nan, dtype=np.float32)
            result[inside] = self.values[row[inside], col[inside]]
            if "packed_fill" in self.metadata:
                result[result == self.metadata["packed_fill"]] = np.nan
                result = result * self.metadata["sampling_scale"] + self.metadata["sampling_offset"]
        return result

    def rgba(self, longitude, latitude):
        sampled = self.sample(longitude, latitude)
        return sampled if sampled.ndim == 3 else colorize(sampled, self.product)

    def image(self, bounds, width=1024, height=768):
        west, south, east, north = bounds
        if not (-180 <= west < east <= 180 and -90 < south < north < 90):
            raise SourceError("unsupported_product", "Invalid image bounds.")
        lon = west + (np.arange(width) + 0.5) * (east - west) / width
        lat = north - (np.arange(height) + 0.5) * (north - south) / height
        return png_bytes(self.rgba(*np.meshgrid(lon, lat)))

    def tile(self, z, x, y):
        if not (0 <= z <= 12 and 0 <= x < 2**z and 0 <= y < 2**z):
            raise SourceError("unsupported_product", "Invalid map tile coordinates.")
        n = 2**z
        lon = ((x + (np.arange(256) + 0.5) / 256) / n) * 360 - 180
        lat = np.degrees(
            np.arctan(np.sinh(math.pi * (1 - 2 * (y + (np.arange(256) + 0.5) / 256) / n)))
        )
        return png_bytes(self.rgba(*np.meshgrid(lon, lat)))
