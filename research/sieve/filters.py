"""Filter registry of the trap sieve ("rây", docs/SIEVE.md): one function per filter id and version.

Every filter function takes a Cand (one candidate launch at one decision slot) and returns
(fired, raw): `fired` is the definition's own condition WITHOUT the entry gate, `raw` the value its
threshold reads (None when the row cannot be scored, e.g. an incomplete trade chain or a missing
external ledger; then fired is False). The chains and the scorecard apply GATE_E (real SOL at the
entry state, end of dslot+1, >= 11.66) to every veto: below that line a 0.5 SOL ticket cannot lose 50%.

Frozen rules
- A definition is never edited in place. A new threshold, window or wallet rule is a NEW id or
  version registered next to the old one. FROZEN holds a hash of each filter function together with
  every module-level helper and constant it reaches; `python filters.py --check` fails on an edit.
- Only trades with slot <= dslot of the candidate are read (no look-ahead). The entry state is used
  only by GATE_E and the REF-DRAIN75 reference, both curve states known at entry.
- Memory filters read other launches strictly time-ordered: launches created before the candidate
  (t0_L < t0_c), events at block time <= t_dec = t0_c + round((dslot - s0) x 0.269 s). The memory is
  built from the census rows passed in (journal.py drops forward launches before anything else).
- The program-owned router BwWK17cb... is excluded from every wallet feature (its trades still move
  the curve state, which stays in every curve-level quantity).

Ports: every function reproduces the module that defined it (scratch sieve2/verify/* and
sieve3/patch-*), checked row by row on the founding pool (README.md). Trade tuple:
[slot, tx_index, event_index, block_time, user, is_buy, sol_lamports, token_raw, v_sol_after,
v_tokens_after, ix_name], in chain order.
"""

import argparse
import hashlib
import inspect
import math
import sys
import types
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from itertools import combinations

ROUTER = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
LAMPORTS = 1_000_000_000
SUPPLY = 1e15
SPS = 0.269  # seconds per slot (median of the census windows)
W60 = round(60 / SPS)  # 223 slots
W120 = round(120 / SPS)  # 446 slots
GATE_E = 11.66  # analytic: below this entry real SOL a 0.5 SOL ticket cannot reach net -50%
GATE_D = 11.73  # SH-DEV-1 / SH-WASH-1 own gate, on the decision-slot real SOL
SIZE, FIXED = 0.5, 0.002
DEFAULT_FEE_BPS = 125
XFER_LINE = 1e12  # 0.1% of supply: a wallet sold this many more tokens than it bought on the curve
SLOT, TX, EV, TS, USER, BUY, SOL, TOK, VS, VT, IX = range(11)


def fee_of(row):
    bps = row.get("fee_bps") or DEFAULT_FEE_BPS
    return (bps if 50 <= bps <= 500 else DEFAULT_FEE_BPS) / 10_000


def state_at(row, slots, slot):
    """(v_sol, v_tokens) after the last trade landed by the end of `slot` (initial state if none)."""
    i = bisect_right(slots, slot) - 1
    if i < 0:
        return float(row["v_sol0"]), float(row["v_tokens0"])
    t = row["trades"][i]
    return float(t[VS]), float(t[VT])


class Cand:
    """One candidate: a census row at decision slot dslot. Feature dicts are cached per family.

    entry: the (v_sol, v_tokens) state at the end of dslot+1 from the FULL row (journal.py passes it
    when the row given here was truncated or perturbed for a robustness test)."""

    def __init__(self, row, dslot, mem=None, entry=None, slots=None):
        self.row = row
        self.dslot = int(dslot)
        self.mem = mem
        self.trades = row.get("trades") or []
        self.slots = slots if slots is not None else [int(t[SLOT]) for t in self.trades]
        self.n = bisect_right(self.slots, self.dslot)
        self.vis = self.trades[: self.n]
        self.mint = row["mint"]
        self.s0 = int(row["create_slot"])
        self.t0 = int(row["create_ts"])
        self.dev = row.get("dev")
        self.creator = row.get("creator")
        self.v0 = float(row["v_sol0"])
        self.vt0 = float(row["v_tokens0"])
        self.tdec = self.t0 + round((self.dslot - self.s0) * SPS)
        self.real_d = (float(self.vis[-1][VS]) - self.v0) / LAMPORTS if self.vis else 0.0
        self.entry = entry if entry is not None else state_at(row, self.slots, self.dslot + 1)
        self.real_e = (self.entry[0] - self.v0) / LAMPORTS
        self.cache = {}
        self.detail = {}

    def get(self, name, fn):
        if name not in self.cache:
            self.cache[name] = fn(self)
        return self.cache[name]


# ============================================================ trade completeness (SIEVE law 9)
TOL_SOL = 1  # lamports
TOL_TOK = 1  # raw token units


def check_ordered(row, upto_slot=None, trades=None):
    """Replay in census order: every trade's before-state must equal the previous after-state."""
    tr = trades if trades is not None else (row.get("trades") or [])
    vs, vt = int(row["v_sol0"]), int(row["v_tokens0"])
    n = gaps = 0
    first = None
    mj = 0.0
    for t in tr:
        if upto_slot is not None and int(t[SLOT]) > upto_slot:
            break
        n += 1
        sg = 1 if t[BUY] else -1
        pre_s = int(t[VS]) - sg * int(t[SOL])
        pre_t = int(t[VT]) + sg * int(t[TOK])
        if abs(pre_s - vs) > TOL_SOL or abs(pre_t - vt) > TOL_TOK:
            gaps += 1
            mj = max(mj, abs(pre_s - vs) / 1e9)
            if first is None:
                first = int(t[TS])
        vs, vt = int(t[VS]), int(t[VT])
    return {"n": n, "gaps": gaps, "first_gap_ts": first, "max_jump_sol": round(mj, 6)}


def chain_events(row, upto_slot=None, trades=None):
    tr = trades if trades is not None else (row.get("trades") or [])
    return [
        (int(t[SOL]), int(t[TOK]), bool(t[BUY]), int(t[VS]), int(t[VT]), int(t[TS]))
        for t in tr
        if upto_slot is None or int(t[SLOT]) <= upto_slot
    ]


def check_chain(events, v_sol0, v_tok0):
    """Order-free check the live bot can run on the PumpPortal stream (no tx_index, arrival order).

    events: (sol, tok, is_buy, v_sol_after, v_tok_after, ts) in any order. Every event's before-state
    must be the initial state or another event's after-state; a complete chain leaves exactly one
    unconsumed after-state, held by one of the newest events. A missing trade at the tail is invisible
    until a later trade arrives: re-check a few slots later or backfill the gap with a paid read."""
    ev = list(events)
    after = Counter((int(e[3]), int(e[4])) for e in ev)
    after[(int(v_sol0), int(v_tok0))] += 1
    gaps = 0
    first = None
    for e in ev:
        sg = 1 if e[2] else -1
        pre = (int(e[3]) - sg * int(e[0]), int(e[4]) + sg * int(e[1]))
        hit = None
        if after[pre] > 0:
            hit = pre
        else:
            for ds in (-TOL_SOL, 0, TOL_SOL):
                for dt in (-TOL_TOK, 0, TOL_TOK):
                    k = (pre[0] + ds, pre[1] + dt)
                    if after[k] > 0:
                        hit = k
                        break
                if hit:
                    break
        if hit is None:
            gaps += 1
            if first is None or int(e[5]) < first:
                first = int(e[5])
        else:
            after[hit] -= 1
    if ev and gaps == 0:
        left = [k for k, v in after.items() if v > 0]
        tmax = max(int(e[5]) for e in ev)
        newest = {(int(e[3]), int(e[4])) for e in ev if int(e[5]) == tmax}
        if len(left) != 1 or not any(
            abs(left[0][0] - a) <= TOL_SOL and abs(left[0][1] - b) <= TOL_TOK for a, b in newest
        ):
            gaps = 1
            first = tmax
    return {"n": len(ev), "gaps": gaps, "first_gap_ts": first}


def complete_chain(row, trades):
    return check_chain(chain_events(row, None, trades), row["v_sol0"], row["v_tokens0"])["gaps"] == 0


def truncate_at_gap(row):
    """The row's trades up to (not including) the first trade whose before-state does not replay."""
    vs, vt = int(row["v_sol0"]), int(row["v_tokens0"])
    keep = []
    for q in row.get("trades") or []:
        sg = 1 if q[BUY] else -1
        if abs(int(q[VS]) - sg * int(q[SOL]) - vs) > 1 or abs(int(q[VT]) + sg * int(q[TOK]) - vt) > 1:
            r2 = dict(row)
            r2["trades"] = keep
            return r2, True
        keep.append(q)
        vs, vt = int(q[VS]), int(q[VT])
    return row, False


