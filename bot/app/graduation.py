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

Hypothesis GS (section 9), registered after a closer look at the same exploration data
(research/graduation_speed.py): 29% of those curves completed within a minute of their create
(343 of 1,815 within 2 s, bundles an outsider cannot enter), curves already at >= 60 SOL at
t0+60 s that had not completed lost 38.5% on average, and curves that reached 60 SOL later had a
mean of +6.0% [+1.9, +10.1] per ticket bought 1 SOL past the trigger (+1.5% at 3 SOL). The +21%
above also kept only curves that rose 3 SOL past the trigger; without that survivor bias it is
+15.5%. GS keeps G's ticket, sample and criteria and only takes triggers that landed >= 60 s after
the create; it is judged once, on its first 300 tickets.
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
# Hypothesis GS (docs/SNIPER.md section 9): G's tickets whose trigger landed at least a minute after
# the create (block time), judged on G's confirmatory sample with G's criteria.
GS_MIN_TRIGGER_S = 60
SPEEDS = ("fast", "slow", "unknown")


# Features at the trigger (trigger_features): the recent-flow window, and what counts as a wash
# cycle (one wallet buying and selling back the same tokens within two slots, three times or more).
FLOW_S = 300
WASH_SLOTS, WASH_TOL, WASH_MIN_CYCLES = 2, 0.02, 3


def level_key(level: float) -> str:
    return f"{level:g}"


def _wash_cycles(p: CurvePath, n: int) -> int:
    """Buy-then-sell-back cycles by one wallet over trades 0..n-1 (FIFO, each trade used once),
    counted for wallets with at least WASH_MIN_CYCLES of them."""
    open_buys: dict[str, list[tuple[int, int]]] = {}
    cycles: dict[str, int] = {}
    for i in range(n):
        u = p.users[i]
        if p.buys[i]:
            open_buys.setdefault(u, []).append((p.slots[i], p.toks[i]))
            continue
        q = open_buys.get(u) or []
        while q and p.slots[i] - q[0][0] > WASH_SLOTS:
            q.pop(0)
        if q and abs(p.toks[i] - q[0][1]) <= WASH_TOL * q[0][1]:
            q.pop(0)
            cycles[u] = cycles.get(u, 0) + 1
    return sum(c for c in cycles.values() if c >= WASH_MIN_CYCLES)


def trigger_features(p: CurvePath, j: int) -> dict[str, Any]:
    """What was public once trade j (the trigger) had landed, for exploring filters: how many
    wallets bought, recent flow, how much supply the insiders (dev, creator, buyers of the create
    slot and the next) and the largest holder still hold, and the share of held tokens bought at a
    third of the current price or less (holders sitting on large gains)."""
    n = j + 1
    insiders = {u for u in (p.dev, p.creator) if u}
    insiders |= {p.users[i] for i in range(n) if p.buys[i] and p.slots[i] <= p.s0 + 1}
    net: dict[str, int] = {}
    paid: dict[str, list[int]] = {}  # wallet -> [SOL spent, tokens bought]
    for i in range(n):
        u, t = p.users[i], p.toks[i]
        net[u] = net.get(u, 0) + (t if p.buys[i] else -t)
        if p.buys[i]:
            c = paid.setdefault(u, [0, 0])
            c[0] += p.sols[i]
            c[1] += t
    held = {u: v for u, v in net.items() if v > 0}
    total = sum(held.values())
    price = p.vs[j] / p.vt[j] if p.vt[j] else 0.0
    cheap = sum(v for u, v in held.items() if paid.get(u, [0, 0])[1] and paid[u][0] / paid[u][1] <= price / 3)
    recent = [i for i in range(n) if p.ts[i] >= p.ts[j] - FLOW_S]
    buy_sol = sum(p.sols[i] for i in recent if p.buys[i])
    sell_sol = sum(p.sols[i] for i in recent if not p.buys[i])
    supply = p.supply or 0

    def share(x: float) -> float | None:
        return round(x / supply, 5) if supply else None

    return {
        "buyers": len({p.users[i] for i in range(n) if p.buys[i]} - insiders),
        "breadth_300": len({p.users[i] for i in recent if p.buys[i]}),
        "sell_share_300": round(sell_sol / buy_sol, 4) if buy_sol else None,
        "net_sol_300": round((buy_sol - sell_sol) / LAMPORTS, 3),
        "insider_ovh": share(sum(held.get(u, 0) for u in insiders)),
        "top1": share(max(held.values())) if held else None,
        "overhang_cheap": round(cheap / total, 4) if total else None,
        "wash_cycles": _wash_cycles(p, n),
        "dev_sold": any(not p.buys[i] and p.users[i] in (p.dev, p.creator) for i in range(n)),
    }


