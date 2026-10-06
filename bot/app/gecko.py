"""GeckoTerminal public API client (free, ~30 req/min, no key).

We only need three things per graduated token: the PumpSwap pool address (known
from the on-chain migration event, or looked up by mint as a fallback), the
pool's 1-minute OHLCV for the first 24h after migration, and its current info.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Candle:
    ts: int  # unix seconds, start of minute
    open: float
    high: float
    low: float
    close: float
    volume_usd: float


class RateLimiter:
    def __init__(self, per_minute: int):
        self.interval = 60.0 / max(1, per_minute)
        self._next = 0.0

    async def wait(self) -> None:
        now = time.monotonic()
        if now < self._next:
            await asyncio.sleep(self._next - now)
        self._next = max(now, self._next) + self.interval


def pick_pool(pools: list[dict[str, Any]]) -> str | None:
    """Prefer a PumpSwap pool, else the deepest one. Returns the pool address."""

    def reserve(p: dict[str, Any]) -> float:
        try:
            return float((p.get("attributes") or {}).get("reserve_in_usd") or 0)
        except (TypeError, ValueError):
            return 0.0

    def dex(p: dict[str, Any]) -> str:
        return str(
            (((p.get("relationships") or {}).get("dex") or {}).get("data") or {}).get("id", "")
        ).lower()

    pump = [p for p in pools if "pump" in dex(p)]
    cands = pump or pools
    if not cands:
        return None
    best = max(cands, key=reserve)
    return (best.get("attributes") or {}).get("address")


class GeckoTerminal:
    def __init__(self, client: httpx.AsyncClient, base_url: str, rpm: int = 25):
        self.c = client
        self.base = base_url.rstrip("/")
        self.rl = RateLimiter(rpm)
        self.stats = {"calls": 0, "rate_limited": 0, "not_found": 0, "errors": 0}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """None only for a 404 (unknown pool/token). Persistent 429s raise, so the harvester
        retries the row next cycle instead of recording an empty result as "no data"."""
        r = None
        for attempt in range(4):
            await self.rl.wait()
            self.stats["calls"] += 1
            r = await self.c.get(
                f"{self.base}{path}", params=params, headers={"accept": "application/json;version=20230302"}
            )
            if r.status_code == 404:
                self.stats["not_found"] += 1
                return None
            if r.status_code == 429:
                self.stats["rate_limited"] += 1
                retry_after = r.headers.get("retry-after") if hasattr(r, "headers") else None
                try:
                    wait = float(retry_after) if retry_after else 5.0 * 2**attempt
                except ValueError:
                    wait = 5.0 * 2**attempt
                await asyncio.sleep(min(wait, 60.0))
                continue
            if r.status_code >= 400:
                self.stats["errors"] += 1
            r.raise_for_status()
            return r.json()
        assert r is not None
        self.stats["errors"] += 1
        r.raise_for_status()  # the last 429: surfaces as httpx.HTTPStatusError
        return None

    async def pool_info(self, pool: str, network: str = "solana") -> dict[str, Any] | None:
        data = await self._get(f"/networks/{network}/pools/{pool}")
        return (data or {}).get("data", {}).get("attributes") if data else None

    async def pools_info_multi(self, pools: list[str], network: str = "solana") -> dict[str, dict[str, Any]]:
        """Attributes for up to 30 pools per call, keyed by pool address: one call instead of thirty."""
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(pools), 30):
            chunk = pools[i : i + 30]
            data = await self._get(f"/networks/{network}/pools/multi/{','.join(chunk)}")
            for p in (data or {}).get("data") or []:
                attrs = p.get("attributes") or {}
                if attrs.get("address"):
                    out[attrs["address"]] = attrs
        return out

    async def token_pools(self, mint: str, network: str = "solana") -> list[dict[str, Any]]:
        data = await self._get(f"/networks/{network}/tokens/{mint}/pools")
        return list((data or {}).get("data") or [])

    async def resolve_pool(self, mint: str) -> str | None:
        return pick_pool(await self.token_pools(mint))

    async def ohlcv_minute(
        self, pool: str, before_ts: int, limit: int = 1000, network: str = "solana"
    ) -> list[Candle]:
        data = await self._get(
            f"/networks/{network}/pools/{pool}/ohlcv/minute",
            {"aggregate": 1, "limit": limit, "before_timestamp": before_ts, "currency": "usd"},
        )
        rows = ((data or {}).get("data", {}).get("attributes", {}) or {}).get("ohlcv_list", [])
        out = [
            Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
            for r in rows
            if len(r) >= 6
        ]
        out.sort(key=lambda c: c.ts)
        return out

    async def candles_between(self, pool: str, start_ts: int, end_ts: int) -> list[Candle]:
        """All minute candles in [start_ts, end_ts], paging backwards (API returns newest first)."""
        seen: dict[int, Candle] = {}
        before = end_ts + 60
        for _ in range(6):  # 6 x 1000 min > 4 days; plenty for a 25h window
            page = await self.ohlcv_minute(pool, before)
            if not page:
                break
            for c in page:
                if start_ts <= c.ts <= end_ts:
                    seen[c.ts] = c
            oldest = page[0].ts
            if oldest <= start_ts or len(page) < 2:
                break
            before = oldest
        return [seen[k] for k in sorted(seen)]
