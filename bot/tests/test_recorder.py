"""Recorder, RPC confirmation and harvester wired together with fakes; no network."""

import asyncio
import contextlib
import time

import httpx
import pytest
from fakechain import POOL, FakeChain, noise, real_swaps
from helpers import PK_A, PK_B, fake_migrate_tx, fake_pubkey

from app.anchor import PUMP_PROGRAM, ChainEvent
from app.chain_feed import ChainNotification
from app.config import Settings
from app.events import Event
from app.gecko import Candle
from app.jsonl import read_jsonl
from app.recorder import SIGNER_MIN_N, WSOL, Recorder
from app.rpc import find_migrate_ix
from app.store import MemoryStore, hour_key
from app.survivor import summarize
from app.swaps import SwapFetcher

WA = fake_pubkey(777)


class FakeGecko:
    def __init__(self, candles, pools=None):
        self.candles = candles
        self.pools = pools or {}
        self.calls = 0
        self.resolved = []

    async def candles_between(self, pool, start, end):
        self.calls += 1
        return [c for c in self.candles if start <= c.ts <= end]

    async def pool_info(self, pool):
        self.calls += 1
        return {"reserve_in_usd": "12345.6"}

    async def pools_info_multi(self, pools):
        self.calls += 1
        self.multi = list(pools)
        return {p: {"address": p, "reserve_in_usd": "12345.6"} for p in pools}

    async def resolve_pool(self, mint):
        self.resolved.append(mint)
        return self.pools.get(mint)


class FakeRpc:
    def __init__(self, txs, signatures=None):
        self.txs = txs
        self.calls = 0
        self.signatures = signatures or []  # newest first, like the RPC
        self.sig_calls = []

    async def get_transaction(self, signature):
        self.calls += 1
        return self.txs.get(signature)

    async def get_signatures(self, address, limit=1000, before=None, until=None):
        self.sig_calls.append((address, limit, before, until))
        out = []
        for s in self.signatures:
            if s["signature"] == until:
                break
            out.append(s)
        return out[:limit]


def sig(s, bt, err=None):
    return {"signature": s, "blockTime": bt, "err": err}


class FakeFeed:
    def __init__(self, notifications=0):
        self.stats = {"notifications": notifications}
        self.mentions = None

    async def set_mentions(self, mentions):
        self.mentions = list(mentions)


@pytest.fixture
def rec(tmp_path):
    cfg = Settings(
        _env_file=None,
        redis_url=None,
        data_dir=str(tmp_path),
        harvest_after_s=10,
        initial_backfill_s=0,  # tests that want the one-off deep walk enable it explicitly
        entry_delays_min=[0, 30],
        horizons_min=[60],
    )
    r = Recorder(cfg, MemoryStore())
    r.portal_delays = r.chain_delays = r.poll_delays = (0,)
    return r


def mig(ts, mint="M1", pool="P1"):
    return ChainEvent(
        ts,
        slot=100,
        signature="s",
        kind="migrate",
        data={
            "mint": mint,
            "pool": pool,
            "timestamp": int(ts),
            "sol_amount_sol": 85.0,
            "mint_amount_ui": 2e8,
            "bonding_curve": "B",
            "user": "U",
        },
    )


def portal_mig(ts, mint="M1", signature="psig", pool="pump-amm"):
    return Event(
        ts=ts,
        tx_type="migrate",
        mint=mint,
        trader="",
        signature=signature,
        sol_amount=0,
        token_amount=0,
        v_sol=0,
        v_tokens=0,
        market_cap_sol=0,
        pool=pool,
        raw={"txType": "migrate", "mint": mint, "signature": signature, "pool": pool},
    )


def test_scope_controls_subscriptions(rec):
    assert rec.mentions() == [rec.cfg.migration_authority]
    rec.cfg.chain_scope = "full"
    assert rec.mentions() == [rec.cfg.migration_authority, PUMP_PROGRAM]
    rec.learned_authority = WA
    assert rec.mentions() == [WA, PUMP_PROGRAM]


def test_counters_registry_and_compact_trade_log(rec):
    t = 1_700_000_000.0
    rec.on_chain(ChainEvent(t, 1, "a", "create", {"mint": "X"}))
    rec.on_chain(
        ChainEvent(t, 1, "b", "trade", {"mint": "X", "is_buy": True, "sol_amount_sol": 0.5, "raw_b64": "zzz"})
    )
    rec.on_chain(mig(t))
    rec.on_chain(mig(t + 1))  # duplicate mint ignored
    assert rec.store.counters("creates_chain", [hour_key(t)]) == {hour_key(t): 1}
    assert rec.store.migration_count() == 1
    assert rec.store.counters("migrations_confirmed", [hour_key(t)]) == {hour_key(t): 1}  # mint counted once
    assert rec.counts["migrate"] == 2 and rec.counts["trade"] == 1
    assert len(list(read_jsonl(rec.cfg.data_dir + "/migrations.jsonl"))) == 2  # every sighting is logged
    rows = list(read_jsonl(rec.chain_log.path_for(t)))
    trade = next(r for r in rows if r["kind"] == "trade")
    assert trade["is_buy"] is True and "raw_b64" not in trade  # compact by default
    assert rows[0]["slot"] == 1 and rows[0]["sig"] == "a"


def test_portal_migration_then_chain_fills_pool(rec):
    t = 1_700_000_000.0
    rec.on_portal(portal_mig(t))  # no running loop: RPC confirmation is skipped silently
    row = rec.store.migrations()[0]
    assert row["pool"] is None and row["source"] == "portal"
    assert rec.store.counters("migrations_confirmed", [hour_key(t)]) == {hour_key(t): 0}
    rec.on_chain(mig(t + 2))
    row = rec.store.migrations()[0]
    assert row["pool"] == "P1" and row["slot"] == 100 and row["source"] == "chain"
    assert row["ts"] == t  # first sighting keeps its timestamp
    assert rec.store.migration_count() == 1
    assert rec.store.counters("migrations_confirmed", [hour_key(t)]) == {hour_key(t): 1}


