"""Wallet memory: what each wallet did early in the launches Ray scored, and what those became.

A launch is noted once, at its first decision-time score: its early buyers (buys in its first 60 s)
and which of them dumped before that decision (app/features.early_activity). Its first outcome adds
to each early buyer's record and to its dev's. The features of a launch never count the launch
itself (`features` takes its own contribution back out when it is scored again at 5 or 10 minutes).

Kept in memory, saved to data/ray/wallets.json.gz, and rebuilt from the row archive and the outcome
journal when that file is missing. Wallets seen early only once are forgotten after a day, all
others after a week without being seen; launches after 6 hours (their outcomes are in by then).
"""

import gzip
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .features import early_activity, memory_features

KEEP_S = 7 * 86_400
ONE_SHOT_S = 86_400
LAUNCH_KEEP_S = 6 * 3_600


class WalletBook:
    def __init__(self) -> None:
        self.wallets: dict[str, list[float]] = {}  # wallet -> [launches, dumps, resolved, traps, last]
        self.devs: dict[str, list[float]] = {}  # dev -> [launches, resolved, traps, last]
        self.launches: dict[str, dict[str, Any]] = {}  # mint -> early, dumpers, dev, at, label

    def __len__(self) -> int:
        return len(self.wallets)

    # --- reading ------------------------------------------------------------------------------
    def features(self, row: dict[str, Any], dslot: int) -> dict[str, float]:
        """Memory features of this launch at this decision slot, from earlier launches only."""
        early, _ = early_activity(row, dslot)
        own = self.launches.get(row["mint"])
        own_early = set(own["early"]) if own else set()
        own_dumpers = set(own["dumpers"]) if own else set()
        own_label = own["label"] if own else None

        def stats(u: str) -> tuple[int, int, int, int]:
            w = self.wallets.get(u)
            if w is None:
                return 0, 0, 0, 0
            launches, dumps, resolved, traps = int(w[0]), int(w[1]), int(w[2]), int(w[3])
            if u in own_early:
                launches -= 1
                dumps -= u in own_dumpers
                if own_label is not None:
                    resolved -= 1
                    traps -= own_label == "trap"
            return launches, dumps, resolved, traps

        def dev_stats(dev: str) -> tuple[int, int, int]:
            d = self.devs.get(dev)
            if d is None:
                return 0, 0, 0
            launches, resolved, traps = int(d[0]), int(d[1]), int(d[2])
            if own and own["dev"] == dev:
                launches -= 1
                if own_label is not None:
                    resolved -= 1
                    traps -= own_label == "trap"
            return launches, resolved, traps

        return memory_features(early, row.get("dev"), stats, dev_stats)

    # --- writing ------------------------------------------------------------------------------
    def note_launch(self, row: dict[str, Any], dslot: int, at: float) -> bool:
        """Remember this launch's early buyers (once per launch)."""
        if row["mint"] in self.launches:
            return False
        early, dumpers = early_activity(row, dslot)
        return self._note(row["mint"], early, dumpers, row.get("dev"), at)

    def _note(
        self, mint: str, early: dict[str, float], dumpers: set[str], dev: str | None, at: float
    ) -> bool:
        if mint in self.launches:
            return False
        for u in early:
            w = self.wallets.setdefault(u, [0, 0, 0, 0, at])
            w[0] += 1
            w[1] += u in dumpers
            w[4] = max(w[4], at)
        if dev:
            d = self.devs.setdefault(dev, [0, 0, 0, at])
            d[0] += 1
            d[3] = max(d[3], at)
        self.launches[mint] = {
            "early": sorted(early),
            "dumpers": sorted(dumpers),
            "dev": dev,
            "at": at,
            "label": None,
        }
        return True

    def note_outcome(self, mint: str, label: str | None) -> bool:
        """The launch's first outcome, added to its early buyers' and its dev's records."""
        rec = self.launches.get(mint)
        if rec is None or rec["label"] is not None or label is None:
            return False
        rec["label"] = label
        trap = label == "trap"
        for u in rec["early"]:
            w = self.wallets.get(u)
            if w is not None:
                w[2] += 1
                w[3] += trap
        d = self.devs.get(rec["dev"]) if rec["dev"] else None
        if d is not None:
            d[1] += 1
            d[2] += trap
        return True

    def prune(self, now: float) -> int:
        gone = [
            u
            for u, w in self.wallets.items()
            if w[4] < now - KEEP_S or (w[0] <= 1 and w[4] < now - ONE_SHOT_S)
        ]
        for u in gone:
            del self.wallets[u]
        for dev in [d for d, v in self.devs.items() if v[3] < now - KEEP_S]:
            del self.devs[dev]
        for mint in [m for m, v in self.launches.items() if v["at"] < now - LAUNCH_KEEP_S]:
            del self.launches[mint]
        return len(gone)

    # --- keeping ------------------------------------------------------------------------------
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt") as fh:
            json.dump({"wallets": self.wallets, "devs": self.devs, "launches": self.launches}, fh)
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "WalletBook | None":
        try:
            with gzip.open(path, "rt") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
        book = cls()
        book.wallets = data.get("wallets") or {}
        book.devs = data.get("devs") or {}
        book.launches = data.get("launches") or {}
        return book

    @classmethod
    def rebuild(cls, rows: Iterable[dict[str, Any]], outcomes: list[dict[str, Any]]) -> "WalletBook":
        """From archived rows (each launch noted at its first scored decision) and the outcome
        journal (each launch's first outcome, when it was known), in time order. Rows are read one
        at a time and only their early buyers kept, so a day of archive fits in memory."""
        events: list[tuple[float, int, Any]] = []
        for row in rows:
            scored = row.get("scored") or {}
            if not scored:
                continue
            first = min(scored.values(), key=lambda e: float(e["at"]))
            early, dumpers = early_activity(row, int(first["slot"]))
            events.append((float(first["at"]), 0, (row["mint"], early, dumpers, row.get("dev"))))
        firsts: dict[str, dict[str, Any]] = {}
        for o in outcomes:
            if o.get("D") and o.get("status") == "ok":
                cur = firsts.get(o["mint"])
                if cur is None or float(o["entry_at"]) < float(cur["entry_at"]):
                    firsts[o["mint"]] = o
        for mint, o in firsts.items():
            # known when it was read (live, the memory learns it then), else at its due time
            at = o.get("read_at") or o.get("due") or float(o["entry_at"]) + 1800
            events.append((float(at), 1, (mint, o.get("label"))))
        events.sort(key=lambda e: (e[0], e[1]))
        book = cls()
        for at, kind, ev in events:
            if kind == 0:
                book._note(*ev, at)
            else:
                book.note_outcome(*ev)
        return book
