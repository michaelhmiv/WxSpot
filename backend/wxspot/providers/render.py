from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw


@dataclass(frozen=True)
class Scale:
    minimum: float
    maximum: float
    units: str
    stops: tuple[tuple[float, tuple[int, int, int]], ...]
    title: str


SCALES = {
    "reflectivity": Scale(
        -10,
        75,
        "dBZ",
        (
            (0, (80, 112, 154)),
            (0.15, (114, 170, 218)),
            (0.27, (0, 190, 70)),
            (0.46, (0, 235, 0)),
            (0.62, (255, 235, 0)),
            (0.76, (255, 128, 0)),
            (0.88, (235, 20, 20)),
            (1, (210, 0, 200)),
        ),
        "Reflectivity",
    ),
    "velocity": Scale(
        -64,
        64,
        "m/s",
        (
            (0, (26, 68, 190)),
            (0.24, (76, 160, 245)),
            (0.5, (248, 248, 248)),
            (0.76, (250, 130, 82)),
            (1, (180, 12, 25)),
        ),
        "Radial velocity",
    ),
    "storm_relative_velocity": Scale(
        -50,
        50,
        "kt",
        (
            (0, (26, 68, 190)),
            (0.24, (76, 160, 245)),
            (0.5, (248, 248, 248)),
            (0.76, (250, 130, 82)),
            (1, (180, 12, 25)),
        ),
        "Storm-relative velocity",
    ),
    "correlation_coefficient": Scale(
        0,
        1,
        "unitless",
        (
            (0, (115, 44, 125)),
            (0.2, (58, 112, 178)),
            (0.55, (64, 190, 175)),
            (0.82, (240, 232, 110)),
            (1, (215, 58, 45)),
        ),
        "Correlation coefficient",
    ),
    "differential_reflectivity": Scale(
        -8,
        8,
        "dB",
        (
            (0, (37, 62, 181)),
            (0.25, (77, 177, 220)),
            (0.5, (245, 245, 245)),
            (0.75, (255, 178, 74)),
            (1, (184, 26, 35)),
        ),
        "Differential reflectivity",
    ),
    "specific_differential_phase": Scale(
        -8,
        8,
        "degrees/km",
        (
            (0, (46, 54, 171)),
            (0.25, (66, 175, 219)),
            (0.5, (245, 245, 245)),
            (0.75, (250, 195, 70)),
            (1, (177, 22, 48)),
        ),
        "Specific differential phase",
    ),
    "precip_rate": Scale(
        0,
        50,
        "mm/h",
        (
            (0, (226, 238, 250)),
            (0.02, (132, 194, 246)),
            (0.12, (30, 113, 219)),
            (0.28, (35, 190, 192)),
            (0.47, (38, 170, 69)),
            (0.68, (244, 222, 43)),
            (0.84, (240, 117, 34)),
            (1, (198, 30, 42)),
        ),
        "Precipitation rate",
    ),
    "precip_1h": Scale(
        0,
        100,
        "mm",
        (
            (0, (226, 238, 250)),
            (0.02, (132, 194, 246)),
            (0.12, (30, 113, 219)),
            (0.28, (35, 190, 192)),
            (0.47, (38, 170, 69)),
            (0.68, (244, 222, 43)),
            (0.84, (240, 117, 34)),
            (1, (198, 30, 42)),
        ),
        "1-hour radar estimate",
    ),
    "precip_3h": Scale(
        0,
        150,
        "mm",
        (
            (0, (226, 238, 250)),
            (0.02, (132, 194, 246)),
            (0.12, (30, 113, 219)),
            (0.28, (35, 190, 192)),
            (0.47, (38, 170, 69)),
            (0.68, (244, 222, 43)),
            (0.84, (240, 117, 34)),
            (1, (198, 30, 42)),
        ),
        "3-hour radar estimate",
    ),
    "precip_24h": Scale(
        0,
        300,
        "mm",
        (
            (0, (226, 238, 250)),
            (0.02, (132, 194, 246)),
            (0.12, (30, 113, 219)),
            (0.28, (35, 190, 192)),
            (0.47, (38, 170, 69)),
            (0.68, (244, 222, 43)),
            (0.84, (240, 117, 34)),
            (1, (198, 30, 42)),
        ),
        "24-hour radar estimate",
    ),
}

