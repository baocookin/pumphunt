"""Hypothesis C ("survivor entry") metrics and analysis — pure functions.

For each graduated token we know T0 (migration time). From 1-minute candles we
compute, for every entry delay d and horizon h:
    gross = P(T0 + d + h) / P(T0 + d) - 1
    net   = (1 + gross) * (1 - cost) - 1          cost = round-trip bps / 1e4
plus the worst drawdown inside the horizon (what a stop-loss would have seen)
and volume buckets (liquidity proxy, since historical reserves aren't free).

`summarize` then reports distribution stats and applies the pre-registered
kill criteria for the d=30, h=60 cell. Pre-registered means: decided before
seeing data, written in docs/RESEARCH.md, not tuned afterwards.
"""

from collections.abc import Sequence
from statistics import median
from typing import Any

from .gecko import Candle


def _last_candle(candles: Sequence[Candle], t: int) -> Candle | None:
    """Last candle starting at or before t (None if the pool had no trade yet)."""
    best = None
    for c in candles:
        if c.ts <= t:
            best = c
        else:
            break
    return best


def _price_at(candles: Sequence[Candle], t: int) -> float | None:
    """AMM mark at t: close of the last traded minute. PumpSwap canonical LP is burned,
    so the pool can't be pulled and that price is sellable (ignoring our own impact);
    callers record how stale it is and can filter."""
    c = _last_candle(candles, t)
    return c.close if c else None


def _min_low(candles: Sequence[Candle], start: int, end: int) -> float | None:
    lows = [c.low for c in candles if start < c.ts <= end]
    return min(lows) if lows else None


def _volume(candles: Sequence[Candle], start: int, end: int) -> float:
    return sum(c.volume_usd for c in candles if start <= c.ts < end)


def compute_metrics(
    candles: Sequence[Candle],
    t0: int,
    delays_min: Sequence[int],
    horizons_min: Sequence[int],
    cost_bps: int,
    now: float | None = None,
) -> dict[str, Any]:
    """`now` guards against reading the future: the AMM mark carries forward from the last
    trade, so without it a 2-hour-old pool would happily report a 24-hour return."""
    cost = cost_bps / 10_000
    out: dict[str, Any] = {"t0": t0, "n_candles": len(candles), "cells": {}}
    if not candles:
        out["no_data"] = True
        out["reason"] = "no_candles"  # the pool exists but nobody traded in the window
        return out
    for d in delays_min:
        t_in = t0 + d * 60
        p_in = _price_at(candles, t_in)
        for h in horizons_min:
            t_out = t_in + h * 60
            key = f"d{d}_h{h}"
            if now is not None and t_out > now:
                out["cells"][key] = None  # horizon not observable yet
                continue
            p_out = _price_at(candles, t_out)
            if p_in is None or p_out is None or p_in <= 0:
                out["cells"][key] = None
                continue
            gross = p_out / p_in - 1
            low = _min_low(candles, t_in, t_out)
            last_out = _last_candle(candles, t_out)
            out["cells"][key] = {
                "gross": gross,
                "net": (1 + gross) * (1 - cost) - 1,
                "mdd": (low / p_in - 1) if low else 0.0,
                # seconds since the pool last traded at exit time: large = dead pool,
                # the mark is nominal and a real sell would move it.
                "exit_stale_s": t_out - last_out.ts if last_out else None,
            }
    out["vol_0_30m"] = _volume(candles, t0, t0 + 1800)
    out["vol_30_60m"] = _volume(candles, t0 + 1800, t0 + 3600)
    out["vol_1_6h"] = _volume(candles, t0 + 3600, t0 + 6 * 3600)
    out["vol_6_24h"] = _volume(candles, t0 + 6 * 3600, t0 + 24 * 3600)
    if now is not None and t0 + 24 * 3600 > now:
        out["alive_24h"] = None
    else:
        out["alive_24h"] = out["vol_6_24h"] > 0 and _price_at(candles, t0 + 24 * 3600) is not None
    return out


def _cell_stats(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0}
    vals_sorted = sorted(vals)
    n = len(vals)
    pos = sorted((v for v in vals if v > 0), reverse=True)
    total_pos = sum(pos)
    top2 = pos[: max(1, round(n * 0.02))]
    return {
        "n": n,
        "median": median(vals),
        "mean": sum(vals) / n,
        "win_rate": sum(1 for v in vals if v > 0) / n,
        "p10": vals_sorted[int(0.10 * (n - 1))],
        "p90": vals_sorted[int(0.90 * (n - 1))],
        # share of all positive PnL coming from the top 2% of names: lottery detector
        "top2pct_share": (sum(top2) / total_pos) if total_pos > 0 else 0.0,
    }


def summarize(
    rows: Sequence[dict[str, Any]], delays_min: Sequence[int], horizons_min: Sequence[int]
) -> dict[str, Any]:
    cells: dict[str, dict[str, Any]] = {}
    for d in delays_min:
        for h in horizons_min:
            key = f"d{d}_h{h}"
            nets = [
                r["cells"][key]["net"] for r in rows if r.get("cells") and r["cells"].get(key) is not None
            ]
            cells[key] = _cell_stats(nets)
    harvested = len(rows)
    with_data = sum(1 for r in rows if not r.get("no_data"))
    alive = sum(1 for r in rows if r.get("alive_24h"))
    no_data: dict[str, int] = {}
    for r in rows:
        if r.get("no_data"):
            reason = str(r.get("reason") or "unknown")
            no_data[reason] = no_data.get(reason, 0) + 1
    return {
        "harvested": harvested,
        "with_data": with_data,
        "no_data": no_data,
        "alive_24h_rate": (alive / with_data) if with_data else 0.0,
        "cells": cells,
        "verdict": verdict(cells.get("d30_h60", {"n": 0})),
    }


MIN_N = 300  # below this, say nothing — a weekend of graduations is not evidence


def verdict(cell: dict[str, Any]) -> dict[str, str]:
    """Pre-registered kill criteria for C (entry T+30min, hold 1h, net of costs)."""
    n = cell.get("n", 0)
    if n < MIN_N:
        return {"status": "INSUFFICIENT", "why": f"n={n} < {MIN_N}"}
    med, wr, lot = cell["median"], cell["win_rate"], cell["top2pct_share"]
    if med <= -0.0125:
        return {"status": "KILL", "why": f"median net {med:+.2%} <= -1.25%"}
    if lot >= 0.5:
        return {"status": "KILL", "why": f"lottery-shaped: top 2% of names = {lot:.0%} of gains"}
    if med > 0.02 and wr >= 0.45:
        return {"status": "PASS", "why": f"median {med:+.2%}, win rate {wr:.0%}, top2% share {lot:.0%}"}
    return {"status": "INCONCLUSIVE", "why": f"median {med:+.2%}, win rate {wr:.0%}"}
