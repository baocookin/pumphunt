"""Hypothesis G, "graduation run" (docs/SNIPER.md, section 8): buy a bonding curve that has reached
X SOL of real reserve, hold it to graduation, sell right after the migration.

Why (measured before registration, exploration only). On 77k classic SOL launches of 27-29/09/2026
(loopholetape) a curve that reached 60 SOL graduated 73% of the time (50 SOL: 59%, 70 SOL: 84%).
From 60 SOL the graduation price is (115/90)^2 = 1.63x higher. Three seconds after a migration the
pool still traded at a median 1.006x the graduation price (602 graduates, 04-05/10; BOOST buys the
token back over the first five minutes) and only 3% of September's full pools had lost 30% of
their SOL within five seconds. Buying at 60 SOL and selling 3 s after migration had a mean of
+21% per ticket even with the entry pushed 3 SOL later, before the open questions below.

Open questions this test answers: whether an outsider can enter (a curve can jump past X in one
buy or complete in the same slot), how often the curves that fail fall back, and whether the
first seconds after migration hold up out of sample.

Curve phase (census rows: every curve trade in chain order). The trigger is the first trade whose
post-state stands at >= X SOL real; the ticket buys at the end of the next slot (one slot of
latency), behind everything in it, for `size` SOL including the curve fee. A curve that completed
by then gives no ticket ("jump"). A curve that does not complete within the 2-hour window is sold
at its last state ("fail"). Exit (the migration's survivor row, harvested a day later): the
ticket's tokens are sold into the PumpSwap pool as it stood 3 s after the migration, before our
sale (the fills model's T+0 entry state), or, as a variant, at T+5 min (after BOOST). Rows
harvested before the fills cells carried the pool's token reserve at entry approximate it from
the opening state with a constant product, which understates the price if BOOST's buys come out
of the virtual reserve (the sale is then valued low, not high).
"""

import math
from collections.abc import Sequence
from typing import Any

from .fills import LAMPORTS, PoolState, sell_ex
from .sniper import FIXED_COST_SOL, CurvePath, sampled
from .survivor import latest_by_mint

G_LEVELS = (50.0, 60.0, 70.0)  # SOL of real reserve that trigger a ticket
G_PRIMARY = 60.0
G_EXITS = ("t3s", "t5m")  # 3 s after migration (primary), 5 min after
G_SIZE = 0.5
G_LATENCY_SLOTS = 1
# Registration (docs/SNIPER.md section 8): launches from this time on, in the 5% census sample.
PREREG_G_TS = 1_791_342_000  # 2026-10-07T03:00:00Z
G_SAMPLE_PER_10K = 500
G_MIN_N = 300
# PumpSwap canonical pool under 420 SOL market cap: lp, protocol, creator (bps)
DEFAULT_POOL_FEES = (2, 93, 30)


def level_key(level: float) -> str:
    return f"{level:g}"


def curve_phase(
    p: CurvePath, level: float, size: float = G_SIZE, latency: int = G_LATENCY_SLOTS
) -> dict[str, Any] | None:
    """The ticket's curve phase, or None when the curve never stood at `level` SOL real."""
    target = p.v_sol0 + level * LAMPORTS
    j = next((i for i, v in enumerate(p.vs) if v >= target), None)
    if j is None:
        return None
    entry_slot = p.slots[j] + latency
    if p.complete_slot is not None and p.complete_slot <= entry_slot:
        return {"why": "jump"}
    if p.known_slot is not None and entry_slot > p.known_slot:
        return {"why": "unresolved"}
    i0 = p.last_by_slot(entry_slot)
    vs, vt = p.vs[i0], p.vt[i0]
    spend = size * LAMPORTS
    net_in = spend / (1 + p.fee)
    dt = vt * net_in / (vs + net_in)
    out: dict[str, Any] = {"entry_real": round((vs - p.v_sol0) / LAMPORTS, 4), "dt": dt}
    if p.complete_slot is not None:
        return {**out, "why": "grad"}
    if p.truncated:
        return {"why": "unresolved"}
    proceeds = p.value(len(p.vs) - 1, dt) / LAMPORTS
    return {**out, "why": "fail", "net": round((proceeds - FIXED_COST_SOL) / size - 1, 5)}


def phases(p: CurvePath) -> dict[str, dict[str, Any] | None]:
    return {level_key(x): curve_phase(p, x) for x in G_LEVELS}


def _cell(row: dict[str, Any]) -> dict[str, Any] | None:
    by_size = (row.get("fills") or {}).get("d0_h60") or {}
    return next((c for c in by_size.values() if isinstance(c, dict) and c.get("liquidity_in_sol")), None)