SRM_LEVEL_COLORS = {
    1: (0, 224, 255),
    2: (0, 128, 255),
    3: (50, 0, 150),
    4: (0, 251, 144),
    5: (0, 187, 0),
    6: (0, 143, 0),
    7: (205, 192, 159),
    8: (118, 118, 118),
    9: (248, 135, 0),
    10: (255, 207, 0),
    11: (255, 255, 0),
    12: (174, 0, 0),
    13: (208, 112, 0),
    14: (255, 0, 0),
}
RANGE_FOLD_COLOR = (119, 0, 125)

MRMS_SENTINELS = {
    "reflectivity": (-99.0, -999.0),
    "precip_rate": (-1.0, -3.0),
    "precip_1h": (-1.0, -3.0),
    "precip_3h": (-1.0, -3.0),
    "precip_24h": (-1.0, -3.0),
}


def colorize(values, product: str, *, missing=None, range_fold=None) -> np.ndarray:
    """Return transparent RGBA for absent data and preserve real zero values."""
    scale = SCALES[product]
    data = np.asarray(values, dtype=np.float32)
    folded = np.zeros(data.shape, dtype=bool) if range_fold is None else np.asarray(range_fold)
    if product == "storm_relative_velocity":
        rgba = np.zeros((*data.shape, 4), dtype=np.uint8)
        for level, color in SRM_LEVEL_COLORS.items():
            rgba[data == level] = (*color, 255)
        rgba[folded] = (*RANGE_FOLD_COLOR, 255)
        return rgba
    absent = ~np.isfinite(data)
    if missing is not None:
        for sentinel in missing:
            absent |= data == sentinel
    valid = ~absent
    normalized = np.clip(
        (np.where(valid, data, scale.minimum) - scale.minimum) / (scale.maximum - scale.minimum),
        0,
        1,
    )
    stops = scale.stops
    positions = np.asarray([stop[0] for stop in stops], dtype=np.float32)
    colors = np.asarray([stop[1] for stop in stops], dtype=np.float32)
    flat = normalized.reshape(-1)
    right = np.clip(np.searchsorted(positions, flat, side="right"), 1, len(stops) - 1)
    left = right - 1
    t = ((flat - positions[left]) / (positions[right] - positions[left]))[:, None]
    rgb = (colors[left] + t * (colors[right] - colors[left])).reshape((*data.shape, 3))
    rgba = np.zeros((*data.shape, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    rgba[..., 3] = valid.astype(np.uint8) * 255
    if range_fold is not None:
        rgba[folded] = (*RANGE_FOLD_COLOR, 255)
    return rgba


def png_bytes(rgba: np.ndarray) -> bytes:
    image = Image.fromarray(np.asarray(rgba, dtype=np.uint8), mode="RGBA")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def legend_png(
    product: str,
    width: int = 512,
    height: int = 32,
    *,
    levels_kt: tuple[float, ...] | None = None,
) -> bytes:
    if product == "storm_relative_velocity":
        legend_width, legend_height = width, 58
        image = Image.new("RGBA", (legend_width, legend_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        codes = [*SRM_LEVEL_COLORS, 15]
        if levels_kt is None:
            labels = [*(str(code) for code in SRM_LEVEL_COLORS), "RF"]
        else:
            if len(levels_kt) != len(SRM_LEVEL_COLORS):
                raise ValueError("Storm-relative legend levels must match the product palette")
            labels = [f"{value:+g}" if value else "0" for value in levels_kt] + ["RF"]
        box_width = legend_width / len(codes)
        for index, (code, label) in enumerate(zip(codes, labels, strict=True)):
            color = SRM_LEVEL_COLORS.get(code, RANGE_FOLD_COLOR)
            left = round(index * box_width)
            right = round((index + 1) * box_width)
            draw.rectangle((left, 0, right, 24), fill=(*color, 255))
            draw.text((left + 1, 32), label, fill=(0, 0, 0, 255))
        return png_bytes(np.asarray(image))
    scale = SCALES[product]
    values = np.linspace(scale.minimum, scale.maximum, width, dtype=np.float32)[None, :]
    rgba = colorize(values, product)
    rgba = np.repeat(rgba, height, axis=0)
    return png_bytes(rgba)
