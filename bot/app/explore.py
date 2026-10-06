"""Exploration tables for feature rules (docs/PREREG.md "C3 trở đi", docs/SNIPER.md "S2 trở đi").

Not evidence: this is where candidate rules are looked for, on each registration's exploration
window (and, apart, on rows from before it). Next to every median sits the mean and the share of
near-total losses, because a median hides a rug tail. On the rows harvested before PREREG_TS, the
C2 pools whose price held near the migration price had a median of +0.6% but a mean of -9.7%,
13% of them going to zero within the hour: almost all were self-graduated curves, whose dev holds
~79% of the supply after migration and can drain the pool at will. So a rule is registered only
if its mean is positive in both halves of the exploration window (docs/RESEARCH.md).

Each feature is cut into terciles of the sample (or its values, when it has three or fewer), and
every bucket reports n, median, mean, win rate, rug share, and the mean in the earlier and the
later half of the sample (by launch or migration time) as a first check of stability.
"""

import math
from collections.abc import Callable, Sequence
from statistics import median
from typing import Any

from . import prereg, sniper
from .survivor import FILLS_VERSION, latest_by_mint

RUG = prereg.RUG
MIN_ROWS = 30  # fewer rows with a feature: no table for it
Feature = Callable[[dict[str, Any]], float | None]


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, int | float) and math.isfinite(v):
        return float(v)
    return None


def _at(row: dict[str, Any], path: str) -> float | None:
    cur: Any = row
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return _num(cur)


def _since_migration(key: str) -> Feature:
    """The pool's `key` at T+30 over its value at the migration (both known at the decision)."""

    def f(row: dict[str, Any]) -> float | None:
        a, b = _at(row, f"decision.d0.{key}"), _at(row, f"decision.d30.{key}")
        return b / a if a and b is not None else None

    return f


def _self_graduated(row: dict[str, Any]) -> float | None:
    dev = _at(row, "curve.dev_buy_sol")
    return None if dev is None else float(dev >= 80)


def _path(p: str) -> Feature:
    return lambda row: _at(row, p)


# Everything here was public at T+30, before the decision (docs/PREREG.md).
C_FEATURES: dict[str, Feature] = {
    "real_sol": _path("decision.d30.real_sol"),
    "idle_s": _path("decision.d30.last_trade_age_s"),
    "price_vs_migration": _since_migration("mark"),
    "real_vs_migration": _since_migration("real_sol"),
    "flow_swaps": _path("flow.d30.swaps"),
    "flow_traders": _path("flow.d30.traders"),
    "flow_buy_sol": _path("flow.d30.buy_sol"),
    "flow_net_sol": _path("flow.d30.net_sol"),
    "flow_top_seller_share": _path("flow.d30.top_seller_share"),
    "flow_creator_sell_sol": _path("flow.d30.creator_sell_sol"),
    "holders_top1": _path("holders.d30.top1"),
    "holders_top10": _path("holders.d30.top10"),
    "holders_1pct": _path("holders.d30.holders_1pct"),
    "holders_dev_share": _path("holders.d30.dev_share"),
    "holders_bundle_share": _path("holders.d30.bundle_share"),
    "holders_top10_exit_share": _path("holders.d30.top10_exit_share"),
    "self_graduated": _self_graduated,
    "curve_graduate_s": _path("curve.graduate_s"),
    "curve_dev_buy_sol": _path("curve.dev_buy_sol"),
    "curve_bundle_sol": _path("curve.bundle_sol"),
    "curve_early_sol": _path("curve.early_sol"),
    "curve_buyers_60s": _path("curve.buyers_60s"),
    "curve_dev_sell_sol": _path("curve.dev_sell_sol"),
    "curve_tx": _path("curve.curve_tx"),
    "fund_fresh_1d": _path("funding.fresh_1d"),
    "fund_max_cluster": _path("funding.max_cluster"),
    "fund_cluster_hold_share": _path("funding.cluster_hold_share"),
    "fund_dev_linked": _path("funding.dev_linked"),
}

# What was public at the end of the entry slot (sniper.entry_features, primary latency).
S_FEATURES: dict[str, Feature] = {
    name: _path(f"entry.{name}")
    for name in ("price_x", "real_sol", "dev_buy_sol", "slot0_buyers", "slot0_sol", "buyers", "dev_sold")
}


