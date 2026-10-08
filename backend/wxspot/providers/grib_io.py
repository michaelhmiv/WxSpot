"""Single codec subprocess: keep ecCodes' native projection libraries separate from pyproj."""

import json
import struct
import sys
from io import BytesIO

import eccodes
import numpy as np

KEYS = (
    "dataDate dataTime endStep startStep stepUnits typeOfLevel level units shortName Nx Ny "
    "alternativeRowScanning jPointsAreConsecutive missingValue longitudeOfFirstGridPointInDegrees "
    "latitudeOfFirstGridPointInDegrees iScansNegatively jScansPositively gridType "
    "iDirectionIncrementInDegrees jDirectionIncrementInDegrees shapeOfTheEarth Latin1InDegrees "
    "Latin2InDegrees LaDInDegrees LoVInDegrees DxInMetres DyInMetres uvRelativeToGrid "
    "stepType typeOfStatisticalProcessing"
).split()


def decode(content):
    handle = eccodes.codes_new_from_message(content)
    if handle is None:
        raise ValueError("Empty GRIB message")
    try:
        metadata = {}
        for key in KEYS:
            try:
                metadata[key] = eccodes.codes_get(handle, key)
            except eccodes.CodesInternalError:
                pass
        nx, ny = int(metadata["Nx"]), int(metadata["Ny"])
        if not 0 < nx * ny <= 4_000_000:
            raise ValueError("Grid exceeds codec memory budget")
        values = np.asarray(eccodes.codes_get_values(handle), dtype=np.float32).reshape(ny, nx)
        output = BytesIO()
        np.savez(output, values=values, metadata=json.dumps(metadata))
        return output.getvalue()
    finally:
        eccodes.codes_release(handle)


def exact(stream, size):
    data = bytearray()
    while len(data) < size:
        block = stream.read(size - len(data))
        if not block:
            raise EOFError("Truncated codec request")
        data.extend(block)
    return bytes(data)


def main():
    while header := sys.stdin.buffer.read(8):
        size = struct.unpack(">Q", header)[0]
        if size == 0:
            return
        if size > 16 * 1024 * 1024:
            raise ValueError("Input exceeds codec budget")
        try:
            result = decode(exact(sys.stdin.buffer, size))
        except Exception:
            result = b""
        sys.stdout.buffer.write(struct.pack(">Q", len(result)))
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
