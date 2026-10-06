"""Append-only JSONL files: the raw dataset is the product, so every message lands on disk.

`rotate_daily=True` writes `name-YYYY-MM-DD.jsonl` (UTC) so old days can be
compressed or shipped off the volume without touching the live file.
"""

import gzip
import json
import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def gzip_file(path: Path) -> Path:
    """Compress `path` to `path.gz` and remove the original (no-op if it is gone)."""
    if not path.exists():
        return path
    gz = path.with_name(path.name + ".gz")
    with open(path, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    path.unlink()
    return gz


class JsonlWriter:
    def __init__(self, path: str | Path, rotate_daily: bool = False, compress_rotated: bool = False):
        self.base = Path(path)
        self.rotate = rotate_daily
        # gzip each finished day in the background (swap dumps are large and compress ~5x)
        self.compress_rotated = compress_rotated and rotate_daily
        self.base.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self._day: str | None = None
        self._path: Path | None = None

    def path_for(self, now: float) -> Path:
        if not self.rotate:
            return self.base
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        return self.base.with_name(f"{self.base.stem}-{day}{self.base.suffix}")

    def write(self, obj: Any, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        day = time.strftime("%Y-%m-%d", time.gmtime(now)) if self.rotate else ""
        if self._fh is None or day != self._day:
            finished = None
            if self._fh is not None:
                self._fh.close()
                finished = self._path
            self._path = self.path_for(now)
            self._fh = open(self._path, "a", buffering=1)  # noqa: SIM115 - long-lived handle
            self._day = day
            if finished is not None and self.compress_rotated and finished != self._path:
                threading.Thread(target=gzip_file, args=(finished,), daemon=True).start()
        self._fh.write(json.dumps(obj, separators=(",", ":")) + "\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
