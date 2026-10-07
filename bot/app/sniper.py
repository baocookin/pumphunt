"""Sniper research (hypothesis S): what a ticket bought seconds after a pump.fun launch returns.

Sample. Every pump.fun create transaction names the program's mint authority, so that address's
signature list is a census of launches on the chain, ~57k a day (measured 06/10/2026: 190 of 190
successful transactions were creates). It is polled with getSignaturesForAddress (1 credit per
1,000) and a fixed share of the launches is kept by a hash of the create signature, which is
deterministic and blind to the outcome. PumpPortal's create feed is not used for this: it relays
~29k creates a day and names a wrong bonding curve for mayhem launches.

Path. Two hours after the launch, its create transaction (1 credit) names the mint, the curve and
the quote asset; for a SOL-quoted curve, every successful transaction of the curve in those two
hours is read oldest first (Helius getTransactionsForAddress, 10 credits per 100) and each pump.fun
trade event is kept in chain order (slot, position in the block, event order) with the curve's
virtual reserves after it. Those reserves chain exactly from one trade to the next, so a gap shows.

Simulation. A ticket of `size` SOL buys at the end of slot create+k, behind every trade of that slot
(the dev's buy, its bundle, the faster snipers), and is sold by an exit rule. Other traders' token
flows are taken as given: the curve is a constant product over its virtual reserves, so with the
ticket's tokens outstanding it sits where the real curve would sit with that many more tokens sold,
and selling them at a later moment returns v_sol * dt / (v_tokens - dt) before the fee, where
(v_sol, v_tokens) are the real curve's reserves then. Buyers who spent a fixed SOL amount would
in fact have received slightly fewer tokens; for a ticket small against the curve this is second
order. Nothing models other bots reacting to the ticket.
"""

import hashlib
import math
import time
from bisect import bisect_right
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from .curve_history import pump_events
from .jsonl import JsonlWriter
from .rpc import SolanaRpc, describe_http_error
from .store import Store, hour_key
from .swaps import SwapFetcher

LAMPORTS = 1_000_000_000
MINT_AUTHORITY = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"  # pump.fun's mint authority PDA
# pump.fun writes the system program id as the quote mint of SOL curves; older events carry none
SOL_QUOTES = {None, "So11111111111111111111111111111111111111112", "11111111111111111111111111111111"}
DEFAULT_FEE_BPS = 125  # 0.95% protocol (half of it funds buybacks) + 0.30% creator, each side

SIM_VERSION = 1
# Registration of hypothesis S (docs/SNIPER.md): launches from this time on are its confirmatory
# sample. Rows are computed two hours after their launch, so none existed when this was committed.
PREREG_S_TS = 1_791_342_000  # 2026-10-07T03:00:00Z
EXPLORE_DAYS = 14
MIN_N = 2_000
# S's sample is the 2% of the census registered with it; the census keeps more since G (5%),
# a superset by the same hash, which the exploratory grid uses in full.
S_SAMPLE_PER_10K = 200

# --- simulation grid -------------------------------------------------------------------------
LATENCIES = (0, 1, 2, 4, 8, 20, 40)  # slots after the create slot (~0.27 s each, measured)
# exit name -> (take profit multiple, stop multiple, time stop in s); None: no such leg. Without a
# time stop a ticket is sold at graduation or marked at the end of the window.
EXITS: dict[str, tuple[float | None, float | None, float | None]] = {
    "p": (2.0, 0.5, 60.0),  # primary: most early buyers sell within the first minute
    "tp1.5": (1.5, None, None),
    "tp2": (2.0, None, None),
    "tp3": (3.0, None, None),
    "tp5": (5.0, None, None),
    "tp10": (10.0, None, None),
    "t10": (None, None, 10.0),
    "t30": (None, None, 30.0),
    "t60": (None, None, 60.0),
    "t300": (None, None, 300.0),
    "hold": (None, None, None),
}
SIZE = 0.5
PRIMARY_K, PRIMARY_EXIT = 2, "p"
EXTRA_SIZES = (0.1, 1.0)  # the primary rule at other ticket sizes
ROBUST_KS = (1, 4)  # a PASS needs a positive mean at these latencies too
FIXED_COST_SOL = 0.002  # priority fees and tips of both legs (median sniper paid ~0.001 per leg)
EXIT_LATENCY_SLOTS = 1  # a triggered sale lands at the end of the next slot

