"""Small infrastructure pieces: daily JSONL rotation, pool picking, feed subscription messages, API."""

import json

from app.chain_feed import SolanaLogsFeed
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
        assert c.get("/api/health").json()["ok"] is True
        assert c.get("/api/stats").json()["chain_scope"] == "migrations"
        assert c.get("/api/survivor/summary").json()["verdict"]["status"] == "INSUFFICIENT"
        assert "dash" in c.get("/").text
