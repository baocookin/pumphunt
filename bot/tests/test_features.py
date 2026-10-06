"""Decision-time features: holder snapshots, bonding-curve history, wallet funders."""

import asyncio
import json

import pytest
from fakehistory import (
    B1,
    B2,
    B3,
    CURVE,
    DEV,
    H1,
    H2,
    MINT,
    POOL,
    HistoryRpc,
    HolderRpc,
    create_event,
    curve_tx,
    first_tx,
    trade_event,
)  # fmt: skip
from helpers import fake_pubkey

from app.curve_history import curve_history, pump_events
from app.fills import LAMPORTS, PoolState, sell_ex
from app.funding import features, first_funders, funder_of, pick_wallets
from app.holders import concentration, exit_power, group_share, snapshot
from app.store import MemoryStore
from app.swaps import SwapFetcher


def run(coro):
    return asyncio.run(coro)


# ---- holder snapshots ----
def test_snapshot_groups_accounts_by_owner_and_keeps_the_pool_apart():
    largest = [("vault", 600), ("a1", 150), ("a2", 100), ("a3", 50), ("gone", 7)]
    owners = {"vault": POOL, "a1": H1, "a2": H2, "a3": H1}  # H1 holds two accounts; "gone" was closed
    snap = run(snapshot(HolderRpc(largest, owners, 1000), MINT, POOL))
    assert snap["pool_amount"] == 600 and snap["holders"] == [[H1, 200], [H2, 100]]
    assert snap["unknown_amount"] == 7 and snap["accounts"] == 5 and snap["credits"] == 3
    c = concentration(snap)
    assert c["pool_share"] == 0.6 and c["top1"] == 0.5 and c["top10"] == 0.75 and c["holders_1pct"] == 2
    assert group_share(snap, [H2, H2, "nobody"]) == 0.25
    empty = run(snapshot(HolderRpc([], {}, 0), MINT, POOL))
    assert empty["credits"] == 1 and concentration(empty)["top1"] is None


def test_exit_power_is_what_the_largest_holders_could_pull_out():
    state = PoolState(10**9, 2 * LAMPORTS, 17 * LAMPORTS, 20, 5, 95, 0)
    snap = {"holders": [[H1, 10**9], [H2, 10**8]], "supply": 2 * 10**9, "pool_amount": 9 * 10**8}
    p = exit_power(snap, state)
    got, _, _, capped = sell_ex(state, 11 * 10**8)
    assert capped and abs(p["top10_exit_share"] - got / state.quote) < 1e-12
    assert 0.98 < p["top10_exit_share"] < 1  # capped at the real vault, minus fees
    assert p["top1_exit_share"] <= p["top10_exit_share"] and p["top10_exit_sol"] == got / LAMPORTS
    assert exit_power(snap, None)["top10_exit_share"] is None


# ---- bonding curve history ----
def test_events_logged_and_mirrored_by_cpi_count_once():
    tx = curve_tx(1, 100, [create_event(100), trade_event(DEV, 2, True, 100)])
    evs = pump_events(tx)
    assert sorted(e["kind"] for e in evs) == ["create", "trade"] and all(e["via"] == "cpi" for e in evs)
    logs_only = curve_tx(1, 100, [trade_event(DEV, 2, True, 100)], both=False)
    assert [e["via"] for e in pump_events(logs_only)] == ["log"]


def _bundled_curve(t0=1_000):
    """Created with a 3-SOL dev buy, two wallets in the same slot, one two slots later, then the
    market: 120 more transactions before migration at t0 + 900."""
    txs = [
        curve_tx(50, t0, [create_event(t0), trade_event(DEV, 3, True, t0)], idx=1),
        curve_tx(50, t0, [trade_event(B1, 10, True, t0)], idx=2),
        curve_tx(50, t0, [trade_event(B2, 5, True, t0)], idx=3),
        curve_tx(52, t0 + 1, [trade_event(B3, 1, True, t0 + 1)]),
        curve_tx(53, t0 + 30, [trade_event(DEV, 1.5, False, t0 + 30)]),
    ]
    txs += [
        curve_tx(60 + i, t0 + 61 + i * 5, [trade_event(fake_pubkey(500 + i), 0.5, True, t0 + 61 + i * 5)])
        for i in range(120)
    ]
    return txs