REASONS = {"tp": "t", "sl": "s", "time": "x", "grad": "g", "end": "e"}


def cell_name(k: int, exit_name: str, size: float = SIZE) -> str:
    return f"k{k}_{exit_name}" + ("" if size == SIZE else f"_s{size:g}")


GRID: list[tuple[int, str, float]] = [(k, e, SIZE) for k in LATENCIES for e in EXITS] + [
    (PRIMARY_K, PRIMARY_EXIT, s) for s in EXTRA_SIZES
]
CELLS = [cell_name(*c) for c in GRID]
PRIMARY_CELL = cell_name(PRIMARY_K, PRIMARY_EXIT)

TRADE_COLUMNS = ("slot", "tx", "ev", "ts", "user", "buy", "sol", "tokens", "v_sol", "v_tokens", "ix")


def sampled(signature: str, per_10k: int) -> bool:
    """Whether a launch is in the sample: a hash of its create signature, blind to the outcome."""
    h = hashlib.sha256(signature.encode()).digest()
    return int.from_bytes(h[:8], "big") % 10_000 < per_10k


# --- reading a launch ------------------------------------------------------------------------
def create_of(tx: dict[str, Any]) -> dict[str, Any] | None:
    """The create event of a create transaction (None when it holds none)."""
    if not tx or (tx.get("meta") or {}).get("err"):
        return None
    return next((e for e in pump_events(tx) if e["kind"] == "create"), None)


def launch_info(create: dict[str, Any], tx: dict[str, Any], signature: str) -> dict[str, Any]:
    return {
        "signature": signature,
        "mint": create.get("mint"),
        "curve": create.get("bonding_curve"),
        "dev": create.get("user"),
        "creator": create.get("creator"),
        "create_slot": int(tx.get("slot") or 0),
        "create_ts": int(tx.get("blockTime") or create.get("timestamp") or 0),
        "quote_mint": create.get("quote_mint"),
        "mayhem": bool(create.get("is_mayhem_mode")),
        "cashback": bool(create.get("is_cashback_enabled")),
        "holder_reward": bool(create.get("is_holder_reward")),
        "token_program": create.get("token_program"),
        "supply": create.get("token_total_supply"),
        "v_sol0": create.get("virtual_sol_reserves"),
        "v_tokens0": create.get("virtual_token_reserves"),
    }


def curve_trades(txs: Sequence[dict[str, Any]], mint: str) -> dict[str, Any]:
    """The mint's trades on its curve in chain order, its completion, and data checks.

    Consecutive trades must hand over the token reserve exactly (pre = post + bought, or post -
    sold); a break means a trade is missing from the read (or out of order)."""
    trades: list[list[Any]] = []
    complete: dict[str, Any] | None = None
    fees: dict[int, int] = {}
    for tx in txs:
        if (tx.get("meta") or {}).get("err"):
            continue
        slot, ts = int(tx.get("slot") or 0), int(tx.get("blockTime") or 0)
        idx = int(tx.get("transactionIndex") or 0)
        ev_i = 0
        for ev in pump_events(tx):
            if ev.get("mint") != mint:
                continue
            if ev["kind"] == "trade":
                trades.append(
                    [
                        slot,
                        idx,
                        ev_i,
                        ts,
                        ev.get("user"),
                        bool(ev.get("is_buy")),
                        int(ev.get("sol_amount") or 0),
                        int(ev.get("token_amount") or 0),
                        int(ev.get("virtual_sol_reserves") or 0),
                        int(ev.get("virtual_token_reserves") or 0),
                        ev.get("ix_name") or "",
                    ]
                )
                ev_i += 1
                bps = int(ev.get("fee_basis_points") or 0) + int(ev.get("creator_fee_basis_points") or 0)
                if bps:
                    fees[bps] = fees.get(bps, 0) + 1
            elif ev["kind"] == "complete" and complete is None:
                complete = {"slot": slot, "tx": idx, "ts": ts}
    trades.sort(key=lambda t: (t[0], t[1], t[2]))
    breaks = 0
    for a, b in zip(trades, trades[1:], strict=False):
        pre = b[9] + b[7] if b[5] else b[9] - b[7]
        if pre != a[9]:
            breaks += 1
    fee_bps = max(fees, key=lambda k: fees[k]) if fees else None
    return {"trades": trades, "complete": complete, "chain_breaks": breaks, "fee_bps": fee_bps}