# ============================================================ memory (cross-launch, time-ordered)
class Memory:
    """Stores built on first use from the census rows passed in (journal.py: t0 <= window end).

    classic / mayhem: status-ok rows (one per mint). launches: (mint, t0, creator, dev) of every
    census row of any status and kind. lt_ledger: optional external creator ledger {wallet: [t0, ...]}
    (loopholetape, 31/08-29/09; N-LTE-FACTORY is not scored without it)."""

    def __init__(self, classic=(), mayhem=(), launches=(), lt_ledger=None):
        self.classic = list(classic)
        self.mayhem = list(mayhem)
        self.launches = list(launches)
        self.lt_ledger = lt_ledger
        self.stores = {}

    def get(self, name, build):
        if name not in self.stores:
            self.stores[name] = build(self)
        return self.stores[name]


def build_wstore(mem):
    """Per-wallet event and trade store (patch exit2-v2 wstore.build_checked): every classic launch is
    truncated at its first reserve gap, so silent loss cannot create phantom XFER events.
    Events, one per (wallet, launch): LF first trade, LB first buy, LS first sell, XS XFER_SELL (first
    sell at which cumulative sold exceeds cumulative bought by > 1e12 raw), XO XFER_ONLY (XS with no
    buy of that wallet in that launch before it); MLF presence in mayhem launches (INFRA test)."""
    ev = {k: defaultdict(list) for k in ("LF", "LB", "LS", "XS", "XO", "MLF")}
    tr = defaultdict(list)
    t0c = []
    n_gap = 0
    for r0 in mem.classic:
        r, had_gap = truncate_at_gap(r0)
        n_gap += had_gap
        m = r["mint"]
        t0 = int(r["create_ts"])
        t0c.append(t0)
        b = defaultdict(int)
        s = defaultdict(int)
        nb = defaultdict(int)
        seen = set()
        sb = set()
        ss = set()
        done = set()
        for t in r.get("trades") or []:
            u = t[USER]
            if u == ROUTER:
                continue
            ts = int(t[TS])
            buy = bool(t[BUY])
            tok = int(t[TOK])
            sol = int(t[SOL])
            o0 = max(0, s[u] - b[u])
            if u not in seen:
                seen.add(u)
                ev["LF"][u].append((ts, t0, m))
            if buy:
                b[u] += tok
                nb[u] += 1
                if u not in sb:
                    sb.add(u)
                    ev["LB"][u].append((ts, t0, m))
            else:
                s[u] += tok
                if u not in ss:
                    ss.add(u)
                    ev["LS"][u].append((ts, t0, m))
                if u not in done and s[u] - b[u] > XFER_LINE:
                    done.add(u)
                    ev["XS"][u].append((ts, t0, m))
                    if nb[u] == 0:
                        ev["XO"][u].append((ts, t0, m))
            tr[u].append((ts, buy, tok, sol, t0, max(0, s[u] - b[u]) - o0))
    t0m = []
    for r in mem.mayhem:
        t0 = int(r["create_ts"])
        t0m.append(t0)
        seen = set()
        for t in r.get("trades") or []:
            u = t[USER]
            if u in seen:
                continue
            seen.add(u)
            ev["MLF"][u].append((int(t[TS]), t0, r["mint"]))
    E = {}
    for k, d in ev.items():
        E[k] = {}
        for u, lst in d.items():
            lst.sort()
            E[k][u] = ([x[0] for x in lst], [x[1] for x in lst], [x[2] for x in lst])
    T = {}
    for u, lst in tr.items():
        lst.sort()
        cb, cs, cbs, css, nbuy, nsell, co = [0], [0], [0], [0], [0], [0], [0]
        for _, buy, tok, sol, _, dov in lst:
            co.append(co[-1] + dov)
            cb.append(cb[-1] + (tok if buy else 0))
            cs.append(cs[-1] + (0 if buy else tok))
            cbs.append(cbs[-1] + (sol if buy else 0))
            css.append(css[-1] + (0 if buy else sol))
            nbuy.append(nbuy[-1] + buy)
            nsell.append(nsell[-1] + (not buy))
        T[u] = {
            "ts": [x[0] for x in lst],
            "t0": [x[4] for x in lst],
            "cb": cb,
            "cs": cs,
            "cbs": cbs,
            "css": css,
            "nb": nbuy,
            "ns": nsell,
            "co": co,
        }
    xs = set(E["XS"])
    big = {u for u, e in E["LF"].items() if len(e[0]) >= WTYPE["infra_min_n"]}
    bigm = {u for u, e in E["MLF"].items() if len(e[0]) >= WTYPE["infra_min_n"]}
    return {
        "E": E,
        "T": T,
        "t0_classic": sorted(t0c),
        "t0_mayhem": sorted(t0m),
        "typed": xs | big | bigm,
        "n_gap_launches": n_gap,
    }


def build_xfer_raw(mem):
    """XS / XO events as the v1 memory family defined them (sieve2/verify/memory/mem_filters.Rep):
    every classic launch read whole, no completeness truncation. N-WM-XIN and N-WM-EXIT2 (v1) read
    this store, so a stream with lost trades shows the phantom XFER events those definitions have."""
    ev = {"XS": defaultdict(list), "XO": defaultdict(list)}
    for r in mem.classic:
        m = r["mint"]
        t0 = int(r["create_ts"])
        b = defaultdict(int)
        s = defaultdict(int)
        nb = defaultdict(int)
        done = set()
        for t in r.get("trades") or []:
            u = t[USER]
            if u == ROUTER:
                continue
            if t[BUY]:
                b[u] += int(t[TOK])
                nb[u] += 1
            else:
                s[u] += int(t[TOK])
                if u not in done and s[u] - b[u] > XFER_LINE:
                    done.add(u)
                    ev["XS"][u].append((int(t[TS]), t0, m))
                    if nb[u] == 0:
                        ev["XO"][u].append((int(t[TS]), t0, m))
    E = {}
    for k, d in ev.items():
        E[k] = {}
        for u, lst in d.items():
            lst.sort()
            E[k][u] = ([x[0] for x in lst], [x[1] for x in lst], [x[2] for x in lst])
    return {"E": E}


def n_events(S, kind, u, t0c, tlim):
    """Distinct launches L (t0_L < t0c) with a `kind` event of wallet u at block time <= tlim."""
    e = S["E"][kind].get(u)
    if not e:
        return 0
    ts, t0s, _ = e
    hi = bisect_right(ts, tlim)
    lo = bisect_left(ts, t0c)  # an event before t0c belongs to a launch created before t0c
    n = lo
    for i in range(lo, hi):
        if t0s[i] < t0c:
            n += 1
    return n


def trade_sums(S, u, t0c, tlim):
    """(tok bought, tok sold, sol bought, sol sold, n buys, n sells, oversold) of u over trades at
    ts <= tlim in launches created before t0c."""
    T = S["T"].get(u)
    if not T:
        return 0, 0, 0, 0, 0, 0, 0
    hi = bisect_right(T["ts"], tlim)
    lo = bisect_left(T["ts"], t0c)
    keys = ("cb", "cs", "cbs", "css", "nb", "ns", "co")
    vals = [T[k][hi] for k in keys]
    for i in range(lo, hi):
        if T["t0"][i] >= t0c:
            d = [T[k][i + 1] - T[k][i] for k in keys]
            vals = [a - b for a, b in zip(vals, d, strict=True)]
    return tuple(vals)


# WTYPE-v1 (frozen 2026-10-08): wallet types as of a decision, rates per 1,000 reputation-universe
# launches so thresholds transfer from the 5% census to the full stream. First match wins.
WTYPE = {
    "infra_f": 250.0,
    "infra_min_n": 20,
    "ind_nxs": 3,
    "ind_rate": 1.75,
    "ind_xs_share": 0.5,
    "ind_over": 0.5,
    "cus_nxs": 3,
    "cus_f": 10.0,
    "cus_buy": 0.5,
    "cus_xs_share": 0.1,
    "cus_over": 0.1,
}


def wtype_v1(S, u, t0c, tlim, U, UM):
    nL = n_events(S, "LF", u, t0c, tlim)
    nLM = n_events(S, "MLF", u, t0c, tlim)
    nBL = n_events(S, "LB", u, t0c, tlim)
    nXS = n_events(S, "XS", u, t0c, tlim)
    _, cs, _, _, _, _, over = trade_sums(S, u, t0c, tlim)
    f = 1000 * nL / U if U else 0.0
    fM = 1000 * nLM / UM if UM else 0.0
    buy_share = nBL / nL if nL else 0.0
    xs_share = nXS / nL if nL else 0.0
    xs_rate = 1000 * nXS / U if U else 0.0
    over_share = over / cs if cs else 0.0
    t = WTYPE
    if nL + nLM >= t["infra_min_n"] and (f >= t["infra_f"] or fM >= t["infra_f"]):
        return "INFRA"
    if (
        nXS >= t["ind_nxs"]
        and xs_rate >= t["ind_rate"]
        and xs_share >= t["ind_xs_share"]
        and over_share >= t["ind_over"]
    ):
        return "INDUSTRIAL"
    if (
        nXS >= t["cus_nxs"]
        and f >= t["cus_f"]
        and buy_share >= t["cus_buy"]
        and (xs_share >= t["cus_xs_share"] or over_share >= t["cus_over"])
    ):
        return "CUSTODIAL"
    return "GENERIC"


