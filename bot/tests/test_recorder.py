"""Recorder, RPC confirmation and harvester wired together with fakes; no network."""

import asyncio
import time

import pytest
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
def _pumpswap_fixtures():
    import json as _json
    from pathlib import Path

    fx = Path(__file__).parent / "fixtures" / "pumpswap"
    return {p.stem: _json.loads(p.read_text()) for p in sorted(fx.glob("*.json"))}


class FakeRpcSigs(FakeRpc):
    """FakeRpc that also serves per-address signature lists (newest first) for the swap fetcher."""

    def __init__(self, txs, by_address):
        super().__init__(txs)
        self.by_address = by_address

    async def get_signatures(self, address, limit=1000, before=None, until=None):
        self.sig_calls.append((address, limit, before, until))
        return list(self.by_address.get(address, []))[:limit]


def test_harvester_adds_executable_fills_and_meters_credits(rec):
    real = _pumpswap_fixtures()
    pool = "F4WJkbXMz8C6GXGeymcKQpXaVkUMdyrqLHc7buEUMRJp"
    times = {k: v["blockTime"] for k, v in real.items()}
    t_mig = min(times.values()) - 120
    rec.cfg.entry_delays_min, rec.cfg.horizons_min = [0, 5], [1, 5]
    rec.cfg.fill_sizes_sol = [0.5, 1]
    sigs = [
        {"signature": k, "blockTime": times[k], "slot": real[k]["slot"], "err": None}
        for k in sorted(times, key=lambda k: -times[k])
    ]
    rec.rpc = FakeRpcSigs(dict(real), {pool: sigs})
    rec.fetcher = SwapFetcher(rec.rpc)
    rec.on_chain(
        ChainEvent(
            float(t_mig),
            1,
            "mig",
            "migrate",
            {"mint": "TOK", "pool": pool, "timestamp": t_mig, "quote_mint": WSOL},
        )
    )
    cs = [Candle(t_mig + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)]
    g = FakeGecko(cs)
    now = t_mig + 26 * 3600
    assert asyncio.run(rec.harvest_once(g, now=now)) == 1
    row = rec.store.survivor_rows()[0]
    assert row["swaps"]["swaps"] == 4 and row["swaps"]["credits"] == 1 + 4 and row["fills_t0"] == t_mig
    cell = row["fills"]["d0_h5"]
    assert set(cell) == {"0.5", "1"} and cell["1"]["net"] < cell["0.5"]["net"] < 0.1
    assert cell["1"]["liquidity_in_sol"] > 17 and cell["1"]["fees_sol"] > 0.01
    hs = rec.harvest_stats
    assert (
        hs["fills_rows"] == 1
        and hs["swaps_fetched"] == 4
        and hs["credits_today"] == 5
        and hs["fills_paused"] is False
    )
    assert rec.store.get_kv("credits:" + time.strftime("%Y-%m-%d", time.gmtime(now))) == "5"
    # the summary carries a per-size executable table and its own verdict
    s = summarize(
        rec.store.survivor_rows(), [0, 5], [1, 5], [0.5, 1.0]
    )  # pydantic hands sizes over as floats
    assert s["with_fills"] == 1 and s["fills"]["1"]["d0_h5"]["n"] == 1 and s["fill_primary_size"] == "1"
    # rows written by an earlier build keyed "1.0" still count
    legacy = {"mint": "L", "pool": "P", "fills": {"d0_h5": {"1.0": {"net": 0.25}}}}
    s2 = summarize([legacy], [0], [5], [1.0])
    assert s2["fills"]["1"]["d0_h5"]["n"] == 1
    assert s["verdict_fill"]["status"] == "INSUFFICIENT"


def test_harvester_pauses_when_the_daily_credit_budget_is_spent(rec):
    rec.cfg.fills_daily_credits = 10
    rec.rpc = FakeRpcSigs({}, {})
    rec.fetcher = SwapFetcher(rec.rpc)
    now = 1_700_000_000.0
    rec.store.incr_kv("credits:" + time.strftime("%Y-%m-%d", time.gmtime(now)), 10)
    rec.on_chain(mig(now - 100_000, mint="M1", pool="P1"))
    g = FakeGecko([])
    assert asyncio.run(rec.harvest_once(g, now=now)) == 0
    assert rec.harvest_stats["fills_paused"] is True and "budget" in rec.harvest_stats["last_error"]
    assert rec.store.pending_counts(now)[1] == 1  # the row waits instead of being harvested without fills


def test_rows_harvested_before_fills_are_requeued_once(rec):
    t0 = 1_700_000_000
    rec.on_chain(mig(float(t0), mint="OLD", pool="P1"))
    rec.on_chain(mig(float(t0), mint="USDC", pool="P2"))
    rec.store.mark_harvested("OLD", {"mint": "OLD", "pool": "P1", "quote_mint": None})
    rec.store.mark_harvested("USDC", {"mint": "USDC", "pool": "P2", "quote_mint": "EPjF"})  # not SOL-quoted
    assert rec.requeue_for_fills() == 1
    assert (
        rec.store.pending_counts(t0 + 10)[1] == 1
        and rec.store.pending_harvest(t0 + 10, 10)[0]["mint"] == "OLD"
    )
    assert rec.requeue_for_fills() == 0  # flagged: never again
    assert rec.store.get_kv("fills_requeued_v1")
