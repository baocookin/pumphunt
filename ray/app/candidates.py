"""Candidate scan: threshold rules on the decision-time features that the journal of the last 7 days
supports (registered 09/10/2026, docs/PREREG-RAY-L3.md).

PREREG-RAY-L2's method, run by itself every hour: the settled decision-time rows that carry features
are split by entry time; each feature's rules (its 20th and 33rd percentiles of the earlier 60% as
"<=", its 67th and 80th as ">=") that left the 0.5 SOL ticket >= 10 points worse than the same SOL
band x decision time on the earlier 60% are checked unchanged on the later 40%. A candidate passes
the live rule's entry bar there (>= 30 rows, >= 10 launches, >= 10 points worse, the lower end of the
95% interval clustered by launch above zero) and Benjamini-Hochberg at q = 0.10 over all the later
checks.

Candidates are shown, never used: none changes a verdict or the risk. One becomes a filter only when
the owner approves it; it is then registered under a new frozen id and, like every filter, decides
nothing until the live rule confirms it on data after its registration. Only warnings are searched
(rules where the ticket did worse): Ray never looks for, or shows, a buy signal.
"""

import math
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from .live_rules import ENTER_SAVED, MIN_MINTS, MIN_ROWS, WINDOW_S, clustered_mean, fired_ids, journal_rows
from .model import FEATURES, VI

QUANTILES = ((0.20, "<="), (0.33, "<="), (0.67, ">="), (0.80, ">="))
# the features a registered filter already measures (another threshold would be a new version of it)
MEASURED_BY = {
    "n120": "RAY-HOT-v1",
    "wash_share": "RAY-WASH-v1",
    "wallets120": "RAY-CROWD-v1",
    "dd_pre": "RAY-PEAK-v1",
    "serial_vol": "RAY-SERIAL-v1",
}
SPLIT = 0.6
MIN_SCAN_ROWS = 200
EARLY_ROWS = 25
BH_Q = 0.10


def _record(part: list[dict[str, Any]], fires: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    """The rule's rows against the same band x decision time where it did not fire (the live rule's
    measure): mean of (expected net - net), 95% interval clustered by launch, trap shares."""
    on = [r for r in part if fires(r)]
    if not on:
        return None
    cells: dict[tuple[Any, Any], list[float]] = defaultdict(lambda: [0, 0, 0.0])
    for r in part:
        if not fires(r):
            c = cells[(r["band"], r["D"])]
            c[0] += 1
            c[1] += r.get("label") == "trap"
            c[2] += float(r.get("net") or 0.0)
    diffs: list[tuple[Any, float]] = []
    exp_t = 0.0
    for r in on:
        c = cells.get((r["band"], r["D"]))
        if c and c[0]:
            diffs.append((r.get("mint"), c[2] / c[0] - float(r.get("net") or 0.0)))
            exp_t += c[1] / c[0]
    if not diffs:
        return None
    saved, lo, hi = clustered_mean(diffs)
    return {
        "n": len(on),
        "mints": len({r.get("mint") for r in on}),
        "saved": saved,
        "ci": None if lo is None else [lo, hi],
        "trap_on": sum(r.get("label") == "trap" for r in on) / len(on),
        "trap_exp": exp_t / len(diffs),
    }


def _p_value(rec: dict[str, Any] | None) -> float:
    """One-sided p of `saved` > 0 from its clustered interval (normal)."""
    if not rec or not rec["ci"] or rec["saved"] is None:
        return 1.0
    se = (rec["ci"][1] - rec["ci"][0]) / (2 * 1.96)
    if se <= 0:
        return 0.0 if rec["saved"] > 0 else 1.0
    return 0.5 * math.erfc(rec["saved"] / se / math.sqrt(2))


def _rule(name: str, d: str, thr: float) -> Callable[[dict[str, Any]], bool]:
    def fires(r: dict[str, Any]) -> bool:
        v = (r.get("features") or {}).get(name)
        if v is None:
            return False
        return float(v) >= thr if d == ">=" else float(v) <= thr

    return fires


def scan(lines: list[dict[str, Any]], now: float, registered: list[str]) -> dict[str, Any]:
    """The candidates on the journal of the last 7 days. `registered`: the filters that can decide a
    verdict (each candidate shows how many of its rows they already flag)."""
    rows = [r for r in journal_rows(lines, now - WINDOW_S) if r.get("features") and r.get("label")]
    rows.sort(key=lambda r: float(r.get("entry_at") or 0))
    out: dict[str, Any] = {"at": now, "rows": len(rows), "tested": 0, "candidates": []}
    if len(rows) < MIN_SCAN_ROWS:
        out["note"] = f"chưa đủ dữ liệu: cần ≥ {MIN_SCAN_ROWS} dòng có đặc trưng"
        return out
    cut = int(len(rows) * SPLIT)
    earlier, later = rows[:cut], rows[cut:]
    out["split_at"] = float(later[0]["entry_at"])
    out["earlier_rows"], out["later_rows"] = len(earlier), len(later)
    tests = []
    for name in FEATURES:
        vals = sorted(float(r["features"][name]) for r in earlier if r["features"].get(name) is not None)
        if not vals:
            continue
        for q, d in QUANTILES:
            thr = vals[int(q * (len(vals) - 1))]
            fires = _rule(name, d, thr)
            rd = _record(earlier, fires)
            if rd is None or rd["n"] < EARLY_ROWS or rd["saved"] < ENTER_SAVED:
                continue
            rv = _record(later, fires)
            t = {"feature": name, "dir": d, "thr": thr, "q": q, "earlier": rd, "later": rv}
            tests.append({**t, "p": _p_value(rv)})
    out["tested"] = len(tests)
    # Benjamini-Hochberg over every later check
    tests.sort(key=lambda t: t["p"])
    m = len(tests)
    k = max([i + 1 for i, t in enumerate(tests) if t["p"] <= BH_Q * (i + 1) / m] or [0])
    reg = set(registered)
    for t in tests[:k]:
        rv = t["later"]
        if not (
            rv
            and rv["n"] >= MIN_ROWS
            and rv["mints"] >= MIN_MINTS
            and rv["saved"] >= ENTER_SAVED
            and rv["ci"]
            and rv["ci"][0] > 0
        ):
            continue
        fires = _rule(t["feature"], t["dir"], t["thr"])
        on = [r for r in rows if fires(r)]
        flagged = sum(1 for r in on if fired_ids(r) & reg)
        out["candidates"].append(
            {
                **t,
                "vi": VI.get(t["feature"], t["feature"]),
                "measured_by": MEASURED_BY.get(t["feature"]),
                "overlap": flagged / len(on) if on else 0.0,
            }
        )
    return out
