import atexit
import json
import os
import select
import struct
import subprocess
import sys
import threading
import time
from io import BytesIO

import numpy as np

from wxspot.weather import SourceError

_lock = threading.Lock()
_process = None


def close_codec():
    global _process
    if _process is not None:
        try:
            _process.stdin.write(struct.pack(">Q", 0))
            _process.stdin.flush()
            _process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            _process.kill()
            _process.wait(timeout=5)
        finally:
            _process.stdin.close()
            _process.stdout.close()
            _process = None


atexit.register(close_codec)


def read_exact(size, deadline):
    data = bytearray()
    while len(data) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([_process.stdout], [], [], remaining)[0]:
            raise TimeoutError("Model codec timed out")
        block = os.read(_process.stdout.fileno(), min(size - len(data), 65536))
        if not block:
            raise OSError("Model codec exited")
        data.extend(block)
    return bytes(data)


def isolated_grib(content):
    global _process
    with _lock:
        if _process is None or _process.poll() is not None:
            close_codec()
            _process = subprocess.Popen(
                [sys.executable, "-u", "-m", "wxspot.providers.grib_io"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                bufsize=0,
            )
        try:
            request = struct.pack(">Q", len(content)) + content
            view = memoryview(request)
            while view:
                written = _process.stdin.write(view)
                if not written:
                    raise OSError("Model codec input closed")
                view = view[written:]
            deadline = time.monotonic() + 45
            size = struct.unpack(">Q", read_exact(8, deadline))[0]
            if not 0 < size <= 32 * 1024 * 1024:
                raise ValueError("Invalid model codec result size")
            with np.load(BytesIO(read_exact(size, deadline)), allow_pickle=False) as data:
                return data["values"], json.loads(str(data["metadata"]))
        except Exception as exc:
            close_codec()
            raise SourceError(
                "source_unavailable", "Model GRIB decoding failed within its bounded codec process."
            ) from exc