SWARM_SELLERS = 10  # a 'swarm slot': >= 10 distinct non-router wallets sell in one slot


def build_vet(mem):
    """wallet -> [(t0_L, ts, mint_L)] for every swarm slot of every launch (classic and mayhem)."""
    W = defaultdict(list)
    for r in mem.classic + mem.mayhem:
        per = defaultdict(set)
        ts = {}
        for t in r.get("trades") or []:
            if t[BUY] or t[USER] == ROUTER:
                continue
            sl = int(t[SLOT])
            per[sl].add(t[USER])
            ts[sl] = int(t[TS])
        for sl, us in per.items():
            if len(us) >= SWARM_SELLERS:
                for u in us:
                    W[u].append((int(r["create_ts"]), ts[sl], r["mint"]))
    return W


def build_creators(mem):
    """wallet -> sorted create times of census launches (any status, any kind, one per mint) where it
    is the creator or the dev."""
    led = defaultdict(list)
    seen = set()
    for m, t0, creator, dev in mem.launches:
        if not m or t0 is None or m in seen:
            continue
        seen.add(m)
        for w in {creator, dev}:
            if w and w != ROUTER:
                led[w].append(int(t0))
    for v in led.values():
        v.sort()
    return led


# ============================================================ per-candidate feature families
def _v1(c):
    """SIEVE v1 tier 0/1 features (scratch sieve/lib.features + sieve2/journal.extra)."""
    dev, cr = c.dev, c.creator
    net = defaultdict(int)
    bought = defaultdict(int)
    sold = defaultdict(int)
    gross = defaultdict(int)
    switches = defaultdict(int)
    last_side = {}
    last_buy = {}
    flip = set()
    early = set()
    early_sol = 0
    buyers = set()
    for t in c.vis:
        u = t[USER]
        if u == ROUTER:
            continue
        b = bool(t[BUY])
        sol = int(t[SOL])
        tok = int(t[TOK])
        sl = int(t[SLOT])
        gross[u] += sol
        if b:
            net[u] += tok
            bought[u] += tok
            last_buy[u] = sl
            if u not in (dev, cr):
                buyers.add(u)
            if sl <= c.s0 + 1:
                early.add(u)
                early_sol += sol
        else:
            net[u] -= tok
            sold[u] += tok
            if u in last_buy and sl - last_buy[u] <= 5:
                flip.add(u)
        if u in last_side and last_side[u] != b:
            switches[u] += 1
        last_side[u] = b
    holds = sorted((max(v, 0) for v in net.values()), reverse=True)
    dev_share = max(net.get(dev, 0), 0) / SUPPLY + (max(net.get(cr, 0), 0) / SUPPLY if cr != dev else 0.0)
    tot_gross = sum(gross.values()) or 1e-9
    wash = sum(gross[u] for u, k in switches.items() if k >= 3) / tot_gross
    for u in (dev, cr):
        if u:
            early.add(u)
    j60 = bisect_right(c.slots, c.dslot - W60) - 1
    real60 = (float(c.trades[j60][VS]) - c.v0) / LAMPORTS if j60 >= 0 else 0.0
    return {
        "top10": sum(holds[:10]) / SUPPLY,
        "dev_share": dev_share,
        "wash_share": wash,
        "d_real_60s": c.real_d - real60,
        "flippers": len(flip),
        "transfer_in": sum(max(0, sold[u] - bought[u]) for u in sold) / SUPPLY,
        "early_hold": sum(max(0, net[u]) for u in early) / SUPPLY,
        "early_buy_sol": early_sol / LAMPORTS,
        "uniq_buyers": len(buyers),
    }


def _sh(c):
    """SHARPEN family (scratch sieve2/verify/sharpen/sharpen_filters.features)."""
    bought = defaultdict(int)
    sold = defaultdict(int)
    bought_sol = defaultdict(int)
    first_buy_slot = {}
    first_buy_sol = {}
    last_side = {}
    switches = defaultdict(int)
    gross = defaultdict(int)
    gross_all = 0
    for t in c.vis:
        u, b, sol, tok, sl = t[USER], bool(t[BUY]), int(t[SOL]), int(t[TOK]), int(t[SLOT])
        gross_all += sol
        if u == ROUTER:
            continue
        gross[u] += sol
        if b:
            bought[u] += tok
            bought_sol[u] += sol
            if u not in first_buy_slot:
                first_buy_slot[u] = sl
                first_buy_sol[u] = sol
        else:
            sold[u] += tok
        if u in last_side and last_side[u] != b:
            switches[u] += 1
        last_side[u] = b
    net = {u: bought[u] - sold[u] for u in set(bought) | set(sold)}
    creation = {u for u, s in first_buy_slot.items() if s <= c.s0 + 1}
    for u in (c.dev, c.creator):
        if u and u != ROUTER:
            creation.add(u)
    dev_share = max(net.get(c.dev, 0), 0) if c.dev else 0
    if c.creator and c.creator != c.dev:
        dev_share += max(net.get(c.creator, 0), 0)
    sg_bought = sum(bought[u] for u in creation)
    sg_sold = sum(min(sold[u], bought[u]) for u in creation)
    sizes = defaultdict(int)
    for u in creation:
        if u in first_buy_sol:
            sizes[round(first_buy_sol[u] / LAMPORTS, 2)] += 1
    washers = [u for u, k in switches.items() if k >= 3]
    return {
        "dev_share": dev_share / SUPPLY,
        "sg_sol": sum(bought_sol[u] for u in creation) / LAMPORTS,
        "sg_out": sg_sold / sg_bought if sg_bought else 0.0,
        "sg_same": max(sizes.values()) if sizes else 0,
        "wash_share": (sum(gross[u] for u in washers) / gross_all) if gross_all else 0.0,
    }


def _wave(buys, tol, span):
    """buys: [(tx, user, sol)] of one slot. Most distinct wallets in one cluster whose amounts satisfy
    (max - min) / max <= tol and, if span is set, whose tx_index lie within span of each other."""
    best = 0
    if len({u for _, u, _ in buys}) < 2:
        return len({u for _, u, _ in buys})
    amts = sorted({s for _, _, s in buys})
    txs = sorted({t for t, _, _ in buys}) if span is not None else [None]
    for a in amts:
        hi = a / (1 - tol)
        for t0 in txs:
            us = {u for t, u, s in buys if a <= s <= hi and (span is None or t0 <= t <= t0 + span)}
            if len(us) > best:
                best = len(us)
    return best


def _mm(c):
    """MMAAS family (scratch sieve2/verify/mmaas/mmaas_filters.features): dev, creator, router out."""
    excl = {c.dev, c.creator, ROUTER}
    per_slot = defaultdict(list)
    for t in c.vis:
        sl = int(t[SLOT])
        if sl <= c.s0 or not t[BUY] or t[USER] in excl or int(t[SOL]) < 10_000_000:
            continue
        per_slot[sl].append((int(t[TX]), t[USER], int(t[SOL])))
    wave_strict = wave_stream = 0
    for b in per_slot.values():
        if len(b) < 2:
            continue
        wave_strict = max(wave_strict, _wave(b, 0.005, 64))
        wave_stream = max(wave_stream, _wave(b, 0.02, None))
    ev = defaultdict(list)
    for t in c.vis:
        if t[USER] in excl:
            continue
        ev[t[USER]].append((bool(t[BUY]), int(t[SOL])))
    sell_first = sum(1 for e in ev.values() if not e[0][0])
    dust = sum(1 for e in ev.values() if len(e) == 1 and e[0][0] and e[0][1] < 5_000_000)
    txs = defaultdict(lambda: [set(), 0])
    for t in c.vis:
        if t[USER] == ROUTER:
            continue
        k = (int(t[SLOT]), int(t[TX]))
        if t[BUY]:
            txs[k][1] += 1
        else:
            txs[k][0].add(t[USER])
    ms = sum(1 for sellers, nb in txs.values() if len(sellers) >= 2 and nb == 0)
    return {
        "wave_max": wave_strict,
        "wave_stream_max": wave_stream,
        "sell_first": sell_first,
        "dust_holders": dust,
        "ms_sell_txs": ms,
    }


