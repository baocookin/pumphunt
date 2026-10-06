"""Small infrastructure pieces: daily JSONL rotation, pool picking, feed subscription messages, API."""

import asyncio
import json

import websockets
from helpers import PK_A, PK_B, migrate_event_log

from app.anchor import PUMP_PROGRAM
from app.chain_feed import SolanaLogsFeed
from app.feed import PumpPortalFeed
from app.gecko import pick_pool
from app.jsonl import JsonlWriter, read_jsonl

DAY = 86_400


def test_jsonl_daily_rotation(tmp_path):
    w = JsonlWriter(tmp_path / "chain.jsonl", rotate_daily=True)
    t0 = 1_700_000_000  # 2023-11-14 22:13 UTC
    w.write({"i": 1}, now=t0)
    w.write({"i": 2}, now=t0 + 10)
    w.write({"i": 3}, now=t0 + DAY)
    w.close()
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["chain-2023-11-14.jsonl", "chain-2023-11-15.jsonl"]
    assert [r["i"] for r in read_jsonl(tmp_path / "chain-2023-11-14.jsonl")] == [1, 2]
    assert [r["i"] for r in read_jsonl(tmp_path / "chain-2023-11-15.jsonl")] == [3]


def test_jsonl_no_rotation(tmp_path):
    w = JsonlWriter(tmp_path / "flat.jsonl")
    w.write({"a": 1}, now=1_700_000_000)
    w.write({"a": 2}, now=1_700_000_000 + DAY)
    w.close()
    assert [p.name for p in tmp_path.iterdir()] == ["flat.jsonl"]
    assert len(list(read_jsonl(tmp_path / "flat.jsonl"))) == 2


def _pool(address, dex, reserve):
    return {
        "attributes": {"address": address, "reserve_in_usd": str(reserve)},
        "relationships": {"dex": {"data": {"id": dex}}},
    }


def test_pick_pool_prefers_pumpswap_then_depth():
    pools = [_pool("A", "raydium", 50_000), _pool("B", "pumpswap", 4_000), _pool("C", "pumpswap", 9_000)]
    assert pick_pool(pools) == "C"
    assert pick_pool([_pool("A", "raydium", 50_000), _pool("D", "meteora", 60_000)]) == "D"
    assert pick_pool([]) is None
    assert pick_pool([{"attributes": {"address": "E"}}]) == "E"


def test_logs_feed_one_subscription_per_address():
    feed = SolanaLogsFeed("wss://x", ["ADDR1", "ADDR2"], commitment="processed")
    msgs = [json.loads(m) for m in feed.subscribe_messages()]
    assert [m["id"] for m in msgs] == [1, 2]
    assert [m["params"][0]["mentions"] for m in msgs] == [["ADDR1"], ["ADDR2"]]
    assert all(m["params"][1]["commitment"] == "processed" for m in msgs)


def _notification(sub, sig, logs, slot=5, err=None):
    return {
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "subscription": sub,
            "result": {"context": {"slot": slot}, "value": {"signature": sig, "err": err, "logs": logs}},
        },
    }


def test_logs_feed_reports_every_notification_with_its_subscription():
    feed = SolanaLogsFeed("wss://x", ["AUTH", "PROG"])
    seen = []
    feed.on_notification = seen.append
    assert feed._on_message({"id": 1, "result": 77}, 1.0) == []
    assert feed._on_message({"id": 2, "result": 78}, 1.0) == []
    # logs cut off before the event: no ChainEvent, but the recorder still hears about it
    cut = [f"Program {PUMP_PROGRAM} invoke [1]", "Log truncated"]
    assert feed._on_message(_notification(77, "sigA", cut, slot=9), 2.0) == []
    n = seen[-1]
    assert (n.signature, n.mention, n.slot, n.kinds, n.logs_truncated, n.err) == (
        "sigA",
        "AUTH",
        9,
        [],
        True,
        None,
    )
    # full logs: the event decodes and the notification says so
    evs = feed._on_message(_notification(78, "sigB", [migrate_event_log(PK_A, PK_B)]), 3.0)
    assert (
        [e.kind for e in evs] == ["migrate"] and seen[-1].kinds == ["migrate"] and seen[-1].mention == "PROG"
    )
    assert feed.stats["notifications"] == 2 and feed.stats["events"] == 1
    # a failed tx is reported with its error and never decoded
    assert feed._on_message(_notification(77, "sigC", cut, err={"InstructionError": [0, "x"]}), 4.0) == []
    assert seen[-1].err and seen[-1].kinds == []


def test_feeds_reconnect_when_the_socket_goes_silent():
    """A server that acknowledges subscriptions and then says nothing must be dropped and redialed."""

    async def handler(ws):
        async for msg in ws:
            m = json.loads(msg)
            if m.get("method") == "logsSubscribe":
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": 100 + m["id"]}))

    async def drain(feed):
        async for _ in feed.events():
            pass

    async def run():
        server = await websockets.serve(handler, "127.0.0.1", 0)
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        chain = SolanaLogsFeed(url, ["A"], stale_s=0.15, backoff_s=0.05)
        portal = PumpPortalFeed(url, stale_s=0.15, backoff_s=0.05)
        tasks = [asyncio.create_task(drain(chain)), asyncio.create_task(drain(portal))]
        await asyncio.sleep(0.8)
        for t in tasks:
            t.cancel()
        server.close()
        await server.wait_closed()
        return chain.stats, portal.stats

    cs, ps = asyncio.run(run())
    assert cs["connects"] >= 2 and cs["stale_reconnects"] >= 1 and cs["subscribed"] >= 2
    assert ps["connects"] >= 2 and ps["stale_reconnects"] >= 1
    assert "no message" in cs["last_error"] and "no message" in ps["last_error"]


def test_api_routes_under_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv("PH_RUN_RECORDER", "0")
    monkeypatch.setenv("PH_REDIS_URL", "")
    monkeypatch.setenv("PH_STATIC_DIR", str(tmp_path))
    (tmp_path / "index.html").write_text("<h1>dash</h1>")
    import importlib

    from fastapi.testclient import TestClient

    import app.config as config_mod

    importlib.reload(config_mod)
    import app.api as api_mod

    importlib.reload(api_mod)
    with TestClient(api_mod.app) as c:
        health = c.get("/api/health").json()
        assert health["ok"] is True and health["build_sha"] == "dev"
        assert c.get("/api/stats").json()["chain_scope"] == "migrations"
        assert c.get("/api/survivor/summary").json()["verdict"]["status"] == "INSUFFICIENT"
        assert "dash" in c.get("/").text
