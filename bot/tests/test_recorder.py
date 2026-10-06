"""Recorder, RPC confirmation and harvester wired together with fakes; no network."""

import asyncio

import pytest
from helpers import PK_A, PK_B, fake_migrate_tx, fake_pubkey

from app.anchor import PUMP_PROGRAM, ChainEvent
from app.chain_feed import ChainNotification
from app.config import Settings
from app.events import Event
from app.gecko import Candle
from app.jsonl import read_jsonl
from app.recorder import SIGNER_MIN_N, Recorder
from app.rpc import find_migrate_ix
from app.store import MemoryStore, hour_key

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
        return {"reserve_in_usd": "12345.6"}

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
    assert asyncio.run(rec.harvest_once(g, now=t0 + 100)) == 1
    rows = rec.store.survivor_rows()
    assert len(rows) == 1 and rows[0]["mint"] == "M1" and rows[0]["reserve_usd_now"] == 12345.6
    assert rows[0]["pool"] == "P1" and rows[0]["pool_resolved"] is False
    cell = rows[0]["cells"]["d30_h60"]
    assert abs(cell["gross"] - (1.090 / 1.030 - 1)) < 1e-9
    # nothing left pending
    assert asyncio.run(rec.harvest_once(g, now=t0 + 200)) == 0
    assert g.calls == 1 and g.resolved == []


def test_harvest_resolves_pool_for_portal_only_migrations(rec):
    t0 = 1_700_000_000
    rec.on_portal(portal_mig(float(t0), mint="M2"))
    rec.on_portal(portal_mig(float(t0), mint="M3"))  # never gets a pool anywhere
    cs = [Candle(t0 + m * 60, 1.0, 1.0, 1.0, 1.0, 10.0) for m in range(0, 1500)]
    g = FakeGecko(cs, pools={"M2": "POOL2"})
    assert asyncio.run(rec.harvest_once(g, now=t0 + 100)) == 2
    by_mint = {r["mint"]: r for r in rec.store.survivor_rows()}
    assert by_mint["M2"]["pool"] == "POOL2" and by_mint["M2"]["pool_resolved"] is True
    assert by_mint["M3"]["pool"] is None and by_mint["M3"]["no_data"] is True
    assert sorted(g.resolved) == ["M2", "M3"]
    assert rec.store.migrations()[0]["harvested"] is True
