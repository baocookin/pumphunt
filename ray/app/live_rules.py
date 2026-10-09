"""Live rule for the filters, on the outcome journal (registered 09/10/2026, before any later data).

Why: on its first 226 decision-time outcomes (09/10/2026, 15:05-17:05 UTC) the active filters did
not hold up out of sample. SH-DEV-1 fired on 43 rows with 60% traps against 66% expected from the
rows' SOL band x decision time; N-MMAAS-WAVE-STREAM on 33 rows with 61% against 57%, and twice the
winners; N-MMAAS-SPLDIST (shadow) on 44 rows with 39% against 63%. The founding pool's shares that
Ray showed (80-90%) were in-sample.

The rule. A filter decides a verdict (TRÁNH for an active one, CẢNH GIÁC for a shadow one) only
once new launches confirm it: in the journal of the last 7 days it has fired on >= 30
decision-time rows from >= 10 launches and, on those rows,
  - the trap share is at least 10 points above the share the same SOL band x decision time gives
    on the rows where it did not fire, and the lower end of its 95% Wilson interval is not below
    that share, and
  - the winner share is not above the share they give.
A confirmed filter keeps deciding while its trap share stays at least 5 points above and its winner
share not above (amended the same day after SH-SG-1 went in and out within an hour on 30-40 rows:
entering now needs evidence, leaving needs it gone). Until then ("unproven"), or when its record no
longer holds ("suspended"), it is computed, shown and journaled but decides nothing. The tiers stay those of
research/sieve/filters.py: the rule never makes an info filter decide (PREREG-SIEVE-R1 section 5
for promotions).

The risk shown is the journal's trap share for the launch's band x decision time (>= 30 rows), else
for its band (>= 30 rows), else the founding pool's (in-sample, said so).
"""

from collections import defaultdict
from typing import Any

from .sieve import wilson

WINDOW_S = 7 * 86_400
MIN_ROWS, MIN_MINTS = 30, 10
ENTER_LIFT, KEEP_LIFT = 0.10, 0.05
MIN_CELL = 30


def journal_rows(lines: list[dict[str, Any]], since: float) -> list[dict[str, Any]]:
    """Settled decision-time outcomes since `since`, one per score (the last written)."""
    latest: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for r in lines:
        if (
            r.get("D")
            and r.get("status") == "ok"
            and r.get("band")
            and float(r.get("entry_at") or 0) >= since
        ):
            latest[(r.get("mint"), r.get("key"), r.get("score_at"))] = r
    return list(latest.values())


def fired_ids(r: dict[str, Any]) -> set[str]:
    f = r.get("fired") or {}
    return set(f.get("active") or []) | set(f.get("shadow") or []) | set(f.get("info") or [])


def filter_record(rows: list[dict[str, Any]], fid: str, was_ok: bool = False) -> dict[str, Any]:
    """A filter's record on these rows: its trap and winner shares when it fired, and the shares the
    same band x decision time give on the rows where it did not fire (scored and silent). `was_ok`:
    it decides now, so the keeping bar applies instead of the entry one."""
    on = [r for r in rows if fid in fired_ids(r)]
    cells: dict[tuple[Any, Any], list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if fid in fired_ids(r) or fid in (r.get("unscored") or []):
            continue
        c = cells[(r["band"], r["D"])]
        c[0] += 1
        c[1] += r.get("label") == "trap"
        c[2] += r.get("label") == "winner"
    exp_t = exp_w = 0.0
    used = 0
    for r in on:
        c = cells.get((r["band"], r["D"]))
        if c and c[0]:
            exp_t += c[1] / c[0]
            exp_w += c[2] / c[0]
            used += 1
    n = len(on)
    traps = sum(r.get("label") == "trap" for r in on)
    winners = sum(r.get("label") == "winner" for r in on)
    rec: dict[str, Any] = {
        "n": n,
        "mints": len({r.get("mint") for r in on}),
        "traps": traps,
        "winners": winners,
        "trap_on": traps / n if n else None,
        "win_on": winners / n if n else None,
        "trap_exp": exp_t / used if used else None,
        "win_exp": exp_w / used if used else None,
    }
    if n < MIN_ROWS or rec["mints"] < MIN_MINTS or not used:
        rec["status"] = "unproven"
        return rec
    lift = rec["trap_on"] - rec["trap_exp"]
    fewer_winners = rec["win_on"] <= rec["win_exp"]
    if was_ok:
        ok = lift >= KEEP_LIFT and fewer_winners
    else:
        ok = lift >= ENTER_LIFT and wilson(traps, n)[0] >= rec["trap_exp"] and fewer_winners
    rec["status"] = "ok" if ok else "suspended"
    return rec


class LiveRules:
    """The rule's current state, refreshed from the journal by the engine."""

    def __init__(self) -> None:
        self.at = 0.0
        self.rows = 0
        self.cells: dict[tuple[str, int], tuple[int, int]] = {}
        self.bands: dict[str, tuple[int, int]] = {}
        self.filters: dict[str, dict[str, Any]] = {}

    def refresh(self, lines: list[dict[str, Any]], now: float, ids: list[str]) -> None:
        rows = journal_rows(lines, now - WINDOW_S)
        cells: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
        bands: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in rows:
            trap = r.get("label") == "trap"
            for c in (cells[(r["band"], int(r["D"]))], bands[r["band"]]):
                c[0] += 1
                c[1] += trap
        self.cells = {k: (v[0], v[1]) for k, v in cells.items()}
        self.bands = {k: (v[0], v[1]) for k, v in bands.items()}
        was = {fid for fid, rec in self.filters.items() if rec["status"] == "ok"}
        self.filters = {fid: filter_record(rows, fid, fid in was) for fid in ids}
        self.rows = len(rows)
        self.at = now

    def allows(self, fid: str) -> bool:
        """Whether this filter may decide a verdict now: new launches have confirmed it."""
        rec = self.filters.get(fid)
        return rec is not None and rec["status"] == "ok"

    def record(self, fid: str) -> dict[str, Any] | None:
        return self.filters.get(fid)

    def base(self, band: str, D: int) -> tuple[int, int, str] | None:
        """(rows, traps, basis) of the journal for this band x decision time, else the band."""
        n, k = self.cells.get((band, D), (0, 0))
        if n >= MIN_CELL:
            return n, k, f"coin mới 7 ngày qua: tầng {band} SOL lúc {D // 60} phút"
        n, k = self.bands.get(band, (0, 0))
        if n >= MIN_CELL:
            return n, k, f"coin mới 7 ngày qua: tầng {band} SOL (mọi mốc)"
        return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "rows": self.rows,
            "suspended": sorted(f for f, r in self.filters.items() if r["status"] == "suspended"),
            "ok": sorted(f for f, r in self.filters.items() if r["status"] == "ok"),
        }
