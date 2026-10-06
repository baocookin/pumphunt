"""PumpSwap decoding and fill simulation, checked against real mainnet swaps (tests/fixtures/pumpswap)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.fills import (
    LAMPORTS,
    PoolState,
    apply_swap,
    buy,
    compute_fills,
    curve_buy,
    flow_features,
    sell,
    sell_ex,
    simulate_cell,
    state_at,
)
from app.pumpswap import DISCRIMINATORS, Swap, event_discriminator, swaps_from_tx
from app.swaps import chain_breaks, quote_gaps

FIX = Path(__file__).parent / "fixtures" / "pumpswap"
CHAIN = Path(__file__).parent / "fixtures" / "pumpswap_chain"  # consecutive swaps of one pool


def _load():
    out = {}
    for p in sorted(FIX.glob("*.json")):
        tx = json.loads(p.read_text())
        for s in swaps_from_tx(tx, signature=p.stem):
            out[(s.slot, s.side, s.user, s.base_amount)] = s  # the same swap appears in several fixtures
    return sorted(out.values(), key=lambda s: s.slot)


def test_discriminators_follow_anchor_convention():
    assert event_discriminator("BuyEvent") == bytes([103, 244, 82, 31, 44, 245, 119, 119])
    assert DISCRIMINATORS[bytes([62, 47, 55, 10, 165, 3, 220, 42])] == "sell"


def test_real_swaps_decode_and_the_curve_reproduces_them_to_the_lamport():
    swaps = _load()
    assert [s.side for s in swaps] == ["buy", "sell", "buy", "sell"]
    pool = swaps[0].pool
    assert all(s.pool == pool and s.virtual_quote == 17_584_505_288 for s in swaps)
    for s in swaps:
        st = PoolState(
            s.base_pre, s.quote_pre, s.virtual_quote, s.lp_bps, s.protocol_bps, s.creator_bps, s.ts
        )
        if s.side == "buy":
            tokens, new = curve_buy(st, s.quote_amount)  # the exact curve input the user's tx put in
            assert tokens == s.base_amount
            assert new.base == s.base_post and new.quote == s.quote_post
            # the user's total payment splits back into exactly that curve input plus fees
            tokens_b, _, fees = buy(st, s.user_quote)
            assert tokens_b == s.base_amount and fees == s.user_quote - s.quote_amount
        else:
            got, new, _ = sell(st, s.base_amount)
            assert got == s.user_quote  # what the user really received, fees rounded up per component
            assert new.base == s.base_post and new.quote == s.quote_post
    # where two fixture swaps are consecutive on chain (same base reserve handed over), the state
    # after the first is exactly the state before the second: the LP fee stays in the pool
    chained = [(a, b) for a, b in zip(swaps, swaps[1:], strict=False) if a.base_post == b.base_pre]
    assert len(chained) >= 2
    for a, b in chained:
        assert a.quote_post == b.quote_pre


@pytest.mark.parametrize("kind", ["buy", "buy_exact_quote_in", "buy_exact_quote_in_v2", "sell"])
def test_every_buy_instruction_chains_into_the_next_swap(kind):
    """Each fixture holds a swap and the pool's next swap on chain. The exact-in buys report
    their amounts in permuted fields and v2 keeps most fees in the vault; decoded right, the
    first swap's post-state is the second one's pre-state, with or without token balances."""
    fx = json.loads((CHAIN / f"{kind}.json").read_text())
    pool = fx["pool"]
    (a,), (b,) = (swaps_from_tx(tx, pool=pool) for tx in fx["txs"])
    assert a.ix_name == ("" if kind == "sell" else kind) and a.side == kind.split("_")[0]
    assert (a.base_post, a.quote_post) == (b.base_pre, b.quote_pre)
    stripped = [
        dict(tx, meta={k: v for k, v in tx["meta"].items() if "TokenBalances" not in k}) for tx in fx["txs"]
    ]
    (ra,) = swaps_from_tx(stripped[0], pool=pool)
    assert ra.quote_post == b.quote_pre  # the per-instruction rule agrees with the vault's balance
    pre = PoolState(a.base_pre, a.quote_pre, a.virtual_quote, a.lp_bps, a.protocol_bps, a.creator_bps, a.ts)
    after = apply_swap(pre, a)
    assert (after.base, after.quote) == (b.base_pre, b.quote_pre)
    if a.side == "buy":
        exact_in = kind.startswith("buy_exact_quote_in")
        tokens, _ = curve_buy(pre, a.quote_amount - exact_in)
        assert tokens == a.base_amount
        assert a.user_quote == a.quote_amount + pre.fees_on(a.quote_amount)[0]
    else:
        got, _, _ = sell(pre, a.base_amount)
        assert got == a.user_quote


def test_state_at_and_simulated_round_trip():
    swaps = _load()
    first, last = swaps[0], swaps[-1]
    assert state_at([], 0) is None
    before = state_at(swaps, first.ts - 1)
    assert (before.base, before.quote) == (first.base_pre, first.quote_pre)
    after = state_at(swaps, last.ts + 5)
    assert (after.base, after.quote) == (last.base_post, last.quote_post)
    # buy 1 SOL just before the first swap, sell right after the last one
    cell = simulate_cell(swaps, first.ts - 10, last.ts, LAMPORTS, 1_000_000, latency_s=3)
    assert cell is not None and -1 < cell["net"] < 1 and cell["mdd"] <= cell["net"] + 1e-12
    assert 0 < cell["impact_in"] < 0.2 and cell["liquidity_in_sol"] > 17
    assert cell["fees_sol"] > 0.012  # 1.25% in and out plus two tx fees


def test_compute_fills_grid_blanks_the_future():
    swaps = _load()
    t0 = swaps[0].ts - 60
    grid = compute_fills(swaps, t0, [0, 5], [1, 60], [0.5, 1], now=t0 + 10 * 60)
    assert set(grid) == {"d0_h1", "d0_h60", "d5_h1", "d5_h60"}
    assert grid["d0_h60"] is None and grid["d5_h60"] is None  # not observable yet
    assert set(grid["d0_h1"]) == {"0.5", "1"} and grid["d0_h1"]["1"]["net"] < 0  # fees alone lose money
    assert set(compute_fills(swaps, t0, [0], [1], [1.0, 5.0])["d0_h1"]) == {"1", "5"}  # floats -> short keys
    # a bigger order takes more of the pool: more impact, worse net
    assert grid["d0_h1"]["1"]["impact_in"] > grid["d0_h1"]["0.5"]["impact_in"]
    assert grid["d0_h1"]["1"]["net"] < grid["d0_h1"]["0.5"]["net"]


def test_swap_post_state_properties():
    s = Swap(
        1,
        1,
        "s",
        "sell",
        "P",
        "U",
        base_pre=100,
        quote_pre=50,
        virtual_quote=10,
        base_amount=10,
        quote_amount=5,
        lp_fee=1,
        lp_bps=2,
        protocol_bps=93,
        creator_bps=30,
    )
    assert s.base_post == 110 and s.quote_post == 46 and s.fee_bps == 125


def _state(s):
    return PoolState(s.base_pre, s.quote_pre, s.virtual_quote, s.lp_bps, s.protocol_bps, s.creator_bps, s.ts)


def test_reexecuting_each_real_swap_on_its_real_pre_state_gives_its_real_post_state():
    for s in _load():
        st = apply_swap(_state(s), s)
        assert (st.base, st.quote, st.virtual, st.ts) == (s.base_post, s.quote_post, s.virtual_quote, s.ts)


def test_sell_never_pays_more_than_the_real_vault():
    # a boosted pool drained of real SOL: 0.29 SOL real, 17.58 SOL virtual (seen on mainnet at T+60m)
    st = PoolState(993_455_871_563_402, 293_700_000, 17_584_000_000, 2, 93, 30, 0)
    recv, new, fees, capped = sell_ex(st, st.base // 20)
    assert capped and recv + fees == st.quote and new.quote == st.fees_on(st.quote)[1]
    small = sell_ex(st, st.base // 100_000)
    assert small[3] is False and small[0] > 0
    # negative virtual reserves (allowed since 2026-09-30) lower the price but never below zero
    neg = PoolState(10**15, 5 * LAMPORTS, -2 * LAMPORTS, 2, 93, 30, 0)
    assert neg.effective == 3 * LAMPORTS and sell(neg, 10**13)[0] < sell(replace(neg, virtual=0), 10**13)[0]


def mk(state, side, amount, ts, slot, user="U", creator="CREATOR"):
    """A swap executed on `state`, recorded exactly as the chain would report it."""
    if side == "buy":
        tokens, new = curve_buy(state, amount)
        base_amt, quote_amt = tokens, amount
    else:
        recv, new, fees, _ = sell_ex(state, amount)
        base_amt, quote_amt = amount, recv + fees
    sw = Swap(
        ts,
        slot,
        f"s{slot}",
        side,
        "P",
        user,
        state.base,
        state.quote,
        state.virtual,
        base_amt,
        quote_amt,
        state.fees_on(quote_amt)[1],
        state.lp_bps,
        state.protocol_bps,
        state.creator_bps,
        coin_creator=creator,
    )
    assert (sw.base_post, sw.quote_post) == (new.base, new.quote)
    return sw, replace(new, ts=ts)


def test_models_bracket_each_other_when_a_holder_dumps_after_our_entry():
    s0 = PoolState(10**15, 5 * LAMPORTS, 13 * LAMPORTS, 2, 93, 30, 0)
    a, s1 = mk(s0, "buy", LAMPORTS // 100, ts=100, slot=1)
    b, _ = mk(s1, "sell", 10**14, ts=400, slot=2, user="HOLDER")  # dumps 10% of the pool's tokens
    swaps = [a, b]
    cell = simulate_cell(swaps, 200, 500, LAMPORTS, 0, 3, replay_swaps=swaps)
    assert cell["model"] == "replay" and cell["replayed_swaps"] == 1
    # ghost forgets our SOL, persist ignores that the dump executed against our bid, replay is between
    assert cell["net_ghost"] < cell["net_replay"] < cell["net_persist"] and cell["net"] == cell["net_replay"]
    assert cell["real_in_sol"] > 5 and cell["virtual_in_sol"] == 13 and cell["last_trade_age_in_s"] == 103
    plain = simulate_cell(swaps, 200, 500, LAMPORTS, 0, 3)
    assert plain["model"] == "ghost" and plain["net"] == plain["net_ghost"] == cell["net_ghost"]


def test_with_nobody_else_trading_replay_and_persist_cost_only_fees():
    s0 = PoolState(10**15, 50 * LAMPORTS, 0, 20, 5, 5, 0)
    a, _ = mk(s0, "buy", LAMPORTS // 10, ts=100, slot=1)
    cell = simulate_cell([a], 200, 800, LAMPORTS, 0, 3, replay_swaps=[a])
    assert abs(cell["net_replay"] - cell["net_persist"]) < 1e-9 and -0.01 < cell["net_replay"] < 0
    assert cell["net_ghost"] < cell["net_replay"] - 0.02  # ghost charges the impact twice
    assert cell["exit_capped"] is False and cell["replayed_swaps"] == 0


def test_replay_runs_only_where_the_window_is_complete():
    s0 = PoolState(10**15, 50 * LAMPORTS, 0, 20, 5, 5, 0)
    a, s1 = mk(s0, "buy", LAMPORTS // 10, ts=60, slot=1)
    b, _ = mk(s1, "sell", 10**12, ts=400, slot=2)
    grid = compute_fills([a, b], 0, [0, 5], [5], [1], latency_s=3, replay_swaps=[a, b], replay_range=(0, 320))
    assert grid["d0_h5"]["1"]["model"] == "replay"  # [3, 303] inside [0, 320]
    assert grid["d5_h5"]["1"]["model"] == "ghost"  # exit at 603 is past the window


def test_replay_carries_vault_moves_made_outside_any_swap():
    """Fees swept out of the vault between two swaps leave the real pool poorer; the
    counterfactual pool loses the same SOL. A position too small to matter must then end where
    the real pool ended."""
    s0 = PoolState(10**15, 50 * LAMPORTS, 0, 20, 5, 5, 0)
    a, s1 = mk(s0, "buy", LAMPORTS, ts=100, slot=1)
    swept = replace(s1, quote=s1.quote - LAMPORTS // 2)  # 0.5 SOL leaves without a swap
    b, s2 = mk(swept, "sell", 10**13, ts=400, slot=2)
    c, s3 = mk(s2, "buy", LAMPORTS // 4, ts=450, slot=3)
    assert chain_breaks([a, b, c]) == 0 and quote_gaps([a, b, c]) == (1, -(LAMPORTS // 2))
    # a 0.001-SOL position barely moves a 50-SOL pool: replayed, it must sell into (almost) the
    # real final state, as ghost and persist do. Without the sweep the replayed vault would hold
    # 0.5 SOL more than the real one and pay ~1% more.
    small = simulate_cell([a, b, c], 0, 600, LAMPORTS // 1000, 0, 3, replay_swaps=[a, b, c])
    assert small["replayed_swaps"] == 3
    assert abs(small["net_replay"] - small["net_ghost"]) < 1e-4
    assert abs(small["net_replay"] - small["net_persist"]) < 1e-4
    big = simulate_cell([a, b, c], 0, 600, LAMPORTS, 0, 3, replay_swaps=[a, b, c])
    # with the sweep carried, replay stays between the bounds
    assert big["net_ghost"] <= big["net_replay"] <= big["net_persist"] + 1e-9


def test_flow_features_count_the_minutes_before_entry():
    s0 = PoolState(10**15, 50 * LAMPORTS, 0, 20, 5, 5, 0)
    a, s1 = mk(s0, "buy", 2 * LAMPORTS, ts=1010, slot=1, user="B1")
    b, s2 = mk(s1, "sell", 10**13, ts=1100, slot=2, user="CREATOR")
    c, _ = mk(s2, "sell", 10**12, ts=1250, slot=3, user="S2")
    f = flow_features([a, b, c], t_end=1300, span_s=300)
    assert (f["swaps"], f["buys"], f["sells"], f["traders"], f["buyers"]) == (3, 1, 2, 3, 1)
    assert f["creator"] == "CREATOR" and f["creator_sell_sol"] > 0 and f["top_seller_share"] > 0.9
    assert abs(f["net_sol"] - (f["buy_sol"] - f["sell_sol"])) < 1e-12 and f["last_trade_age_s"] == 50
    assert (
        flow_features([a, b, c], t_end=900)["swaps"] == 0 and flow_features([], 5)["last_trade_age_s"] is None
    )
