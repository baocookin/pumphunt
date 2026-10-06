"""Sniper sample (hypothesis S): census, sampling, curve paths, ticket simulation, summary."""

import asyncio
import json
import random
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fakehistory import HistoryRpc, curve_tx, event_bytes
from helpers import fake_pubkey

from app import anchor
from app.jsonl import read_jsonl
from app.sniper import (
    CELLS,
    EXITS,
    LAMPORTS,
    MIN_N,
    PREREG_S_TS,
    PRIMARY_CELL,
    SIM_VERSION,
    CurvePath,
    SniperRecorder,
    cell_name,
    create_of,
    curve_trades,
    launch_info,
    sampled,
    simulate,
    simulate_row,
    summarize,
    verdict,
)
from app.store import MemoryStore

FIX = Path(__file__).parent / "fixtures" / "sniper_launch.json"
V0, T0 = 30 * LAMPORTS, 1_073_000_000 * 10**6
K = V0 * T0
F = 0.0125
SOL = "11111111111111111111111111111111"
DEV, A, B, C = (fake_pubkey(n) for n in (21, 22, 23, 24))


def run(coro):
    return asyncio.run(coro)


def state(real_sol: float) -> tuple[float, float]:
    vs = V0 + real_sol * LAMPORTS
    return vs, K / vs


def path_row(steps, complete_slot=None, span_s=7_200, truncated=False, s0=100, t0=1_000_000):
    """A launch whose curve moves to the given real-SOL levels: (dslot, dts, user, real_sol)."""
    trades = []
    prev_vt = T0
    for i, (dslot, dts, user, real) in enumerate(steps):
        vs, vt = state(real)
        buy = vt < prev_vt
        trades.append([s0 + dslot, i, 0, t0 + dts, user, buy, 0, int(abs(prev_vt - vt)), vs, vt, "buy"])
        prev_vt = vt
    last = trades[-1] if trades else [s0, 0, 0, t0]
    return {
        "status": "ok",
        "mint": "M",
        "signature": "S",
        "dev": DEV,
        "create_slot": s0,
        "create_ts": t0,
        "v_sol0": V0,
        "v_tokens0": T0,
        "mayhem": False,
        "trades": trades,
        "complete": {"slot": s0 + complete_slot, "tx": 0, "ts": t0} if complete_slot is not None else None,
        "fee_bps": 125,
        "chain_breaks": 0,
        "window": {"span_s": span_s, "truncated": truncated, "last_slot": last[0], "last_ts": last[3]},
    }


def ticket_value(real_in: float, real_now: float, size: float = 0.5) -> float:
    """Closed form: SOL back for a ticket bought at real_in, sold when the real curve is at real_now."""
    vs, vt = state(real_in)
    n = size * LAMPORTS / (1 + F)
    dt = vt * n / (vs + n)
    vs2, vt2 = state(real_now)
    return (1 - F) * vs2 * dt / (vt2 - dt) / LAMPORTS


def net(real_in, real_now, size=0.5, cost=0.002):
    return (ticket_value(real_in, real_now, size) - cost) / size - 1


# ---- sampling ----
def test_sample_is_a_hash_of_the_signature_at_the_configured_rate():
    rng = random.Random(7)
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    sigs = ["".join(rng.choice(alphabet) for _ in range(88)) for _ in range(2_000)]
    sigs += [f"sig{i}" for i in range(40_000)]
    picked = [s for s in sigs if sampled(s, 200)]
    assert 0.017 < len(picked) / len(sigs) < 0.023
    assert [s for s in sigs if sampled(s, 200)] == picked  # deterministic
    assert not any(sampled(s, 0) for s in sigs[:1000]) and all(sampled(s, 10_000) for s in sigs[:1000])