def _an(c):
    """ANATOMY family (scratch sieve2/verify/anatomy/anat_filters.features)."""
    peak = 0.0
    for t in c.vis:
        peak = max(peak, (float(t[VS]) - c.v0) / LAMPORTS)
    dd = (1 - c.real_d / peak) if peak > 0 else 0.0
    excl_who = {c.dev, c.creator, ROUTER}
    slot_buys = defaultdict(lambda: defaultdict(int))
    net = defaultdict(int)
    for t in c.vis:
        u, b, sol, tok, sl = t[USER], bool(t[BUY]), int(t[SOL]), int(t[TOK]), int(t[SLOT])
        if u == ROUTER:
            continue
        net[u] += tok if b else -tok
        if b and u not in excl_who:
            slot_buys[sl][u] += sol
    pair_slots = defaultdict(set)
    for sl, by in slot_buys.items():
        if len(by) > 4 or len(by) < 2:
            continue
        for a, b2 in combinations(sorted(by), 2):
            sa, sc = by[a] / LAMPORTS, by[b2] / LAMPORTS
            lo, hi = min(sa, sc), max(sa, sc)
            if lo >= 0.01 and (hi - lo) / hi <= 0.35:
                pair_slots[(a, b2)].add(sl)
    lock = set()
    for (a, b2), ss in pair_slots.items():
        if len(ss) >= 2:
            lock.add(a)
            lock.add(b2)
    circ = sum(v for v in net.values() if v > 0)
    lock_hold = sum(net[u] for u in lock if net[u] > 0)
    return {"peak_pre": peak, "dd_pre": dd, "lock_hold_circ": lock_hold / circ if circ > 0 else 0.0}


def _x2(c):
    """Wallet-memory family, time-ordered: v1 XFER counts (N-WM-XIN, N-WM-EXIT2 v1) on the whole-launch
    event store, and the WTYPE-v1 INDUSTRIAL roster (N-WM-EXIT2-v2a/v2b) on the gap-checked store.
    'complete' is the order-free chain check of the candidate's trades up to dslot (v2a/v2b are not
    scored on an incomplete chain)."""
    S = c.mem.get("wstore", build_wstore)
    X = c.mem.get("xfer_raw", build_xfer_raw)
    t0c, tlim = c.t0, c.tdec
    b = defaultdict(int)
    s = defaultdict(int)
    seen = []
    for t in c.vis:
        u = t[USER]
        if u == ROUTER:
            continue
        if u not in b:
            seen.append(u)
            b[u] = 0
            s[u] = 0
        if t[BUY]:
            b[u] += int(t[TOK])
        else:
            s[u] += int(t[TOK])
    xin = 0
    nexit = 0
    for u in seen:
        if u not in X["E"]["XS"]:
            continue
        kx = n_events(X, "XS", u, t0c, tlim)
        ko = n_events(X, "XO", u, t0c, tlim)
        if kx or ko:
            xin += max(0, s[u] - b[u])
        if ko:
            nexit += 1
    out = {"xin": xin / SUPPLY, "nexit": nexit, "complete": complete_chain(c.row, c.vis)}
    U = bisect_left(S["t0_classic"], t0c)
    UM = bisect_left(S["t0_mayhem"], t0c)
    ind = [u for u in seen if u in S["typed"] and wtype_v1(S, u, t0c, tlim, U, UM) == "INDUSTRIAL"]
    out.update(
        n_ind=len(ind),
        ind_over=sum(max(0, s[u] - b[u]) for u in ind) / SUPPLY,
        ind_wallets=sorted(ind),
        U=U,
    )
    return out


PRESETS = (0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.3, 0.5, 1, 1.5, 2, 2.5, 3, 5, 10)


def is_preset(sol_lamports):
    """A trading-terminal preset buy size: round SOL net of ~1-3% fees."""
    s = sol_lamports / LAMPORTS
    return any(0.97 * v <= s <= 1.002 * v for v in PRESETS)


def _p1(c):
    """Scripted-farm features (patch swarm-exit swarm_filters.scripted_features)."""
    ins = {c.dev, c.creator, ROUTER}
    first = {}
    nsell = defaultdict(int)
    net = defaultdict(int)
    for t in c.vis:
        u = t[USER]
        if u in ins:
            continue
        if t[BUY]:
            net[u] += int(t[TOK])
            if u not in first:
                first[u] = int(t[SOL])
        else:
            net[u] -= int(t[TOK])
            nsell[u] += 1
    F = [u for u, s in first.items() if s >= 10_000_000]
    NP = [u for u in F if not is_preset(first[u])]
    np_hold = sum(1 for u in NP if nsell[u] == 0 and net[u] > 0)
    n = len(F)
    return {
        "n_fb": n,
        "p_hat": (n - len(NP)) / n if n else None,
        "np_hold_share": np_hold / len(NP) if NP else 0.0,
    }


def _p2(c):
    """Swarm veterans among the candidate's non-insider holders (patch swarm-exit compute_vet)."""
    W = c.mem.get("vet", build_vet)
    ins = {c.dev, c.creator, ROUTER}
    net = defaultdict(int)
    for t in c.vis:
        net[t[USER]] += int(t[TOK]) if t[BUY] else -int(t[TOK])
    H = {u for u, v in net.items() if v > 0 and u not in ins}
    shared = defaultdict(set)
    for u in H:
        for t0L, ts, mL in W.get(u, ()):
            if mL != c.mint and t0L < c.t0 and ts <= c.tdec:
                shared[mL].add(u)
    best = max(((len(v), m) for m, v in shared.items()), default=(0, None))
    return {"vet_max_shared": best[0], "vet_mint": best[1] or "", "vet_n_launches": len(shared)}


def _ledgers(trades):
    """Per-wallet [tok bought, tok sold, lamports spent, lamports received, n buys, n sells,
    first buy slot], router excluded."""
    L = {}
    for t in trades:
        u = t[USER]
        if u == ROUTER:
            continue
        e = L.get(u)
        if e is None:
            e = L[u] = [0, 0, 0, 0, 0, 0, None]
        if t[BUY]:
            e[0] += int(t[TOK])
            e[2] += int(t[SOL])
            e[4] += 1
            if e[6] is None:
                e[6] = int(t[SLOT])
        else:
            e[1] += int(t[TOK])
            e[3] += int(t[SOL])
            e[5] += 1
    return L


def trap_line(vs, vt, f):
    """Reserve state at which a 0.5 SOL ticket bought at (vs, vt) is worth net -50% (journal value)."""
    k = vs * vt
    n = SIZE * LAMPORTS / (1 + f)
    dt = vt * n / (vs + n)
    A = (0.5 * SIZE + FIXED) * LAMPORTS / ((1 - f) * dt)
    vs_t = (-A * dt + math.sqrt((A * dt) ** 2 + 4 * A * k)) / 2
    return vs_t, k / vs_t, dt


def _cc(c):
    """Crowd-cascade raws (patch crowd-cascade cc_filters): cheap supply vs my trap line; top-10
    cohort (fixed at w0 = dslot - 223) sells in the last 60 s, capped per wallet at its w0 holding."""
    f = fee_of(c.row)
    vs, vt = (float(c.vis[-1][VS]), float(c.vis[-1][VT])) if c.vis else (c.v0, c.vt0)
    vs_t, vt_t, _ = trap_line(vs, vt, f)
    need = vt_t - vt
    px_t = (1 - f) * vs_t / vt_t
    cheap = 0
    for bt, st, bs, ss, _, _, _ in _ledgers(c.vis).values():
        h = bt - st
        if h > 0 and bs - ss <= h * px_t:
            cheap += h
    w0 = c.dslot - W60
    k0 = bisect_right(c.slots, w0)
    hold = sorted(
        ((e[0] - e[1], u) for u, e in _ledgers(c.vis[:k0]).items() if e[0] - e[1] > 0), reverse=True
    )
    cohort = {u: h for h, u in hold[:10]}
    tot = sum(cohort.values())
    top = 0.0
    if tot > 0:
        sold = defaultdict(int)
        for t in c.vis[k0:]:
            if t[USER] in cohort and not t[BUY]:
                sold[t[USER]] += int(t[TOK])
        top = min(1.0, sum(min(v, cohort[u]) for u, v in sold.items()) / tot)
    return {"cheap": cheap / need if need > 0 else float("inf"), "top": top}


def _lc(c):
    """Late-collapse raws (patch late-collapse lc_filters): transfer-in supply sold; deepest pre-D dump
    from a peak >= 11.66 SOL, counted only if the curve recovered >= 50% of it by D."""
    b = defaultdict(int)
    s = defaultdict(int)
    for t in c.vis:
        u = t[USER]
        if u == ROUTER:
            continue
        if t[BUY]:
            b[u] += int(t[TOK])
        else:
            s[u] += int(t[TOK])
    ex = [s[u] - b[u] for u in s if s[u] - b[u] > XFER_LINE]
    out = {"xfer": sum(ex) / SUPPLY, "xfer_wallets": len(ex), "repump": 0.0, "depth": 0.0, "rec": 0.0}
    if not c.vis:
        return out
    P = -1.0
    Pidx = None
    best = (0.0, None, None)
    for i, t in enumerate(c.vis):
        r = (float(t[VS]) - c.v0) / LAMPORTS
        if r > P:
            P, Pidx = r, i
        if P >= GATE_E:
            d = 1 - r / P
            if d > best[0]:
                best = (d, Pidx, i)
    X, pi, ti = best
    if pi is None:
        return out
    Pk = (float(c.vis[pi][VS]) - c.v0) / LAMPORTS
    Tr = (float(c.vis[ti][VS]) - c.v0) / LAMPORTS
    rec = (c.real_d - Tr) / (Pk - Tr) if Pk > Tr else 0.0
    out.update(repump=X if rec >= 0.5 else 0.0, depth=X, rec=rec)
    return out