def test_rpc_confirmation_fills_pool_and_learns_authority(rec):
    t = 1_700_000_000.0
    rec.rpc = FakeRpc({"sig1": fake_migrate_tx(PK_A, PK_B, WA, slot=4242)})
    rec.feed = FakeFeed(notifications=0)
    rec.on_portal(portal_mig(t, mint=PK_A, signature="sig1"))
    assert asyncio.run(rec.confirm_migration("sig1", t, delays=(0,))) is True
    row = rec.store.migrations()[0]
    assert row["pool"] == PK_B and row["slot"] == 4242 and row["source"] == "rpc"
    assert row["sol_amount"] == 85.0 and row["ts"] == t and row["quote_mint"] == PK_B
    assert rec.rpc_stats["confirmed"] == 1 and rec.rpc_stats["withdraw_authority"] == WA
    assert rec.rpc_stats["via"] == {"log": 1, "cpi": 0, "accounts": 0}
    assert rec.store.counters("migrations_confirmed", [hour_key(t)]) == {hour_key(t): 1}
    # configured guess was wrong and the feed is silent -> re-subscribe to the learned address
    assert rec.learned_authority == WA and rec.feed.mentions == [WA]
    assert rec.store.counters("migrations_rpc", [hour_key(t)]) == {hour_key(t): 1}


def test_rpc_confirmation_does_not_churn_a_working_feed(rec):
    t = 1_700_000_000.0
    rec.rpc = FakeRpc({"sig1": fake_migrate_tx(PK_A, PK_B, WA)})
    rec.feed = FakeFeed(notifications=50)
    assert asyncio.run(rec.confirm_migration("sig1", t, delays=(0,))) is True
    assert rec.learned_authority is None and rec.feed.mentions is None


def test_rpc_confirmation_skips_lookup_table_authority(rec):
    t = 1_700_000_000.0
    rec.rpc = FakeRpc({"sig1": fake_migrate_tx(PK_A, PK_B, WA, authority_in_lookup_table=True)})
    rec.feed = FakeFeed(notifications=0)
    assert asyncio.run(rec.confirm_migration("sig1", t, delays=(0,))) is True
    assert rec.rpc_stats["authority_static"] is False
    assert rec.learned_authority is None and rec.feed.mentions is None


def test_rpc_confirmation_retries_then_gives_up(rec):
    rec.rpc = FakeRpc({})
    rec.feed = FakeFeed()
    assert asyncio.run(rec.confirm_migration("missing", 1.0, delays=(0, 0))) is False
    assert rec.rpc.calls == 2 and rec.rpc_stats["failed"] == 1


def test_rpc_confirmation_survives_truncated_logs(rec):
    t = 1_700_000_000.0
    tx = fake_migrate_tx(PK_A, PK_B, WA, slot=9)
    tx["meta"]["logMessages"] = ["Log truncated"]
    acc = find_migrate_ix(tx)
    rec.rpc = FakeRpc({"sig1": tx})
    rec.feed = FakeFeed(notifications=0)
    rec.on_portal(portal_mig(t, mint=acc["base_mint"], signature="sig1"))
    assert asyncio.run(rec.confirm_migration("sig1", t, delays=(0,))) is True
    row = rec.store.migrations()[0]
    assert row["mint"] == acc["base_mint"] and row["pool"] == acc["pool"]
    assert row["slot"] == 9 and row["source"] == "rpc" and row.get("sol_amount") is None
    assert rec.rpc_stats["via"]["accounts"] == 1 and rec.learned_authority == WA


def notif(sig, mention, ts=1_700_000_000.0, kinds=(), err=None):
    return ChainNotification(ts=ts, slot=1, signature=sig, mention=mention, err=err, kinds=list(kinds))


def test_websocket_notification_without_event_is_confirmed_once(rec):
    t = 1_700_000_000.0
    tx = fake_migrate_tx(PK_A, PK_B, WA, slot=11)
    tx["meta"]["logMessages"] = ["Log truncated"]
    acc = find_migrate_ix(tx)
    rec.rpc = FakeRpc({"sigW": tx})
    rec.feed = FakeFeed(notifications=3)

    async def run():
        auth = rec.cfg.migration_authority
        rec.on_notification(notif("sigW", auth, t))
        rec.on_notification(notif("sigW", auth, t))  # same tx again: no second fetch
        rec.on_portal(portal_mig(t + 1, mint=acc["base_mint"], signature="sigW"))  # nor from PumpPortal
        await asyncio.gather(*rec._tasks)

    asyncio.run(run())
    assert rec.rpc.calls == 1
    assert (
        rec.rpc_stats["triggered"] == {"portal": 0, "chain": 1, "poller": 0}
        and rec.rpc_stats["confirmed"] == 1
    )
    row = rec.store.migrations()[0]
    assert row["pool"] == acc["pool"] and row["slot"] == 11 and row["source"] == "rpc"
    assert rec.store.counters("migrations_confirmed", [hour_key(t)]) == {hour_key(t): 1}
    assert rec.store.counters("migrations_portal", [hour_key(t)]) == {hour_key(t): 1}


def test_websocket_notification_is_ignored_when_not_worth_fetching(rec):
    rec.rpc = FakeRpc({})
    rec.feed = FakeFeed()

    async def run():
        auth = rec.cfg.migration_authority
        rec.on_notification(notif("s1", auth, err={"InstructionError": [0, "x"]}))  # failed tx
        rec.on_notification(notif("s2", auth, kinds=["migrate"]))  # already decoded from the logs
        rec.on_notification(notif("s3", PUMP_PROGRAM))  # program-wide firehose subscription
        rec.on_notification(notif("s4", None))  # unknown subscription
        await asyncio.gather(*rec._tasks)

    asyncio.run(run())
    assert rec.rpc.calls == 0 and rec.rpc_stats["triggered"] == {"portal": 0, "chain": 0, "poller": 0}
    # a migrate decoded from the logs claims its signature, so PumpPortal does not re-fetch it
    t = 1_700_000_000.0
    rec.on_chain(mig(t, mint="MX", pool="PX"))
    ev = ChainEvent(t, 1, "s2", "migrate", mig(t).data)
    rec.on_chain(ev)
    assert rec._claim("s2") is False and rec._claim("s") is False


