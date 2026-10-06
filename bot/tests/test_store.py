"""The same contract for both stores. Redis runs when REDIS_TEST_URL points at a server (CI starts
one); its database is flushed first, so never point it at a database that matters."""

import os
import time

import pytest

from app.store import MemoryStore, RedisStore


def _redis():
    url = os.environ.get("REDIS_TEST_URL")
    if not url:
        pytest.skip("REDIS_TEST_URL not set")
    s = RedisStore(url)
    try:
        s.r.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"redis unreachable: {exc}")
    s.r.flushdb()
    return s


@pytest.fixture(params=["memory", "redis"])
def store(request):
    return MemoryStore() if request.param == "memory" else _redis()


def row(mint, ts, pool=None, **kw):
    return {"mint": mint, "pool": pool, "ts": ts, "slot": None, "signature": f"sig-{mint}", **kw}


def test_migrations_merge_and_harvest_queue(store):
    assert store.add_migration(row("A", 100)) == "new"
    assert store.add_migration(row("A", 100)) == "dup"
    assert store.add_migration(row("A", 100, pool="P", sol_amount=85.0, chain_ts=99)) == "filled"
    assert store.add_migration(row("B", 200, pool="Q")) == "new"
    assert store.migration_count() == 2 and [r["mint"] for r in store.migrations()] == ["B", "A"]
    assert [r["mint"] for r in store.pending_harvest(150, 10)] == ["A"]
    assert store.pending_counts(150) == (1, 2)
    store.mark_harvested("A", {"mint": "A", "pool": "P", "x": 1})
    assert store.pending_counts(1_000) == (1, 1) and store.survivor_rows()[-1]["x"] == 1
    assert store.requeue(["A", "B"]) == 1 and store.pending_counts(1_000) == (2, 2)
    assert store.drop_migration("A") is False  # has a pool


def test_counters_status_and_kv(store):
    store.incr("m", "2026-10-06T10")
    store.incr("m", "2026-10-06T10", 2)
    assert store.counters("m", ["2026-10-06T10", "2026-10-06T11"]) == {"2026-10-06T10": 3, "2026-10-06T11": 0}
    store.set_status(a=1, b={"c": [1, 2]})
    assert store.status()["b"] == {"c": [1, 2]}
    assert store.get_kv("k") is None and store.incr_kv("k", 5) == 5 and store.incr_kv("k", 2) == 7
    store.set_kv("f", "1")
    assert store.get_kv("f") == "1" and store.get_kv("k") == "7"


def test_timed_queue_hands_out_due_members_once(store):
    assert store.schedule("snap", "M|P|30", 1_000) is True
    assert store.schedule("snap", "M|P|30", 5_000) is False  # already queued: the due time stays
    store.schedule("snap", "M|P|60", 2_800)
    store.schedule("snap", "N|Q|30", 900)
    assert store.queue_len("snap") == 3
    assert store.take_due("snap", 500, 10) == []
    assert store.take_due("snap", 1_000, 1) == [("N|Q|30", 900.0)]
    assert store.take_due("snap", 3_000, 10) == [("M|P|30", 1_000.0), ("M|P|60", 2_800.0)]
    assert store.queue_len("snap") == 0 and store.take_due("other", 1e12, 10) == []


def test_documents_wait_for_the_harvester_and_go_once_taken(store):
    store.put_doc("holders", "M|30", {"supply": 10**15, "holders": [["W", 5]]})
    assert store.pop_doc("holders", "M|30") == {"supply": 10**15, "holders": [["W", 5]]}
    assert store.pop_doc("holders", "M|30") is None and store.pop_doc("nothing", "x") is None


def test_cache_expires(store):
    store.cache_set("funder:W", "F", ttl_s=60)
    assert store.cache_get("funder:W") == "F" and store.cache_get("funder:X") is None
    store.cache_set("short", "v", ttl_s=1)
    time.sleep(1.1)
    assert store.cache_get("short") is None
