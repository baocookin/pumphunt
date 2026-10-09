"""Decision-time features of a launch: what its own trades show up to the decision slot, and what
its early buyers did in earlier launches (the wallet memory, app/wallets.py).

Every feature reads only trades with slot <= the decision slot, and the memory holds only launches
Ray had scored before this decision (their outcomes only once known), so a feature never sees the
future. The definitions here are frozen with the native filters that read them (app/native.py):
editing one changes their hashes, and the health check reports it.

Curve features (the launch's own trades):
  n120, trades60          trades in the last 120 / 60 s
  wallets120              distinct wallets trading in the last 120 s
  per_wallet120           trades per such wallet (bots trade many times each)
  cadence_cv120           coefficient of variation of the slot gaps between those trades (a timer
                          trades at even gaps: low; people trade in bursts: high)
  same_size_share         share of buys whose exact lamport amount repeats >= 3 times
  dust_buyers             share of buyers whose buys add up to < 0.01 SOL (holder-count padding)
  sell_sol_share60        SOL sold / SOL traded in the last 60 s
  wash_share              research/sieve's SH-WASH-1 measure
  top5_buy_share          share of all buy SOL from the five largest buyers
  d_real_60s, dd_pre      real SOL gained in 60 s; drawdown from the peak before the decision
Memory features (the launch's early buyers: buys in its first 60 s, up to the decision slot):
  n_early                 distinct early buyers
  serial_share/_vol       share of them (of their SOL) that were early buyers in >= 2 earlier launches
  dumper_share/_vol       share of them (of their SOL) that dumped early in an earlier launch: sold
                          >= half of their early tokens before that launch's first decision
  trapw_vol               share of early SOL from wallets whose earlier early launches (>= 2 with a
                          known outcome) were >= 70% traps
  dev_prior, dev_traps    the dev's earlier launches Ray scored, and their trap share (known ones)
"""

from collections import Counter, defaultdict
from typing import Any

from .sieve import FL

SLOT, TX, EV, TS, USER, BUY, SOL, TOK, VS, VT, IX = range(11)
LAMPORTS = 1_000_000_000
EARLY_S = 60
DUST_SOL = 0.01
DUMP_SHARE = 0.5
SERIAL_MIN, TRAPW_MIN_RESOLVED, TRAPW_SHARE = 2, 2, 0.7


def early_slot(row: dict[str, Any]) -> int:
    return int(row["create_slot"]) + round(EARLY_S / FL.SPS)


def early_activity(row: dict[str, Any], upto_slot: int) -> tuple[dict[str, float], set[str]]:
    """({early buyer: SOL bought early}, {early buyers who sold >= half of their early tokens}),
    from the trades up to `upto_slot`."""
    end = early_slot(row)
    bought_sol: dict[str, float] = defaultdict(float)
    bought_tok: dict[str, int] = defaultdict(int)
    sold_tok: dict[str, int] = defaultdict(int)
    for t in row.get("trades") or []:
        slot = int(t[SLOT])
        if slot > upto_slot:
            break
        u = t[USER]
        if t[BUY]:
            if slot <= end:
                bought_sol[u] += int(t[SOL]) / LAMPORTS
                bought_tok[u] += int(t[TOK])
        elif u in bought_tok:
            sold_tok[u] += int(t[TOK])
    dumpers = {u for u, n in bought_tok.items() if n and sold_tok[u] >= DUMP_SHARE * n}
    return dict(bought_sol), dumpers


def curve_features(cand: Any) -> dict[str, float]:
    """The launch's own trades up to the decision slot (cand: research/sieve Cand)."""
    vis = cand.vis
    dslot = cand.dslot
    w60, w120 = dslot - FL.W60, dslot - FL.W120
    last120 = [t for t in vis if int(t[SLOT]) > w120]
    last60 = [t for t in last120 if int(t[SLOT]) > w60]
    wallets120 = {t[USER] for t in last120}
    gaps = [int(b[SLOT]) - int(a[SLOT]) for a, b in zip(last120, last120[1:], strict=False)]
    if len(gaps) >= 2:
        mean = sum(gaps) / len(gaps)
        sd = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5
        cadence_cv = sd / mean if mean > 0 else 0.0
    else:
        cadence_cv = 0.0
    buys = [t for t in vis if t[BUY]]
    sizes = Counter(int(t[SOL]) for t in buys)
    by_buyer: dict[str, float] = defaultdict(float)
    for t in buys:
        by_buyer[t[USER]] += int(t[SOL]) / LAMPORTS
    total_buy = sum(by_buyer.values())
    top5 = sum(sorted(by_buyer.values(), reverse=True)[:5])
    sold60 = sum(int(t[SOL]) for t in last60 if not t[BUY])
    traded60 = sum(int(t[SOL]) for t in last60)
    v1 = cand.get("v1", FL._v1)
    an = cand.get("an", FL._an)
    sh = cand.get("sh", FL._sh)
    return {
        "n120": float(len(last120)),
        "trades60": float(len(last60)),
        "wallets120": float(len(wallets120)),
        "per_wallet120": len(last120) / len(wallets120) if wallets120 else 0.0,
        "cadence_cv120": cadence_cv,
        "same_size_share": sum(n for n in sizes.values() if n >= 3) / len(buys) if buys else 0.0,
        "dust_buyers": sum(1 for s in by_buyer.values() if s < DUST_SOL) / len(by_buyer) if by_buyer else 0.0,
        "sell_sol_share60": sold60 / traded60 if traded60 else 0.0,
        "wash_share": float(sh["wash_share"]),
        "top5_buy_share": top5 / total_buy if total_buy else 0.0,
        "d_real_60s": float(v1["d_real_60s"]),
        "dd_pre": float(an["dd_pre"]),
    }


def memory_features(early: dict[str, float], dev: str | None, stats: Any, dev_stats: Any) -> dict[str, float]:
    """The early buyers' records in earlier launches. `stats(wallet)` gives (early launches, early
    dumps, resolved, traps) for that wallet before this launch; `dev_stats(dev)` gives (launches,
    resolved, traps) for the dev before this launch."""
    n = len(early)
    total = sum(early.values())
    serial = dumper = 0
    serial_sol = dumper_sol = trapw_sol = 0.0
    for u, sol in early.items():
        launches, dumps, resolved, traps = stats(u)
        if launches >= SERIAL_MIN:
            serial += 1
            serial_sol += sol
        if dumps >= 1:
            dumper += 1
            dumper_sol += sol
        if resolved >= TRAPW_MIN_RESOLVED and traps >= TRAPW_SHARE * resolved:
            trapw_sol += sol
    d_launches, d_resolved, d_traps = dev_stats(dev) if dev else (0, 0, 0)
    return {
        "n_early": float(n),
        "serial_share": serial / n if n else 0.0,
        "serial_vol": serial_sol / total if total else 0.0,
        "dumper_share": dumper / n if n else 0.0,
        "dumper_vol": dumper_sol / total if total else 0.0,
        "trapw_vol": trapw_sol / total if total else 0.0,
        "dev_prior": float(d_launches),
        "dev_traps": d_traps / d_resolved if d_resolved else -1.0,
    }
