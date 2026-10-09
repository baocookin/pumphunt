"""A candidate's curve history, read incrementally, as a census row.

The first read lists the curve's successful transactions from its create on (oldest first, Helius
getTransactionsForAddress); later reads ask only for transactions from the last block time seen,
dropping the overlap by signature. Trades are kept as the census kept them, so the frozen filters
read the same tuples they were measured on.

Completeness. Every trade carries the curve's reserves after it, so a missing trade shows as a
break in the chain (check_ordered in the filters). The tail is checked against the curve account:
the replayed state at the account's slot must equal the account. When it does not, the index has
not caught up with the chain yet; the engine reads again a moment later.
"""

from collections import Counter
from typing import Any

from .chain import chain_breaks, chain_order, curve_trades, signature_of
from .rpc import Rpc

PAGE = 100


class History:
    def __init__(self, info: dict[str, Any]):
        self.info = info
        self.sigs: set[str] = set()
        self.trades: list[list[Any]] = []
        self.complete: dict[str, Any] | None = None
        self.fees: Counter[int] = Counter()
        self.last_ts: int | None = None
        self.last_slot = 0
        self.n_tx = 0
        self.truncated = False
        self.synthetic_tx_index = 0
        self.reads = 0

    async def update(self, rpc: Rpc, max_tx: int, kind: str = "history") -> int:
        """Read the transactions since the last read; returns how many new ones came in."""
        info = self.info
        t_from = int(info["create_ts"]) if self.last_ts is None else self.last_ts
        token = None
        new_txs: list[dict[str, Any]] = []
        while True:
            # 100 full transactions per page: the public RPC serves at most 100 whatever is asked
            # (measured 09/10/2026), so only a page under 100 is the last one. Helius bills per 100
            # transactions returned, so small pages cost it nothing more.
            limit = PAGE
            res = await rpc.gtfa(
                info["curve"], kind=kind, sort="asc", limit=limit, t_from=t_from, token=token
            )
            data = res["data"]
            for tx in data:
                sig = signature_of(tx)
                if sig and sig in self.sigs:
                    continue
                if sig:
                    self.sigs.add(sig)
                new_txs.append(tx)
            self.n_tx += len(data)
            token = res.get("paginationToken")
            short = len(data) < int(res.get("asked") or limit)
            if not data or not token or short:
                break
            if self.n_tx >= max_tx:
                self.truncated = True
                break
        self.reads += 1
        if new_txs:
            self._absorb(new_txs)
        return len(new_txs)

    def _absorb(self, txs: list[dict[str, Any]]) -> None:
        path = curve_trades(txs, self.info["mint"])
        self.trades.extend(path["trades"])
        chain_order(self.trades)
        self.fees.update(path["fees"])
        self.synthetic_tx_index += path["synthetic_tx_index"]
        if path["complete"] and self.complete is None:
            self.complete = path["complete"]
        for tx in txs:
            bt = int(tx.get("blockTime") or 0)
            if bt and (self.last_ts is None or bt > self.last_ts):
                self.last_ts = bt
            self.last_slot = max(self.last_slot, int(tx.get("slot") or 0))

    def state_at(self, slot: int) -> tuple[int, int]:
        """(v_sol, v_tokens) after the last trade landed by the end of `slot`."""
        v = (int(self.info["v_sol0"]), int(self.info["v_tokens0"]))
        for t in self.trades:
            if int(t[0]) > slot:
                break
            v = (int(t[8]), int(t[9]))
        return v

    def synced_with(self, account: dict[str, Any] | None, slot: int) -> bool:
        """Whether the replayed state at `slot` equals the curve account read at that slot."""
        if not account:
            return False
        return self.state_at(slot) == (int(account["v_sol"]), int(account["v_tokens"]))

    def row(self) -> dict[str, Any]:
        """The census-format row the filters read (bot/app/sniper.read_launch)."""
        info = self.info
        fee_bps = max(self.fees, key=lambda k: self.fees[k]) if self.fees else None
        return {
            **info,
            "status": "ok",
            "trades": self.trades,
            "complete": self.complete,
            "fee_bps": fee_bps,
            "chain_breaks": chain_breaks(self.trades, int(info["v_tokens0"])),
            "window": {"tx": self.n_tx, "truncated": self.truncated, "last_slot": self.last_slot},
        }
