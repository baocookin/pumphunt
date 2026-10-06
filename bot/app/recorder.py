"""Long-running jobs: chain recorder, PumpPortal feed, RPC confirmation, candle harvester.

Files under data_dir:
  chain-YYYY-MM-DD.jsonl   every decoded pump.fun event seen on the RPC stream
                           (trades compact unless record_raw_trades), with slot + signature
  portal-YYYY-MM-DD.jsonl  every PumpPortal message
  migrations.jsonl         one line per graduation sighting (portal, rpc-confirmed, chain)
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
from .rpc import SolanaRpc, describe_http_error, http_url_from_ws, migration_from_tx, tx_diagnostics
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
        self.feed: SolanaLogsFeed | None = None
        self.rpc: SolanaRpc | None = None
        self.learned_authority: str | None = None
        self.rpc_stats: dict[str, Any] = {
            "confirmed": 0,
            "failed": 0,
            "no_event": 0,
            "last_rpc_ts": 0.0,
            "via": {"log": 0, "cpi": 0, "accounts": 0},
            "last_no_event": None,
            "withdraw_authority": None,
            "authority_static": None,
            "migrate_ix": None,
        }
        self._tasks: set[asyncio.Task] = set()

    def mentions(self) -> list[str]:
        out = [self.learned_authority or self.cfg.migration_authority]
        if self.cfg.chain_scope == "full":
            out.append(PUMP_PROGRAM)
        return out

    def _spawn(self, coro) -> None:
        """Run a coroutine in the background when a loop is running (no-op in sync tests)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            return
        task = loop.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

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
            row = self._migration_row(ev.data, ev.ts, ev.slot, ev.signature, "chain")
            if row["mint"] and row["pool"]:
                self.store.add_migration(row)
                self.migrations.write(row)

    @staticmethod
    def _migration_row(
        d: dict[str, Any], ts: float, slot: int | None, sig: str, source: str
    ) -> dict[str, Any]:
        return {
            "mint": d.get("mint"),
            "pool": d.get("pool"),
            "ts": ts,
            "slot": slot,
            "signature": sig,
            "chain_ts": d.get("timestamp"),
            "sol_amount": d.get("sol_amount_sol"),
            "mint_amount": d.get("mint_amount_ui"),
            "bonding_curve": d.get("bonding_curve"),
            "user": d.get("user"),
            "source": source,
        }

    async def run_chain(self) -> None:
        self.feed = SolanaLogsFeed(self.cfg.solana_ws_url, self.mentions(), self.cfg.chain_commitment)
        print(
            f"[chain] logsSubscribe {self.cfg.solana_ws_url} scope={self.cfg.chain_scope} {self.mentions()}"
        )
        async for ev in self.feed.events():
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
            # No pool address here; RPC confirmation (below) or the chain feed fills it in,
            # and the harvester resolves it by mint as a last resort.
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
            if self.rpc is not None and ev.signature:
                self._spawn(self.confirm_migration(ev.signature, ev.ts))

    async def run_portal(self) -> None:
        feed = PumpPortalFeed(self.cfg.pumpportal_ws_url, self.cfg.pumpportal_api_key)
        print(f"[portal] {self.cfg.pumpportal_ws_url}")
        async for ev in feed.events():
            self.on_portal(ev)

    # ---- RPC confirmation of PumpPortal migrations ----
    async def confirm_migration(
        self, signature: str, seen_ts: float, delays: tuple[float, ...] = (3, 10, 30, 60)
    ) -> bool:
        """Fetch the migrate tx by signature, register pool + slot, and learn the withdraw authority."""
        assert self.rpc is not None
        tx = None
        for delay in delays:
            await asyncio.sleep(delay)
            try:
                tx = await self.rpc.get_transaction(signature)
            except httpx.HTTPError as exc:
                print(f"[rpc] getTransaction failed: {describe_http_error(exc)}")
                tx = None
            if tx:
                break
        if not tx:
            self.rpc_stats["failed"] += 1
            return False
        info = migration_from_tx(tx)
        if info is None:
            self.rpc_stats["no_event"] += 1
            diag = {"signature": signature, **tx_diagnostics(tx)}
            self.rpc_stats["last_no_event"] = diag
            print(f"[rpc] no migrate in {signature}: {diag}")
            return False
        row = self._migration_row(info["event"], seen_ts, info["slot"], signature, "rpc")
        if row["mint"] and row["pool"]:
            self.store.add_migration(row)
            self.migrations.write(row)
            self.store.incr("migrations_rpc", hour_key(seen_ts))
        self.rpc_stats["confirmed"] += 1
        self.rpc_stats["last_rpc_ts"] = time.time()
        via = info["event"].get("via", "log")
        self.rpc_stats["via"][via] = self.rpc_stats["via"].get(via, 0) + 1
        await self._learn_authority(info.get("accounts"))
        return True

    async def _learn_authority(self, accounts: dict[str, Any] | None) -> None:
        if not accounts:
            return
        wa = accounts.get("withdraw_authority")
        self.rpc_stats["withdraw_authority"] = wa
        self.rpc_stats["authority_static"] = accounts.get("withdraw_authority_static")
        self.rpc_stats["migrate_ix"] = accounts.get("ix")
        if not wa or wa == self.learned_authority:
            return
        if self.feed is None or self.feed.stats["notifications"] > 0:
            return  # the current subscription already delivers; don't churn
        if wa == self.cfg.migration_authority:
            return
        if not accounts.get("withdraw_authority_static"):
            print(f"[rpc] withdraw_authority {wa} is loaded via lookup table; logsSubscribe cannot watch it")
            return
        print(f"[rpc] learned withdraw_authority {wa} (was {self.cfg.migration_authority}); re-subscribing")
        self.learned_authority = wa
        await self.feed.set_mentions(self.mentions())

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

    async def run_harvester(self, client: httpx.AsyncClient) -> None:
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
                chain_feed=self.feed.stats if self.feed else None,
                rpc=self.rpc_stats,
                mentions=self.mentions(),
            )
            await asyncio.sleep(5)

    async def run(self) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            if self.cfg.rpc_confirm:
                self.rpc = SolanaRpc(
                    client, self.cfg.solana_http_url or http_url_from_ws(self.cfg.solana_ws_url)
                )
            tasks = [self.run_chain(), self.run_status()]
            if self.cfg.pumpportal_enabled:
                tasks.append(self.run_portal())
            if self.cfg.run_harvester:
                tasks.append(self.run_harvester(client))
            await asyncio.gather(*tasks)


if __name__ == "__main__":
    from .config import settings
    from .store import make_store

    asyncio.run(Recorder(settings, make_store(settings.redis_url)).run())