def pool_after_migration(row: dict[str, Any], when: str) -> PoolState | None:
    """The PumpSwap pool of a survivor row 3 s ("t3s") or 5 min ("t5m") after the migration."""
    d = row.get("decision") or {}
    lp, proto, creator = DEFAULT_POOL_FEES
    if when == "t5m":
        st = d.get("d5") or {}
        liq, mark = st.get("liquidity_sol"), st.get("mark")
        if not liq or not mark:
            return None
        real = st.get("real_sol") if st.get("real_sol") is not None else liq
        effective = liq * LAMPORTS
        virtual = int(effective - real * LAMPORTS)
        return PoolState(int(effective / mark), int(real * LAMPORTS), virtual, lp, proto, creator, 0)
    c = _cell(row)
    if c is None:
        return None
    real, virtual = c.get("real_in_sol"), c.get("virtual_in_sol") or 0.0
    effective = c["liquidity_in_sol"] * LAMPORTS
    base = c.get("base_in")
    if base is None:
        d0 = d.get("d0") or {}
        if not d0.get("liquidity_sol") or not d0.get("mark"):
            return None
        q0 = d0["liquidity_sol"] * LAMPORTS
        base = q0 * (q0 / d0["mark"]) / effective  # constant product from the opening state
    lp, proto, creator = c.get("pool_fees_bps") or DEFAULT_POOL_FEES
    real_lamports = int((real if real is not None else c["liquidity_in_sol"] - virtual) * LAMPORTS)
    return PoolState(int(base), real_lamports, int(virtual * LAMPORTS), lp, proto, creator, 0)


def ticket_net(phase: dict[str, Any] | None, survivor_row: dict[str, Any] | None, when: str) -> float | None:
    """Net of one ticket, None when there is none or its exit is not known yet."""
    if not phase or phase["why"] in ("jump", "unresolved"):
        return None
    if phase["why"] == "fail":
        return phase["net"]
    if survivor_row is None:
        return None
    pool = pool_after_migration(survivor_row, when)
    if pool is None:
        return None
    recv, _, _, _ = sell_ex(pool, int(phase["dt"]))
    return (recv / LAMPORTS - FIXED_COST_SOL) / G_SIZE - 1


def _stats(vals: list[float]) -> dict[str, Any]:
    n = len(vals)
    if not n:
        return {"n": 0}
    mean = sum(vals) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else None
    s = sorted(vals)
    gains = sorted((v for v in vals if v > 0), reverse=True)
    return {
        "n": n,
        "mean": mean,
        "mean_ci95": [mean - half, mean + half] if half is not None else None,
        "median": s[n // 2],
        "win_rate": sum(v > 0 for v in vals) / n,
        "rug_share": sum(v <= -0.9 for v in vals) / n,
        "top1pct_share": sum(gains[: max(1, n // 100)]) / sum(gains) if gains else None,
    }


def verdict(st: dict[str, Any], robust_means: Sequence[float | None]) -> str:
    if st.get("n", 0) < G_MIN_N:
        return "WAIT"
    lo, hi = st["mean_ci95"]
    if hi < 0 or (st.get("top1pct_share") or 0) >= 0.5:
        return "KILL"
    if lo > 0 and all(m is not None and m > 0 for m in robust_means):
        return "PASS"
    return "INCONCLUSIVE"


def summarize(results: Sequence[dict[str, Any]], survivor_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Every level x exit on classic launches, and G's verdict on its confirmatory sample."""
    exits = {r.get("mint"): r for r in latest_by_mint(survivor_rows)}
    launches: dict[str, dict[str, Any]] = {}
    for r in results:
        if r.get("g") is not None and not r.get("mayhem"):
            launches[r["mint"]] = r
    table: dict[str, dict[str, Any]] = {}
    conf_nets: dict[str, list[float]] = {}
    for x in G_LEVELS:
        key = level_key(x)
        reached = [r for r in launches.values() if (r["g"] or {}).get(key)]
        whys = [r["g"][key]["why"] for r in reached]
        kinds = {w: whys.count(w) for w in ("grad", "fail", "jump", "unresolved")}
        waiting = sum(1 for r in reached if r["g"][key]["why"] == "grad" and r["mint"] not in exits)
        cells = {}
        for when in G_EXITS:
            outcomes = [(r, ticket_net(r["g"][key], exits.get(r["mint"]), when)) for r in reached]
            nets = [v for _, v in outcomes if v is not None]
            cells[when] = _stats(nets)
            if when == G_EXITS[0]:
                conf_nets[key] = [
                    v
                    for r, v in outcomes
                    if v is not None
                    and r["t0"] >= PREREG_G_TS
                    and sampled(r.get("signature") or "", G_SAMPLE_PER_10K)
                ]
        tickets = kinds["grad"] + kinds["fail"]
        table[key] = {
            "reached": len(reached),
            **kinds,
            "exit_waiting": waiting,
            "p_grad_given_ticket": kinds["grad"] / tickets if tickets else None,
            "cells": cells,
        }
    st = _stats(conf_nets[level_key(G_PRIMARY)])
    robust = [_stats(conf_nets[level_key(x)]).get("mean") for x in G_LEVELS if x != G_PRIMARY]
    return {
        "levels": table,
        "prereg": {
            "since": PREREG_G_TS,
            "level": G_PRIMARY,
            "exit": G_EXITS[0],
            "size": G_SIZE,
            "min_n": G_MIN_N,
            "robust_levels": [x for x in G_LEVELS if x != G_PRIMARY],
            "robust_means": robust,
            **st,
            "verdict": verdict(st, robust),
        },
    }