def test_other_launchpad_migrations_are_counted_but_not_recorded(rec):
    t = 1_700_000_000.0
    rec.rpc = FakeRpc({})
    rec.on_portal(portal_mig(t, mint="B1", signature="sb", pool="raydium-launchlab"))
    rec.on_portal(portal_mig(t, mint="P1", signature="sp", pool="pump-amm"))
    rec.on_portal(portal_mig(t, mint="P2", signature="sq", pool="pump"))
    assert rec.counts["portal_migrate_other"] == 1 and rec.counts["portal_migrate"] == 2
    assert sorted(r["mint"] for r in rec.store.migrations()) == ["P1", "P2"]
    assert rec.portal_pools == {"raydium-launchlab": 1, "pump-amm": 1, "pump": 1}
    assert rec.rpc_stats["triggered"]["portal"] == 2
    assert rec._claim("sb") is True  # nothing was ever fetched for the bonk.fun one


def test_dominant_migrate_signer_gets_subscribed(rec):
    t = 1_700_000_000.0
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    acc = find_migrate_ix(tx)
    rec.feed = FakeFeed(notifications=400)  # the authority feed delivers, yet misses ALT-loaded migrations
    rec.rpc = FakeRpc({f"s{i}": tx for i in range(SIGNER_MIN_N + 1)})

    async def run():
        for i in range(SIGNER_MIN_N):
            assert await rec.confirm_migration(f"s{i}", t, delays=(0,))
            if i < SIGNER_MIN_N - 1:
                assert rec.learned_signer is None and rec.feed.mentions is None
        # notifications from the signer's own subscription are now worth fetching
        rec.on_notification(notif(f"s{SIGNER_MIN_N}", acc["user"], t))
        await asyncio.gather(*rec._tasks)

    asyncio.run(run())
    assert acc["user_static"] is True and rec.learned_signer == acc["user"]
    assert rec.feed.mentions == [rec.cfg.migration_authority, acc["user"]] == rec.mentions()
    assert rec.rpc_stats["migrate_users"] == {acc["user"]: SIGNER_MIN_N + 1}
    assert rec.rpc_stats["triggered"]["chain"] == 1 and rec.rpc_stats["confirmed"] == SIGNER_MIN_N + 1


def test_poller_confirms_new_signatures_once_and_keeps_a_cursor(rec):
    now = 1_700_000_000.0
    tx_a = fake_migrate_tx(PK_A, PK_B, WA, slot=1)
    tx_b = fake_migrate_tx(PK_A, PK_B, WA, slot=2)
    rec.feed = FakeFeed(notifications=5)
    rec.rpc = FakeRpc(
        {"sA": tx_a, "sB": tx_b},
        signatures=[
            sig("sA", now - 10),
            sig("sF", now - 20, err={"x": 1}),
            sig("sW", now - 30),
            sig("sB", now - 40),
        ],
    )
    rec._claim("sW")  # the websocket already fetched this one

    async def run():
        n = await rec.poll_once(now=now)
        await asyncio.gather(*rec._tasks)
        return n

    assert asyncio.run(run()) == 2
    assert (
        rec.rpc.calls == 2 and rec.rpc_stats["triggered"]["poller"] == 2 and rec.rpc_stats["confirmed"] == 2
    )
    st = rec.rpc_stats["poller"]
    assert st["polls"] == 1 and st["listed"] == 4 and st["skipped_failed"] == 1 and st["cursor"] == "sA"
    assert rec.store.get_kv("poller_cursor") == "sA" and st["backfill_from"] == now - rec.cfg.backfill_s
    assert rec.rpc.sig_calls == [(rec.cfg.migration_authority, 1000, None, None)]
    row = rec.store.migrations()[0]
    assert row["pool"] == PK_B and row["ts"] == now - 40  # oldest tx first: the row keeps its block time
    # next poll: only signatures newer than the cursor are listed, nothing new to do
    assert asyncio.run(rec.poll_once(now=now + 30)) == 0
    assert rec.rpc.sig_calls[-1] == (rec.cfg.migration_authority, 1000, None, "sA")
    assert rec.rpc.calls == 2 and rec.rpc_stats["poller"]["cursor"] == "sA"


def test_failed_fetches_are_retried_on_later_polls_until_they_give_up(rec):
    now = 1_700_000_000.0
    tx = fake_migrate_tx(PK_A, PK_B, WA, slot=5)
    rec.feed = FakeFeed()
    rec.cfg.retry_max_attempts = 3
    rec.rpc = FakeRpc({}, signatures=[sig("sR", now - 10)])

    async def run():
        assert await rec.poll_once(now=now) == 1  # listed and fetched: the RPC has nothing yet
        await asyncio.gather(*rec._tasks)
        assert rec.rpc_stats["failed"] == 1 and rec.rpc_stats["retry_pending"] == 1
        assert rec.rpc_stats["last_failed"] == {"signature": "sR", "error": "not found"}
        rec.rpc.txs["sR"] = tx  # the tx shows up before the next poll
        assert await rec.poll_once(now=now + 30) == 1  # nothing new listed, one retry re-queued
        await asyncio.gather(*rec._tasks)

    asyncio.run(run())
    assert rec.rpc_stats["confirmed"] == 1 and rec.rpc_stats["retry_pending"] == 0
    assert rec.store.migrations()[0]["pool"] == PK_B and rec.store.migrations()[0]["ts"] == now - 10
    # a signature that never resolves is dropped after retry_max_attempts rounds
    rec.rpc = FakeRpc({}, signatures=[sig("sDead", now - 5)])

    async def exhaust():
        for i in range(4):
            await rec.poll_once(now=now + 60 + 30 * i)
            await asyncio.gather(*rec._tasks)

    asyncio.run(exhaust())
    assert rec.rpc_stats["failed_final"] == 1 and rec.rpc_stats["retry_pending"] == 0
    assert rec.rpc.calls == 3  # 3 rounds, one attempt each with poll_delays=(0,)


