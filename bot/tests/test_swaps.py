"""SwapFetcher selection and paging against a fake RPC."""

import asyncio
import json
from pathlib import Path

from app.swaps import SwapFetcher

FIX = Path(__file__).parent / "fixtures" / "pumpswap"


class FakeRpc:
    def __init__(self, sigs_newest_first, txs):
        self.sigs = sigs_newest_first
        self.txs = txs
        self.sig_calls = []
        self.tx_calls = []

    async def get_signatures(self, address, limit=1000, before=None, until=None):
        self.sig_calls.append((address, limit, before))
        start = 0
        if before:
            start = next(i for i, s in enumerate(self.sigs) if s["signature"] == before) + 1
        return self.sigs[start : start + limit]

    async def get_transaction(self, signature):
        self.tx_calls.append(signature)
        return self.txs.get(signature)


def sig(s, bt, err=None):
    return {"signature": s, "blockTime": bt, "slot": bt, "err": err}


def test_select_takes_the_full_window_then_one_tx_per_later_point():
    sigs = [sig(f"s{i}", 100 + i * 10) for i in range(20)]  # oldest first, 100..290
    chosen = SwapFetcher.select(sigs, full_until=150, max_full=100, point_times=[205, 207, 1000])
    assert [s["signature"] for s in chosen] == ["s0", "s1", "s2", "s3", "s4", "s5", "s10", "s19"]
    # the cap keeps the earliest transactions (the entry side of every cell)
    capped = SwapFetcher.select(sigs, full_until=150, max_full=3, point_times=[])
    assert [s["signature"] for s in capped] == ["s0", "s1", "s2"]
    # a decision time inside a capped window still gets the transaction that fixes its state
    capped_pt = SwapFetcher.select(sigs, full_until=150, max_full=3, point_times=[145])
    assert [s["signature"] for s in capped_pt] == ["s0", "s1", "s2", "s4"]
    assert SwapFetcher.select(sigs, full_until=50, max_full=3, point_times=[90]) == []  # nothing that early


def test_fetch_pages_back_to_the_pool_creation_and_decodes_only_this_pool():
    real = {p.stem: json.loads(p.read_text()) for p in sorted(FIX.glob("*.json"))}
    pool = "F4WJkbXMz8C6GXGeymcKQpXaVkUMdyrqLHc7buEUMRJp"
    t = {k: v["blockTime"] for k, v in real.items()}
    # newest first like the RPC; two pages of 1000 would be needed if there were that many; here 4 + noise
    sigs = [sig("newer-noise", max(t.values()) + 100)] + [
        sig(k, t[k]) for k in sorted(t, key=lambda k: -t[k])
    ]
    sigs += [sig("failed", t["BuyEvent_3"] - 1, err={"x": 1}), sig("older-than-pool", t["BuyEvent_3"] - 5000)]
    rpc = FakeRpc(sigs, dict(real))
    f = SwapFetcher(rpc, max_pages=5)
    t0 = t["BuyEvent_3"] - 10
    swaps, st = asyncio.run(f.fetch(pool, t0, full_until=t0 + 100_000, max_full=100, point_times=[]))
    assert (
        st["pages"] == 1 and st["listed"] == 5 and st["fetched"] == 5 and st["missing"] == 1
    )  # newer-noise has no tx
    assert [s.side for s in swaps] == ["buy", "sell", "buy", "sell"] and st["swaps"] == 4
    assert "failed" not in rpc.tx_calls and "older-than-pool" not in rpc.tx_calls
    assert st["credits"] == 6 and st["window_truncated"] is False


def test_fetch_stops_paging_at_max_pages():
    sigs = [sig(f"s{i}", 10_000 - i) for i in range(2500)]
    rpc = FakeRpc(sigs, {})
    f = SwapFetcher(rpc, max_pages=2)
    got, pages = asyncio.run(f.signatures_since("P", 0))
    assert pages == 2 and len(got) == 2000 and got[0]["signature"] == "s1999"