def curve_phase(
    p: CurvePath, level: float, size: float = G_SIZE, latency: int = G_LATENCY_SLOTS
) -> dict[str, Any] | None:
    """The ticket's curve phase, or None when the curve never stood at `level` SOL real. Every
    phase carries how long after the create the trigger landed (`trigger_s`, block time;
    `trigger_slots`), and a graduate how many slots the curve then took to complete."""
    target = p.v_sol0 + level * LAMPORTS
    j = next((i for i, v in enumerate(p.vs) if v >= target), None)
    if j is None:
        return None
    timing = {"trigger_s": p.ts[j] - p.t0, "trigger_slots": p.slots[j] - p.s0}
    entry_slot = p.slots[j] + latency
    if p.complete_slot is not None and p.complete_slot <= entry_slot:
        return {"why": "jump", **timing}
    if p.known_slot is not None and entry_slot > p.known_slot:
        return {"why": "unresolved", **timing}
    i0 = p.last_by_slot(entry_slot)
    vs, vt = p.vs[i0], p.vt[i0]
    spend = size * LAMPORTS
    net_in = spend / (1 + p.fee)
    dt = vt * net_in / (vs + net_in)
    out: dict[str, Any] = {"entry_real": round((vs - p.v_sol0) / LAMPORTS, 4), "dt": dt, **timing}
    if p.complete_slot is not None:
        return {
            **out,
            "f": trigger_features(p, j),
            "why": "grad",
            "complete_slots": p.complete_slot - p.slots[j],
        }
    if p.truncated:
        return {"why": "unresolved", **timing}
    out["f"] = trigger_features(p, j)
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


def speed(phase: dict[str, Any]) -> str:
    """Return "slow" when the trigger landed at least GS_MIN_TRIGGER_S after the create, "fast"
    before, and "unknown" for phases recorded before the trigger time was kept."""
    t = phase.get("trigger_s")
    if t is None:
        return "unknown"
    return "slow" if t >= GS_MIN_TRIGGER_S else "fast"


def _kinds(phases: Sequence[dict[str, Any]]) -> dict[str, int]:
    whys = [ph["why"] for ph in phases]
    return {w: whys.count(w) for w in ("grad", "fail", "jump", "unresolved")}


# a confirmatory ticket: (launch time, signature, net or None while the exit is pending)
Ticket = tuple[float, str, float | None]
Tickets = dict[str, list[Ticket]]


def _nets(tickets: Sequence[Ticket]) -> list[float]:
    return [v for _, _, v in tickets if v is not None]


def _in_launch_order(tickets: Sequence[Ticket]) -> list[Ticket]:
    return sorted(tickets, key=lambda t: (t[0], t[1]))