def stats(vals: Sequence[float]) -> dict[str, Any]:
    n = len(vals)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "median": median(vals),
        "mean": sum(vals) / n,
        "win": sum(v > 0 for v in vals) / n,
        "rug": sum(v <= RUG for v in vals) / n,
    }


def _mean(vals: Sequence[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def feature_table(
    points: Sequence[tuple[float, float, float]],
) -> list[dict[str, Any]] | None:
    """Buckets of (feature value, net, time) points: terciles, or one bucket per value when there
    are three values or fewer. None below MIN_ROWS points."""
    if len(points) < MIN_ROWS:
        return None
    xs = sorted(p[0] for p in points)
    values = sorted(set(xs))
    if len(values) <= 3:
        edges = [(v, v) for v in values]
    else:
        c1, c2 = xs[len(xs) // 3], xs[2 * len(xs) // 3]
        cuts = sorted({c1, c2})
        bounds = [-math.inf, *cuts, math.inf]
        edges = list(zip(bounds, bounds[1:], strict=False))
    t_mid = median(p[2] for p in points)
    out = []
    for lo, hi in edges:
        sel = [p for p in points if (p[0] == lo if lo == hi else lo <= p[0] < hi)]
        if not sel:
            continue
        st = stats([p[1] for p in sel])
        st["range"] = [None if math.isinf(lo) else lo, None if math.isinf(hi) else hi]
        st["mean_early"] = _mean([p[1] for p in sel if p[2] < t_mid])
        st["mean_late"] = _mean([p[1] for p in sel if p[2] >= t_mid])
        out.append(st)
    return out


def _sample(
    rows: Sequence[dict[str, Any]],
    net: Callable[[dict[str, Any]], float | None],
    time_of: Callable[[dict[str, Any]], float],
    features: dict[str, Feature],
) -> dict[str, Any]:
    with_net = [(r, v) for r in rows if (v := net(r)) is not None]
    table = {}
    for name, f in features.items():
        pts = [(x, v, time_of(r)) for r, v in with_net if (x := f(r)) is not None]
        table[name] = {"n": len(pts), "buckets": feature_table(pts)}
    return {"all": stats([v for _, v in with_net]), "features": table}


def explore_c(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """C2 pools, the primary cell (T+30 -> 1 h, 1 SOL, executable net): the registered exploration
    window and, apart, the rows from before PREREG_TS."""
    current = [
        r
        for r in latest_by_mint(rows)
        if r.get("fills")
        and (r.get("fills_version") or 1) >= FILLS_VERSION
        and r.get("quote_mint") in prereg.SOL_QUOTES
        and prereg.c2_member(r)
    ]
    start, end = prereg.PREREG_TS, prereg.PREREG_TS + prereg.EXPLORE_DAYS * 86_400
    samples = {
        "window": [r for r in current if start <= prereg.t_mig(r) < end],
        "before": [r for r in current if prereg.t_mig(r) < start],
    }
    return {
        "population": "C2",
        "cell": prereg.PRIMARY_CELL,
        "size": prereg.PRIMARY_SIZE,
        "window": [start, end],
        "rug_at": RUG,
        "samples": {k: _sample(v, prereg._net, prereg.t_mig, C_FEATURES) for k, v in samples.items()},
    }


S_CELLS = (
    sniper.PRIMARY_CELL,
    sniper.cell_name(sniper.PRIMARY_K, "tp2"),
    sniper.cell_name(sniper.PRIMARY_K, "hold"),
)


def explore_s(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Classic sniper tickets at the primary latency, for a few exits: S's exploration window and,
    apart, the launches from before PREREG_S_TS."""
    rows: dict[str, dict[str, Any]] = {}
    for r in results:
        if r.get("sim_version") == sniper.SIM_VERSION and not r.get("mayhem"):
            rows[r["mint"]] = r
    start = sniper.PREREG_S_TS
    end = start + sniper.EXPLORE_DAYS * 86_400
    samples = {
        "window": [r for r in rows.values() if start <= r["t0"] < end],
        "before": [r for r in rows.values() if r["t0"] < start],
    }
    out: dict[str, Any] = {"window": [start, end], "rug_at": RUG, "cells": list(S_CELLS), "samples": {}}
    for name, rs in samples.items():
        out["samples"][name] = {}
        for cell in S_CELLS:
            i = sniper.CELLS.index(cell)
            net = lambda r, i=i: r["nets"][i]  # noqa: E731
            out["samples"][name][cell] = _sample(rs, net, lambda r: r["t0"], S_FEATURES)
    return out