def _cld(c):
    """Closed-loop-drain raws (patch closed-loop-drain cld_filters + info_variant)."""
    L = _ledgers(c.vis)
    ins = {c.dev, c.creator}
    fl = re_ = 0
    holders = holders_big = 0
    for u, e in L.items():
        h = e[0] - e[1]
        if h >= XFER_LINE:
            holders_big += 1
        if h <= 0:
            continue
        fl += h
        holders += 1
        if u not in ins and (e[4] >= 2 or e[5] >= 1):
            re_ += h
    creation = {u for u, e in L.items() if e[6] is not None and e[6] <= c.s0 + 1} | (ins & set(L))
    cb = sum(L[u][0] for u in creation)
    cs = sum(min(L[u][1], L[u][0]) for u in creation)
    ins_share = sum(max(L[u][0] - L[u][1], 0) for u in ins if u in L) / SUPPLY
    vs_t, _, _ = trap_line(c.entry[0], c.entry[1], fee_of(c.row))
    return {
        "react": re_ / fl if fl > 0 else 0.0,
        "orphan": c.real_d / holders if holders else 0.0,
        "orphan_d": c.real_d / holders_big if holders_big else 0.0,
        "creation_out": cs / cb if cb > 0 else 0.0,
        "ins_share": ins_share,
        "holders": holders,
        "drain_need": 1 - max(vs_t - c.v0, 0) / 1e9 / c.real_e if c.real_e > 0 else 0.0,
    }


def _lte(c):
    """Earlier launches of the creator (or dev): external ledger + census rows passed in."""
    if c.mem is None or c.mem.lt_ledger is None:
        return None
    cen = c.mem.get("creators", build_creators)
    lt = c.mem.lt_ledger
    best = 0
    for w in dict.fromkeys((c.creator, c.dev)):
        if not w or w == ROUTER:
            continue
        best = max(best, bisect_left(lt.get(w, []), c.t0) + bisect_left(cen.get(w, []), c.t0))
    return best


# ============================================================ filter functions (fired, raw)
def gate_e(c):
    return c.real_e >= GATE_E, c.real_e


def sh_dev_1(c):
    f = c.get("sh", _sh)
    return c.real_d >= GATE_D and f["dev_share"] >= 0.03, f["dev_share"]


def n_mmaas_wave_stream(c):
    f = c.get("mm", _mm)
    return f["wave_stream_max"] >= 4, f["wave_stream_max"]


def sh_sg_1(c):
    f = c.get("sh", _sh)
    return f["sg_sol"] >= 20 and (f["sg_out"] >= 0.5 or f["sg_same"] >= 5), f["sg_sol"]


def n_mmaas_spldist(c):
    f = c.get("mm", _mm)
    return f["sell_first"] >= 5, f["sell_first"]


def n_mmaas_wave(c):
    f = c.get("mm", _mm)
    return f["wave_max"] >= 4, f["wave_max"]


def n_wm_exit2_v2b(c):
    f = c.get("x2", _x2)
    if not f["complete"]:
        return False, None
    c.detail["N-WM-EXIT2-v2b"] = {"ind_wallets": f["ind_wallets"], "U": f["U"]}
    return f["ind_over"] >= 0.02, f["ind_over"]


def cld_orphan_v1(c):
    f = c.get("cld", _cld)
    ok = f["creation_out"] >= 0.5 and f["ins_share"] < 0.03 and f["orphan"] >= 0.50
    return ok, f["orphan"]


def n_wm_exit2_v1(c):
    f = c.get("x2", _x2)
    return f["nexit"] >= 2, f["nexit"]


def n_wm_exit2_v2a(c):
    f = c.get("x2", _x2)
    if not f["complete"]:
        return False, None
    c.detail["N-WM-EXIT2-v2a"] = {"ind_wallets": f["ind_wallets"], "U": f["U"]}
    return f["n_ind"] >= 2, f["n_ind"]


P_REF = 0.37  # frozen: outcome-blind median preset share over gated pool rows (0.3659)


def p1_swarm_scripted_v1(c):
    f = c.get("p1", _p1)
    if not f["n_fb"]:
        return False, None
    z = (f["p_hat"] - P_REF) / math.sqrt(P_REF * (1 - P_REF) / f["n_fb"])
    return f["p_hat"] <= P_REF / 2 and z <= -3 and f["np_hold_share"] >= 0.5, round(z, 2)


def p2_swarm_vet_v1(c):
    f = c.get("p2", _p2)
    if f["vet_max_shared"]:
        c.detail["P2-SWARM-VET-v1"] = {"vet_mint": f["vet_mint"][:8], "vet_n_launches": f["vet_n_launches"]}
    return f["vet_max_shared"] >= 10, f["vet_max_shared"]


def cc_topdist_v1(c):
    f = c.get("cc", _cc)
    return f["top"] >= 0.35, f["top"]


def cc_cheapload_v1(c):
    f = c.get("cc", _cc)
    return f["cheap"] >= 1.0, f["cheap"]


def posthoc_cc_fragile_v0(c):
    f = c.get("cc", _cc)
    return f["cheap"] <= 0.05, f["cheap"]


def lc_xfersup_v1(c):
    f = c.get("lc", _lc)
    return f["xfer"] >= 0.055, f["xfer"]


def lc_repump_v1(c):
    f = c.get("lc", _lc)
    return f["repump"] >= 0.70, f["repump"]


def cld_reactfloat_v1(c):
    f = c.get("cld", _cld)
    return f["react"] >= 0.60, f["react"]


def cld_orphan_v1d(c):
    f = c.get("cld", _cld)
    ok = f["creation_out"] >= 0.5 and f["ins_share"] < 0.03 and f["orphan_d"] >= 0.65
    return ok, f["orphan_d"]


def ref_drain75(c):
    f = c.get("cld", _cld)
    return f["drain_need"] >= 0.75, f["drain_need"]


def sh_wash_1(c):
    f = c.get("sh", _sh)
    return c.real_d >= GATE_D and f["wash_share"] >= 0.30, f["wash_share"]


def n_anat_fade(c):
    f = c.get("an", _an)
    return c.real_d >= 13 and f["dd_pre"] >= 0.30, f["dd_pre"]


def n_anat_lockstep(c):
    f = c.get("an", _an)
    return f["lock_hold_circ"] >= 0.10, f["lock_hold_circ"]


def n_lte_factory(c):
    n = c.get("lte", _lte)
    if n is None:
        return False, None
    return n >= 5 and 13 <= c.real_d < 30, n


def n_lte_factory_repeat1(c):
    n = c.get("lte", _lte)
    if n is None:
        return False, None
    return n >= 1 and 13 <= c.real_d < 30, n


def n_wm_xin(c):
    f = c.get("x2", _x2)
    return f["xin"] >= 0.005, f["xin"]


def n_mmaas_mstx(c):
    f = c.get("mm", _mm)
    return f["ms_sell_txs"] >= 1, f["ms_sell_txs"]


def n_mmaas_dusthold(c):
    f = c.get("mm", _mm)
    return f["dust_holders"] >= 20, f["dust_holders"]


def v1_s0_selfgrad_fill(c):
    f = c.get("v1", _v1)
    return f["early_buy_sol"] >= 20, f["early_buy_sol"]


def v1_s1_top10(c):
    f = c.get("v1", _v1)
    return f["top10"] >= 0.20, f["top10"]


def v1_s1_dev_hold(c):
    f = c.get("v1", _v1)
    return f["dev_share"] >= 0.03, f["dev_share"]


def v1_s1_wash(c):
    f = c.get("v1", _v1)
    return f["wash_share"] >= 0.30, f["wash_share"]


def v1_s1_spike(c):
    f = c.get("v1", _v1)
    return f["d_real_60s"] >= 10, f["d_real_60s"]


def v1_s1_flippers(c):
    f = c.get("v1", _v1)
    return f["flippers"] >= 8, f["flippers"]


def v1_s1_transfer_in(c):
    f = c.get("v1", _v1)
    return f["transfer_in"] >= 0.005, f["transfer_in"]


def v1_s1_early_hold(c):
    f = c.get("v1", _v1)
    return f["early_hold"] >= 0.05, f["early_hold"]


# Ray live round 1 (09/10/2026, docs/PREREG-RAY-L1.md): found on the outcome journal of the live
# scorer, checked unchanged on its later rows; they decide in Ray only once their forward record
# passes ray/app/live_rules.py.
def ray_hot_v1(c):
    lo = c.dslot - W120
    n = 0
    for t in reversed(c.vis):
        if int(t[SLOT]) <= lo:
            break
        n += 1
    return n >= 300, n


def ray_wash_v1(c):
    f = c.get("sh", _sh)
    return c.real_d >= GATE_D and f["wash_share"] >= 0.30, f["wash_share"]