def test_noop_migrates_and_enrichment(rec):
    t = 1_700_000_000.0
    acc_only = fake_migrate_tx(PK_A, PK_B, WA, slot=8)
    acc_only["meta"]["logMessages"] = ["Log truncated"]  # pool CPI present, event lost: accounts path
    acc = find_migrate_ix(acc_only)
    # on chain the event names the same mint/pool as the instruction accounts; mirror that here
    real = fake_migrate_tx(acc["base_mint"], acc["pool"], WA, slot=9)
    noop = fake_migrate_tx(acc["base_mint"], acc["pool"], WA, slot=10)
    noop["meta"]["logMessages"] = ["Program log: Bonding curve already migrated"]
    noop["meta"]["innerInstructions"] = []
    rec.feed = FakeFeed(notifications=1)
    rec.rpc = FakeRpc({"sN": noop, "sAcc": acc_only, "sReal": real})

    async def run():
        assert await rec.confirm_migration("sN", t, delays=(0,)) is False
        assert await rec.confirm_migration("sAcc", t + 1, delays=(0,)) is True
        assert await rec.confirm_migration("sReal", t + 2, delays=(0,)) is True

    asyncio.run(run())
    assert rec.rpc_stats["noop"] == 1 and rec.rpc_stats["confirmed"] == 2 and rec.rpc_stats["no_event"] == 0
    rows = rec.store.migrations()
    assert len(rows) == 1 and rows[0]["mint"] == acc["base_mint"]
    # the accounts-only row got the event's amounts from the real tx, and was counted once
    assert rows[0]["sol_amount"] == 85.0 and rows[0]["slot"] == 9 and rows[0]["ts"] == t + 1
    assert rec.store.counters("migrations_confirmed", [hour_key(t)]) == {hour_key(t): 1}


def test_first_poll_of_a_process_walks_back_even_with_a_stored_cursor(rec):
    now = 1_700_000_000.0
    rec.store.set_kv("poller_cursor", "sOld")  # left by a previous run
    rec.feed = FakeFeed()
    rec.rpc = FakeRpc({}, signatures=[sig("sNew", now - 5), sig("sOld", now - 50), sig("sOlder", now - 90)])
    assert asyncio.run(rec.poll_once(now=now)) == 3  # listed everything in the window, not just past sOld
    assert rec.rpc.sig_calls[0] == (rec.cfg.migration_authority, 1000, None, None)
    assert asyncio.run(rec.poll_once(now=now + 30)) == 0
    assert rec.rpc.sig_calls[-1][3] == "sNew"  # in-process cursor from here on


def test_first_ever_poll_walks_the_initial_window_once(rec):
    now = 1_700_000_000.0
    rec.cfg.backfill_s = 3600
    rec.cfg.initial_backfill_s = 48 * 3600
    rec.feed = FakeFeed()
    rec.rpc = FakeRpc(
        {}, signatures=[sig("h1", now - 100), sig("h30", now - 30 * 3600), sig("h60", now - 60 * 3600)]
    )
    assert asyncio.run(rec.poll_once(now=now)) == 2  # 48h window: h1 and h30, not h60
    st = rec.rpc_stats["poller"]
    assert st["initial_backfill"] is True and st["backfill_from"] == now - 48 * 3600
    assert rec.store.get_kv("initial_backfill_done") == str(int(now))
    # a later process start walks only the regular window
    fresh = Recorder(rec.cfg, rec.store)
    fresh.poll_delays = (0,)
    fresh.feed = FakeFeed()
    fresh.rpc = FakeRpc({}, signatures=rec.rpc.signatures)
    assert asyncio.run(fresh.poll_once(now=now)) == 1
    assert fresh.rpc_stats["poller"]["initial_backfill"] is False
    assert fresh.rpc_stats["poller"]["backfill_from"] == now - 3600


def test_startup_drops_portal_rows_the_chain_contradicts(rec):
    t = 1_700_000_000.0
    rec.on_chain(mig(t, mint="REAL", pool="P1"))  # signature "s" belongs to REAL
    # a phantom left behind by an older build: PumpPortal paired "s" with another mint
    rec.store.add_migration(
        {"mint": "PHANTOM", "pool": None, "ts": t, "slot": None, "signature": "s", "source": "portal"}
    )
    rec.on_portal(portal_mig(t, mint="WAITING", signature="s9"))  # legit, just not confirmed yet
    assert rec.store.migration_count() == 3
    fresh = Recorder(rec.cfg, rec.store)
    assert fresh.prime_claims() == 1
    assert sorted(r["mint"] for r in rec.store.migrations()) == ["REAL", "WAITING"]
    assert fresh.rpc_stats["portal_mislabeled"] == 1


def test_harvest_stats_and_reasons(rec):
    t0 = 1_700_000_000
    rec.on_chain(mig(float(t0), mint="TRADED", pool="P1"))
    rec.on_chain(mig(float(t0), mint="SILENT", pool="P2"))
    rec.on_portal(portal_mig(float(t0), mint="NOWHERE", signature="x"))
    cs = [Candle(t0 + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)]

    class G(FakeGecko):
        async def candles_between(self, pool, start, end):
            self.calls += 1
            return [c for c in self.candles if start <= c.ts <= end] if pool == "P1" else []

    g = G(cs)
    assert asyncio.run(rec.harvest_once(g, now=t0 + 100)) == 3
    hs = rec.harvest_stats
    assert hs["runs"] == 1 and hs["rows_last_run"] == 3 and hs["last_run_ts"] == t0 + 100
    assert hs["with_data"] == 1 and hs["no_candles"] == 1 and hs["no_pool"] == 1
    assert hs["due"] == 0 and hs["pending"] == 0
    by = {r["mint"]: r for r in rec.store.survivor_rows()}
    assert by["SILENT"]["reason"] == "no_candles" and by["NOWHERE"]["reason"] == "no_pool"
    assert "reason" not in by["TRADED"] and by["TRADED"]["quote_mint"] is None
    # cells beyond `now` are blank: now is only 100s after t0, so every horizon is unobservable
    assert all(v is None for v in by["TRADED"]["cells"].values()) and by["TRADED"]["alive_24h"] is None


def test_poller_cold_start_stays_inside_the_backfill_window(rec):
    now = 1_700_000_000.0
    rec.cfg.backfill_s = 3600
    rec.feed = FakeFeed()
    rec.rpc = FakeRpc({}, signatures=[sig("new", now - 100), sig("old", now - 7200)])
    assert asyncio.run(rec.poll_once(now=now)) == 1
    assert rec.rpc_stats["poller"]["listed"] == 1 and rec.rpc_stats["poller"]["cursor"] == "new"
    assert rec._claim("old") is True  # never touched


