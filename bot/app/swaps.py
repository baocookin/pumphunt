"""Fetch a pool's swaps from the RPC.

Most transactions that touch a busy PumpSwap pool are not trades: MEV bots name the pool, its
vaults, the mint and even the creator-fee vault in transactions that read the price and exit
(measured: 95 of 100 successful transactions around T+25 min on a pool holding 170 SOL). Yet
half of all pools see fewer than 15 transactions in the 95 minutes after T+25 (40 random pools:
median 13, p90 7,041, max > 31,000). Hence:
  * the pool state at a decision time is the newest SWAP at or before it, found by scanning
    backwards from that time (`states`), never "the last transaction";
  * a complete window costs every transaction in it, trades or not, so when it does not fit in
    one page a cheap signature count decides first whether it fits its cap (`window`);
  * Helius' `tokenTransfer` filter (transfers of the pool's token in or out of the pool's vault)
    would leave only trades. It is used only once side-by-side pages show that the provider
    honours it and keeps every swap, and it is audited from time to time after that.

With Helius every read is `getTransactionsForAddress` (10 credits per 100 full transactions,
10 flat per 1,000 signatures). A provider without the method falls back to the signature index
plus one `getTransaction` (1 credit) per transaction, capped.

Consecutive swaps chain exactly on the token side: one's post-state is the next one's pre-state,
so a complete window with a token-side break is missing a swap. The SOL side also moves between
swaps without one (measured: fees kept in the vault by `buy_exact_quote_in_v2` are swept out
later); those gaps are counted and summed apart.
"""

from collections.abc import Sequence
from typing import Any

import httpx

from .pumpswap import Swap, swaps_from_tx, tx_signature
from .rpc import RpcError, SolanaRpc, gtfa_credits

FULL_PAGE = 1000  # full transactions per window page after the first (Helius' maximum)
FIRST_PAGE = 100  # most windows hold fewer: one 10-credit page settles them


def chain_breaks(swaps: Sequence[Swap]) -> int:
    """Consecutive swaps (chain order) whose token reserves do not hand over exactly: a swap is
    missing between them (or liquidity was added or removed)."""
    return sum(1 for a, b in zip(swaps, swaps[1:], strict=False) if b.base_pre != a.base_post)


def quote_gaps(swaps: Sequence[Swap]) -> tuple[int, int]:
    """(count, net lamports) of SOL that entered or left the vault between consecutive swaps
    whose token reserves did hand over: moves outside any swap, such as fee sweeps."""
    n = total = 0
    for a, b in zip(swaps, swaps[1:], strict=False):
        if b.base_pre == a.base_post and b.quote_pre != a.quote_post:
            n += 1
            total += b.quote_pre - a.quote_post
    return n, total


