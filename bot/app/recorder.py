"""Long-running jobs: chain recorder, PumpPortal feed, RPC confirmation, candle harvester.

Files under data_dir:
  chain-YYYY-MM-DD.jsonl   every decoded pump.fun event seen on the RPC stream
                           (trades compact unless record_raw_trades), with slot + signature
  portal-YYYY-MM-DD.jsonl  every PumpPortal message
  migrations.jsonl         one line per graduation sighting (portal, rpc-confirmed, chain)

Counters per hour: migrations_confirmed counts each mint once, the first time a pool is
known from chain (websocket event, or getTransaction triggered by any path).

Sources of migrate signatures, all deduplicated through `_claim`:
  poller     getSignaturesForAddress(withdraw_authority) every poll_s; sees every migration,
             including those whose authority is loaded via a lookup table. Primary.
  websocket  logsSubscribe mentions=authority; only static-key txs (~54%), but instant.
  PumpPortal relays about half of the migrations and sometimes pairs the wrong mint with a
             signature; such rows are dropped once the chain says otherwise.
  survivor.jsonl           one line per harvested token (hypothesis C metrics)
"""

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx

from .anchor import PUMP_PROGRAM, ChainEvent
from .chain_feed import ChainNotification, SolanaLogsFeed
from .config import Settings
from .events import Event
from .feed import PumpPortalFeed
from .gecko import GeckoTerminal
from .jsonl import JsonlWriter
from .rpc import SolanaRpc, describe_http_error, http_url_from_ws, migration_from_tx, tx_diagnostics
from .store import Store, hour_key
from .survivor import compute_metrics