def test_prime_claims_skips_confirmed_rows_but_not_pool_less_ones(rec):
    t = 1_700_000_000.0
    rec.on_chain(mig(t, mint="M1", pool="P1"))  # signature "s", has pool
    rec.on_portal(portal_mig(t, mint="M2", signature="s2"))  # no pool yet
    fresh = Recorder(rec.cfg, rec.store)
    assert fresh.prime_claims() == 1
    assert fresh._claim("s") is False and fresh._claim("s2") is True


def test_mislabeled_portal_rows_are_dropped_or_refused(rec):
    t = 1_700_000_000.0
    tx = fake_migrate_tx(PK_A, PK_B, WA, slot=3)  # the chain says this tx migrated PK_A
    rec.feed = FakeFeed(notifications=5)
    rec.rpc = FakeRpc({"sX": tx, "sY": tx})
    # PumpPortal first, with the wrong mint: the phantom row goes once the chain answers
    rec.on_portal(portal_mig(t, mint="WRONG", signature="sX"))
    assert [r["mint"] for r in rec.store.migrations()] == ["WRONG"]
    assert asyncio.run(rec.confirm_migration("sX", t, delays=(0,))) is True
    assert [r["mint"] for r in rec.store.migrations()] == [PK_A]
    assert rec.rpc_stats["portal_mislabeled"] == 1
    # chain first, PumpPortal later with the wrong mint: the row is never created
    assert asyncio.run(rec.confirm_migration("sY", t, delays=(0,))) is True
    rec.on_portal(portal_mig(t + 1, mint="WRONG2", signature="sY"))
    assert [r["mint"] for r in rec.store.migrations()] == [PK_A]
    assert rec.rpc_stats["portal_mislabeled"] == 2
    # a row that already has a pool is never dropped
    assert rec.store.drop_migration(PK_A) is False


def test_supervisor_restarts_a_crashed_loop_and_records_it(rec):
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return "done"  # second run finishes cleanly

    asyncio.run(rec._supervise("flaky", flaky, restart_s=0))
    assert calls["n"] == 2
    assert rec.task_errors["flaky"]["count"] == 1 and rec.task_errors["flaky"]["last"] == "RuntimeError: boom"


def test_rpc_confirmation_records_why_a_tx_is_not_a_migration(rec):
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    tx["meta"]["logMessages"] = ["Program log: nothing here"]
    tx["transaction"]["message"]["instructions"] = []
    rec.rpc = FakeRpc({"sig1": tx})
    rec.feed = FakeFeed()
    assert asyncio.run(rec.confirm_migration("sig1", 1.0, delays=(0,))) is False
    assert rec.rpc_stats["no_event"] == 1 and rec.rpc_stats["confirmed"] == 0
    diag = rec.rpc_stats["last_no_event"]
    assert diag["signature"] == "sig1" and diag["found"] is True and diag["pump_ixs"] == []


def test_harvest_waits_then_computes(rec):
    t0 = 1_700_000_000
    rec.on_chain(mig(float(t0)))
    cs = [Candle(t0 + m * 60, 1.0, 1.0, 1.0, 1.0 + m / 1000, 10.0) for m in range(0, 1500)]
    g = FakeGecko(cs)
    # too early: migration younger than harvest_after_s
    assert asyncio.run(rec.harvest_once(g, now=t0 + 5)) == 0
    assert asyncio.run(rec.harvest_once(g, now=t0 + 26 * 3600)) == 1
    rows = rec.store.survivor_rows()
    assert len(rows) == 1 and rows[0]["mint"] == "M1" and rows[0]["reserve_usd_now"] == 12345.6
    assert rows[0]["pool"] == "P1" and rows[0]["pool_resolved"] is False
    cell = rows[0]["cells"]["d30_h60"]
    assert abs(cell["gross"] - (1.090 / 1.030 - 1)) < 1e-9
    # nothing left pending
    assert asyncio.run(rec.harvest_once(g, now=t0 + 200)) == 0
    assert g.calls == 2 and g.resolved == []  # one batched info call + one candles call, no per-row info
    assert g.multi == ["P1"]


def test_harvest_resolves_pool_for_portal_only_migrations(rec):
    t0 = 1_700_000_000
    rec.on_portal(portal_mig(float(t0), mint="M2"))
    rec.on_portal(portal_mig(float(t0), mint="M3"))  # never gets a pool anywhere
    cs = [Candle(t0 + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)]
    g = FakeGecko(cs, pools={"M2": "POOL2"})
    assert asyncio.run(rec.harvest_once(g, now=t0 + 26 * 3600)) == 2
    by_mint = {r["mint"]: r for r in rec.store.survivor_rows()}
    assert by_mint["M2"]["pool"] == "POOL2" and by_mint["M2"]["pool_resolved"] is True
    assert by_mint["M3"]["pool"] is None and by_mint["M3"]["no_data"] is True
    assert sorted(g.resolved) == ["M2", "M3"]
    assert rec.store.migrations()[0]["harvested"] is True


# ---- executable fills through the harvester ----
def _fills_setup(rec, gtfa, noise_n=0):
    real = real_swaps()
    times = {k: v["blockTime"] for k, v in real.items()}
    t_mig = min(times.values()) - 120  # swaps at +120, +400, +665, +673 s
    rec.cfg.entry_delays_min, rec.cfg.horizons_min = [0, 5], [1, 5]
    rec.cfg.fill_sizes_sol = [0.5, 1]
    rec.cfg.fills_replay_cells = ["d0_h5", "d5_h5"]
    txs = list(real.values()) + noise(noise_n, t_mig - 300, t_mig + 900)
    rec.rpc = FakeChain(txs, gtfa=gtfa)
    rec.fetcher = SwapFetcher(rec.rpc, token_filter=False)
    rec.on_chain(
        ChainEvent(
            float(t_mig),
            1,
            "mig",
            "migrate",
            {"mint": "TOK", "pool": POOL, "timestamp": t_mig, "quote_mint": WSOL},
        )
    )
    return t_mig