def _prereg(tickets: Tickets, fixed_n: bool = False, **extra: Any) -> dict[str, Any]:
    """Verdict on confirmatory tickets per level. G reads every resolved ticket so far. GS
    (`fixed_n`) is judged once: on the first G_MIN_N tickets at the primary level in launch order,
    with the robustness levels cut at the launch time of the last of them, and only once none of
    those tickets still waits for its exit (a graduate's pool row comes a day later)."""
    primary = _in_launch_order(tickets[level_key(G_PRIMARY)])
    others = {x: _in_launch_order(tickets[level_key(x)]) for x in G_LEVELS if x != G_PRIMARY}
    after: dict[str, Any] = {}
    if fixed_n and len(primary) >= G_MIN_N:
        cutoff = primary[G_MIN_N - 1][0]
        others = {x: [t for t in v if t[0] <= cutoff] for x, v in others.items()}
        waiting = sum(v is None for _, _, v in primary[:G_MIN_N])
        waiting += sum(v is None for t in others.values() for _, _, v in t)
        after = {"n_after": len(primary) - G_MIN_N, "judged_until": cutoff, "exit_waiting": waiting}
        primary = primary[:G_MIN_N]
    st = _stats(_nets(primary))
    robust = [_stats(_nets(others[x])).get("mean") for x in others]
    judged = verdict(st, robust)
    if after.get("exit_waiting"):
        judged = "WAIT"
    return {
        "since": PREREG_G_TS,
        "level": G_PRIMARY,
        "exit": G_EXITS[0],
        "size": G_SIZE,
        "min_n": G_MIN_N,
        **extra,
        "robust_levels": list(others),
        "robust_means": robust,
        **st,
        **after,
        "verdict": judged,
    }


def summarize(results: Sequence[dict[str, Any]], survivor_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Every level x exit on classic launches, split by how fast the curve reached the level, and
    the verdicts of G and GS on their confirmatory sample."""
    exits = {r.get("mint"): r for r in latest_by_mint(survivor_rows)}
    launches: dict[str, dict[str, Any]] = {}
    for r in results:
        if r.get("g") is not None and not r.get("mayhem"):
            launches[r["mint"]] = r
    table: dict[str, dict[str, Any]] = {}
    conf_nets: Tickets = {}
    conf_slow: Tickets = {}
    for x in G_LEVELS:
        key = level_key(x)
        reached = [r for r in launches.values() if (r["g"] or {}).get(key)]
        kinds = _kinds([r["g"][key] for r in reached])
        waiting = sum(1 for r in reached if r["g"][key]["why"] == "grad" and r["mint"] not in exits)
        cells: dict[str, Any] = {}
        by_speed: dict[str, Any] = {}
        for when in G_EXITS:
            outcomes = [(r, ticket_net(r["g"][key], exits.get(r["mint"]), when)) for r in reached]
            nets = [v for _, v in outcomes if v is not None]
            cells[when] = _stats(nets)
            if when == G_EXITS[0]:
                # tickets of the confirmatory sample, a graduate whose pool row is not in yet as None
                conf = [
                    (r["t0"], r.get("signature") or "", v, r["g"][key])
                    for r, v in outcomes
                    if r["g"][key]["why"] in ("grad", "fail")
                    and r["t0"] >= PREREG_G_TS
                    and sampled(r.get("signature") or "", G_SAMPLE_PER_10K)
                ]
                conf_nets[key] = [(t0, sig, v) for t0, sig, v, _ in conf if v is not None]
                conf_slow[key] = [(t0, sig, v) for t0, sig, v, ph in conf if speed(ph) == "slow"]
                for sp in SPEEDS:
                    sub = [(r, v) for r, v in outcomes if speed(r["g"][key]) == sp]
                    by_speed[sp] = {
                        "reached": len(sub),
                        **_kinds([r["g"][key] for r, _ in sub]),
                        G_EXITS[0]: _stats([v for _, v in sub if v is not None]),
                    }
        tickets = kinds["grad"] + kinds["fail"]
        table[key] = {
            "reached": len(reached),
            **kinds,
            "exit_waiting": waiting,
            "p_grad_given_ticket": kinds["grad"] / tickets if tickets else None,
            "cells": cells,
            "by_speed": by_speed,
        }
    return {
        "levels": table,
        "prereg": _prereg(conf_nets),
        "prereg_gs": _prereg(conf_slow, fixed_n=True, min_trigger_s=GS_MIN_TRIGGER_S),
    }