class SwapFetcher:
    def __init__(
        self,
        rpc: SolanaRpc,
        max_pages: int = 25,
        fallback_max_tx: int = 150,
        scan_page: int = 100,
        scan_pages: int = 3,
        fallback_walk: int = 8,
        token_filter: bool = True,
    ):
        self.rpc = rpc
        self.max_pages = max_pages  # signature-index pages, fallback only
        self.fallback_max_tx = fallback_max_tx
        self.scan_page = scan_page  # transactions per backwards-scan page (10 credits per 100)
        self.scan_pages = scan_pages  # pages spent on one decision time before giving up
        self.fallback_walk = fallback_walk
        self.gtfa: bool | None = None  # unknown until the first call; False: fallback for the run
        self.gtfa_error: str | None = None
        self._gtfa_failures = 0
        # tokenTransfer filter: None while unverified (not used), True verified, False off/unsafe
        self.token_filter: bool | None = None if token_filter else False
        self.filter_checks = {
            "same": 0,
            "reduced": 0,
            "unreduced": 0,
            "violations": 0,
            "audits": 0,
            "repaired": 0,
        }
        self.filter_note: str | None = None
        self._filtered_windows = 0
        self.credits = 0  # everything this fetcher spent, for per-pool metering
        self._sigs_cache: tuple[str, float, list[dict[str, Any]]] | None = None

    # ---- plumbing ----
    def _filters(
        self, t_from: float | None, t_to: float | None, mint: str | None, use_token: bool
    ) -> dict[str, Any]:
        flt: dict[str, Any] = {"status": "succeeded"}
        bt = {}
        if t_from is not None:
            bt["gte"] = int(t_from)
        if t_to is not None:
            bt["lte"] = int(t_to)
        if bt:
            flt["blockTime"] = bt
        if use_token and mint:
            flt["tokenAccounts"] = "balanceChanged"
            flt["tokenTransfer"] = {"mint": mint}
        return flt

    def _use_filter(self, mint: str | None) -> bool:
        return bool(mint) and self.token_filter is True

    async def _page(
        self, pool: str, *, full: bool, sort: str, limit: int, flt: dict[str, Any], token: str | None = None
    ) -> dict[str, Any]:
        """One getTransactionsForAddress page. A 413 (response too large for this provider)
        halves the page; a filter the provider rejects is switched off and the page retried."""
        while True:
            # Helius answers -32602 to tokenTransfer at "confirmed"; harvest reads are a day old,
            # long finalized either way
            commitment = "finalized" if "tokenTransfer" in flt else "confirmed"
            try:
                res = await self.rpc.get_transactions_for_address(
                    pool,
                    full=full,
                    sort=sort,
                    limit=limit,
                    filters=flt,
                    pagination_token=token,
                    commitment=commitment,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 413 and limit > 10:
                    limit //= 2
                    continue
                raise
            except RpcError as exc:
                if "tokenTransfer" in flt and not exc.method_unsupported:
                    self.token_filter = False
                    self.filter_note = f"rejected: {exc.code} {exc.rpc_message[:120]}"
                    flt = {k: v for k, v in flt.items() if k not in ("tokenTransfer", "tokenAccounts")}
                    continue
                raise
            n = len(res.get("data") or [])
            self.credits += gtfa_credits(n) if full else 10
            self._gtfa_failures = 0
            self.gtfa = True
            return res

    def _gtfa_failed(self, exc: RpcError) -> None:
        """An unsupported method ends getTransactionsForAddress for the run at once; other errors
        do after three in a row, so a provider that keeps refusing cannot stall the harvester."""
        self._gtfa_failures += 1
        self.gtfa_error = f"{exc.code}: {exc.rpc_message[:160]}"
        if exc.method_unsupported or self._gtfa_failures >= 3:
            self.gtfa = False

    async def signatures_since(self, pool: str, since_ts: float) -> tuple[list[dict[str, Any]], int]:
        """Successful signatures mentioning `pool` with blockTime >= since_ts, oldest first, and
        the number of pages (credits) it took. Cached for the last pool asked."""
        if self._sigs_cache and self._sigs_cache[0] == pool and self._sigs_cache[1] <= since_ts:
            return [s for s in self._sigs_cache[2] if (s.get("blockTime") or 0) >= since_ts], 0
        out: list[dict[str, Any]] = []
        before = None
        pages = 0
        while pages < self.max_pages:
            page = await self.rpc.get_signatures(pool, limit=1000, before=before)
            pages += 1
            self.credits += 1
            if not page:
                break
            out.extend(s for s in page if not s.get("err") and (s.get("blockTime") or 0) >= since_ts)
            if len(page) < 1000 or (page[-1].get("blockTime") or 0) < since_ts:
                break
            before = page[-1]["signature"]
        out.sort(key=lambda s: (s.get("blockTime") or 0, s.get("slot") or 0))
        self._sigs_cache = (pool, since_ts, out)
        return out, pages

    async def _tx(self, signature: str) -> dict[str, Any] | None:
        self.credits += 1
        return await self.rpc.get_transaction(signature)

    # ---- any address's history (curves, wallets) ----
    async def history_page(
        self,
        address: str,
        *,
        full: bool,
        sort: str,
        limit: int,
        t_from: float | None = None,
        t_to: float | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """One getTransactionsForAddress page of successful transactions; needs the method
        (callers check `gtfa is not False`). Raises RpcError like any read."""
        try:
            return await self._page(
                address,
                full=full,
                sort=sort,
                limit=limit,
                flt=self._filters(t_from, t_to, None, False),
                token=token,
            )
        except RpcError as exc:
            self._gtfa_failed(exc)
            raise

    async def count_txs(self, address: str, t_from: float, t_to: float, cap: int) -> tuple[int, bool]:
        """(successful transactions in [t_from, t_to], whether that is the full count) up to `cap`."""
        try:
            n = await self._count(
                address, int(t_from), int(t_to), self._filters(None, None, None, False), cap
            )
        except RpcError as exc:
            self._gtfa_failed(exc)
            raise
        return min(n, cap), n <= cap

    # ---- windows ----
    async def _count(self, pool: str, t_from: int, t_to: int, flt: dict[str, Any], cap: int) -> int:
        """Successful transactions in [t_from, t_to], counted up to just past `cap`."""
        flt = dict(flt, blockTime={"gte": t_from, "lte": t_to})
        n = 0
        token = None
        while True:
            res = await self._page(pool, full=False, sort="asc", limit=1000, flt=flt, token=token)
            data = res.get("data") or []
            n += len(data)
            token = res.get("paginationToken")
            if not data or not token or n > cap:
                return n

    def _compare(self, pool: str, plain: dict[str, Any], filt: dict[str, Any], t_to: int) -> None:
        """Side-by-side first pages of one window, unfiltered and filtered: over the span both
        cover, every swap-carrying transaction must be in the filtered page."""

        def reach(page: dict[str, Any]) -> float:
            data = page.get("data") or []
            if not page.get("paginationToken") or not data:
                return t_to
            return int(data[-1].get("blockTime") or 0) - 1  # that second may continue

        hi = min(reach(plain), reach(filt))
        p = [tx for tx in plain.get("data") or [] if int(tx.get("blockTime") or 0) <= hi]
        f = {tx_signature(tx) for tx in filt.get("data") or [] if int(tx.get("blockTime") or 0) <= hi}
        trades = {tx_signature(tx) for tx in p if swaps_from_tx(tx, pool=pool)}
        if not trades:
            return
        c = self.filter_checks
        if not trades <= f:
            c["violations"] += 1
            self.token_filter = False
            self.filter_note = f"dropped {len(trades - f)} of {len(trades)} swap transactions; off"
            return
        if len(f) < len(p):
            c["reduced"] += 1
        elif len(trades) < len(p):
            c["unreduced"] += 1  # there was noise to drop and the provider kept it
        else:
            c["same"] += 1
        if self.token_filter is None:
            if c["reduced"] >= 2:
                self.token_filter = True
                self.filter_note = "verified: keeps every swap, drops the rest"
            elif c["unreduced"] >= 3:
                self.token_filter = False
                self.filter_note = "ignored by the provider; off"

    async def _window_gtfa(
        self, pool: str, t_from: int, t_to: int, max_tx: int, mint: str | None
    ) -> tuple[list[Swap], dict[str, Any]]:
        spent = self.credits
        use_f = self._use_filter(mint)
        flt = self._filters(t_from, t_to, mint, use_f)
        swaps: list[Swap] = []
        fetched = 0
        covered_to = t_from - 1
        complete = False
        counted = None
        token = None
        first = True
        while True:
            limit = min(FIRST_PAGE if first else FULL_PAGE, max_tx - fetched)
            res = await self._page(pool, full=True, sort="asc", limit=limit, flt=flt, token=token)
            data = res.get("data") or []
            for item in data:
                swaps.extend(swaps_from_tx(item, pool=pool))
                fetched += 1
                covered_to = max(covered_to, int(item.get("blockTime") or covered_to))
            token = res.get("paginationToken")
            if first and mint and data:
                await self._check_filter(pool, res, use_f, t_from, t_to, mint, limit)
            if not data or not token:
                complete = True
                break
            if fetched >= max_tx:
                covered_to -= 1  # the last second may continue on the next page
                break
            if first:
                # more than a page: count the rest before paying for it
                counted = fetched + await self._count(pool, covered_to, t_to, flt, max_tx - fetched)
                if counted > max_tx:
                    covered_to -= 1
                    break
            first = False
        swaps.sort(key=lambda s: s.order)
        repaired = await self._repair_gaps(pool, swaps) if use_f else []
        if repaired:
            swaps = sorted([*swaps, *repaired], key=lambda s: s.order)
        return swaps, {
            "method": "gtfa",
            "filtered": use_f,
            "fetched": fetched,
            "counted": counted,
            "complete": complete,
            "covered_to": t_to if complete else covered_to,
            "repaired": len(repaired),
            "chain_breaks": chain_breaks(swaps),
            "quote_gaps": quote_gaps(swaps)[0],
            "quote_gap_sol": quote_gaps(swaps)[1] / 1e9,
            "credits": self.credits - spent,
        }

    async def _repair_gaps(self, pool: str, swaps: list[Swap], max_gaps: int = 20) -> list[Swap]:
        """Swaps a filtered window missed, read back without the filter.

        Between two consecutive swaps the token reserves hand over exactly, so a break means
        something in between is missing. Measured on production: Helius' tokenTransfer filter
        dropped one buy in ~210,000 (routed through an aggregator in a version-1 transaction).
        The slot range of each break is read again unfiltered and the swaps found are added."""
        known = {(s.signature, s.ev_index) for s in swaps}
        gaps = [(a, b) for a, b in zip(swaps, swaps[1:], strict=False) if b.base_pre != a.base_post]
        found: list[Swap] = []
        for a, b in gaps[:max_gaps]:
            flt = {"status": "succeeded", "slot": {"gte": a.slot, "lte": b.slot}}
            token = None
            for _ in range(self.scan_pages):
                res = await self._page(
                    pool, full=True, sort="asc", limit=self.scan_page, flt=flt, token=token
                )
                for item in res.get("data") or []:
                    for sw in swaps_from_tx(item, pool=pool):
                        if (sw.signature, sw.ev_index) not in known:
                            known.add((sw.signature, sw.ev_index))
                            found.append(sw)
                token = res.get("paginationToken")
                if not token:
                    break
        self.filter_checks["repaired"] = self.filter_checks.get("repaired", 0) + len(found)
        return found

    async def _check_filter(
        self, pool: str, first: dict[str, Any], used: bool, t_from: int, t_to: int, mint: str, limit: int
    ) -> None:
        """Verify the tokenTransfer filter on this window's first page while it is unverified,
        and audit it on every 20th filtered window once it is in use."""
        if self.token_filter is False:
            return
        if used:
            self._filtered_windows += 1
            if self._filtered_windows % 20:
                return
            self.filter_checks["audits"] += 1
            other_flt = self._filters(t_from, t_to, mint, False)
        else:
            trades = [bool(swaps_from_tx(tx, pool=pool)) for tx in first.get("data") or []]
            if all(trades) or not any(trades):
                return  # nothing to drop, or nothing to keep: the comparison would teach nothing
            other_flt = self._filters(t_from, t_to, mint, True)
        other = await self._page(pool, full=True, sort="asc", limit=limit, flt=other_flt)
        plain, filt = (other, first) if used else (first, other)
        self._compare(pool, plain, filt, t_to)

    async def _window_fallback(
        self, pool: str, t_from: int, t_to: int, sigs: Sequence[dict[str, Any]]
    ) -> tuple[list[Swap], dict[str, Any]]:
        spent = self.credits
        inside = [s for s in sigs if t_from <= (s.get("blockTime") or 0) <= t_to]
        take = inside[: self.fallback_max_tx]
        swaps: list[Swap] = []
        for s in take:
            tx = await self._tx(s["signature"])
            if tx is not None:
                swaps.extend(swaps_from_tx(tx, pool=pool, signature=s["signature"]))
        complete = len(take) == len(inside)
        covered_to = (
            t_to if complete else (int(take[-1].get("blockTime") or t_from) - 1 if take else t_from - 1)
        )
        swaps.sort(key=lambda s: s.order)
        return swaps, {
            "method": "signatures",
            "filtered": False,
            "fetched": len(take),
            "counted": len(inside),
            "complete": complete,
            "covered_to": covered_to,
            "repaired": 0,
            "chain_breaks": chain_breaks(swaps),
            "quote_gaps": quote_gaps(swaps)[0],
            "quote_gap_sol": quote_gaps(swaps)[1] / 1e9,
            "credits": self.credits - spent,
        }

    async def window(
        self,
        pool: str,
        t_from: float,
        t_to: float,
        max_tx: int,
        mint: str | None = None,
        floor_ts: float | None = None,
    ) -> tuple[list[Swap], dict[str, Any]]:
        """Every swap of `pool` with t_from <= blockTime <= t_to, in chain order, unless the window
        holds more than `max_tx` transactions. stats["covered_to"] is the time up to which the
        result is complete (t_to when nothing was cut). `floor_ts` lets the fallback's signature
        listing also serve a later `states` call for the same pool."""
        t_from, t_to = int(t_from), int(t_to)
        if self.gtfa is not False:
            try:
                return await self._window_gtfa(pool, t_from, t_to, max_tx, mint)
            except RpcError as exc:
                self._gtfa_failed(exc)
                if self.gtfa is not False:
                    raise
        sigs, _ = await self.signatures_since(pool, min(t_from, floor_ts if floor_ts is not None else t_from))
        return await self._window_fallback(pool, t_from, t_to, sigs)

    # ---- states at decision times ----
    async def _states_gtfa(
        self, pool: str, times: Sequence[float], floor_ts: int, mint: str | None
    ) -> tuple[list[Swap], dict[str, Any]]:
        """Descending scans: from a time, page backwards until a transaction carrying a swap of
        the pool appears; the first one met is the newest swap at or before that time. A scan
        that already reached a later time's answer serves it without another call."""
        spent = self.credits
        use_f = self._use_filter(mint)
        found: dict[tuple[str, int], Swap] = {}
        seg: list[Swap] = []  # swaps of the current contiguous scan
        hi = lo = None  # the current scan has read every transaction with lo < ts <= hi
        token: str | None = None
        exhausted = False  # the current scan reached floor_ts
        resolved = unresolved = before_first = 0
        pages = 0
        for t in sorted({int(x) for x in times}, reverse=True):
            if t < floor_ts:
                continue
            if hi is None or lo is None or not (lo <= t <= hi):
                hi, lo, token, seg, exhausted = t, t + 1, None, [], False
            spent_pages = 0
            while not any(s.ts <= t for s in seg) and not exhausted and spent_pages < self.scan_pages:
                flt = self._filters(floor_ts, hi, mint, use_f)
                res = await self._page(
                    pool, full=True, sort="desc", limit=self.scan_page, flt=flt, token=token
                )
                pages += 1
                spent_pages += 1
                data = res.get("data") or []
                for item in data:
                    for s in swaps_from_tx(item, pool=pool):
                        found.setdefault((s.signature, s.ev_index), s)
                        seg.append(s)
                token = res.get("paginationToken")
                if data:
                    lo = min(lo, int(data[-1].get("blockTime") or lo))
                if not data or not token:
                    exhausted, lo = True, floor_ts
            if any(s.ts <= t for s in seg):
                resolved += 1
            elif exhausted:
                before_first += 1  # no swap between floor_ts and t: the state is the next swap's "before"
            else:
                unresolved += 1
        if before_first:
            # some time had no swap since floor_ts: its state is the first swap's pre-state
            token = None
            for _ in range(self.scan_pages):
                flt = self._filters(floor_ts, None, mint, use_f)
                res = await self._page(
                    pool, full=True, sort="asc", limit=self.scan_page, flt=flt, token=token
                )
                pages += 1
                first = [s for item in res.get("data") or [] for s in swaps_from_tx(item, pool=pool)]
                for s in first:
                    found.setdefault((s.signature, s.ev_index), s)
                token = res.get("paginationToken")
                if first or not token:
                    break
        swaps = sorted(found.values(), key=lambda s: s.order)
        return swaps, {
            "method": "gtfa",
            "filtered": use_f,
            "pages": pages,
            "resolved": resolved,
            "before_first": before_first,
            "unresolved": unresolved,
            "credits": self.credits - spent,
        }

    async def _states_fallback(
        self, pool: str, sigs: Sequence[dict[str, Any]], times: Sequence[float]
    ) -> tuple[list[Swap], dict[str, Any]]:
        """From the signature index: for each time, fetch transactions backwards from it until one
        carries a swap of the pool (at most `fallback_walk`)."""
        spent = self.credits
        cache: dict[str, list[Swap]] = {}
        resolved = unresolved = 0

        async def swaps_of(s: dict[str, Any]) -> list[Swap]:
            sig = s["signature"]
            if sig not in cache:
                tx = await self._tx(sig)
                cache[sig] = swaps_from_tx(tx, pool=pool, signature=sig) if tx else []
            return cache[sig]

        for t in sorted({int(x) for x in times}):
            before = [s for s in sigs if (s.get("blockTime") or 0) <= t]
            hit = False
            for s in reversed(before[-self.fallback_walk :]):
                if await swaps_of(s):
                    hit = True
                    break
            if not hit:
                for s in [s for s in sigs if (s.get("blockTime") or 0) > t][: self.fallback_walk]:
                    if await swaps_of(s):
                        break  # the next swap's pre-state stands for t
            resolved += hit
            unresolved += not hit
        swaps = sorted((s for group in cache.values() for s in group), key=lambda s: s.order)
        return swaps, {
            "method": "signatures",
            "filtered": False,
            "pages": 0,
            "resolved": resolved,
            "before_first": 0,
            "unresolved": unresolved,
            "credits": self.credits - spent,
        }

    async def states(
        self, pool: str, times: Sequence[float], floor_ts: float, mint: str | None = None
    ) -> tuple[list[Swap], dict[str, Any]]:
        """The swaps fixing the pool state at each time: the newest swap at or before it (or, when
        none happened since floor_ts, the first one after). floor_ts bounds the history read."""
        floor = int(floor_ts)
        if self.gtfa is not False:
            try:
                return await self._states_gtfa(pool, times, floor, mint)
            except RpcError as exc:
                self._gtfa_failed(exc)
                if self.gtfa is not False:
                    raise
        sigs, _ = await self.signatures_since(pool, floor)
        return await self._states_fallback(pool, sigs, times)


def merge_swaps(*groups: Sequence[Swap]) -> list[Swap]:
    """One chain-ordered list, each swap once (the same transaction can come from several reads)."""
    seen: dict[tuple[str, int], Swap] = {}
    for g in groups:
        for s in g:
            seen.setdefault((s.signature, s.ev_index), s)
    return sorted(seen.values(), key=lambda s: (s.slot, s.tx_index, s.ev_index))


SWAP_COLUMNS = [
    "slot",
    "tx_index",
    "ev_index",
    "ts",
    "side",  # 1 buy, 0 sell
    "base_pre",
    "quote_pre",
    "virtual",
    "base_amount",
    "quote_amount",
    "lp_fee",
    "fee_bps",
    "user",  # index into "users"
    "vault_delta",
    "ix",  # 0 sell, 1 buy, 2 buy_exact_quote_in, 3 buy_exact_quote_in_v2, 9 other
]
_IX_CODES = {"": 0, "buy": 1, "buy_exact_quote_in": 2, "buy_exact_quote_in_v2": 3}


def encode_swaps(swaps: Sequence[Swap]) -> dict[str, Any]:
    """Compact, lossless enough to re-run any simulation offline: one row per swap, wallets interned."""
    users: dict[str, int] = {}
    rows = []
    for s in swaps:
        u = users.setdefault(s.user, len(users))
        rows.append(
            [
                s.slot,
                s.tx_index,
                s.ev_index,
                s.ts,
                1 if s.side == "buy" else 0,
                s.base_pre,
                s.quote_pre,
                s.virtual_quote,
                s.base_amount,
                s.quote_amount,
                s.lp_fee,
                [s.lp_bps, s.protocol_bps, s.creator_bps],
                u,
                s.quote_post - s.quote_pre,
                _IX_CODES.get(s.ix_name, 9),
            ]
        )
    return {"columns": SWAP_COLUMNS, "users": list(users), "rows": rows}