# --- simulation --------------------------------------------------------------------------------
class CurvePath:
    """A launch's curve in chain order: its reserves before any trade and after each one."""

    def __init__(self, row: dict[str, Any]):
        cols = {c: i for i, c in enumerate(TRADE_COLUMNS)}
        tr = row.get("trades") or []
        self.s0 = int(row["create_slot"])
        self.t0 = int(row["create_ts"])
        self.v_sol0 = float(row["v_sol0"])
        self.v_tok0 = float(row["v_tokens0"])
        self.slots = [int(t[cols["slot"]]) for t in tr]
        self.ts = [int(t[cols["ts"]]) for t in tr]
        self.vs = [float(t[cols["v_sol"]]) for t in tr]
        self.vt = [float(t[cols["v_tokens"]]) for t in tr]
        # who traded, for features at a decision time (graduation.trigger_features)
        self.users = [t[cols["user"]] for t in tr]
        self.buys = [bool(t[cols["buy"]]) for t in tr]
        self.sols = [int(t[cols["sol"]]) for t in tr]
        self.toks = [int(t[cols["tokens"]]) for t in tr]
        self.dev, self.creator = row.get("dev"), row.get("creator")
        self.supply = int(row.get("supply") or 0)
        c = row.get("complete")
        self.complete_slot = int(c["slot"]) if c else None
        self.complete_ts = int(c["ts"]) if c and c.get("ts") is not None else None
        bps = row.get("fee_bps") or DEFAULT_FEE_BPS
        self.fee = (bps if 50 <= bps <= 500 else DEFAULT_FEE_BPS) / 10_000
        win = row.get("window") or {}
        self.window_end = self.t0 + int(win.get("span_s") or 0)
        # A read cut short by its cap is known up to the slot before its last transaction's (that
        # slot may be partly read) and the second before its time; a complete one to its end.
        self.truncated = bool(win.get("truncated"))
        self.known_slot = int(win.get("last_slot") or 0) - 1 if self.truncated else None
        self.known_until = int(win.get("last_ts") or 0) - 1 if self.truncated else self.window_end

    def value(self, i: int, dt: float) -> float:
        """Lamports received for selling `dt` tokens after trade i (-1: before any trade)."""
        vs, vt = (self.v_sol0, self.v_tok0) if i < 0 else (self.vs[i], self.vt[i])
        if vt <= dt:
            return 0.0
        return (1 - self.fee) * vs * dt / (vt - dt)

    def last_by_slot(self, slot: int) -> int:
        """Index of the last trade landed by the end of `slot` (-1 if none)."""
        return bisect_right(self.slots, slot) - 1