def row_features(c):
    """Covariates the scorecard uses for strata and matched placebos (curve and activity level)."""
    v1 = c.get("v1", _v1)
    return {
        "d_real_60s": v1["d_real_60s"],
        "uniq_buyers": v1["uniq_buyers"],
        "n_trades": c.n,
        "an_dd_pre": c.get("an", _an)["dd_pre"],
    }


# ============================================================ registry
# tier: active | shadow | info | watch | retired.  score=False: never scored (kept for the record).
# none_unscored: raw None means 'not scored' (default) rather than 'cannot fire' (P1: no first buyer).
# needs: what the live bot needs to compute it. complete: needs every trade of the launch (stream
# loss can flip it; scorecard drops days whose candidates fail the completeness check). memory: reads
# other launches. thr/dir: the raw threshold, for the near-threshold canary (None: not one number).
def _f(fid, fn, tier, family, definition, needs, next_review, evidence="", **kw):
    d = {
        "id": fid,
        "fn": fn,
        "tier": tier,
        "family": family,
        "definition": definition,
        "needs": needs,
        "evidence": evidence,
        "next_review": next_review,
        "complete": False,
        "memory": False,
        "thr": None,
        "dir": ">=",
        "score": True,
        "none_unscored": True,
    }
    d.update(kw)
    return d


