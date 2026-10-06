"""How the bonding curve filled before migration, read at harvest time from its oldest page.

Everything here was public before the decision at T+30, so it can enter a pre-registered rule.
Measured on graduates (06/10/2026): one curve was bought out in its creation slot by four
wallets (~79 SOL) and graduated within the minute, then its pool fell 98.6% in the first hour
on PumpSwap; another graduated on its creator's own 85-SOL buy in the creation slot.

Cost on Helius: the oldest 100 transactions of the curve (10 credits) plus a signature count up
to migration (10 credits per 1,000). pump.fun events arrive twice in a transaction (log line
and self-CPI copy); one copy per kind is kept, the CPI one when present (logs get truncated).
"""

from typing import Any

from .rpc import events_from_tx
from .swaps import SwapFetcher

LAMPORTS = 1_000_000_000
PAGE = 100


def pump_events(tx: dict[str, Any]) -> list[dict[str, Any]]:
    """The transaction's pump.fun events, each once: per kind, the self-CPI copies if any."""
    evs = events_from_tx(tx)
    kinds = {e["kind"] for e in evs}
    out = []
    for k in kinds:
        same = [e for e in evs if e["kind"] == k]
        cpi = [e for e in same if e.get("via") == "cpi"]
        out.extend(cpi or same)
    return out


def summarize(
    create: dict[str, Any],
    trades: list[dict[str, Any]],
    t_mig: float,
    page_last_ts: float,
    page_complete: bool,
) -> dict[str, Any]:
    """Features of the curve's first page. `create` and every trade carry `slot` and `ts`."""
    dev = create.get("user")
    s0, t0 = create["slot"], create["ts"]
    buys = [t for t in trades if t.get("is_buy")]
    sells = [t for t in trades if not t.get("is_buy")]

    def sol(xs: list[dict[str, Any]]) -> float:
        return sum(int(x.get("sol_amount") or 0) for x in xs) / LAMPORTS

    in_slot = [t for t in buys if t["slot"] == s0]
    bundle = [t for t in in_slot if t.get("user") != dev]
    early = [t for t in buys if t["slot"] <= s0 + 2]
    first_min = [t for t in trades if t["ts"] <= t0 + 60]
    bundle_wallets = sorted({t["user"] for t in bundle})
    early_wallets = []
    for t in early:
        if t.get("user") != dev and t["user"] not in early_wallets:
            early_wallets.append(t["user"])
    return {
        "t_create": t0,
        "create_slot": s0,
        "dev": dev,
        "creator": create.get("creator"),
        "graduate_s": t_mig - t0,
        "dev_buy_sol": sol([t for t in in_slot if t.get("user") == dev]),
        "bundle_buyers": len(bundle_wallets),
        "bundle_sol": sol(bundle),
        "early_buyers": len({t["user"] for t in early}),  # creation slot and the two after it
        "early_sol": sol(early),
        "buyers_60s": len({t["user"] for t in first_min if t.get("is_buy")}),
        "buy_sol_60s": sol([t for t in first_min if t.get("is_buy")]),
        "sell_sol_60s": sol([t for t in first_min if not t.get("is_buy")]),
        "dev_sell_sol": sol([t for t in sells if t.get("user") == dev]),  # within the page
        "page_span_s": page_last_ts - t0,
        "page_complete": page_complete,  # the whole curve life fit in the page
        "first_minute_complete": page_complete or page_last_ts > t0 + 60,
        "bundle_wallets": bundle_wallets[:10],
        "early_wallets": early_wallets[:10],
    }


async def curve_history(
    fetcher: SwapFetcher, curve: str, mint: str, t_mig: float, count_cap: int = 5_000
) -> dict[str, Any]:
    """{"found": False, ...} when the page holds no creation of `mint` (curve reused, or history
    unavailable), else the features of `summarize` plus the transaction count to migration."""
    spent = fetcher.credits
    res = await fetcher.history_page(curve, full=True, sort="asc", limit=PAGE, t_to=t_mig)
    data = res.get("data") or []
    create: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    for tx in data:
        slot, ts = int(tx.get("slot") or 0), int(tx.get("blockTime") or 0)
        for ev in pump_events(tx):
            if ev.get("mint") != mint:
                continue
            if ev["kind"] == "create" and create is None:
                create = dict(ev, slot=slot, ts=ts)
            elif ev["kind"] == "trade":
                trades.append(dict(ev, slot=slot, ts=ts))
    if create is None:
        return {"found": False, "page_tx": len(data), "credits": fetcher.credits - spent}
    complete = not res.get("paginationToken")
    out = summarize(create, trades, t_mig, int(data[-1].get("blockTime") or create["ts"]), complete)
    if complete:
        n, exact = len(data), True
    else:
        n, exact = await fetcher.count_txs(curve, create["ts"], t_mig, count_cap)
    out.update({"found": True, "page_tx": len(data), "curve_tx": n, "curve_tx_complete": exact})
    out["credits"] = fetcher.credits - spent
    return out