def test_harvester_replays_a_complete_window_and_meters_credits(rec):
    t_mig = _fills_setup(rec, gtfa=True)
    g = FakeGecko([Candle(t_mig + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)])
    now = t_mig + 26 * 3600
    assert asyncio.run(rec.harvest_once(g, now=now)) == 1
    row = rec.store.survivor_rows()[0]
    # window [t_mig-300, t_mig+604] holds the swaps at +120 and +400; every decision time is inside it
    sw = row["swaps"]
    assert sw["window"]["method"] == "gtfa" and sw["window"]["complete"] and sw["window"]["fetched"] == 2
    # the fixtures are a sample of the pool's swaps: the window sees the gap between the two
    assert sw["window"]["chain_breaks"] == 1 and sw["flow_windows"] == {}
    # every decision time lies in the window; the one before it predates the migration
    assert sw["states"]["pages"] == 0 and sw["credits"] == 10 and sw["swaps"] == 2
    assert row["fills_version"] == 2 and row["fills_t0"] == t_mig
    cell = row["fills"]["d5_h5"]
    assert set(cell) == {"0.5", "1"} and cell["1"]["model"] == "replay" and cell["1"]["replayed_swaps"] == 1
    assert cell["1"]["net_ghost"] <= cell["1"]["net_replay"] and cell["1"]["net"] == cell["1"]["net_replay"]
    # the ghost model charges impact twice, so a bigger order looks worse there; under replay the
    # fixed 0.001 SOL per transaction weighs more on the smaller order
    assert cell["1"]["net_ghost"] < cell["0.5"]["net_ghost"] and cell["1"]["net"] > cell["0.5"]["net"]
    assert row["fills"]["d0_h5"]["1"]["model"] == "replay" and row["flow"]["d5"]["swaps"] == 1
    hs = rec.harvest_stats
    assert hs["gtfa"] is True and hs["replay_windows"] == 1 and hs["window_incomplete"] == 0
    assert hs["fills_rows"] == 1 and hs["swaps_fetched"] == 2 and hs["credits_today"] == 10
    assert rec.store.get_kv("credits:" + time.strftime("%Y-%m-%d", time.gmtime(now))) == "10"
    assert hs["windows_with_breaks"] == 1 and hs["flow_rows"] == 1 and hs["states_unresolved"] == 0
    # every fetched swap is in the day's dataset file, compact and lossless
    lines = list(read_jsonl(rec.swaps_log.path_for(now)))
    assert len(lines) == 1 and lines[0]["pool"] == row["pool"] and len(lines[0]["swaps"]["rows"]) == 2
    s = summarize(rec.store.survivor_rows(), [0, 5], [1, 5], [0.5, 1.0])
    assert s["with_fills"] == 1 and s["fills"]["1"]["d0_h5"]["n"] == 1 and s["fill_primary_size"] == "1"
    assert s["verdict_fill"]["status"] == "INSUFFICIENT" and s["fills_version"] == 2
    # rows from the older execution model never enter the tables
    legacy = {"mint": "L", "pool": "P", "fills": {"d0_h5": {"1.0": {"net": 0.25}}}}
    assert summarize([legacy], [0], [5], [1.0])["fills"]["1"]["d0_h5"]["n"] == 0


def test_harvester_without_helius_falls_back_and_marks_replay_where_it_can(rec):
    t_mig = _fills_setup(rec, gtfa=False)
    g = FakeGecko([Candle(t_mig + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)])
    assert asyncio.run(rec.harvest_once(g, now=t_mig + 26 * 3600)) == 1
    row = rec.store.survivor_rows()[0]
    assert row["swaps"]["window"]["method"] == "signatures" and row["swaps"]["window"]["complete"]
    assert rec.harvest_stats["gtfa"] is False and "Method not found" in rec.harvest_stats["gtfa_error"]
    assert row["fills"]["d5_h5"]["1"]["model"] == "replay"  # the window was small enough to fetch whole


def test_a_window_over_its_cap_still_yields_flow_and_states(rec):
    t_mig = _fills_setup(rec, gtfa=True, noise_n=3000)  # 2.5 bot transactions a second, 4 swaps
    rec.cfg.fills_replay_max_tx = 500
    rec.fetcher.scan_pages = 10
    g = FakeGecko([Candle(t_mig + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)])
    assert asyncio.run(rec.harvest_once(g, now=t_mig + 26 * 3600)) == 1
    row = rec.store.survivor_rows()[0]
    sw = row["swaps"]
    assert not sw["window"]["complete"] and sw["window"]["fetched"] == 100
    # the 5-minute windows before each entry fit their own cap and give the order flow
    assert sw["flow_windows"]["d5"]["complete"] and row["flow"]["d5"]["swaps"] == 1
    # entry/exit and decision states come from backwards scans past the noise; the decision and
    # the entry at T+0 and the exit at T+1 min precede every swap: the first swap's pre-state
    st = sw["states"]
    assert st["unresolved"] == 0 and st["resolved"] == 4 and st["before_first"] == 3
    assert (
        row["decision"]["d5"]["last_trade_age_s"] == 180 and row["decision"]["d0"]["last_trade_age_s"] is None
    )
    cell = row["fills"]["d5_h5"]["1"]
    assert cell["model"] == "ghost" and cell["net_replay"] is None  # no complete window to replay
    assert rec.harvest_stats["window_incomplete"] == 1


class FlakyChain(FakeChain):
    """Answers the first `ok` getTransactionsForAddress calls, then fails with HTTP 500."""

    def __init__(self, txs, ok):
        super().__init__(txs)
        self.ok = ok

    async def get_transactions_for_address(self, *a, **kw):
        if len(self.calls) >= self.ok:
            req = httpx.Request("POST", "http://rpc.invalid")
            raise httpx.HTTPStatusError("500", request=req, response=httpx.Response(500, request=req))
        return await super().get_transactions_for_address(*a, **kw)