# ---- the ticket's value ----
def test_a_round_trip_at_one_state_loses_both_fees_and_the_first_buyer_gets_its_sol_back():
    row = path_row([(0, 0, DEV, 1.0), (5, 3, A, 6.0), (9, 8, A, 1.0)])
    p = CurvePath(row)
    r = simulate(p, 2, "hold", fixed_cost=0)
    # bought behind the dev at 1 SOL; the curve ends back at 1 SOL: only the two fees are lost
    assert r["why"] == "end" and r["net"] == pytest.approx((1 - F) / (1 + F) - 1, abs=1e-9)
    assert r["peak"] == pytest.approx(ticket_value(1.0, 6.0) / 0.5, rel=1e-9)
    # the same ticket is worth less if the dev also sells out (it bought above the curve's floor)
    row = path_row([(0, 0, DEV, 1.0), (5, 3, DEV, 0.0)])
    assert simulate(CurvePath(row), 2, "hold")["net"] == pytest.approx(net(1.0, 0.0), abs=1e-9)
    assert net(1.0, 0.0) < (1 - F) / (1 + F) - 1 - 0.004


def test_take_profit_sells_at_the_end_of_the_next_slot():
    # entry at the end of slot +2 (real 1 SOL); a buy to 20 SOL at slot +10 triggers 2x, and a
    # sell in slot +11 lands before ours: the sale happens at 15 SOL, not at the trigger
    row = path_row([(0, 0, DEV, 1.0), (10, 3, A, 20.0), (11, 3, B, 15.0), (12, 4, B, 30.0)])
    r = simulate(CurvePath(row), 2, "tp2")
    assert ticket_value(1.0, 20.0) >= 2 * 0.5 and r["why"] == "tp"
    assert r["net"] == pytest.approx(net(1.0, 15.0), abs=1e-9)
    # with no exit latency it sells at the trigger's state
    r0 = simulate(CurvePath(row), 2, "tp2", exit_latency=0)
    assert r0["net"] == pytest.approx(net(1.0, 20.0), abs=1e-9)


def test_stop_loss_and_time_stop():
    # A ticket can lose at most its premium over the launch price (the curve cannot fall below its
    # first state), so a 0.5x stop needs an entry well above it: here at 4x (real 30 SOL).
    row = path_row([(0, 0, DEV, 5.0), (3, 1, A, 30.0), (20, 5, DEV, 2.0), (30, 20, A, 8.0)])
    r = simulate(CurvePath(row), 4, "p")
    assert ticket_value(30.0, 2.0) < 0.25 and ticket_value(30.0, 0.0) > 0.12
    assert r["why"] == "sl" and r["net"] == pytest.approx(net(30.0, 2.0), abs=1e-9)
    # a pure 10 s time stop sells at the last state at or before entry + 10 s (real 2 SOL)
    r = simulate(CurvePath(row), 4, "t10")
    assert r["why"] == "time" and r["net"] == pytest.approx(net(30.0, 2.0), abs=1e-9)
    r = simulate(CurvePath(row), 4, "t30")  # quiet after 20 s: sold at the curve's last state
    assert r["why"] == "time" and r["net"] == pytest.approx(net(30.0, 8.0), abs=1e-9)
    assert simulate(CurvePath(row), 4, "t30")["peak"] == pytest.approx((1 - F) / (1 + F), rel=1e-9)


def test_graduation_and_completion_before_entry():
    steps = [(0, 0, DEV, 2.0), (6, 2, A, 40.0), (8, 3, B, 85.005)]
    row = path_row(steps, complete_slot=8)
    r = simulate(CurvePath(row), 2, "hold")
    assert r["why"] == "grad" and r["net"] == pytest.approx(net(2.0, 85.005), abs=1e-9)
    assert 12 < r["net"] < 13.5  # ~13x from just behind a 2-SOL dev buy, before fees
    assert simulate(CurvePath(row), 8, "hold") is None  # the curve completed in the entry slot
    assert simulate(CurvePath(row), 2, "tp10")["why"] == "tp"


def test_a_truncated_read_leaves_late_exits_unresolved():
    row = path_row([(0, 0, DEV, 1.0), (5, 2, A, 3.0), (400, 100, A, 2.0)], truncated=True)
    p = CurvePath(row)
    assert simulate(p, 2, "t30")["why"] == "time"  # 30 s after entry is inside what was read
    held = simulate(p, 2, "hold")
    assert held["net"] is None and held["why"] == "unresolved"
    row = path_row([(0, 0, DEV, 1.0), (5, 2, A, 30.0)], truncated=True)
    assert simulate(CurvePath(row), 2, "tp2")["why"] == "unresolved"  # its sale slot was not read


