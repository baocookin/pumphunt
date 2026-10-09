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
longer holds ("suspended"), it is computed, shown and journaled but decides nothing.

Amended 09/10/2026 evening (wave A): judged by money, not by the trap share. On 387 rows a trap count
ranked the filters wrongly both ways: N-MMAAS-WAVE-STREAM fired on 7 points more traps, yet the 0.5 SOL
ticket did 11 points better on its rows than on the rows of the same band x decision time (it caught
the big winners too); SH-SG-1 fired on only 6 points more traps, yet its rows did 21 points worse.
So a filter now enters when, on >= 30 rows from >= 10 launches, the ticket did at least 10 points
worse on average where it fired than the same band x decision time did where it did not, with the
lower end of a 95% interval clustered by launch above zero; it keeps deciding while it stays at least
5 points worse. The trap and winner shares are still computed and shown. The tiers stay those of
research/sieve/filters.py: the rule never makes an info filter decide (PREREG-SIEVE-R1 section 5
for promotions).

Which filters decide is saved at each refresh (data/ray/rules.json) and read back at start, so a
restart or a deploy keeps the keeping bar for the filters that were deciding.

The risk shown is the journal's trap share for the launch's band x decision time (>= 30 rows), else
for its band (>= 30 rows), else the founding pool's (in-sample, said so).
"""

from collections import defaultdict
from typing import Any

WINDOW_S = 7 * 86_400
MIN_ROWS, MIN_MINTS = 30, 10
ENTER_SAVED, KEEP_SAVED = 0.10, 0.05  # mean net of the ticket, points of 1: the filter's rows did worse
MIN_CELL = 30
MIN_TIME_CELL = 10  # rows a band x decision time needs to be shown in the time profile


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


def clustered_mean(pairs: list[tuple[Any, float]]) -> tuple[float | None, float | None, float | None]:
    """Mean of the values and its 95% interval, clustered by key (a launch's rows at 2, 5 and 10
    minutes move together, so they count as one draw)."""
    n = len(pairs)
    if not n:
        return None, None, None
    mean = sum(v for _, v in pairs) / n
    dev: dict[Any, float] = defaultdict(float)
    for k, v in pairs:
        dev[k] += v - mean
    m = len(dev)
    if m < 2:
        return mean, None, None
    se = (sum(x * x for x in dev.values()) / (n * n) * m / (m - 1)) ** 0.5
    return mean, mean - 1.96 * se, mean + 1.96 * se


def filter_record(rows: list[dict[str, Any]], fid: str, was_ok: bool = False) -> dict[str, Any]:
    """A filter's record on these rows: the ticket's mean net, trap and winner shares where it fired,
    against what the same band x decision time gave on the rows where it did not fire (scored and
    silent). `saved` is how much worse its rows did (expected net - net), with a 95% interval
    clustered by launch. `was_ok`: it decides now, so the keeping bar applies, not the entry one."""
    on = [r for r in rows if fid in fired_ids(r)]
    cells: dict[tuple[Any, Any], list[float]] = defaultdict(lambda: [0, 0, 0, 0.0])
    for r in rows:
        if fid in fired_ids(r) or fid in (r.get("unscored") or []):
            continue
        c = cells[(r["band"], r["D"])]
        c[0] += 1
        c[1] += r.get("label") == "trap"
        c[2] += r.get("label") == "winner"
        c[3] += float(r.get("net") or 0.0)
    exp_t = exp_w = exp_n = net_used = 0.0
    diffs: list[tuple[Any, float]] = []
    for r in on:
        c = cells.get((r["band"], r["D"]))
        if c and c[0]:
            exp_t += c[1] / c[0]
            exp_w += c[2] / c[0]
            exp_n += c[3] / c[0]
            net_used += float(r.get("net") or 0.0)
            diffs.append((r.get("mint"), c[3] / c[0] - float(r.get("net") or 0.0)))
    n = len(on)
    used = len(diffs)
    traps = sum(r.get("label") == "trap" for r in on)
    winners = sum(r.get("label") == "winner" for r in on)
    saved, lo, hi = clustered_mean(diffs)
    rec: dict[str, Any] = {
        "n": n,
        "mints": len({r.get("mint") for r in on}),
        "traps": traps,
        "winners": winners,
        "trap_on": traps / n if n else None,
        "win_on": winners / n if n else None,
        "trap_exp": exp_t / used if used else None,
        "win_exp": exp_w / used if used else None,
        "net_on": net_used / used if used else None,
        "net_exp": exp_n / used if used else None,
        "saved": saved,
        "saved_ci": None if lo is None else [lo, hi],
    }
    if n < MIN_ROWS or rec["mints"] < MIN_MINTS or not used:
        rec["status"] = "unproven"
        return rec
    entered = saved >= ENTER_SAVED and lo is not None and lo > 0
    rec["status"] = "ok" if (saved >= KEEP_SAVED if was_ok else entered) else "suspended"
    return rec


class LiveRules:
    """The rule's current state, refreshed from the journal by the engine."""

    def __init__(self) -> None:
        self.at = 0.0
        self.rows = 0
        self.cells: dict[tuple[str, int], tuple[int, int, float]] = {}  # rows, traps, net sum
        self.bands: dict[str, tuple[int, int, float]] = {}
        self.filters: dict[str, dict[str, Any]] = {}
        self.restored: set[str] = set()  # filters that decided before a restart (rules.json)

    def restore(self, ok: list[str]) -> None:
        """The filters that decided when the app stopped: the keeping bar, not the entry one, applies
        to them at the first refresh (a deploy does not make a confirmed filter prove itself again)."""
        self.restored = set(ok)

    def refresh(self, lines: list[dict[str, Any]], now: float, ids: list[str]) -> None:
        rows = journal_rows(lines, now - WINDOW_S)
        cells: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0, 0, 0.0])
        bands: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0.0])
        for r in rows:
            trap = r.get("label") == "trap"
            for c in (cells[(r["band"], int(r["D"]))], bands[r["band"]]):
                c[0] += 1
                c[1] += trap
                c[2] += float(r.get("net") or 0.0)
        self.cells = {k: (int(v[0]), int(v[1]), v[2]) for k, v in cells.items()}
        self.bands = {k: (int(v[0]), int(v[1]), v[2]) for k, v in bands.items()}
        was = {fid for fid, rec in self.filters.items() if rec["status"] == "ok"} | self.restored
        self.restored = set()
        self.filters = {fid: filter_record(rows, fid, fid in was) for fid in ids}
        self.rows = len(rows)
        self.at = now

    def allows(self, fid: str) -> bool:
        """Whether this filter may decide a verdict now: new launches have confirmed it."""
        rec = self.filters.get(fid)
        return rec is not None and rec["status"] == "ok"

    def record(self, fid: str) -> dict[str, Any] | None:
        return self.filters.get(fid)

    def base(self, band: str, D: int) -> tuple[int, int, str, float] | None:
        """(rows, traps, basis, mean net) of the journal for this band x decision time, else the band."""
        n, k, net = self.cells.get((band, D), (0, 0, 0.0))
        if n >= MIN_CELL:
            return n, k, f"coin mới 7 ngày qua: tầng {band} SOL lúc {D // 60} phút", net / n
        n, k, net = self.bands.get(band, (0, 0, 0.0))
        if n >= MIN_CELL:
            return n, k, f"coin mới 7 ngày qua: tầng {band} SOL (mọi mốc)", net / n
        return None

    def by_time(self, band: str) -> list[dict[str, Any]]:
        """The band's trap share and mean net at each decision time (rows >= MIN_TIME_CELL)."""
        out = []
        for D in (120, 300, 600):
            n, k, net = self.cells.get((band, D), (0, 0, 0.0))
            if n >= MIN_TIME_CELL:
                out.append({"D": D, "n": n, "trap": k / n, "net": net / n})
        return out

    def snapshot(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "rows": self.rows,
            "suspended": sorted(f for f, r in self.filters.items() if r["status"] == "suspended"),
            "ok": sorted(f for f, r in self.filters.items() if r["status"] == "ok"),
        }
