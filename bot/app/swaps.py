"""Fetch a pool's swaps from the RPC: the signature index gives every transaction that touched
the pool since it was created; getTransaction gives the swap events.

Credits are the constraint (1 per signature page, 1 per transaction), so a pool is read as:
  * every transaction in the first `full_window_s` after migration, capped at `max_full`
    (the cells with short horizons live here, and so does the drawdown path), plus
  * for each decision time (entries and exits), the last transaction at or before it, which
    fixes the pool state at that moment even when the full window had to be capped.
"""

from collections.abc import Sequence
from typing import Any

from .pumpswap import Swap, swaps_from_tx
from .rpc import SolanaRpc


class SwapFetcher:
    def __init__(self, rpc: SolanaRpc, max_pages: int = 25):
        self.rpc = rpc
        self.max_pages = max_pages

    async def signatures_since(self, pool: str, since_ts: float) -> tuple[list[dict[str, Any]], int]:
        """Successful signatures mentioning `pool` with blockTime >= since_ts, oldest first, and
        the number of pages (credits) it took."""
        out: list[dict[str, Any]] = []
        before = None
        pages = 0
        while pages < self.max_pages:
            page = await self.rpc.get_signatures(pool, limit=1000, before=before)
            pages += 1
            if not page:
                break
            out.extend(s for s in page if not s.get("err") and (s.get("blockTime") or 0) >= since_ts)
            if len(page) < 1000 or (page[-1].get("blockTime") or 0) < since_ts:
                break
            before = page[-1]["signature"]
        out.sort(key=lambda s: (s.get("blockTime") or 0, s.get("slot") or 0))
        return out, pages

    @staticmethod
    def select(
        sigs: Sequence[dict[str, Any]], full_until: float, max_full: int, point_times: Sequence[float]
    ) -> list[dict[str, Any]]:
        """Which transactions to fetch: the full window (oldest first, capped) plus one per later point."""
        chosen: dict[str, dict[str, Any]] = {}
        for s in sigs:
            if (s.get("blockTime") or 0) <= full_until:
                if len(chosen) >= max_full:
                    break
                chosen[s["signature"]] = s
        for t in point_times:
            last = None
            for s in sigs:
                if (s.get("blockTime") or 0) <= t:
                    last = s
                else:
                    break
            if last is not None:
                chosen.setdefault(last["signature"], last)
        return sorted(chosen.values(), key=lambda s: (s.get("blockTime") or 0, s.get("slot") or 0))

    async def fetch(
        self, pool: str, t0: float, full_until: float, max_full: int, point_times: Sequence[float]
    ) -> tuple[list[Swap], dict[str, Any]]:
        sigs, pages = await self.signatures_since(pool, t0 - 60)
        wanted = self.select(sigs, full_until, max_full, point_times)
        swaps: list[Swap] = []
        missing = 0
        for s in wanted:
            tx = await self.rpc.get_transaction(s["signature"])
            if tx is None:
                missing += 1
                continue
            swaps.extend(swaps_from_tx(tx, pool=pool, signature=s["signature"]))
        swaps.sort(key=lambda x: (x.ts, x.slot))
        in_window = sum(1 for s in sigs if (s.get("blockTime") or 0) <= full_until)
        return swaps, {
            "listed": len(sigs),
            "pages": pages,
            "in_window": in_window,
            "fetched": len(wanted),
            "missing": missing,
            "swaps": len(swaps),
            "window_truncated": in_window > max_full,
            "credits": pages + len(wanted),
        }