def simulate(
    p: CurvePath,
    k: int,
    exit_name: str,
    size: float = SIZE,
    fixed_cost: float = FIXED_COST_SOL,
    exit_latency: int = EXIT_LATENCY_SLOTS,
) -> dict[str, Any] | None:
    """One ticket: {"net", "why", "peak"} or None when there is none (the curve completed by the
    entry slot) or its exit lies past what was read ({"net": None, "why": "unresolved"})."""
    entry_slot = p.s0 + k
    if p.complete_slot is not None and p.complete_slot <= entry_slot:
        return None
    i0 = p.last_by_slot(entry_slot)
    vs, vt = (p.v_sol0, p.v_tok0) if i0 < 0 else (p.vs[i0], p.vt[i0])
    entry_ts = p.t0 if i0 < 0 else p.ts[i0]
    spend = size * LAMPORTS
    net_in = spend / (1 + p.fee)
    dt = vt * net_in / (vs + net_in)
    tp, sl, stop = EXITS[exit_name]
    deadline = entry_ts + stop if stop is not None else None
    peak = p.value(i0, dt)
    n = len(p.vs)

    def done(i: int, why: str) -> dict[str, Any]:
        proceeds = p.value(i, dt) / LAMPORTS
        return {"net": (proceeds - fixed_cost) / size - 1, "why": why, "peak": peak / spend}

    for j in range(i0 + 1, n):
        if deadline is not None and p.ts[j] > deadline:
            return done(j - 1, "time")
        v = p.value(j, dt)
        peak = max(peak, v)
        if (tp is not None and v >= tp * spend) or (sl is not None and v <= sl * spend):
            sell_slot = p.slots[j] + exit_latency
            if p.known_slot is not None and sell_slot > p.known_slot:
                return {"net": None, "why": "unresolved", "peak": peak / spend}
            return done(p.last_by_slot(sell_slot), "tp" if tp is not None and v >= tp * spend else "sl")
    if p.complete_slot is not None:
        return done(n - 1, "grad")
    if deadline is not None and deadline <= p.known_until:
        return done(n - 1, "time")
    if p.truncated:
        return {"net": None, "why": "unresolved", "peak": peak / spend}
    return done(n - 1, "end")


def entry_features(p: CurvePath, row: dict[str, Any], k: int = PRIMARY_K) -> dict[str, Any]:
    """What was public at the end of slot create+k: the price paid, who bought ahead."""
    cols = {c: i for i, c in enumerate(TRADE_COLUMNS)}
    tr = row.get("trades") or []
    i0 = p.last_by_slot(p.s0 + k)
    before = tr[: i0 + 1]
    dev = row.get("dev")
    buys = [t for t in before if t[cols["buy"]]]
    dev_buy = sum(t[cols["sol"]] for t in buys if t[cols["user"]] == dev and t[cols["slot"]] == p.s0)
    in_slot0 = [t for t in buys if t[cols["slot"]] == p.s0 and t[cols["user"]] != dev]
    vs, vt = (p.v_sol0, p.v_tok0) if i0 < 0 else (p.vs[i0], p.vt[i0])
    return {
        "price_x": (vs / vt) / (p.v_sol0 / p.v_tok0) if p.v_tok0 and vt else None,
        "real_sol": (vs - p.v_sol0) / LAMPORTS,
        "dev_buy_sol": dev_buy / LAMPORTS,
        "slot0_buyers": len({t[cols["user"]] for t in in_slot0}),
        "slot0_sol": sum(t[cols["sol"]] for t in in_slot0) / LAMPORTS,
        "buyers": len({t[cols["user"]] for t in buys if t[cols["user"]] != dev}),
        "dev_sold": any((not t[cols["buy"]]) and t[cols["user"]] == dev for t in before),
    }