def test_an_empty_curve_costs_the_fees():
    row = path_row([])
    r = simulate(CurvePath(row), 0, "p")
    assert r["why"] == "time" and r["net"] == pytest.approx((1 - F) / (1 + F) - 1 - 0.004, abs=1e-9)


# ---- a real launch (mainnet, 06/10/2026, fetched from a public RPC) ----
def _real_row():
    d = json.loads(FIX.read_text())
    txs = d["txs"]
    tx = next(t for t in txs if create_of(t))
    row = launch_info(create_of(tx), tx, d["create_signature"])
    row.update(curve_trades(txs, row["mint"]))
    last = txs[-1]
    row["window"] = {
        "span_s": 7_200,
        "tx": len(txs),
        "truncated": False,
        "last_slot": last["slot"],
        "last_ts": last["blockTime"],
    }
    row["status"] = "ok"
    return row


def test_real_launch_reads_in_chain_order():
    row = _real_row()
    assert row["quote_mint"] == SOL and not row["mayhem"] and row["v_sol0"] == V0 and row["v_tokens0"] == T0
    assert len(row["trades"]) == 12 and row["chain_breaks"] == 0 and row["fee_bps"] == 125
    assert row["complete"] is None
    first = row["trades"][0]
    # a bot bought 4.15 SOL one slot after the create and sold it all six slots later
    assert first[0] - row["create_slot"] == 1 and first[5] and first[6] == 4_148_148_147
    sold = row["trades"][1]
    assert sold[4] == first[4] and not sold[5] and sold[7] == first[7]


def test_real_launch_simulation():
    row = _real_row()
    res = simulate_row(row)
    nets = dict(zip(CELLS, res["nets"], strict=True))
    assert len(res["whys"]) == len(CELLS) and res["sim_version"] == SIM_VERSION
    # ahead of the bot (end of the create slot): the curve ends empty, the ticket keeps its SOL
    assert nets[cell_name(0, "hold")] == pytest.approx((1 - F) / (1 + F) - 1 - 0.004, abs=1e-5)
    # behind it: bought at 1.30x the launch price, the bot dumps: -25% after a minute
    assert nets[PRIMARY_CELL] == pytest.approx(-0.2526, abs=1e-4)
    assert res["entry"]["buyers"] == 1 and res["entry"]["dev_buy_sol"] == 0
    assert res["entry"]["price_x"] == pytest.approx(1.2957, abs=1e-4)


# ---- summary and verdict ----
def _sigs(per_10k, n, lo=0):
    """n signatures inside the census sample `per_10k` and outside the one at `lo`."""
    out, i = [], 0
    while len(out) < n:
        sig = f"sig{i}"
        if sampled(sig, per_10k) and not (lo and sampled(sig, lo)):
            out.append(sig)
        i += 1
    return out


S2 = _sigs(200, MIN_N + 5)  # in S's registered 2%


def _res(mint, t0, primary, k1=None, k4=None, mayhem=False, signature=None):
    nets = [None] * len(CELLS)
    idx = {n: i for i, n in enumerate(CELLS)}
    nets[idx[PRIMARY_CELL]] = primary
    nets[idx[cell_name(1, "p")]] = primary if k1 is None else k1
    nets[idx[cell_name(4, "p")]] = primary if k4 is None else k4
    whys = "".join("x" if v is not None else "-" for v in nets)
    sig = signature or S2[0]
    return {
        "mint": mint,
        "signature": sig,
        "t0": t0,
        "mayhem": mayhem,
        "sim_version": SIM_VERSION,
        "nets": nets,
        "whys": whys,
    }


def test_verdict_rules():
    base = {"n": MIN_N, "top1pct_share": 0.1}
    assert verdict({"n": 10}, [1, 1]) == "WAIT"
    assert verdict({**base, "mean_ci95": [-0.05, -0.01]}, [1, 1]) == "KILL"
    assert verdict({**base, "mean_ci95": [0.01, 0.05]}, [0.02, 0.01]) == "PASS"
    assert verdict({**base, "mean_ci95": [0.01, 0.05]}, [0.02, -0.01]) == "INCONCLUSIVE"  # not robust
    assert verdict({**base, "mean_ci95": [-0.01, 0.05]}, [1, 1]) == "INCONCLUSIVE"
    assert verdict({**base, "mean_ci95": [0.01, 0.05], "top1pct_share": 0.6}, [1, 1]) == "KILL"