# Subscribe to the wallet that signs migrations once it clearly is one keeper, not random users.
SIGNER_MIN_N = 10
SIGNER_MIN_SHARE = 0.8

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
            "portal_migrate_other": 0,  # PumpPortal also relays other launchpads' migrations
            "harvested": 0,
        }
        self.portal_pools: dict[str, int] = {}  # PumpPortal `pool` field of migration messages
        self.last_chain_ts = 0.0
        self.last_portal_ts = 0.0
        self.feed: SolanaLogsFeed | None = None
        self.portal_feed: PumpPortalFeed | None = None
        self.gecko: GeckoTerminal | None = None
        self.harvest_stats: dict[str, Any] = {
            "runs": 0,
            "last_run_ts": 0.0,
            "last_error": None,
            "rows_last_run": 0,
            "with_data": 0,
            "no_pool": 0,
            "no_candles": 0,
            "due": 0,  # rows older than harvest_after_s still waiting
            "pending": 0,  # rows not harvested yet at all
        }
        self.rpc: SolanaRpc | None = None
        self.learned_authority: str | None = None
        self.learned_signer: str | None = None
        self.rpc_stats: dict[str, Any] = {
            "confirmed": 0,
            "failed": 0,
            "no_event": 0,
            "last_rpc_ts": 0.0,
            "via": {"log": 0, "cpi": 0, "accounts": 0},
            "triggered": {"portal": 0, "chain": 0, "poller": 0},
            "poller": {
                "polls": 0,
                "listed": 0,
                "skipped_failed": 0,
                "cursor": None,
                "last_poll_ts": 0.0,
                "last_error": None,
                "backfill_from": None,
            },
            "portal_mislabeled": 0,
            "noop": 0,  # successful migrate tx that found the curve already migrated (race losers)
            "retry_pending": 0,
            "failed_final": 0,
            "last_failed": None,
            "last_no_event": None,
            "withdraw_authority": None,
            "authority_static": None,
            "migrate_ix": None,
            "migrate_users": {},  # signer -> confirmed migrations, top entries only
            "migrate_user_static": None,
        }
        self._tasks: set[asyncio.Task] = set()
        self._claimed: dict[str, None] = {}  # signatures already handled by some path (ordered set)
        self._sig_mint: dict[str, str] = {}  # signature -> mint as the chain says
        self._portal_sig_mint: dict[str, str] = {}  # signature -> mint as PumpPortal said
        self._rpc_sem = asyncio.Semaphore(cfg.rpc_concurrency)
        self._retry: dict[str, tuple[float, int]] = {}  # signature -> (seen_ts, attempts so far)
        # seconds to wait before each getTransaction attempt, per trigger (RPC lag differs)
        self.portal_delays: tuple[float, ...] = (3, 10, 30, 60)
        self.chain_delays: tuple[float, ...] = (0, 3, 10)
        self.poll_delays: tuple[float, ...] = (0, 5, 20)
        self._poll_cursor: str | None = None  # newest signature seen by this process's poller

    def mentions(self) -> list[str]:
        out = [self.learned_authority or self.cfg.migration_authority]
        if self.learned_signer and self.learned_signer not in out:
            out.append(self.learned_signer)
        if self.cfg.chain_scope == "full":
            out.append(PUMP_PROGRAM)
        return out

    @staticmethod
    def _trim(d: dict[str, Any], cap: int = 20_000) -> None:
        while len(d) > cap:
            del d[next(iter(d))]

    def _claim(self, signature: str) -> bool:
        """True the first time a signature is seen. Every path that could fetch a tx checks here,
        so one migration costs at most one getTransaction."""
        if not signature or signature in self._claimed:
            return False
        self._claimed[signature] = None
        self._trim(self._claimed)
        return True

    def prime_claims(self) -> int:
        """On startup, treat every registry row that already has a pool as handled, so a cold-start
        backfill does not re-fetch what earlier runs confirmed. Rows without a pool stay open,
        except PumpPortal rows whose signature the chain already attributed to another mint:
        those are phantoms and are dropped."""
        rows = self.store.migrations(limit=50_000)
        n = 0
        for row in rows:
            sig = row.get("signature")
            if sig and row.get("pool"):
                self._claimed[sig] = None
                self._sig_mint[sig] = row["mint"]
                n += 1
        for row in rows:
            sig = row.get("signature")
            chain_mint = self._sig_mint.get(sig) if sig else None
            phantom = not row.get("pool") and chain_mint and chain_mint != row["mint"]
            if phantom and self.store.drop_migration(row["mint"]):
                self.rpc_stats["portal_mislabeled"] += 1
        return n

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
            self._claim(ev.signature)  # decoded from the logs: no need to fetch this tx
            row = self._migration_row(ev.data, ev.ts, ev.slot, ev.signature, "chain")
            if row["mint"] and row["pool"]:
                self._note_chain_mint(ev.signature, row["mint"])
                self._register(row, hour)

    def _note_chain_mint(self, signature: str, mint: str) -> None:
        """Remember the mint the chain reports for a signature and evict a PumpPortal row that
        attached this signature to some other mint (seen in ~3% of its migration messages)."""
        self._sig_mint[signature] = mint
        self._trim(self._sig_mint)
        wrong = self._portal_sig_mint.pop(signature, None)
        if wrong and wrong != mint and self.store.drop_migration(wrong):
            self.rpc_stats["portal_mislabeled"] += 1

    def _register(self, row: dict[str, Any], hour: str) -> str:
        """Record a sighting that carries the pool; count the mint as confirmed the first time."""
        status = self.store.add_migration(row)
        self.migrations.write(row)
        if status in ("new", "filled"):
            self.store.incr("migrations_confirmed", hour)
        return status

    def on_notification(self, n: ChainNotification) -> None:
        """Websocket saw a tx of the authority but its logs held no migrate event.

        Almost always the event was cut off with the logs (10 KB cap), so confirm it by
        signature exactly like a PumpPortal sighting. Only for the authority subscription:
        the program-wide one in "full" scope is far too busy to fetch.
        """
        if n.err or "migrate" in n.kinds or self.rpc is None:
            return
        if n.mention is None or n.mention == PUMP_PROGRAM or n.mention not in self.mentions():
            return
        if not self._claim(n.signature):
            return
        self.rpc_stats["triggered"]["chain"] += 1
        self._spawn(self.confirm_migration(n.signature, n.ts, delays=self.chain_delays))

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
            # Not every curve is SOL-quoted any more; sol_amount is in quote units for the others.
            "quote_mint": d.get("quote_mint"),
            "source": source,
        }

    async def run_chain(self) -> None:
        self.feed = SolanaLogsFeed(
            self.cfg.solana_ws_url, self.mentions(), self.cfg.chain_commitment, stale_s=self.cfg.chain_stale_s
        )
        self.feed.on_notification = self.on_notification
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
            self.portal_pools[ev.pool] = self.portal_pools.get(ev.pool, 0) + 1
            if "pump" not in ev.pool.lower():
                # bonk.fun / Raydium LaunchLab graduations ride the same channel; not our market.
                self.counts["portal_migrate_other"] += 1
                return
            self.counts["portal_migrate"] += 1
            self.store.incr("migrations_portal", hour)
            known = self._sig_mint.get(ev.signature)
            if known and known != ev.mint:
                self.rpc_stats["portal_mislabeled"] += 1  # chain already said this tx migrated another mint
                return
            self._portal_sig_mint[ev.signature] = ev.mint
            self._trim(self._portal_sig_mint)
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
            if self.store.add_migration(row) == "new":
                self.migrations.write(row)
            if self.rpc is not None and self._claim(ev.signature):
                self.rpc_stats["triggered"]["portal"] += 1
                self._spawn(self.confirm_migration(ev.signature, ev.ts, delays=self.portal_delays))

    async def run_portal(self) -> None:
        self.portal_feed = PumpPortalFeed(
            self.cfg.pumpportal_ws_url, self.cfg.pumpportal_api_key, stale_s=self.cfg.pumpportal_stale_s
        )
        print(f"[portal] {self.cfg.pumpportal_ws_url}")
        async for ev in self.portal_feed.events():
            self.on_portal(ev)

    # ---- RPC confirmation of PumpPortal migrations ----
    async def confirm_migration(
        self,
        signature: str,
        seen_ts: float,
        delays: tuple[float, ...] | None = None,
        attempts: int = 0,
    ) -> bool:
        """Fetch the migrate tx by signature, register pool + slot, and learn the withdraw authority.

        A fetch that fails every delay (rate limit, RPC lag) is queued for a later poll
        instead of being forgotten: `attempts` counts those rounds."""
        assert self.rpc is not None
        delays = self.portal_delays if delays is None else delays
        tx = None
        err = None
        for delay in delays:
            await asyncio.sleep(delay)
            try:
                async with self._rpc_sem:
                    tx = await self.rpc.get_transaction(signature)
            except httpx.HTTPError as exc:
                err = describe_http_error(exc)
                tx = None
            if tx:
                break
        if not tx:
            self.rpc_stats["failed"] += 1
            self.rpc_stats["last_failed"] = {"signature": signature, "error": err or "not found"}
            if attempts + 1 < self.cfg.retry_max_attempts:
                self._retry[signature] = (seen_ts, attempts + 1)
            else:
                self.rpc_stats["failed_final"] += 1
                print(f"[rpc] giving up on {signature} after {attempts + 1} rounds ({err or 'not found'})")
            self.rpc_stats["retry_pending"] = len(self._retry)
            return False
        info = migration_from_tx(tx)
        if info is not None and info.get("noop"):
            self.rpc_stats["noop"] += 1
            return False
        if info is None:
            self.rpc_stats["no_event"] += 1
            diag = {"signature": signature, **tx_diagnostics(tx)}
            self.rpc_stats["last_no_event"] = diag
            print(f"[rpc] no migrate in {signature}: {diag}")
            return False
        row = self._migration_row(info["event"], seen_ts, info["slot"], signature, "rpc")
        if row["mint"] and row["pool"]:
            self._note_chain_mint(signature, row["mint"])
            self._register(row, hour_key(seen_ts))
            self.store.incr("migrations_rpc", hour_key(seen_ts))
        self.rpc_stats["confirmed"] += 1
        self.rpc_stats["last_rpc_ts"] = time.time()
        via = info["event"].get("via", "log")
        self.rpc_stats["via"][via] = self.rpc_stats["via"].get(via, 0) + 1
        await self._learn_authority(info.get("accounts"))
        await self._learn_signer(info.get("accounts"))
        return True

    async def _learn_signer(self, accounts: dict[str, Any] | None) -> None:
        """Watch the wallet that signs migrations once one wallet clearly does nearly all of them.

        `withdraw_authority` can be loaded through an address lookup table, which
        `logsSubscribe` cannot match; the signer is always a static key.
        """
        if not accounts or not accounts.get("user"):
            return
        user = accounts["user"]
        users = self.rpc_stats["migrate_users"]
        users[user] = users.get(user, 0) + 1
        if len(users) > 10:  # keep the table small: drop the rarest
            del users[min(users, key=users.get)]
        self.rpc_stats["migrate_user_static"] = accounts.get("user_static")
        if self.learned_signer or self.feed is None or not accounts.get("user_static"):
            return
        total = self.rpc_stats["confirmed"]
        if total < SIGNER_MIN_N or users[user] < SIGNER_MIN_SHARE * total:
            return
        print(f"[rpc] {user} signed {users[user]}/{total} migrations; subscribing to it as well")
        self.learned_signer = user
        await self.feed.set_mentions(self.mentions())

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

    # ---- poller: the authority's signature list is the complete record of migrations ----
    async def poll_once(self, now: float | None = None) -> int:
        """List the authority's signatures newer than this process's cursor and confirm every
        successful one nobody claimed yet; then re-queue earlier fetch failures.

        The first poll of a process always walks `backfill_s` back regardless of the stored
        cursor: rows that already have a pool were claimed at startup, so the walk only costs
        the listing plus whatever the previous run never managed to confirm (crash, rate
        limits, feed outage). Returns how many transactions were handed to confirm_migration."""
        assert self.rpc is not None
        now = now or time.time()
        address = self.learned_authority or self.cfg.migration_authority
        cursor = self._poll_cursor
        st = self.rpc_stats["poller"]
        window = self.cfg.backfill_s
        initial = (
            cursor is None
            and self.cfg.initial_backfill_s > 0
            and not self.store.get_kv("initial_backfill_done")
        )
        if initial:
            window = max(window, self.cfg.initial_backfill_s)
        floor = now - window
        sigs: list[dict[str, Any]] = []
        before = None
        while True:
            page = await self.rpc.get_signatures(address, limit=1000, before=before, until=cursor)
            sigs.extend(page)
            if len(page) < 1000 or (page[-1].get("blockTime") or 0) < floor:
                break
            before = page[-1]["signature"]
        if cursor is None:
            st["backfill_from"] = floor
            st["initial_backfill"] = initial
            if initial:
                self.store.set_kv("initial_backfill_done", str(int(now)))
        sigs = [s for s in sigs if (s.get("blockTime") or now) >= floor]
        st["polls"] += 1
        st["listed"] += len(sigs)
        st["last_poll_ts"] = now
        fetched = 0
        for s in reversed(sigs):  # oldest first, so rows land in chain order
            if s.get("err"):
                st["skipped_failed"] += 1
                continue
            if not self._claim(s["signature"]):
                continue
            self.rpc_stats["triggered"]["poller"] += 1
            fetched += 1
            seen = float(s.get("blockTime") or now)
            self._spawn(self.confirm_migration(s["signature"], seen, delays=self.poll_delays))
        if sigs:
            self._poll_cursor = st["cursor"] = sigs[0]["signature"]
            self.store.set_kv("poller_cursor", st["cursor"])
        # earlier failures get another round, a bounded batch per poll so a bad RPC day cannot pile up
        for signature in list(self._retry)[: self.cfg.retry_batch]:
            seen, attempts = self._retry.pop(signature)
            fetched += 1
            self._spawn(self.confirm_migration(signature, seen, delays=self.poll_delays, attempts=attempts))
        self.rpc_stats["retry_pending"] = len(self._retry)
        return fetched

    async def run_poller(self) -> None:
        hours = self.cfg.backfill_s / 3600
        print(f"[poller] getSignaturesForAddress every {self.cfg.poll_s:.0f}s, backfill {hours:.1f}h")
        while True:
            try:
                n = await self.poll_once()
                if n:
                    print(f"[poller] {n} new tx")
            except httpx.HTTPError as exc:
                self.rpc_stats["poller"]["last_error"] = describe_http_error(exc)
                print(f"[poller] rpc error: {describe_http_error(exc)}")
            except Exception as exc:  # noqa: BLE001 - never let the poller die
                self.rpc_stats["poller"]["last_error"] = f"{type(exc).__name__}: {exc}"
                print(f"[poller] error: {exc}")
            await asyncio.sleep(self.cfg.poll_s)

    # ---- harvester ----
    async def harvest_once(self, gecko: GeckoTerminal, now: float | None = None) -> int:
        now = now or time.time()
        hs = self.harvest_stats
        cutoff = now - self.cfg.harvest_after_s
        hs["due"], hs["pending"] = self.store.pending_counts(cutoff)
        rows = self.store.pending_harvest(cutoff, self.cfg.harvest_batch)
        # Current pool info for the whole batch in one or two calls (30 pools per call) instead of
        # one call per row: Gecko's per-IP budget is the harvester's bottleneck.
        infos: dict[str, dict[str, Any]] = {}
        known = [r["pool"] for r in rows if r.get("pool")]
        if known:
            try:
                infos = await gecko.pools_info_multi(known)
            except httpx.HTTPError as exc:
                hs["last_error"] = f"pools_info_multi: {type(exc).__name__}"
        done = 0
        for row in rows:
            t0 = int(row["ts"])
            try:
                pool = row.get("pool") or await gecko.resolve_pool(row["mint"])
                candles = await gecko.candles_between(pool, t0 - 60, t0 + 24 * 3600 + 60) if pool else []
                info = infos.get(pool) if pool else None
                if pool and info is None and not row.get("pool"):
                    info = await gecko.pool_info(pool)  # pool only just resolved: not in the batch call
            except httpx.HTTPError as exc:
                hs["last_error"] = f"{row['mint'][:6]}: {type(exc).__name__}"
                print(f"[harvest] {row['mint'][:6]} http error {type(exc).__name__}; retry next cycle")
                continue
            metrics = compute_metrics(
                candles,
                t0,
                self.cfg.entry_delays_min,
                self.cfg.horizons_min,
                self.cfg.cost_bps_round_trip,
                now=now,
            )
            if not pool:
                metrics["reason"] = "no_pool"  # neither the chain nor Gecko knows a pool for this mint
            metrics.update(
                {
                    "mint": row["mint"],
                    "pool": pool,
                    "pool_resolved": not row.get("pool"),
                    "slot": row.get("slot"),
                    "source": row.get("source"),
                    "migration_sol": row.get("sol_amount"),
                    "quote_mint": row.get("quote_mint"),
                    "harvested_at": now,
                    "reserve_usd_now": float((info or {}).get("reserve_in_usd") or 0) if info else None,
                }
            )
            self.store.mark_harvested(row["mint"], metrics)
            self.survivor.write(metrics)
            self.counts["harvested"] += 1
            key = metrics.get("reason") if metrics.get("no_data") else "with_data"
            hs[key] = hs.get(key, 0) + 1
            done += 1
            hs["due"], hs["pending"] = self.store.pending_counts(cutoff)
        hs["runs"] += 1
        hs["last_run_ts"] = now
        hs["rows_last_run"] = done
        return done

    async def run_harvester(self, client: httpx.AsyncClient) -> None:
        self.gecko = GeckoTerminal(
            client,
            self.cfg.gecko_base_url,
            self.cfg.gecko_rpm,
            candle_minutes=self.cfg.gecko_candle_minutes,
            api_key=self.cfg.gecko_api_key,
            api_key_header=self.cfg.gecko_api_key_header,
        )
        while True:
            try:
                n = await self.harvest_once(self.gecko)
                if n:
                    print(f"[harvest] {n} tokens")
            except Exception as exc:  # noqa: BLE001 - never let the harvester die
                self.harvest_stats["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
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
                portal_feed=self.portal_feed.stats if self.portal_feed else None,
                portal_pools=self.portal_pools,
                rpc={**self.rpc_stats, "transport": self.rpc.stats if self.rpc else None},
                harvest=self.harvest_stats,
                gecko=self.gecko.stats if self.gecko else None,
                mentions=self.mentions(),
            )
            await asyncio.sleep(5)

    async def run(self) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            if self.cfg.rpc_confirm:
                self.rpc = SolanaRpc(
                    client,
                    self.cfg.solana_http_url or http_url_from_ws(self.cfg.solana_ws_url),
                    rps=self.cfg.rpc_rps,
                    penalty_s=self.cfg.rpc_429_penalty_s,
                    max_tx_version=self.cfg.rpc_max_tx_version,
                )
            print(f"[recorder] {self.prime_claims()} confirmed rows already in the registry")
            tasks = [self.run_chain(), self.run_status()]
            if self.rpc is not None and self.cfg.rpc_poll:
                tasks.append(self.run_poller())
            if self.cfg.pumpportal_enabled:
                tasks.append(self.run_portal())
            if self.cfg.run_harvester:
                tasks.append(self.run_harvester(client))
            await asyncio.gather(*tasks)


if __name__ == "__main__":
    from .config import settings
    from .store import make_store

    asyncio.run(Recorder(settings, make_store(settings.redis_url)).run())