def simulate_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """The compact result kept for the summary: every grid cell's net and exit reason, aligned
    with CELLS (None: no ticket), the curve's peak for a ticket held from the primary latency,
    and the entry features. None when the row has no path to simulate."""
    if row.get("status") != "ok":
        return None
    p = CurvePath(row)
    nets: list[float | None] = []
    whys = []
    for k, e, s in GRID:
        r = simulate(p, k, e, s)
        if r is None:
            nets.append(None)
            whys.append("-")
        else:
            nets.append(None if r["net"] is None else round(r["net"], 5))
            whys.append(REASONS.get(r["why"], "u"))
    held = simulate(p, PRIMARY_K, "hold")
    from .graduation import phases  # imports this module

    return {
        "mint": row["mint"],
        "signature": row["signature"],
        "t0": row["create_ts"],
        "mayhem": row.get("mayhem"),
        "graduated": row.get("complete") is not None,
        "chain_breaks": row.get("chain_breaks"),
        "truncated": (row.get("window") or {}).get("truncated"),
        "sim_version": SIM_VERSION,
        "nets": nets,
        "whys": "".join(whys),
        "hold_peak": round(held["peak"], 4) if held else None,
        "entry": entry_features(p, row),
        "g": None if row.get("mayhem") else phases(p),
    }


