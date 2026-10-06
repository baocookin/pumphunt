"""Long-running jobs: chain recorder, PumpPortal feed, candle harvester.

Files under data_dir:
  chain-YYYY-MM-DD.jsonl   every decoded pump.fun event seen on the RPC stream
                           (trades compact unless record_raw_trades), with slot + signature
  portal-YYYY-MM-DD.jsonl  every PumpPortal message
  migrations.jsonl         one line per graduation (first sighting, plus pool fill-ins)
  survivor.jsonl           one line per harvested token (hypothesis C metrics)
"""

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx

from .anchor import PUMP_PROGRAM, ChainEvent
from .chain_feed import SolanaLogsFeed
from .config import Settings
from .events import Event
from .feed import PumpPortalFeed
from .gecko import GeckoTerminal
from .jsonl import JsonlWriter
from .store import Store, hour_key
from .survivor import compute_metrics

_TRADE_COMPACT = (
    "mint",
    "user",
    "is_buy",
    "sol_amount_sol",
    "token_amount_ui",
    "virtual_sol_reserves_sol",
    "virtual_token_reserves_ui",
    "creator",
    "ix_name",
)


class Recorder:
    def __init__(self, cfg: Settings, store: Store):
        self.cfg = cfg
        self.store = store
        d = Path(cfg.data_dir)
        self.chain_log = JsonlWriter(d / "chain.jsonl", rotate_daily=True)
        self.portal_log = JsonlWriter(d / "portal.jsonl", rotate_daily=True)
        self.migrations = JsonlWriter(d / "migrations.jsonl")
        self.survivor = JsonlWriter(d / "survivor.jsonl")
        self.started = time.time()
        self.counts = {
            "create": 0,
            "trade": 0,
            "complete": 0,
            "migrate": 0,
            "portal_create": 0,
            "portal_migrate": 0,
            "harvested": 0,
        }
        self.last_chain_ts = 0.0
        self.last_portal_ts = 0.0

    def mentions(self) -> list[str]:
        out = [self.cfg.migration_authority]
        if self.cfg.chain_scope == "full":
            out.append(PUMP_PROGRAM)
        return out

    # ---- chain (primary) ----
    def on_chain(self, ev: ChainEvent) -> None:
        self.last_chain_ts = ev.ts
        if ev.kind in self.counts:
            self.counts[ev.kind] += 1
        hour = hour_key(ev.ts)
        head: dict[str, Any] = {"ts": ev.ts, "slot": ev.slot, "sig": ev.signature, "kind": ev.kind}
        if ev.kind == "trade" and not self.cfg.record_raw_trades:
            self.chain_log.write({**head, **{k: ev.data.get(k) for k in _TRADE_COMPACT}}, now=ev.ts)
        else:
            self.chain_log.write({**head, **ev.data}, now=ev.ts)

        if ev.kind == "create":
            self.store.incr("creates_chain", hour)
        elif ev.kind == "complete":
            self.store.incr("completes_chain", hour)
        elif ev.kind == "migrate":
            self.store.incr("migrations_chain", hour)
            d = ev.data
            row = {
                "mint": d.get("mint"),
                "pool": d.get("pool"),
                "ts": ev.ts,
                "slot": ev.slot,
                "signature": ev.signature,
                "chain_ts": d.get("timestamp"),
                "sol_amount": d.get("sol_amount_sol"),
                "mint_amount": d.get("mint_amount_ui"),
                "bonding_curve": d.get("bonding_curve"),
                "user": d.get("user"),
                "source": "chain",
            }
            if row["mint"] and row["pool"]:
                self.store.add_migration(row)
                self.migrations.write(row)

    async def run_chain(self) -> None:
        feed = SolanaLogsFeed(self.cfg.solana_ws_url, self.mentions(), self.cfg.chain_commitment)
        print(f"[chain] logsSubscribe {self.cfg.solana_ws_url} scope={self.cfg.chain_scope}")
        async for ev in feed.events():
            self.on_chain(ev)

    # ---- portal (coverage + migration fallback) ----
    def on_portal(self, ev: Event) -> None:
        self.last_portal_ts = ev.ts
        self.portal_log.write({"ts": ev.ts, "msg": ev.raw}, now=ev.ts)
        hour = hour_key(ev.ts)
        if ev.is_create:
            self.counts["portal_create"] += 1
            self.store.incr("creates_portal", hour)
        elif ev.is_migration:
            self.counts["portal_migrate"] += 1
            self.store.incr("migrations_portal", hour)
            # No pool address here; the harvester resolves it by mint if the chain feed never fills it.
            row = {
                "mint": ev.mint,
                "pool": None,
                "ts": ev.ts,
                "slot": None,
                "signature": ev.signature,
                "source": "portal",
            }
            if self.store.add_migration(row):
                self.migrations.write(row)

    async def run_portal(self) -> None:
        feed = PumpPortalFeed(self.cfg.pumpportal_ws_url, self.cfg.pumpportal_api_key)
        print(f"[portal] {self.cfg.pumpportal_ws_url}")
        async for ev in feed.events():
            self.on_portal(ev)

    # ---- harvester ----
    async def harvest_once(self, gecko: GeckoTerminal, now: float | None = None) -> int:
        now = now or time.time()
        rows = self.store.pending_harvest(now - self.cfg.harvest_after_s, self.cfg.harvest_batch)
        done = 0
        for row in rows:
            t0 = int(row["ts"])
            try:
                pool = row.get("pool") or await gecko.resolve_pool(row["mint"])
                candles = await gecko.candles_between(pool, t0 - 60, t0 + 24 * 3600 + 60) if pool else []
                info = await gecko.pool_info(pool) if pool else None
            except httpx.HTTPError as exc:
                print(f"[harvest] {row['mint'][:6]} http error {exc}; retry next cycle")
                continue
            metrics = compute_metrics(
                candles, t0, self.cfg.entry_delays_min, self.cfg.horizons_min, self.cfg.cost_bps_round_trip
            )
            metrics.update(
                {
                    "mint": row["mint"],
                    "pool": pool,
                    "pool_resolved": not row.get("pool"),
                    "slot": row.get("slot"),
                    "source": row.get("source"),
                    "migration_sol": row.get("sol_amount"),
                    "harvested_at": now,
                    "reserve_usd_now": float((info or {}).get("reserve_in_usd") or 0) if info else None,
                }
            )
            self.store.mark_harvested(row["mint"], metrics)
            self.survivor.write(metrics)
            self.counts["harvested"] += 1
            done += 1
        return done

    async def run_harvester(self) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            gecko = GeckoTerminal(client, self.cfg.gecko_base_url, self.cfg.gecko_rpm)
            while True:
                try:
                    n = await self.harvest_once(gecko)
                    if n:
                        print(f"[harvest] {n} tokens")
                except Exception as exc:  # noqa: BLE001 - never let the harvester die
                    print(f"[harvest] error: {exc}")
                await asyncio.sleep(self.cfg.harvest_interval_s)

    # ---- status heartbeat ----
    async def run_status(self) -> None:
        while True:
            self.store.set_status(
                started=self.started,
                now=time.time(),
                last_chain_ts=self.last_chain_ts,
                last_portal_ts=self.last_portal_ts,
                counts=self.counts,
                chain_scope=self.cfg.chain_scope,
            )
            await asyncio.sleep(5)

    async def run(self) -> None:
        tasks = [self.run_chain(), self.run_status()]
        if self.cfg.pumpportal_enabled:
            tasks.append(self.run_portal())
        if self.cfg.run_harvester:
            tasks.append(self.run_harvester())
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    from .config import settings
    from .store import make_store

    asyncio.run(Recorder(settings, make_store(settings.redis_url)).run())