def test_summary_counts_each_launch_once_and_splits_the_samples():
    rows = [_res(f"m{i}", PREREG_S_TS + i, -0.1 if i % 2 else 0.05, signature=S2[i]) for i in range(MIN_N)]
    rows += [_res("old", PREREG_S_TS - 10, 5.0), _res("may", PREREG_S_TS + 5, 1.0, mayhem=True)]
    rows += [_res("m0", PREREG_S_TS, 0.05, signature=S2[0])]  # read twice: counted once
    rows += [dict(_res("v0", PREREG_S_TS, 9.0), sim_version=SIM_VERSION - 1)]  # stale simulation
    wider = _sigs(500, 3, lo=200)  # in the 5% census, outside S's registered 2%
    rows += [_res(f"w{i}", PREREG_S_TS + 9, 7.0, signature=sig) for i, sig in enumerate(wider)]
    out = summarize(rows)
    pr = out["prereg"]
    assert out["classic"] == MIN_N + 4 and out["mayhem"] == 1
    assert pr["n"] == MIN_N and pr["mean"] == pytest.approx(-0.025) and pr["verdict"] == "KILL"
    assert out["cells"]["classic"][PRIMARY_CELL]["n"] == MIN_N + 4  # the whole census, exploratory
    assert out["cells"]["mayhem"][PRIMARY_CELL]["n"] == 1
    assert set(pr["robust"]) == {cell_name(1, "p"), cell_name(4, "p")}
    assert set(out["grid"]["exits"]) == set(EXITS)


# ---- census and harvest ----
class FakeRpc(HistoryRpc):
    """The mint authority's signatures (newest first), create transactions, curve histories."""

    def __init__(self, sigs, creates, curves):
        super().__init__(curves)
        self.sigs = sigs
        self.creates = creates
        self.sig_calls = []
        self.fail = set()

    async def get_signatures(self, address, limit=1000, before=None, until=None):
        self.sig_calls.append((before, until))
        names = [s["signature"] for s in self.sigs]
        start = names.index(before) + 1 if before else 0
        end = names.index(until) if until in names else len(names)
        return self.sigs[start:end][:limit]

    async def get_transaction(self, sig):
        if sig in self.fail:
            raise httpx.ConnectError("down")
        return self.creates.get(sig)


def create_tx_for(mint, curve, slot, ts, quote=SOL, mayhem=False, dev_buy=1.0):
    vals = {name: 0 for name, _ in anchor.CREATE}
    vals.update(name="T", symbol="T", uri="u", mint=mint, bonding_curve=curve, user=DEV, creator=DEV)
    vals.update(timestamp=ts, token_program=SOL, quote_mint=quote, is_mayhem_mode=mayhem)
    vals.update(is_cashback_enabled=False, is_holder_reward=False)
    vals.update(virtual_sol_reserves=V0, virtual_token_reserves=T0, token_total_supply=10**15)
    evs = [event_bytes("create", anchor.CREATE, vals)]
    if dev_buy:
        evs.append(trade_ev(mint, DEV, True, ts, 0.0, dev_buy))
    return curve_tx(slot, ts, evs, idx=3, curve=curve)


def trade_ev(mint, user, buy, ts, real_before, real_after):
    vs0, vt0 = state(real_before)
    vs, vt = state(real_after)
    vals = {name: 0 for name, _ in anchor.TRADE}
    vals.update(mint=mint, sol_amount=int(abs(vs - vs0)), token_amount=int(abs(vt0 - vt)), is_buy=buy)
    vals.update(user=user, timestamp=ts, virtual_sol_reserves=int(vs), virtual_token_reserves=int(vt))
    vals.update(fee_recipient=SOL, creator=DEV, track_volume=False, ix_name="buy" if buy else "sell")
    vals.update(fee_basis_points=95, creator_fee_basis_points=30, mayhem_mode=False)
    return event_bytes("trade", anchor.TRADE, vals)


