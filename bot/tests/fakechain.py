"""A pool's on-chain history served the way RPC providers serve it, for SwapFetcher tests.

Real PumpSwap swap transactions (tests/fixtures/pumpswap) plus synthetic MEV noise: successful
transactions that name the pool and trade nothing, which bots send by the thousand on busy pools.
"""

import json
from pathlib import Path

import httpx

from app.pumpswap import swaps_from_tx
from app.rpc import RpcError

POOL = "F4WJkbXMz8C6GXGeymcKQpXaVkUMdyrqLHc7buEUMRJp"
MINT = "TokMint1111111111111111111111111111111111111"
FIX = Path(__file__).parent / "fixtures" / "pumpswap"
_REF_SLOT, _REF_TS, _SLOTS_PER_S = 453_878_728, 1_791_283_582, 3.76  # measured on the fixtures


def real_swaps() -> dict[str, dict]:
    """The four fixture swaps of POOL, keyed by a stand-in signature (the fixtures were slimmed)."""
    out = {}
    for i, p in enumerate(sorted(FIX.glob("*.json"))):
        tx = json.loads(p.read_text())
        tx["transactionIndex"] = 10 + i
        tx["transaction"]["signatures"] = [p.stem]
        out[p.stem] = tx
    return out


def slot_of(ts: float) -> int:
    return _REF_SLOT + round((ts - _REF_TS) * _SLOTS_PER_S)


def noise(n: int, t_from: int, t_to: int, tag: str = "mev") -> list[dict]:
    """`n` successful transactions naming the pool and trading nothing, spread over [t_from, t_to]."""
    out = []
    for i in range(n):
        ts = t_from + (t_to - t_from) * i // max(1, n - 1)
        out.append(
            {
                "slot": slot_of(ts),
                "transactionIndex": 500 + i,
                "blockTime": ts,
                "transaction": {
                    "signatures": [f"{tag}{i}"],
                    "message": {"accountKeys": [POOL], "instructions": []},
                },
                "meta": {"err": None, "innerInstructions": [], "logMessages": []},
            }
        )
    return out


def is_trade(tx: dict, pool: str = POOL) -> bool:
    return bool(swaps_from_tx(tx, pool=pool))


class FakeChain:
    """getTransactionsForAddress (full or signatures, asc or desc, blockTime filters, paginated),
    getSignaturesForAddress and getTransaction over one list of transactions.

    token_filter: how the provider treats `tokenTransfer`: "honour" (keeps the trades only),
    "ignore" (returns everything), "drop" (honours it but loses one trade), "reject" (errors)."""

    def __init__(
        self,
        txs,
        *,
        gtfa=True,
        token_filter="honour",
        max_full=1000,
        too_large_above=None,
        finalized_only=True,
        pool=POOL,
        missed=(),
    ):
        self.txs = sorted(txs, key=lambda t: (t["slot"], t.get("transactionIndex", 0)))
        self.by_sig = {t["transaction"]["signatures"][0]: t for t in self.txs}
        self.gtfa = gtfa
        self.token_filter = token_filter
        self.max_full = max_full
        self.too_large_above = too_large_above
        self.finalized_only = finalized_only  # like Helius: tokenTransfer needs finalized commitment
        self.pool = pool
        self.missed = set(missed)  # signatures the filter's index lacks (seen once on Helius)
        self.calls: list[dict] = []
        self.sig_calls: list[tuple] = []
        self.tx_calls: list[str] = []

    async def get_transactions_for_address(
        self, address, *, full, sort, limit, filters, pagination_token=None, commitment="confirmed"
    ):
        filtered = "tokenTransfer" in filters
        self.calls.append(
            {
                "full": full,
                "sort": sort,
                "limit": limit,
                "filtered": filtered,
                "bt": filters.get("blockTime"),
                "commitment": commitment,
                "address": address,
            }
        )
        if filtered and self.finalized_only and commitment != "finalized":
            raise RpcError(-32602, "Invalid params: tokenTransfer filter requires finalized commitment")
        if self.gtfa is not True:
            raise RpcError(-32601, "Method not found") if not self.gtfa else RpcError(-32000, self.gtfa)
        if filtered and self.token_filter == "reject":
            raise RpcError(-32602, "Invalid params: unknown field `tokenTransfer`")
        if full and self.too_large_above and limit > self.too_large_above:
            req = httpx.Request("POST", "http://rpc.invalid")
            raise httpx.HTTPStatusError("413", request=req, response=httpx.Response(413, request=req))
        bt = filters.get("blockTime") or {}
        lo, hi = bt.get("gte", float("-inf")), bt.get("lte", float("inf"))
        sl = filters.get("slot") or {}
        s_lo, s_hi = sl.get("gte", float("-inf")), sl.get("lte", float("inf"))
        items = [t for t in self.txs if lo <= t["blockTime"] <= hi and s_lo <= t["slot"] <= s_hi]
        if filtered and self.token_filter in ("honour", "drop"):
            items = [t for t in items if is_trade(t, self.pool)]
            items = [t for t in items if t["transaction"]["signatures"][0] not in self.missed]
            if self.token_filter == "drop":
                items = items[1:]
        if sort == "desc":
            items = items[::-1]
        start = int(pagination_token or 0)
        size = min(limit, self.max_full if full else 1000)
        chunk = items[start : start + size]
        nxt = start + size
        if not full:
            chunk = [
                {
                    "signature": t["transaction"]["signatures"][0],
                    "slot": t["slot"],
                    "transactionIndex": t.get("transactionIndex", 0),
                    "blockTime": t["blockTime"],
                    "err": None,
                }
                for t in chunk
            ]
        return {"data": chunk, "paginationToken": str(nxt) if nxt < len(items) else None}

    async def get_signatures(self, address, limit=1000, before=None, until=None):
        self.sig_calls.append((address, limit, before))
        newest = [
            {
                "signature": t["transaction"]["signatures"][0],
                "blockTime": t["blockTime"],
                "slot": t["slot"],
                "err": None,
            }
            for t in reversed(self.txs)
        ]
        start = 0
        if before:
            start = next(i for i, s in enumerate(newest) if s["signature"] == before) + 1
        return newest[start : start + limit]

    async def get_transaction(self, signature):
        self.tx_calls.append(signature)
        return self.by_sig.get(signature)
