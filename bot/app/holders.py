"""Who holds the token at a decision time, taken live: it cannot be rebuilt cheaply afterwards.

Three standard RPC calls (1 credit each on Helius): the mint's 20 largest token accounts, their
owners (one getMultipleAccounts), and the supply. The pool's own vault is among the largest
accounts; it is reported apart and left out of every concentration figure, which measures the
supply that can be sold INTO the pool.

The harvester later turns the snapshot into features against the pool state at the same time
(how much SOL the largest holders could pull out) and the curve's history (does the creator or
the creation-slot bundle still hold).
"""

from typing import Any

from .fills import LAMPORTS, PoolState, sell_ex
from .rpc import SolanaRpc

TOP_N = 20  # what getTokenLargestAccounts returns


async def snapshot(rpc: SolanaRpc, mint: str, pool: str) -> dict[str, Any]:
    largest = await rpc.get_token_largest_accounts(mint)
    accounts = await rpc.get_multiple_accounts([a["address"] for a in largest]) if largest else []
    supply = await rpc.get_token_supply(mint)
    owners: dict[str, int] = {}
    unknown = 0
    for a, acc in zip(largest, accounts, strict=False):
        info = (((acc or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
        owner = info.get("owner")
        amount = int(a.get("amount") or 0)
        if not owner:
            unknown += amount
            continue
        owners[owner] = owners.get(owner, 0) + amount
    pool_amount = owners.pop(pool, 0)
    holders = sorted(owners.items(), key=lambda kv: -kv[1])
    return {
        "supply": supply,
        "pool_amount": pool_amount,
        "unknown_amount": unknown,
        "accounts": len(largest),
        "holders": [[o, amt] for o, amt in holders],
        "credits": 3 if largest else 1,
    }


def concentration(snap: dict[str, Any]) -> dict[str, Any]:
    """Shares of the supply outside the pool held by the largest holders (owners, not accounts)."""
    supply = snap.get("supply") or 0
    outside = supply - (snap.get("pool_amount") or 0)
    amounts = [amt for _, amt in snap.get("holders") or []]
    if outside <= 0:
        return {"pool_share": None, "top1": None, "top5": None, "top10": None, "holders_1pct": None}

    def top(k: int) -> float:
        return sum(amounts[:k]) / outside

    return {
        "pool_share": (snap.get("pool_amount") or 0) / supply if supply else None,
        "top1": top(1),
        "top5": top(5),
        "top10": top(10),
        "holders_1pct": sum(1 for a in amounts if a >= outside / 100),
    }


def exit_power(snap: dict[str, Any], state: PoolState | None) -> dict[str, Any]:
    """What the largest holders could pull out: SOL received selling everything into the pool
    state of the same moment, as a share of the real SOL in it (sells stop at the real vault,
    so a share near 1 means they alone can empty it)."""
    if state is None or state.quote <= 0:
        return {"top1_exit_share": None, "top10_exit_share": None, "top10_exit_sol": None}
    amounts = [amt for _, amt in snap.get("holders") or []]

    def recv(k: int) -> int:
        got, _, _, _ = sell_ex(state, sum(amounts[:k]))
        return got

    r10 = recv(10)
    return {
        "top1_exit_share": recv(1) / state.quote,
        "top10_exit_share": r10 / state.quote,
        "top10_exit_sol": r10 / LAMPORTS,
    }


def group_share(snap: dict[str, Any], wallets: list[str]) -> float | None:
    """Share of the supply outside the pool held by `wallets` among the largest holders."""
    outside = (snap.get("supply") or 0) - (snap.get("pool_amount") or 0)
    if outside <= 0:
        return None
    held = dict((o, amt) for o, amt in snap.get("holders") or [])
    return sum(held.get(w, 0) for w in set(wallets)) / outside
