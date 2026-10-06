"""Recorder + harvester wired together with a fake GeckoTerminal; no network."""

import asyncio

import pytest

from app.anchor import PUMP_PROGRAM, ChainEvent
from app.config import Settings
from app.events import Event
from app.gecko import Candle
from app.jsonl import read_jsonl
from app.recorder import Recorder
from app.store import MemoryStore, hour_key


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
    return Recorder(cfg, MemoryStore())


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


def portal_mig(ts, mint="M1"):
    return Event(
        ts=ts,
        tx_type="migrate",
        mint=mint,
        trader="",
        signature="psig",
        sol_amount=0,
        token_amount=0,
        v_sol=0,
        v_tokens=0,
        market_cap_sol=0,
        raw={"txType": "migrate", "mint": mint},
    )


def test_scope_controls_subscriptions(rec):
    assert rec.mentions() == [rec.cfg.migration_authority]
    rec.cfg.chain_scope = "full"
    assert rec.mentions() == [rec.cfg.migration_authority, PUMP_PROGRAM]


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
    assert rec.counts["migrate"] == 2 and rec.counts["trade"] == 1
    assert (
        len(list(read_jsonl(rec.cfg.data_dir + "/migrations.jsonl"))) == 2
    )  # every chain sighting is logged
    rows = list(read_jsonl(rec.chain_log.path_for(t)))
    trade = next(r for r in rows if r["kind"] == "trade")
    assert trade["is_buy"] is True and "raw_b64" not in trade  # compact by default
    assert rows[0]["slot"] == 1 and rows[0]["sig"] == "a"


def test_portal_migration_then_chain_fills_pool(rec):
    t = 1_700_000_000.0
    rec.on_portal(portal_mig(t))
    row = rec.store.migrations()[0]
    assert row["pool"] is None and row["source"] == "portal"
    rec.on_chain(mig(t + 2))
    row = rec.store.migrations()[0]
    assert row["pool"] == "P1" and row["slot"] == 100 and row["source"] == "chain"
    assert row["ts"] == t  # first sighting keeps its timestamp
    assert rec.store.migration_count() == 1


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
