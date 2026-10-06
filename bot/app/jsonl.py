"""Append-only JSONL files: the raw dataset is the product, so every message lands on disk."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class JsonlWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", buffering=1)  # noqa: SIM115 - long-lived handle

    def write(self, obj: Any) -> None:
        self._fh.write(json.dumps(obj, separators=(",", ":")) + "\n")

    def close(self) -> None:
        self._fh.close()


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return
    with open(p) as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
