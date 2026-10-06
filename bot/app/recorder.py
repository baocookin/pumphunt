"""Long-running jobs: chain recorder, PumpPortal coverage feed, candle harvester."""

import asyncio
import time
from pathlib import Path

import httpx

from .anchor import ChainEvent
from .chain_feed import SolanaLogsFeed
from .config import Settings
from .events import Event
from .feed import PumpPortalFeed
from .gecko import GeckoTerminal
from .jsonl import JsonlWriter
from .store import Store, hour_key
from .survivor import compute_metrics


class Recorder:
    def __init__(self, cfg: Settings, store: Store):
        self.cfg = cfg
        self.store = store
        d = Path(cfg.data_dir)
        self.raw_chain = JsonlWriter(d / "raw_chain.jsonl")
        self.raw_portal = JsonlWriter(d / "raw_portal.jsonl")
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

    # ---- chain (primary) ----
    def on_chain(self, ev: ChainEvent) -> None:
        self.last_chain_ts = ev.ts
        if ev.kind in self.counts:
            self.counts[ev.kind] += 1
        hour = hour_key(ev.ts)
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
            }
            if row["mint"] and row["pool"] and self.store.add_migration(row):
                self.migrations.write(row)

    async def run_chain(self) -> None:
        feed = SolanaLogsFeed(self.cfg.solana_ws_url, self.cfg.chain_commitment, record=self.raw_chain)
        print(f"[chain] logsSubscribe {self.cfg.solana_ws_url}")
        async for ev in feed.events():
            self.on_chain(ev)

    # ---- portal (coverage only) ----
    def on_portal(self, ev: Event) -> None:
        self.last_portal_ts = ev.ts
        hour = hour_key(ev.ts)
        if ev.is_create:
            self.counts["portal_create"] += 1
            self.store.incr("creates_portal", hour)
        elif ev.is_migration:
            self.counts["portal_migrate"] += 1
            self.store.incr("migrations_portal", hour)

    async def run_portal(self) -> None:
        feed = PumpPortalFeed(self.cfg.pumpportal_ws_url, self.cfg.pumpportal_api_key, record=self.raw_portal)
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
                candles = await gecko.candles_between(row["pool"], t0 - 60, t0 + 24 * 3600 + 60)
                info = await gecko.pool_info(row["pool"])
            except httpx.HTTPError as exc:
                print(f"[harvest] {row['mint'][:6]} http error {exc}; retry next cycle")
                continue
            metrics = compute_metrics(
                candles, t0, self.cfg.entry_delays_min, self.cfg.horizons_min, self.cfg.cost_bps_round_trip
            )
            metrics.update(
                {
                    "mint": row["mint"],
                    "pool": row["pool"],
                    "slot": row.get("slot"),
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