REGISTRY = [
    _f(
        "GATE_E",
        gate_e,
        "active",
        "gate",
        "real_e (real SOL at the entry state, end of dslot+1) >= 11.66. Below that line a 0.5 SOL ticket "
        "cannot lose 50% (analytic). Every veto applies only above the gate.",
        "Curve state at entry (free, from vSol in the stream).",
        "Analytic. Re-derive only if pump.fun fee or curve parameters change (SIEVE law 10).",
        "All 82 pool trap rows are above the gate; the 69 ungated rows hold 0 traps and 1 winner row.",
        thr=GATE_E,
        score=False,
    ),
    _f(
        "SH-DEV-1",
        sh_dev_1,
        "active",
        "sharpen",
        "dev + creator net curve balance >= 3% of supply (and real_d >= 11.73).",
        "Complete per-token trades from create (free if subscribed at create).",
        "SIEVE AVOID label at >= 200 forward flags at >= 5 SOL. Demote to shadow if, in 2 consecutive "
        "weeks, U <= the best matched placebo or winner mints exceed 1 per 10 trap mints.",
        "Pool: 30 gated rows, 24T/1W; 16 trap mints / 1 winner mint (ukjpAvka@120). Perm p 0.05; MH 3.45.",
        complete=True,
        thr=0.03,
    ),
    _f(
        "N-MMAAS-WAVE-STREAM",
        n_mmaas_wave_stream,
        "active",
        "mmaas",
        "Some slot after the create slot holds buys from >= 4 distinct wallets (dev, creator, router "
        "excluded), each >= 0.01 SOL, whole cluster (max-min)/max <= 2%.",
        "Per-trade slot (or same-slot grouping) and amounts. No tx_index.",
        "SIEVE AVOID label at >= 200 forward flags. Demote on 2 consecutive weeks of U <= best placebo, "
        "or if forward catch share falls below 10% of trap mints.",
        "Pool: 29 gated rows, 26T/0W; 14 trap mints / 0 winner mints. Perm p 0.002; MH 13.6.",
        thr=4,
    ),
    _f(
        "SH-SG-1",
        sh_sg_1,
        "shadow",
        "sharpen",
        "Creation set (dev, creator, wallets whose first buy is in the create slot or the next) bought "
        ">= 20 SOL AND (it sold >= 50% of its tokens, or >= 5 of its wallets bought identical sizes).",
        "Complete trades from create, plus first-buy slots (a paid read live).",
        "Common promote and kill rules (PREREG-SIEVE-R1 section 5); the winner rule is the binding test.",
        "Pool: 24 gated rows, 17T/2W; 11 trap mints / 2 winner mints. Perm p 0.31; MH 2.04.",
        complete=True,
        thr=20,
    ),
    _f(
        "N-MMAAS-SPLDIST",
        n_mmaas_spldist,
        "shadow",
        "mmaas",
        ">= 5 wallets (dev, creator, router excluded) whose first curve event at or before dslot is a sell.",
        "Complete trades with a reserve-chain check: a lost buy makes a buyer look like a sell-first wallet.",
        "Common rules. Score only reserve-verified rows.",
        "Pool: 20 gated rows, 16T/1W; 12 trap mints / 1 winner mint (497zA6Yw). Perm p 0.15; MH 3.02.",
        complete=True,
        thr=5,
    ),
    _f(
        "N-MMAAS-WAVE",
        n_mmaas_wave,
        "shadow",
        "mmaas",
        "WAVE-STREAM with 0.5% tolerance and a tx_index span <= 64 (strict).",
        "tx_index: the full-program feed or RPC, not PumpPortal.",
        "Common rules. Retire to info if forward catch share stays below 10% for 2 weeks.",
        "Pool: 20 gated rows, 19T/0W; 10 trap mints. Perm p 0.005; MH 12.3. Catch share decaying.",
        thr=4,
    ),
    _f(
        "N-WM-EXIT2-v2b",
        n_wm_exit2_v2b,
        "shadow",
        "memory",
        "ind_over >= 0.02: sum over WTYPE-v1 INDUSTRIAL wallets that traded c by dslot of max(0, sold - "
        "bought on c) / 1e15. Not scored when c's trades fail the chain check.",
        "Memory of all launches (rolling, rates per 1,000 launches); complete trades for the candidate.",
        "Promote only if it beats an_dd_pre+, d_real_60s-, real_e-, v1_transfer_in+ and uniq_buyers+ at "
        "the same k over >= 2 forward weeks. Kill if one wallet is behind > 30% of fires.",
        "Pool: 35 gated rows, 24T/1W; 16 trap mints / 16 creators. Perm p 0.087; MH 1.42.",
        complete=True,
        memory=True,
        thr=0.02,
    ),
    _f(
        "CLD-ORPHAN-v1",
        cld_orphan_v1,
        "shadow",
        "closed-loop-drain",
        "creation_out >= 0.5 AND ins_share < 0.03 AND real_d / holders >= 0.50.",
        "Complete, reserve-verified trades; first-buy slots (a paid read live). No memory.",
        "Promote only if it beats the within-conjunct placebos. Kill if a killed winner sits within 5% of "
        "a threshold, or if >= 2 winner mints are killed in a week.",
        "Pool: 12 gated rows, 10T/0W; 9 trap mints / 9 creators. Perm p 0.110; MH 2.90.",
        complete=True,
        thr=0.50,
    ),
    _f(
        "N-WM-EXIT2",
        n_wm_exit2_v1,
        "retired",
        "memory",
        ">= 2 distinct wallets that traded c by dslot carry an earlier XFER_ONLY event.",
        "Memory (threshold not universe-normalised).",
        "None. Replaced by v2b; not edited in place.",
        "Refuted: unique-buyer proxy, threshold drifts with universe size, phantom fires under loss.",
        complete=True,
        memory=True,
        thr=2,
    ),
    _f(
        "N-WM-EXIT2-v2a",
        n_wm_exit2_v2a,
        "info",
        "memory",
        "n_ind >= 2 INDUSTRIAL (WTYPE-v1) wallets traded c by dslot (same store as v2b).",
        "Same memory as v2b.",
        "Reopen as shadow only if it beats unique-buyer-matched controls on traps over 2 forward weeks.",
        "Pool: 20 gated rows, 13T/0W; 9 trap mints; p 0.154; MH 1.22.",
        complete=True,
        memory=True,
        thr=2,
    ),
    _f(
        "P1-SWARM-SCRIPTED-v1",
        p1_swarm_scripted_v1,
        "info",
        "swarm-exit",
        "Preset share p of non-insider first buys >= 0.01 SOL <= 0.185 AND z <= -3 versus P_REF 0.37 AND "
        "NP_hold >= 0.5 (share of non-preset first buyers with no sells and net > 0). raw = z.",
        "Trades from create (free). NP_hold needs complete sells.",
        "INFO label for the mega-swarm watch item. Re-judge only with new forward grounding.",
        "Pool: 10 gated rows, 6T/2W; 6 trap mints / 2 winner mints; U 0, p 0.76.",
        complete=True,
        thr=-3,
        dir="<=",
        none_unscored=False,
    ),
    _f(
        "P2-SWARM-VET-v1",
        p2_swarm_vet_v1,
        "watch",
        "swarm-exit",
        ">= 10 non-insider holders at dslot were sellers in one >= 10-seller slot of a single earlier "
        "launch (time-ordered).",
        "The slot-carrying full-program feed, plus memory over all launches.",
        "Candidate only after >= 3 forward trap mints from >= 2 creators on >= 2 days.",
        "Pool: 2 gated rows, 1 trap mint, 1 block; p 0.68.",
        memory=True,
        thr=10,
    ),
    _f(
        "CC-TOPDIST-v1",
        cc_topdist_v1,
        "info",
        "crowd-cascade",
        "The top-10 holder cohort fixed at w0 = dslot - 223 slots sold >= 35% of its w0 holding in "
        "(w0, dslot]; each wallet's sells capped at its w0 holding.",
        "Trades from create (free).",
        "Logged raw only. Re-score after >= 2 forward weeks under its own pre-registered bars.",
        "Pool: 28-31 gated rows, 20-23T/3W; 3 winner mints; p 0.26-0.37.",
        thr=0.35,
    ),
    _f(
        "CC-CHEAPLOAD-v1",
        cc_cheapload_v1,
        "retired",
        "crowd-cascade",
        "(Holdings of holders still at or above break-even at my -50% line) / (tokens needed to reach "
        "that line) >= 1.",
        "Trades from create.",
        "None.",
        "0/11 grounding mints; p 0.90; 6 winner mints.",
        thr=1.0,
    ),
    _f(
        "POSTHOC-CC-FRAGILE-v0",
        posthoc_cc_fragile_v0,
        "retired",
        "crowd-cascade",
        "The inverse of CHEAPLOAD (raw <= 0.05), chosen post hoc.",
        "Trades from create.",
        "None. Never scored.",
        "Curve-level proxy.",
        thr=0.05,
        dir="<=",
        score=False,
    ),
    _f(
        "LC-XFERSUP-v1",
        lc_xfersup_v1,
        "info",
        "late-collapse",
        "Sum over wallets of curve-sold minus curve-bought tokens, counting only per-wallet excess "
        "> 1e12, / 1e15 >= 0.055 (v1_transfer_in at an 11x higher cut).",
        "Complete trades.",
        "Evaluate forward at the frozen 0.055 cut only.",
        "Pool: 28 gated rows, 18T/1W; 13 trap mints / 1 winner mint; p 0.19; MH 0.96.",
        complete=True,
        thr=0.055,
    ),
    _f(
        "LC-REPUMP-v1",
        lc_repump_v1,
        "retired",
        "late-collapse",
        "The deepest pre-D dump from a peak >= 11.66 is >= 70% with >= 50% recovery by D.",
        "Free.",
        "None.",
        "1 grounding mint; loses to the d_real_60s- placebo.",
        thr=0.70,
    ),
    _f(
        "CLD-REACTFLOAT-v1",
        cld_reactfloat_v1,
        "retired",
        "closed-loop-drain",
        "Float share held by non-insider holders with >= 2 buys or >= 1 sell is >= 0.60.",
        "Complete trades.",
        "None.",
        "p 0.37; MH 0.79; loses to 4 of 8 placebos.",
        complete=True,
        thr=0.60,
    ),
    _f(
        "CLD-ORPHAN-v1d",
        cld_orphan_v1d,
        "info",
        "closed-loop-drain",
        "ORPHAN counting only holders >= 0.1% of supply; threshold 0.65.",
        "Complete trades plus first-buy slots.",
        "Logged next to ORPHAN to measure dust-holder evasion. No verdict.",
        "Pool: 12 rows, 8T/1W (it kills EQu3MS2h@300).",
        complete=True,
        thr=0.65,
    ),
    _f(
        "REF-DRAIN75",
        ref_drain75,
        "info",
        "reference",
        "Reference, not a filter: the trap line needs >= 75% of entry real SOL to leave.",
        "Free.",
        "Curve-level baseline in the weekly comparison only.",
        "Pool: 39 rows, 23T/2W; MH 0.13. It is the stratum variable itself.",
        thr=0.75,
    ),
    _f(
        "SH-WASH-1",
        sh_wash_1,
        "info",
        "sharpen",
        "Wallets that flip buy/sell >= 3 times account for >= 30% of SOL volume (and real_d >= 11.73).",
        "Trades from create.",
        "Log only.",
        "Pool: 26 gated rows, 17T/1W; 12 trap mints / 1 winner mint; p 0.21.",
        thr=0.30,
    ),
    _f(
        "N-ANAT-FADE",
        n_anat_fade,
        "info",
        "anatomy",
        "real_d >= 13 and pre-D drawdown 1 - real_d / peak >= 0.30.",
        "Free.",
        "Log only. It serves as the placebo bar, not a member.",
        "Pool: 36 gated rows, 29T/1W; 21 trap mints / 1 winner mint; p 0.015; MH 3.9.",
        thr=0.30,
    ),
    _f(
        "N-ANAT-LOCKSTEP",
        n_anat_lockstep,
        "info",
        "anatomy",
        "Lockstep cohort (pairs buying within 35% of each other in >= 2 slots of <= 4 buyers) holds "
        ">= 10% of positive holdings.",
        "Trades from create.",
        "Log only.",
        "Pool: 30 gated rows, 19T/2W; 16 trap mints / 2 winner mints; p 0.30; MH 1.03.",
        thr=0.10,
    ),
    _f(
        "N-LTE-FACTORY",
        n_lte_factory,
        "info",
        "early",
        "Creator (or dev) has >= 5 earlier launches in the ledger (loopholetape 31/08-29/09 + census) "
        "AND 13 <= real_d < 30.",
        "Memory of creators plus the external loopholetape ledger (--lt-ledger); not scored without it.",
        "Log only, until a universe-normalised version is registered.",
        "Pool: 37 gated rows, 29T/3W (20 trap mints / 3 winner mints), p 0.13.",
        memory=True,
        thr=5,
    ),
    _f(
        "N-LTE-FACTORY_REPEAT1",
        n_lte_factory_repeat1,
        "info",
        "early",
        "N-LTE-FACTORY with >= 1 earlier launch.",
        "As N-LTE-FACTORY.",
        "Log only, until a universe-normalised version is registered.",
        "Pool: 40 rows, 32T/3W, p 0.083.",
        memory=True,
        thr=1,
    ),
    _f(
        "N-WM-XIN",
        n_wm_xin,
        "info",
        "memory",
        "Oversold tokens on c by wallets with >= 1 earlier XFER event, / 1e15 >= 0.005.",
        "Memory. The >= 1-event reputation is not universe-normalised.",
        "Log only. v2b is its normalised successor.",
        "Pool: 78 gated rows, 53T/4W; 34 trap mints / 3 winner mints; p 0.015; MH 1.92.",
        complete=True,
        memory=True,
        thr=0.005,
    ),
    _f(
        "N-MMAAS-MSTX",
        n_mmaas_mstx,
        "info",
        "mmaas",
        "Some transaction holds sell events from >= 2 wallets and no buys, before D.",
        "Signature grouping (PumpPortal has signatures, not tx_index).",
        "Log only. Feeds the multisig-exit watch item.",
        "Pool: 7 gated rows, 4T/0W; 3 trap mints; p 0.43.",
        thr=1,
    ),
    _f(
        "N-MMAAS-DUSTHOLD",
        n_mmaas_dusthold,
        "info",
        "mmaas",
        ">= 20 wallets whose only events are one buy < 0.005 SOL.",
        "Complete trades.",
        "Log only. Also a dust-evasion probe for ORPHAN.",
        "Pool: 7 gated rows, 6T/0W; 4 trap mints; p 0.21.",
        complete=True,
        thr=20,
    ),
    _f(
        "v1:S1_early_hold",
        v1_s1_early_hold,
        "info",
        "v1",
        "Create-slot wallets (buy in slot s0 or s0+1, plus dev and creator) still hold >= 5%.",
        "Trades from create.",
        "Log only. It kills winners.",
        "Pool: 49 gated rows, 27T/8W; p 0.88; MH 0.73.",
        complete=True,
        thr=0.05,
    ),
    _f(
        "v1:S1_top10",
        v1_s1_top10,
        "info",
        "v1",
        "Top-10 (from trades) >= 20% of supply.",
        "Trades from create.",
        "Log only.",
        "Pool: 116 of 137 gated rows, 71T/11W; p 0.17. Degenerate as a veto.",
        complete=True,
        thr=0.20,
    ),
    _f(
        "v1:S1_flippers",
        v1_s1_flippers,
        "info",
        "v1",
        ">= 8 wallets sell within 5 slots of their own buy.",
        "Trades with slot.",
        "Log only.",
        "Pool: 60 gated rows, 37T/5W; p 0.29.",
        thr=8,
    ),
    _f(
        "v1:S1_transfer_in",
        v1_s1_transfer_in,
        "info",
        "v1",
        "Wallets selling more than they bought hold >= 0.5% of supply.",
        "Complete trades.",
        "Log only. It is the raw behind LC-XFERSUP.",
        "Pool: 89 gated rows, 58T/7W; p 0.086; MH 1.8.",
        complete=True,
        thr=0.005,
    ),
    _f(
        "v1:S1_spike",
        v1_s1_spike,
        "info",
        "v1",
        "Real SOL rises >= 10 within 60 s.",
        "Free.",
        "Log only.",
        "Pool: 19 gated rows, 11T/2W; p 0.57.",
        thr=10,
    ),
    _f(
        "v1:S0_selfgrad_fill",
        v1_s0_selfgrad_fill,
        "info",
        "v1",
        "Wallets buying in the create slot or the next bought >= 20 SOL (SIEVE v1 tier 0).",
        "Trades from create.",
        "Log only. Not part of the honest active chain.",
        "Pool: 24 gated rows, 17T/3W; p 0.47.",
        thr=20,
    ),
    _f(
        "v1:S1_dev_hold",
        v1_s1_dev_hold,
        "info",
        "v1",
        "dev + creator net >= 3% (SIEVE v1 tier 1; ungated twin of SH-DEV-1).",
        "Trades from create.",
        "Log only (v1 chain member).",
        complete=True,
        thr=0.03,
    ),
    _f(
        "v1:S1_wash",
        v1_s1_wash,
        "info",
        "v1",
        "Wallets with >= 3 side switches account for >= 30% of SOL volume (SIEVE v1 tier 1).",
        "Trades from create.",
        "Log only (v1 chain member).",
        thr=0.30,
    ),
    _f(
        "RAY-HOT-v1",
        ray_hot_v1,
        "shadow",
        "ray-live",
        ">= 300 curve trades in the 120 s up to the decision slot.",
        "Per-token trades up to the decision slot.",
        "Decides in Ray only while its forward record passes ray/app/live_rules.py (PREREG-RAY-L1).",
        "Ray journal 09/10/2026, threshold from the first 232 rows (15:05-16:46 UTC; 80th percentile 324, "
        "rounded): +17 points of traps vs the rows' band x D, winners 16% vs 19%. Unchanged on the next "
        "155 rows: +16 points (38 rows, 31 mints), winners 11% vs 16%.",
        thr=300,
    ),
    _f(
        "RAY-WASH-v1",
        ray_wash_v1,
        "shadow",
        "ray-live",
        "SH-WASH-1's measure as a shadow member: wallets with >= 3 side switches carry >= 30% of the "
        "gross curve volume (and real_d >= 11.73).",
        "Complete per-token trades from create.",
        "Decides in Ray only while its forward record passes ray/app/live_rules.py (PREREG-RAY-L1).",
        "SH-WASH-1 (INFO, threshold frozen 08/10) on the Ray journal 09/10/2026: first 233 rows +14 points "
        "of traps vs band x D, winners 4% vs 22%; next 155 rows +11 points (17 rows), winners 6% vs 10%.",
        complete=True,
        thr=0.30,
    ),
]
BY_ID = {d["id"]: d for d in REGISTRY}
V1_CHAIN = [
    "v1:S0_selfgrad_fill",
    "v1:S1_top10",
    "v1:S1_dev_hold",
    "v1:S1_wash",
    "v1:S1_spike",
    "v1:S1_flippers",
    "v1:S1_transfer_in",
    "v1:S1_early_hold",
]