def _cfg(tmp_path, **kw):
    base = dict(
        sniper_sample_per_10k=10_000,
        sniper_window_s=7_200,
        sniper_delay_s=300,
        sniper_max_tx=5_000,
        sniper_daily_credits=20_000,
        sniper_census_max_pages=30,
        sniper_batch=20,
        data_dir=str(tmp_path),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_census_queues_sampled_launches_and_resumes_from_its_cursor(tmp_path):
    store = MemoryStore()
    sigs = [{"signature": f"s{i}", "slot": 1000 - i, "blockTime": 5000 - i, "err": None} for i in range(2500)]
    sigs[3]["err"] = {"x": 1}  # a failed create is not a launch
    rpc = FakeRpc(sigs[1500:], {}, {})
    sn = SniperRecorder(_cfg(tmp_path), store, rpc, tmp_path)
    assert run(sn.census_once(now=6000)) == 1000  # first poll: newest page only, no backfill
    assert store.get_kv("sniper:cursor") == "s1500" and store.get_kv("sniper_credits:1970-01-01") == "1"
    rpc.sigs = sigs  # 1,500 newer launches arrived: two pages back to the cursor
    assert run(sn.census_once(now=6000)) == 1499
    assert store.get_kv("sniper:cursor") == "s0" and sn.stats["census_gaps"] == 0
    assert store.queue_len("snipe") == 2499
    due = dict(store.take_due("snipe", 1e12, 5000))
    assert due["s0|1000|5000"] == 5000 + 7_200 + 300
    assert sum(store.counters("creates_census", ["1970-01-01T00", "1970-01-01T01"]).values()) == 2499


def test_census_gap_after_a_long_outage(tmp_path):
    store = MemoryStore()
    store.set_kv("sniper:cursor", "gone")  # older than anything still listed
    sigs = [{"signature": f"s{i}", "slot": 1, "blockTime": 100, "err": None} for i in range(3000)]
    sn = SniperRecorder(_cfg(tmp_path, sniper_census_max_pages=2), store, FakeRpc(sigs, {}, {}), tmp_path)
    run(sn.census_once(now=200))
    assert sn.stats["census_gaps"] == 1 and store.get_kv("sniper:cursor") == "s0"


def test_harvest_reads_the_create_and_the_curve_then_simulates(tmp_path):
    store = MemoryStore()
    mint, curve, mint2, curve2 = (fake_pubkey(n) for n in (31, 32, 33, 34))
    t = 10_000
    c_tx = create_tx_for(mint, curve, 500, t)
    curve_txs = [
        c_tx,
        curve_tx(503, t + 1, [trade_ev(mint, A, True, t + 1, 1.0, 9.0)], idx=7, curve=curve),
        curve_tx(510, t + 4, [trade_ev(mint, A, False, t + 4, 9.0, 1.0)], idx=2, curve=curve),
    ]
    usdc = create_tx_for(mint2, curve2, 600, t, quote=fake_pubkey(99))
    rpc = FakeRpc([], {"c1": c_tx, "c2": usdc}, {curve: curve_txs})
    cfg = _cfg(tmp_path)
    sn = SniperRecorder(cfg, store, rpc, tmp_path)
    for sig in ("c1", "c2"):
        store.schedule("snipe", f"{sig}|500|{t}", t + 7_500)
    store.schedule("snipe", f"later|1|{t + 99}", t + 99 + 7_500)
    assert run(sn.harvest_once(now=t + 7_500)) == 2 and store.queue_len("snipe") == 1
    rows = list(read_jsonl(tmp_path / "sniper-1970-01-01.jsonl"))
    by = {r["signature"]: r for r in rows}
    assert by["c2"]["status"] == "not_sol" and "trades" not in by["c2"] and sn.stats["not_sol"] == 1
    r = by["c1"]
    assert r["status"] == "ok" and r["mint"] == mint and r["curve"] == curve
    assert len(r["trades"]) == 3 and r["chain_breaks"] == 0 and r["window"]["tx"] == 3
    assert r["sim"]["version"] == SIM_VERSION and len(r["sim"]["nets"]) == len(CELLS)
    res = store.rows("sniper")
    assert len(res) == 1 and res[0]["mint"] == mint
    nets = dict(zip(CELLS, res[0]["nets"], strict=True))
    # behind the dev at slot 0: ahead of the 8-SOL buyer at slot +3, who sold back to 1 SOL
    assert nets[cell_name(2, "hold")] == pytest.approx(net(1.0, 1.0), abs=1e-5)
    assert nets[cell_name(4, "hold")] == pytest.approx(net(9.0, 1.0), abs=1e-5)
    # credits: 2 create reads + one 10-credit page
    assert store.get_kv("sniper_credits:1970-01-01") == str(1 + 1 + 10)
    assert rpc.calls[0] == (curve, True, "asc", 100)


def test_harvest_retries_on_rpc_errors_and_pauses_at_the_budget(tmp_path):
    store = MemoryStore()
    rpc = FakeRpc([], {}, {})
    rpc.fail.add("bad")
    sn = SniperRecorder(_cfg(tmp_path), store, rpc, tmp_path)
    store.schedule("snipe", "bad|1|100", 200)
    assert run(sn.harvest_once(now=1_000)) == 0 and sn.stats["errors"] == 1
    assert store.take_due("snipe", 1e9, 5) == [("bad|1|100", 1_300.0)]  # back in the queue, 5 min later
    store.set_kv("sniper_credits:1970-01-01", "20000")
    store.schedule("snipe", "x|1|100", 200)
    assert run(sn.harvest_once(now=1_000)) == 0 and sn.stats["paused"] and store.queue_len("snipe") == 1


def test_lottery_touches_combine_the_curve_and_the_pool():
    hold = CELLS.index(cell_name(2, "hold"))

    def r(mint, net_hold, peak, graduated=False):
        nets = [None] * len(CELLS)
        nets[hold] = net_hold
        row = {"mint": mint, "sim_version": SIM_VERSION, "nets": nets, "hold_peak": peak}
        return dict(row, graduated=graduated)

    from app.sniper import lottery

    results = [r("a", -0.9, 1.5), r("b", 12.0, 13.1, True), r("c", 8.0, 9.0, True), r("d", 5.0, 6.0, True)]
    results += [dict(r("e", 1.0, 2.0), mayhem=True), dict(r("f", None, None))]
    survivor = [{"mint": "b", "peak_x": {"24h": 9.0}}, {"mint": "c", "peak_x": {"24h": 0.9}}]
    out = lottery(results, survivor)
    # b: 13x at graduation, its pool then ran 9x: a 117x touch; c touched 9x on the curve; d's pool
    # is not harvested yet; mayhem and ticketless launches are left out
    assert out["tickets"] == 3 and out["graduated_waiting"] == 1
    assert out["n_touch_100x"] == 1 and out["n_touch_10x"] == 1 and out["p_touch_10x"] == pytest.approx(1 / 3)


def test_a_launch_that_cannot_be_read_is_recorded_and_the_batch_goes_on(tmp_path):
    store = MemoryStore()
    mint, curve = fake_pubkey(41), fake_pubkey(42)
    good = create_tx_for(mint, curve, 700, 50_000)
    rpc = FakeRpc([], {"weird": {"slot": 1, "meta": {"err": None}}, "good": good}, {curve: [good]})
    sn = SniperRecorder(_cfg(tmp_path), store, rpc, tmp_path)
    store.schedule("snipe", "weird|1|100", 100)
    store.schedule("snipe", "good|700|50000", 200)
    assert run(sn.harvest_once(now=60_000)) == 2 and sn.stats["errors"] == 1
    rows = {r["signature"]: r for r in read_jsonl(tmp_path / "sniper-1970-01-01.jsonl")}
    assert rows["weird"]["status"] == "error" and "KeyError" in rows["weird"]["error"]
    assert rows["good"]["status"] == "ok" and store.rows("sniper")[0]["mint"] == mint
    assert rows["good"]["credits"] == 11 and sn.stats["gtfa"] is True