# --- summary -----------------------------------------------------------------------------------
def _stats(vals: list[float]) -> dict[str, Any]:
    n = len(vals)
    if not n:
        return {"n": 0}
    s = sorted(vals)
    mean = sum(vals) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else None
    gains = sorted((v for v in vals if v > 0), reverse=True)
    top = sum(gains[: max(1, n // 100)]) / sum(gains) if gains else None
    return {
        "n": n,
        "mean": mean,
        "mean_ci95": [mean - half, mean + half] if half is not None else None,
        "median": s[n // 2],
        "win_rate": sum(v > 0 for v in vals) / n,
        "p_2x": sum(v >= 1 for v in vals) / n,
        "p_5x": sum(v >= 4 for v in vals) / n,
        "p_10x": sum(v >= 9 for v in vals) / n,
        "top1pct_share": top,
    }


def verdict(st: dict[str, Any], robust_means: Sequence[float | None]) -> str:
    """S's kill criteria (docs/SNIPER.md): judged once n >= MIN_N on the confirmatory sample."""
    if st.get("n", 0) < MIN_N:
        return "WAIT"
    lo, hi = st["mean_ci95"]
    if hi < 0 or (st["top1pct_share"] or 0) >= 0.5:
        return "KILL"
    if lo > 0 and all(m is not None and m > 0 for m in robust_means):
        return "PASS"
    return "INCONCLUSIVE"


def summarize(results: Sequence[dict[str, Any]], now: float | None = None) -> dict[str, Any]:
    """Every grid cell per stratum (classic, mayhem) on the whole sample, and hypothesis S on its
    confirmatory sample (classic launches from PREREG_S_TS on)."""
    rows = {}
    for r in results:
        if r.get("sim_version") == SIM_VERSION:
            rows[r["mint"]] = r  # a launch read twice counts once
    by: dict[str, list[dict[str, Any]]] = {"classic": [], "mayhem": []}
    for r in rows.values():
        by["mayhem" if r.get("mayhem") else "classic"].append(r)

    def cell_vals(rs: list[dict[str, Any]], i: int) -> list[float]:
        return [r["nets"][i] for r in rs if r["nets"][i] is not None]

    cells: dict[str, dict[str, Any]] = {}
    for stratum, rs in by.items():
        cells[stratum] = {}
        for i, name in enumerate(CELLS):
            st = _stats(cell_vals(rs, i))
            st["unresolved"] = sum(1 for r in rs if r["whys"][i] == "u")
            cells[stratum][name] = st
    conf = [
        r
        for r in by["classic"]
        if r["t0"] >= PREREG_S_TS and sampled(r.get("signature") or "", S_SAMPLE_PER_10K)
    ]
    idx = {n: i for i, n in enumerate(CELLS)}
    st = _stats(cell_vals(conf, idx[PRIMARY_CELL]))
    st["unresolved"] = sum(1 for r in conf if r["whys"][idx[PRIMARY_CELL]] == "u")
    robust = []
    for k in ROBUST_KS:
        rs = _stats(cell_vals(conf, idx[cell_name(k, PRIMARY_EXIT)]))
        robust.append(rs.get("mean") if rs["n"] else None)
    held = [r["hold_peak"] for r in by["classic"] if r.get("hold_peak") is not None]
    return {
        "sim_version": SIM_VERSION,
        "launches": len(rows),
        "classic": len(by["classic"]),
        "mayhem": len(by["mayhem"]),
        "graduated": sum(1 for r in by["classic"] if r.get("graduated")),
        "with_chain_breaks": sum(1 for r in rows.values() if r.get("chain_breaks")),
        "truncated": sum(1 for r in rows.values() if r.get("truncated")),
        "grid": {"latencies": LATENCIES, "exits": EXITS, "size": SIZE, "extra_sizes": EXTRA_SIZES},
        "cells": cells,
        "hold_peak": {
            "n": len(held),
            "p_2x": sum(h >= 2 for h in held) / len(held) if held else None,
            "p_5x": sum(h >= 5 for h in held) / len(held) if held else None,
            "p_10x": sum(h >= 10 for h in held) / len(held) if held else None,
        },
        "prereg": {
            "since": PREREG_S_TS,
            "explore_until": PREREG_S_TS + EXPLORE_DAYS * 86_400,
            "cell": PRIMARY_CELL,
            "rule": {"k": PRIMARY_K, "exit": EXITS[PRIMARY_EXIT], "size": SIZE, "fixed_cost": FIXED_COST_SOL},
            "min_n": MIN_N,
            "robust": dict(zip([cell_name(k, PRIMARY_EXIT) for k in ROBUST_KS], robust, strict=True)),
            **st,
            "verdict": verdict(st, robust),
        },
    }


def lottery(results: Sequence[dict[str, Any]], survivor_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive, not a hypothesis: how often a ticket from the primary latency, held, touched 10x
    or 100x. On the curve the touch is the ticket's best value before graduation (at most ~14.7x
    the launch price); a graduate then multiplies its value at graduation by its pool's highest
    5-minute candle within 24 h of the migration (survivor rows, `peak_x`). A touch is not a fill:
    nobody sells a whole ticket at the top of a candle."""
    peaks = {r.get("mint"): (r.get("peak_x") or {}).get("24h") for r in survivor_rows}
    hold = CELLS.index(cell_name(PRIMARY_K, "hold"))
    rows = {r["mint"]: r for r in results if r.get("sim_version") == SIM_VERSION and not r.get("mayhem")}
    tickets = [r for r in rows.values() if r["nets"][hold] is not None]
    touches = []
    waiting = 0
    for r in tickets:
        touch = r.get("hold_peak") or 0.0
        if r.get("graduated"):
            pk = peaks.get(r["mint"])
            if pk is None:
                waiting += 1  # its pool is harvested a day after the migration
                continue
            touch = max(touch, (1 + r["nets"][hold]) * pk)
        touches.append(touch)
    n = len(touches)
    return {
        "tickets": n,
        "graduated_waiting": waiting,
        "p_touch_10x": sum(t >= 10 for t in touches) / n if n else None,
        "p_touch_100x": sum(t >= 100 for t in touches) / n if n else None,
        "n_touch_10x": sum(t >= 10 for t in touches),
        "n_touch_100x": sum(t >= 100 for t in touches),
    }


# --- recording ---------------------------------------------------------------------------------
class SniperRecorder:
    """Census of launches, the sample's queue and its harvest; owned by the Recorder."""

    QUEUE = "snipe"

    def __init__(self, cfg: Any, store: Store, rpc: SolanaRpc, data_dir: str | Path):
        self.cfg = cfg
        self.store = store
        self.rpc = rpc
        self.fetcher = SwapFetcher(rpc)  # its own credit meter, apart from the fills harvester's
        self.log = JsonlWriter(Path(data_dir) / "sniper.jsonl", rotate_daily=True, compress_rotated=True)
        self.stats: dict[str, Any] = {
            "polls": 0,
            "creates_seen": 0,
            "sampled": 0,
            "census_gaps": 0,  # polls that could not reach back to the previous cursor
            "harvested": 0,
            "not_sol": 0,
            "errors": 0,
            "credits_today": 0,
            "paused": False,
            "gtfa": None,
            "gtfa_error": None,
            "short_then_empty": 0,  # a page shorter than asked, then an empty one: the usual end
            "short_then_more": 0,  # a page shorter than asked, then more data: never seen so far
            "queued": 0,
            "last_poll_ts": 0.0,
            "last_harvest_ts": 0.0,
            "last_error": None,
        }

    def _credits_key(self, now: float) -> str:
        return "sniper_credits:" + time.strftime("%Y-%m-%d", time.gmtime(now))

    async def census_once(self, now: float | None = None) -> int:
        """List the creates since the stored cursor; queue the sampled ones for their harvest. On
        the very first poll only the newest page is read (no backfill)."""
        now = now or time.time()
        cfg = self.cfg
        cursor = self.store.get_kv("sniper:cursor")
        sigs: list[dict[str, Any]] = []
        before = None
        pages = 0
        reached = cursor is None
        while pages < (cfg.sniper_census_max_pages if cursor else 1):
            page = await self.rpc.get_signatures(MINT_AUTHORITY, limit=1000, before=before, until=cursor)
            pages += 1
            sigs.extend(page)
            if len(page) < 1000:
                reached = True
                break
            before = page[-1]["signature"]
        self.store.incr_kv(self._credits_key(now), pages)
        if cursor and not reached:
            self.stats["census_gaps"] += 1  # the oldest launches since the last poll were not listed
        if sigs:
            self.store.set_kv("sniper:cursor", sigs[0]["signature"])
        per_hour: dict[str, int] = {}
        queued = 0
        for s in sigs:
            if s.get("err"):
                continue
            bt = int(s.get("blockTime") or now)
            hk = hour_key(bt)
            per_hour[hk] = per_hour.get(hk, 0) + 1
            if sampled(s["signature"], cfg.sniper_sample_per_10k):
                member = f"{s['signature']}|{s.get('slot') or 0}|{bt}"
                if self.store.schedule(self.QUEUE, member, bt + cfg.sniper_window_s + cfg.sniper_delay_s):
                    queued += 1
        for hk, n in per_hour.items():
            self.store.incr("creates_census", hk, n)
        self.stats["polls"] += 1
        self.stats["creates_seen"] += sum(per_hour.values())
        self.stats["sampled"] += queued
        self.stats["last_poll_ts"] = now
        return queued

    async def read_launch(self, signature: str, bt: int) -> dict[str, Any]:
        """The launch's create and, for a SOL curve, its trades in the window after it."""
        cfg = self.cfg
        tx = await self.rpc.get_transaction(signature)
        credits = 1
        create = create_of(tx) if tx else None
        if create is None:
            status = "no_create" if tx else "tx_not_found"
            return {"signature": signature, "status": status, "credits": credits}
        row = launch_info(create, tx, signature)
        if row["quote_mint"] not in SOL_QUOTES:
            return {**row, "status": "not_sol", "credits": credits}
        if not row["curve"] or not row["mint"]:
            return {**row, "status": "no_curve", "credits": credits}  # an event layout we cannot read
        f = self.fetcher
        spent = f.credits
        txs: list[dict[str, Any]] = []
        token = None
        t_to = row["create_ts"] + cfg.sniper_window_s
        short = False  # the previous page held fewer than asked
        while True:
            limit = 100 if not txs else 1000
            res = await f.history_page(
                row["curve"],
                full=True,
                sort="asc",
                limit=limit,
                t_from=row["create_ts"],
                t_to=t_to,
                token=token,
            )
            data = res.get("data") or []
            # Helius hands out a pagination token even after the last page (measured: 920 of 920
            # curve reads). Whether a short page is always the last one decides if that extra
            # call can be skipped; until it is shown, the read goes on and counts the cases.
            if short:
                self.stats["short_then_more" if data else "short_then_empty"] += 1
            short = len(data) < limit
            txs.extend(data)
            token = res.get("paginationToken")
            if not token or not data or len(txs) >= cfg.sniper_max_tx:
                break
        path = curve_trades(txs, row["mint"])
        credits += f.credits - spent
        row.update(path)
        last = txs[-1] if txs else {}
        row["window"] = {
            "span_s": cfg.sniper_window_s,
            "tx": len(txs),
            "truncated": bool(token) and len(txs) >= cfg.sniper_max_tx,
            "last_slot": int(last.get("slot") or 0),
            "last_ts": int(last.get("blockTime") or 0),
        }
        row["status"] = "ok"
        row["credits"] = credits
        return row

    async def harvest_once(self, now: float | None = None) -> int:
        """Read every sampled launch whose window has passed, within the daily credit budget."""
        now = now or time.time()
        cfg = self.cfg
        st = self.stats
        st["credits_today"] = int(self.store.get_kv(self._credits_key(now)) or 0)
        st["paused"] = st["credits_today"] >= cfg.sniper_daily_credits
        st["queued"] = self.store.queue_len(self.QUEUE)
        st["gtfa"], st["gtfa_error"] = self.fetcher.gtfa, self.fetcher.gtfa_error
        if st["paused"] or self.fetcher.gtfa is False:
            return 0
        done = 0
        # one at a time: a launch leaves the queue only when it is about to be read
        for _ in range(cfg.sniper_batch):
            due = self.store.take_due(self.QUEUE, now, 1)
            if not due:
                break
            member = due[0][0]
            sig, _slot, bt = member.split("|")
            spent = self.fetcher.credits
            try:
                row = await self.read_launch(sig, int(bt))
            except httpx.HTTPError as exc:
                st["errors"] += 1
                st["last_error"] = f"{sig[:8]}: {describe_http_error(exc)}"
                self.store.incr_kv(self._credits_key(now), self.fetcher.credits - spent)
                self.store.schedule(self.QUEUE, member, now + 300)  # retried later, still in the sample
                continue
            except Exception as exc:  # noqa: BLE001 - a launch we cannot read is recorded, not lost
                st["errors"] += 1
                st["last_error"] = f"{sig[:8]}: {type(exc).__name__}: {exc}"[:200]
                row = {"signature": sig, "status": "error", "error": st["last_error"], "credits": 0}
            st["credits_today"] = self.store.incr_kv(self._credits_key(now), row.get("credits", 0))
            row["read_at"] = now
            try:
                res = simulate_row(row)
            except Exception as exc:  # noqa: BLE001 - keep the raw path even if the simulation fails
                res = None
                row["sim_error"] = f"{type(exc).__name__}: {exc}"[:200]
                st["errors"] += 1
                st["last_error"] = f"{sig[:8]}: simulation {row['sim_error']}"
            if res is not None:
                row["sim"] = {"version": SIM_VERSION, "nets": res["nets"], "whys": res["whys"]}
                self.store.push_row("sniper", res)
            elif row.get("status") == "not_sol":
                st["not_sol"] += 1
            self.log.write(row, now=now)
            st["harvested"] += 1
            done += 1
            if st["credits_today"] >= cfg.sniper_daily_credits:
                st["paused"] = True
                break
        st["queued"] = self.store.queue_len(self.QUEUE)
        st["gtfa"], st["gtfa_error"] = self.fetcher.gtfa, self.fetcher.gtfa_error
        st["last_harvest_ts"] = now
        return done