def test_credits_of_a_pool_that_fails_half_way_are_still_metered(rec):
    t_mig = _fills_setup(rec, gtfa=True, noise_n=3000)
    rec.cfg.fills_replay_max_tx = 500
    rec.rpc = FlakyChain(rec.rpc.txs, ok=2)  # the window's first page and its count, then errors
    rec.fetcher = SwapFetcher(rec.rpc, token_filter=False)
    g = FakeGecko([Candle(t_mig + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)])
    now = t_mig + 26 * 3600
    assert asyncio.run(rec.harvest_once(g, now=now)) == 0  # retried next cycle
    assert rec.harvest_stats["credits_today"] == 20 and "fills TOK" in rec.harvest_stats["last_error"]
    assert rec.store.get_kv("credits:" + time.strftime("%Y-%m-%d", time.gmtime(now))) == "20"


def test_the_budget_is_checked_before_every_pool(rec):
    t_mig = _fills_setup(rec, gtfa=True)
    rec.on_chain(
        ChainEvent(
            float(t_mig + 1),
            2,
            "mig2",
            "migrate",
            {"mint": "TOK2", "pool": POOL, "timestamp": t_mig + 1, "quote_mint": WSOL},
        )
    )
    rec.cfg.fills_daily_credits = 5  # the first pool's single page (10 credits) spends it
    g = FakeGecko([Candle(t_mig + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)])
    now = t_mig + 26 * 3600
    assert asyncio.run(rec.harvest_once(g, now=now)) == 1
    assert rec.harvest_stats["fills_paused"] is True and rec.store.pending_counts(now)[1] == 1


def test_harvester_pauses_when_the_daily_credit_budget_is_spent(rec):
    rec.cfg.fills_daily_credits = 10
    rec.rpc = FakeChain([])
    rec.fetcher = SwapFetcher(rec.rpc)
    now = 1_700_000_000.0
    rec.store.incr_kv("credits:" + time.strftime("%Y-%m-%d", time.gmtime(now)), 10)
    rec.on_chain(mig(now - 100_000, mint="M1", pool="P1"))
    g = FakeGecko([])
    assert asyncio.run(rec.harvest_once(g, now=now)) == 0
    assert rec.harvest_stats["fills_paused"] is True and "budget" in rec.harvest_stats["last_error"]
    assert rec.store.pending_counts(now)[1] == 1  # the row waits instead of being harvested without fills


def test_rows_from_an_older_execution_model_are_requeued_once(rec):
    t0 = 1_700_000_000
    for m, pool in (("NOFILLS", "P1"), ("V1", "P2"), ("V2", "P3"), ("USDC", "P4")):
        rec.on_chain(mig(float(t0), mint=m, pool=pool))
    rec.store.mark_harvested("NOFILLS", {"mint": "NOFILLS", "pool": "P1", "quote_mint": None})
    rec.store.mark_harvested("V1", {"mint": "V1", "pool": "P2", "quote_mint": None, "fills": {"d0_h5": {}}})
    rec.store.mark_harvested(
        "V2", {"mint": "V2", "pool": "P3", "quote_mint": None, "fills": {}, "fills_version": 2}
    )
    rec.store.mark_harvested("USDC", {"mint": "USDC", "pool": "P4", "quote_mint": "EPjF"})  # not SOL-quoted
    assert rec.requeue_for_fills() == 2
    assert sorted(r["mint"] for r in rec.store.pending_harvest(t0 + 10, 10)) == ["NOFILLS", "V1"]
    assert rec.requeue_for_fills() == 0  # flagged: never again for this version
    assert rec.store.get_kv("fills_requeued_v2")


# ---- decision-time features ----
def _mig_event(t, mint, pool, **data):
    return ChainEvent(
        float(t), 1, f"sig-{mint}", "migrate", {"mint": mint, "pool": pool, "timestamp": t, **data}
    )


