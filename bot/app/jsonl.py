"""Append-only JSONL files: the raw dataset is the product, so every message lands on disk.

`rotate_daily=True` writes `name-YYYY-MM-DD.jsonl` (UTC) so old days can be
compressed or shipped off the volume without touching the live file.
"""

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class JsonlWriter:
    def __init__(self, path: str | Path, rotate_daily: bool = False):
        self.base = Path(path)
        self.rotate = rotate_daily
        self.base.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self._day: str | None = None

    def path_for(self, now: float) -> Path:
        if not self.rotate:
            return self.base
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        return self.base.with_name(f"{self.base.stem}-{day}{self.base.suffix}")

    def write(self, obj: Any, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        day = time.strftime("%Y-%m-%d", time.gmtime(now)) if self.rotate else ""
        if self._fh is None or day != self._day:
            if self._fh is not None:
                self._fh.close()
            self._fh = open(self.path_for(now), "a", buffering=1)  # noqa: SIM115 - long-lived handle
            self._day = day
        self._fh.write(json.dumps(obj, separators=(",", ":")) + "\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return
    with open(p) as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
