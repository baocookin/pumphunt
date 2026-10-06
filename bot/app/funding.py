"""Who funded the wallets around a token: its creator, the creation-slot bundle and the largest
holders at the decision time.

A wallet's oldest transaction (getTransactionsForAddress, oldest first, limit 1: 10 credits on
Helius) usually is the transfer that first gave it SOL; the account that lost the most SOL in it
is taken as the funder. Wallets sharing a funder, or funded by the creator, are likely one
operator (a coordinated cluster held 36.5% of supply at migration in MELT, arXiv 2602.13480).
Exchange hot wallets also fund many unrelated wallets, so the raw funder of every wallet is kept
for offline checks (a funder seen across many unrelated tokens is an exchange, not a cluster).
Lookups are cached per wallet: snipers and bundlers come back token after token.
"""

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from .rpc import account_keys
from .store import Store
from .swaps import SwapFetcher

DAY = 86_400


def funder_of(tx: dict[str, Any], wallet: str) -> dict[str, Any]:
    """First-transaction facts: when, and which other account paid the most SOL in it."""
    keys, _ = account_keys(tx)
    meta = tx.get("meta") or {}
    pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
    best: tuple[str, int] | None = None
    for i, k in enumerate(keys):
        if k == wallet or i >= len(pre) or i >= len(post):
            continue
        d = int(post[i]) - int(pre[i])
        if d < 0 and (best is None or d < best[1]):
            best = (k, d)
    return {"first_ts": tx.get("blockTime"), "funder": best[0] if best else None}


async def first_funders(
    fetcher: SwapFetcher, store: Store, wallets: Iterable[str], ttl_s: int
) -> tuple[dict[str, dict[str, Any]], int]:
    """wallet -> {"first_ts", "funder"}, and how many lookups hit the RPC (the rest were cached)."""
    out: dict[str, dict[str, Any]] = {}
    looked = 0
    for w in wallets:
        if not w or w in out:
            continue
        cached = store.cache_get("fund:" + w)
        if cached is not None:
            out[w] = json.loads(cached)
            continue
        res = await fetcher.history_page(w, full=True, sort="asc", limit=1)
        data = res.get("data") or []
        info = funder_of(data[0], w) if data else {"first_ts": None, "funder": None}
        store.cache_set("fund:" + w, json.dumps(info), ttl_s)
        out[w] = info
        looked += 1
    return out, looked


def pick_wallets(
    dev: str | None, bundle: Sequence[str], holders: Sequence[Sequence[Any]], cap: int
) -> list[str]:
    """The creator, then the creation-slot bundle (at most 5), then the largest holders."""
    out: list[str] = []
    for w in [dev, *list(bundle)[:5], *[h[0] for h in holders]]:
        if w and w not in out:
            out.append(w)
        if len(out) >= cap:
            break
    return out


def features(
    funders: dict[str, dict[str, Any]],
    dev: str | None,
    t_create: float | None,
    holdings: dict[str, int],
    outside_supply: int,
) -> dict[str, Any]:
    """Cluster facts over the looked-up wallets; shares are of the supply outside the pool."""
    groups: dict[str, set[str]] = defaultdict(set)
    for w, info in funders.items():
        if info.get("funder"):
            groups[info["funder"]].add(w)
    largest = max(groups.values(), key=len, default=set())
    if len(largest) < 2:
        largest = set()
    dev_funder = (funders.get(dev) or {}).get("funder") if dev else None
    linked = {
        w
        for w, info in funders.items()
        if w != dev
        and dev
        and (
            info.get("funder") == dev or (dev_funder and info.get("funder") == dev_funder) or w == dev_funder
        )
    }

    def share(ws: Iterable[str]) -> float | None:
        return sum(holdings.get(w, 0) for w in ws) / outside_supply if outside_supply > 0 else None

    fresh = [
        w
        for w, info in funders.items()
        if t_create is not None and info.get("first_ts") and t_create - info["first_ts"] < DAY
    ]
    return {
        "wallets": len(funders),
        "fresh_1d": len(fresh),  # first transaction less than a day before the token existed
        "max_cluster": len(largest),
        "cluster_hold_share": share(largest) if largest else 0.0,
        "dev_linked": len(linked),
        "dev_group_hold_share": share(linked | ({dev} if dev else set())),
        "funders": {w: [info.get("first_ts"), info.get("funder")] for w, info in funders.items()},
    }
