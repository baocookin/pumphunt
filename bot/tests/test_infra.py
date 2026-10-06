"""Small infrastructure pieces: daily JSONL rotation, pool picking, feed subscription messages, API."""

import asyncio
import json

import pytest
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


def test_gecko_raises_after_persistent_rate_limits_and_counts_calls(monkeypatch):
    import httpx

    from app.gecko import GeckoTerminal

    class Resp:
        def __init__(self, status, payload=None, headers=None):
            self.status_code = status
            self._p = payload
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                req = httpx.Request("GET", "https://g")
                raise httpx.HTTPStatusError(
                    "x", request=req, response=httpx.Response(self.status_code, request=req)
                )

        def json(self):
            return self._p

    class Client:
        def __init__(self, codes):
            self.codes = list(codes)
            self.urls = []

        async def get(self, url, params=None, headers=None):
            self.urls.append(url)
            code = self.codes.pop(0)
            if "/pools/multi/" in url and code == 200:
                addrs = url.rsplit("/", 1)[1].split(",")
                return Resp(
                    200,
                    {
                        "data": [
                            {"attributes": {"address": a, "reserve_in_usd": str(i)}}
                            for i, a in enumerate(addrs)
                        ]
                    },
                )
            return Resp(
                code,
                {"data": {"attributes": {"reserve_in_usd": "1"}}} if code == 200 else None,
                {"retry-after": "7"},
            )

    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr("app.gecko.asyncio.sleep", fake_sleep)
    g = GeckoTerminal(Client([429, 429, 429, 429]), "https://g", rpm=100_000)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(g.pool_info("P"))
    assert _counts(g) == {"calls": 4, "rate_limited": 4, "not_found": 0, "errors": 1}
    g = GeckoTerminal(Client([429, 200, 404]), "https://g", rpm=100_000)
    assert asyncio.run(g.pool_info("P")) == {"reserve_in_usd": "1"}
    assert asyncio.run(g.pool_info("Q")) is None
    assert _counts(g) == {"calls": 3, "rate_limited": 1, "not_found": 1, "errors": 0}
    assert 7.0 in slept  # Retry-After honoured (the other sleeps are the per-minute pacer)
    # multi: 30 pools per call, keyed by address
    c = Client([200, 200])
    g = GeckoTerminal(c, "https://g", rpm=100_000)
    pools = [f"P{i}" for i in range(31)]
    info = asyncio.run(g.pools_info_multi(pools))
    assert (
        len(c.urls) == 2
        and c.urls[0].endswith("/pools/multi/" + ",".join(pools[:30]))
        and c.urls[1].endswith("/pools/multi/P30")
    )
    assert info["P0"]["reserve_in_usd"] == "0" and info["P30"]["reserve_in_usd"] == "0" and len(info) == 31


async def _no_sleep(_s):
    return None


def _counts(g):
    return {k: v for k, v in g.stats.items() if k != "rpm_now"}


def test_gecko_limiter_adapts_and_candles_default_to_five_minutes(monkeypatch):
    from app.gecko import GeckoTerminal, RateLimiter

    rl = RateLimiter(20, min_per_minute=3)
    rl.rejected()
    assert rl.rpm == 14.0
    for _ in range(10):
        rl.rejected()
    assert rl.rpm == 3.0  # floor
    for _ in range(20):
        rl.accepted()
    assert abs(rl.rpm - 3.3) < 1e-9  # +10% per 20 clean calls
    for _ in range(2000):
        rl.accepted()
    assert rl.rpm == 20.0  # ceiling

    class Client:
        def __init__(self):
            self.params = []

        async def get(self, url, params=None, headers=None):
            self.params.append(params)

            class R:
                status_code = 200
                headers = {}

                def raise_for_status(self):
                    pass

                def json(self):
                    return {"data": {"attributes": {"ohlcv_list": [[600, 1, 1, 1, 1, 5]]}}}

            return R()

    c = Client()
    g = GeckoTerminal(c, "https://g", rpm=100_000)
    assert asyncio.run(g.candles_between("P", 0, 1000))[0].ts == 600
    assert c.params[0]["aggregate"] == 5 and c.params[0]["before_timestamp"] == 1000 + 300
    assert g.stats["rpm_now"] == 100000.0
    g1 = GeckoTerminal(c, "https://g", rpm=100_000, candle_minutes=1)
    asyncio.run(g1.ohlcv_minute("P", 50))
    assert c.params[-1]["aggregate"] == 1
    # a CoinGecko plan key goes in the header the plan expects; the public API sends none
    keyed = GeckoTerminal(
        c, "https://pro-api.coingecko.com/api/v3/onchain", api_key="K", api_key_header="x-cg-pro-api-key"
    )
    assert keyed.headers["x-cg-pro-api-key"] == "K" and "x-cg-pro-api-key" not in g1.headers


def test_feeds_survive_a_rejected_handshake_and_reconnect():
    """PumpPortal was seen dropping the socket and then answering the reconnect with an HTTP
    error; that exception escaped the loop. Now any failure is retried."""
    from websockets.http11 import Response

    rejected = {"n": 0}

    async def process_request(connection, request):
        if rejected["n"] < 1:
            rejected["n"] += 1
            return Response(429, "Too Many Requests", websockets.Headers(), b"slow down")
        return None

    async def handler(ws):
        async for msg in ws:
            m = json.loads(msg)
            if m.get("method") == "logsSubscribe":
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": 1}))

    async def drain(feed):
        async for _ in feed.events():
            pass

    async def run():
        server = await websockets.serve(handler, "127.0.0.1", 0, process_request=process_request)
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        portal = PumpPortalFeed(url, stale_s=0.3, backoff_s=0.05)
        task = asyncio.create_task(drain(portal))
        await asyncio.sleep(0.6)
        task.cancel()
        server.close()
        await server.wait_closed()
        return portal.stats

    st = asyncio.run(run())
    assert rejected["n"] == 1 and st["connects"] >= 1  # rejected once, then connected
    assert st["stale_reconnects"] >= 1  # and kept cycling afterwards: the loop never died


def test_api_routes_under_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv("PH_RUN_RECORDER", "0")
    monkeypatch.setenv("PH_REDIS_URL", "")
    monkeypatch.setenv("PH_STATIC_DIR", str(tmp_path))
    monkeypatch.setenv("PH_DATA_DIR", str(tmp_path))
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
        # exports and the data-volume listing
        api_mod.store.add_migration({"mint": "M1", "pool": "P1", "ts": 1.0, "slot": 2, "signature": "s"})
        api_mod.store.mark_harvested(
            "M1",
            {
                "mint": "M1",
                "pool": "P1",
                "t0": 1,
                "no_data": False,
                "cells": {"d30_h60": {"net": 0.1, "gross": 0.14, "mdd": -0.2, "exit_stale_s": 30}},
            },
        )
        mig = c.get("/api/export/migrations.jsonl")
        assert mig.headers["content-type"].startswith("application/x-ndjson") and '"mint":"M1"' in mig.text
        assert '"net":0.1' in c.get("/api/export/survivor.jsonl").text
        csv_text = c.get("/api/export/survivor.csv").text.splitlines()
        assert csv_text[0].startswith("mint,pool,t0,") and "d30_h60_net" in csv_text[0]
        assert csv_text[1].startswith("M1,P1,1,") and ",0.1,0.14,-0.2,30" in csv_text[1]
        files = c.get("/api/files").json()
        assert files["dir"] == str(tmp_path) and {f["name"] for f in files["files"]} == {"index.html"}