def test_curve_history_reads_how_the_curve_filled():
    t0 = 1_000
    rpc = HistoryRpc({CURVE: _bundled_curve(t0)}, page_cap=100)
    f = SwapFetcher(rpc)
    h = run(curve_history(f, CURVE, MINT, t0 + 900))
    assert h["found"] and h["dev"] == DEV and h["graduate_s"] == 900 and h["create_slot"] == 50
    assert h["dev_buy_sol"] == 3 and h["bundle_buyers"] == 2 and h["bundle_sol"] == 15
    assert h["bundle_wallets"] == sorted([B1, B2]) and h["early_buyers"] == 4 and h["early_sol"] == 19
    assert (
        h["buyers_60s"] == 4
        and h["buy_sol_60s"] == 19
        and h["sell_sol_60s"] == 1.5
        and h["dev_sell_sol"] == 1.5
    )
    assert h["early_wallets"][:3] == [B1, B2, B3] and h["first_minute_complete"] and not h["page_complete"]
    assert h["curve_tx"] == 125 and h["curve_tx_complete"] and h["page_tx"] == 100
    assert h["credits"] == 10 + 10  # one full page, one signature count
    # a curve whose history is not there (or not this mint's) says so
    assert run(curve_history(SwapFetcher(HistoryRpc({})), CURVE, MINT, t0 + 900))["found"] is False


# ---- funders ----
def test_funder_is_the_account_that_paid_most():
    tx = first_tx(H1, DEV, 123)
    assert funder_of(tx, H1) == {"first_ts": 123, "funder": DEV}
    tx["meta"]["postBalances"] = [5 * LAMPORTS, LAMPORTS, 1]  # nobody else lost SOL
    assert funder_of(tx, H1)["funder"] is None


def test_first_funders_are_cached_and_clusters_found():
    t_create = 100_000
    fund_a = fake_pubkey(777)
    txs = {
        DEV: [first_tx(DEV, fund_a, t_create - 3_000)],
        B1: [first_tx(B1, fund_a, t_create - 1_200)],
        B2: [first_tx(B2, fund_a, t_create - 1_100)],
        H1: [first_tx(H1, DEV, t_create - 900)],
        H2: [first_tx(H2, fake_pubkey(778), t_create - 400 * 86_400)],
    }
    rpc = HistoryRpc(txs)
    f = SwapFetcher(rpc)
    store = MemoryStore()
    wallets = pick_wallets(DEV, [B1, B2], [[H1, 300], [H2, 200], [B1, 100]], cap=8)
    assert wallets == [DEV, B1, B2, H1, H2]
    fund, looked = run(first_funders(f, store, wallets, ttl_s=3600))
    assert looked == 5 and fund[H1] == {"first_ts": t_create - 900, "funder": DEV} and f.credits == 50
    again, looked = run(first_funders(f, store, wallets, ttl_s=3600))
    assert looked == 0 and again == fund and f.credits == 50  # all from the cache
    held = {H1: 300, H2: 200, B1: 100}
    fe = features(fund, DEV, t_create, held, outside_supply=1_000)
    assert fe["wallets"] == 5 and fe["fresh_1d"] == 4  # H2 is a year old
    assert fe["max_cluster"] == 3 and fe["cluster_hold_share"] == pytest.approx(
        0.1
    )  # DEV, B1, B2 share fund_a
    # B1 and B2 share the creator's funder, H1 was funded by the creator
    assert fe["dev_linked"] == 3 and fe["dev_group_hold_share"] == pytest.approx(0.4)
    assert fe["funders"][H2] == [t_create - 400 * 86_400, fake_pubkey(778)]
    assert pick_wallets(None, [], [[H1, 1]], cap=0) == []
    assert json.dumps(fe)  # stored in the survivor row as is