def test_holder_snapshots_are_queued_for_tradeable_sol_pools_only(rec):
    rec.cfg.holder_snapshot_delays_min = [30, 60]
    rec.on_chain(_mig_event(1_000, "TINY", "PT", quote_mint=WSOL, sol_amount_sol=0.03))
    rec.on_chain(_mig_event(1_000, "USD", "PU", quote_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"))
    rec.on_chain(_mig_event(1_000, "OK", "PO", quote_mint=WSOL, sol_amount_sol=85.0))
    rec.on_chain(_mig_event(1_000, "OK", "PO", quote_mint=WSOL, sol_amount_sol=85.0))  # seen again
    assert rec.store.queue_len("snap") == 2
    # due at the decision times themselves: what a trader could see before acting
    assert rec.store.take_due("snap", 1e12, 10) == [("OK|PO|30", 1_000 + 1_800), ("OK|PO|60", 1_000 + 3_600)]


class BrokenHolderRpc:
    async def get_token_largest_accounts(self, mint):
        raise httpx.ConnectError("down")


def test_a_late_snapshot_is_dropped_and_a_failed_one_retried_while_on_time(rec):
    rec.cfg.holder_snapshot_max_late_s = 300
    rec.rpc = BrokenHolderRpc()
    rec.store.schedule("snap", "M|P|30", 1_000)
    assert asyncio.run(rec.snapshot_once(now=1_400)) == 0 and rec.snapshot_stats["late"] == 1
    rec.store.schedule("snap", "N|Q|30", 2_000)
    assert asyncio.run(rec.snapshot_once(now=2_005)) == 0
    assert rec.snapshot_stats["errors"] == 1 and "ConnectError" in rec.snapshot_stats["last_error"]
    assert rec.store.take_due("snap", 1e12, 10) == [("N|Q|30", 2_020.0)]  # retried 15 s later


def test_harvest_attaches_snapshots_curve_history_and_funders(rec):
    from fakehistory import HistoryRpc, HolderRpc, Router, create_event, curve_tx, first_tx, trade_event

    real = real_swaps()
    t_mig = min(tx["blockTime"] for tx in real.values()) - 120  # swaps at +120, +400, +665, +673 s
    cfg = rec.cfg
    cfg.entry_delays_min, cfg.horizons_min, cfg.fill_sizes_sol = [0, 5], [1, 5], [1]
    cfg.fills_replay_cells = ["d0_h5", "d5_h5"]
    cfg.holder_snapshot_delays_min = [5]
    cfg.features_funding_min_real_sol = 0
    mint, curve, dev, b1, h1, funder = (fake_pubkey(n) for n in (9001, 9003, 11, 12, 15, 777))
    rec.on_chain(_mig_event(t_mig, mint, POOL, quote_mint=WSOL, sol_amount_sol=85.0, bonding_curve=curve))

    # the live snapshot at the T+5 min decision, taken 10 s after it was due
    largest = [("vault", 6 * 10**14), ("a1", 3 * 10**13), ("a2", 10**13)]  # 1e15 supply, 6 decimals
    rec.rpc = HolderRpc(largest, {"vault": POOL, "a1": dev, "a2": h1}, 10**15)
    now = t_mig + 300 + 10
    assert asyncio.run(rec.snapshot_once(now=now)) == 1 and rec.snapshot_stats["taken"] == 1
    assert rec.store.get_kv("credits:" + time.strftime("%Y-%m-%d", time.gmtime(now))) == "3"
    assert len(list(read_jsonl(rec.holders_log.path_for(now)))) == 1

    # at harvest: the pool's swaps, the curve's history and the wallets' first transactions
    t_create = t_mig - 600
    history = HistoryRpc(
        {
            curve: [
                curve_tx(10, t_create, [create_event(t_create, mint, curve, dev)], idx=1, curve=curve),
                curve_tx(10, t_create, [trade_event(dev, 2, True, t_create, mint, dev)], idx=2, curve=curve),
                curve_tx(10, t_create, [trade_event(b1, 5, True, t_create, mint, dev)], idx=3, curve=curve),
            ],
            dev: [first_tx(dev, funder, t_create - 2_000)],
            b1: [first_tx(b1, funder, t_create - 1_000)],
            h1: [first_tx(h1, dev, t_create - 500)],
        }
    )
    rec.fetcher = SwapFetcher(Router({POOL: FakeChain(list(real.values()))}, history), token_filter=False)
    g = FakeGecko([Candle(t_mig + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)])
    assert asyncio.run(rec.harvest_once(g, now=t_mig + 26 * 3600)) == 1
    row = rec.store.survivor_rows()[0]
    h = row["holders"]["d5"]
    assert h["top1"] == 0.075 and h["top10"] == 0.1 and h["pool_share"] == 0.6 and h["late_s"] == 10
    assert h["dev_share"] == 0.075 and h["bundle_share"] == 0 and 0 < h["top10_exit_share"] < 1
    c = row["curve"]
    assert c["found"] and c["graduate_s"] == 600 and c["dev_buy_sol"] == 2 and c["bundle_sol"] == 5
    assert c["bundle_wallets"] == [b1] and c["curve_tx"] == 3 and c["page_complete"]
    fu = row["funding"]
    assert fu["wallets"] == 3 and fu["looked"] == 3 and fu["max_cluster"] == 2  # dev and b1 share a funder
    assert fu["dev_linked"] == 2 and fu["fresh_1d"] == 3
    hs = rec.harvest_stats
    assert hs["features_rows"] == 1 and hs["funding_rows"] == 1 and hs["funding_lookups"] == 3
    assert rec.store.pop_doc("holders", f"{mint}|5") is None  # attached once, then gone


# ---- loop supervision ----
def test_a_stalled_loop_is_cancelled_and_restarted_and_shutdown_still_works(rec):
    starts = []

    async def hangs():
        starts.append(time.time())
        rec.beat("stuck")
        await asyncio.Event().wait()  # an await that never returns: no exception to catch

    async def scenario():
        sup = asyncio.create_task(rec._supervise("stuck", hangs, restart_s=0, stall_s=10))
        await asyncio.sleep(0.01)
        assert len(starts) == 1 and rec.check_stalls(now=time.time() + 5) == []  # still fresh
        assert set(rec.loop_ages()) == {"stuck"}  # only watched loops are reported
        assert rec.check_stalls(now=time.time() + 60) == ["stuck"]
        await asyncio.sleep(0.05)
        assert len(starts) == 2 and "stalled" in rec.task_errors["stuck"]["last"]
        sup.cancel()  # shutdown: the supervisor and its loop both end
        with contextlib.suppress(asyncio.CancelledError):
            await sup
        assert rec._loops["stuck"][0].cancelled()

    asyncio.run(scenario())


def test_funders_without_a_snapshot_use_the_curves_earliest_buyers(rec):
    from fakehistory import HistoryRpc, Router, create_event, curve_tx, first_tx, trade_event

    real = real_swaps()
    t_mig = min(tx["blockTime"] for tx in real.values()) - 120
    cfg = rec.cfg
    cfg.entry_delays_min, cfg.horizons_min, cfg.fill_sizes_sol = [0, 5], [1, 5], [1]
    cfg.fills_replay_cells = ["d0_h5", "d5_h5"]
    cfg.holder_snapshot_delays_min = [5]
    cfg.features_funding_min_real_sol = 0
    mint, curve, dev, b1, e1 = (fake_pubkey(n) for n in (9001, 9003, 11, 12, 21))
    rec.on_chain(_mig_event(t_mig, mint, POOL, quote_mint=WSOL, sol_amount_sol=85.0, bonding_curve=curve))
    t_create = t_mig - 600
    history = HistoryRpc(
        {
            curve: [
                curve_tx(10, t_create, [create_event(t_create, mint, curve, dev)], idx=1, curve=curve),
                curve_tx(10, t_create, [trade_event(b1, 5, True, t_create, mint, dev)], idx=2, curve=curve),
                curve_tx(11, t_create + 1, [trade_event(e1, 1, True, t_create + 1, mint, dev)], curve=curve),
            ],
            dev: [first_tx(dev, e1, t_create - 50)],
            e1: [first_tx(e1, fake_pubkey(777), t_create - 999_999)],
        }
    )
    rec.fetcher = SwapFetcher(Router({POOL: FakeChain(list(real.values()))}, history), token_filter=False)
    g = FakeGecko([Candle(t_mig + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)])
    assert asyncio.run(rec.harvest_once(g, now=t_mig + 26 * 3600)) == 1  # no snapshot was ever taken
    row = rec.store.survivor_rows()[0]
    assert row["holders"] is None and row["curve"]["early_wallets"] == [b1, e1]
    fu = row["funding"]
    assert sorted(fu["funders"]) == sorted([dev, b1, e1]) and fu["looked"] == 3
    assert fu["dev_linked"] == 1 and fu["cluster_hold_share"] == 0.0 and fu["dev_group_hold_share"] is None