def members(tier):
    return [d["id"] for d in REGISTRY if d["tier"] == tier and d["id"] != "GATE_E"]


def chains():
    """Chain name -> (gated, member ids). 'v1' is the SIEVE.md section 5 chain as built (no gate)."""
    act = members("active")
    return {
        "none": (False, []),
        "bare gate": (True, None),
        "v1": (False, V1_CHAIN),
        "v1 gated": (True, V1_CHAIN),
        "active": (True, act),
        "active+shadow": (True, act + members("shadow")),
    }


def evaluate(c, ids=None):
    """{id: (fired, raw)} for every registry filter (or `ids`) on candidate c."""
    out = {}
    for d in REGISTRY:
        if ids is None or d["id"] in ids:
            fired, raw = d["fn"](c)
            out[d["id"]] = (bool(fired), raw)
    return out


# ============================================================ frozen definitions
_NOT_HASHED = {"REGISTRY", "BY_ID", "FROZEN", "V1_CHAIN", "__name__", "__file__", "__doc__"}


def _reach(fn):
    """Source of fn plus every module-level function, class and constant it reaches."""
    g = globals()
    seen = {}
    stack = [fn]
    while stack:
        obj = stack.pop()
        key = getattr(obj, "__qualname__", repr(obj))
        if key in seen:
            continue
        seen[key] = inspect.getsource(obj)
        codes = []
        if inspect.isfunction(obj):
            codes.append(obj.__code__)
        else:
            codes += [m.__code__ for m in vars(obj).values() if inspect.isfunction(m)]
        names = set()
        while codes:
            co = codes.pop()
            names.update(co.co_names)
            codes += [k for k in co.co_consts if isinstance(k, types.CodeType)]
        for n in sorted(names):
            o = g.get(n)
            if (inspect.isfunction(o) or inspect.isclass(o)) and getattr(o, "__module__", None) == __name__:
                stack.append(o)
            elif isinstance(o, int | float | str | tuple | frozenset | dict) and n not in _NOT_HASHED:
                seen["const:" + n] = repr(o)
    return "\n".join(seen[k] for k in sorted(seen))


def definition_hash(fid):
    """Hash of the filter function, everything it reaches, and the candidate / memory classes."""
    src = _reach(BY_ID[fid]["fn"]) + _reach(Cand) + _reach(Memory)
    return hashlib.sha256(src.encode()).hexdigest()[:16]


# Frozen 2026-10-08 (founding registry). Never edit a value here to make --check pass: register a new
# id/version instead and freeze its hash.
FROZEN = {
    "GATE_E": "8eb9850fe51cb59d",
    "SH-DEV-1": "30bae1cbfbb957a6",
    "N-MMAAS-WAVE-STREAM": "f3631a784876a3ca",
    "SH-SG-1": "367480282fdda01c",
    "N-MMAAS-SPLDIST": "1f10d03b3694b6f6",
    "N-MMAAS-WAVE": "0b04adf004536ba2",
    "N-WM-EXIT2-v2b": "7c50876413e8f3ee",
    "CLD-ORPHAN-v1": "55f65955c88b7abe",
    "N-WM-EXIT2": "8a24f527e04748f4",
    "N-WM-EXIT2-v2a": "59aa147996d5b711",
    "P1-SWARM-SCRIPTED-v1": "4a1f9630ab47ab63",
    "P2-SWARM-VET-v1": "08ab80c7a501b17c",
    "CC-TOPDIST-v1": "72b15e4beb91df07",
    "CC-CHEAPLOAD-v1": "898dcb8794408f55",
    "POSTHOC-CC-FRAGILE-v0": "3cc970758f80e037",
    "LC-XFERSUP-v1": "67cf51653ed7e90a",
    "LC-REPUMP-v1": "e2d8546ac8951a8c",
    "CLD-REACTFLOAT-v1": "60b0282087046db7",
    "CLD-ORPHAN-v1d": "53ddf374d479c790",
    "REF-DRAIN75": "50b48d59c3dc5df4",
    "SH-WASH-1": "e529ee41225d5a32",
    "N-ANAT-FADE": "c6bf5246cb242df6",
    "N-ANAT-LOCKSTEP": "5125545d8a09089a",
    "N-LTE-FACTORY": "3c51e1062bb76bfd",
    "N-LTE-FACTORY_REPEAT1": "463c42656d55809e",
    "N-WM-XIN": "bbb670706e381bbf",
    "N-MMAAS-MSTX": "f9682e62e88f5ac8",
    "N-MMAAS-DUSTHOLD": "2f340082c66cd3ac",
    "v1:S1_early_hold": "00a8954f326c6aed",
    "v1:S1_top10": "fd4d4edbf4f309b6",
    "v1:S1_flippers": "c23ffe53cb2691eb",
    "v1:S1_transfer_in": "183bc503d9cf620d",
    "v1:S1_spike": "e79f2e532870538c",
    "v1:S0_selfgrad_fill": "2affeacb4430bd59",
    "v1:S1_dev_hold": "39d7dcfde5bc954b",
    "v1:S1_wash": "6360b57c767fb5b0",
    # Ray live round 1, frozen 2026-10-09 (docs/PREREG-RAY-L1.md)
    "RAY-HOT-v1": "5e0698bae2b2c6fb",
    "RAY-WASH-v1": "d3abfd51b48ed38f",
}


def check_frozen():
    bad = []
    for d in REGISTRY:
        h = definition_hash(d["id"])
        want = FROZEN.get(d["id"])
        if want is None:
            bad.append((d["id"], "not frozen", h))
        elif want != h:
            bad.append((d["id"], f"edited in place (frozen {want})", h))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sieve filter registry.")
    ap.add_argument("--check", action="store_true", help="fail if a frozen definition was edited")
    ap.add_argument("--hashes", action="store_true", help="print the current definition hashes")
    ap.add_argument("--list", action="store_true", help="list the registry")
    a = ap.parse_args(argv)
    if a.hashes:
        for d in REGISTRY:
            print(f'    "{d["id"]}": "{definition_hash(d["id"])}",')
    if a.list:
        for d in REGISTRY:
            print(f"{d['id']:24s} {d['tier']:8s} {d['family']:18s} {d['definition']}")
    if a.check:
        bad = check_frozen()
        for b in bad:
            print("FROZEN CHECK:", *b)
        print("frozen check:", "OK" if not bad else f"{len(bad)} problem(s)")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
