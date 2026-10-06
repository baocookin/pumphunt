"""PumpSwap decoding and fill simulation, checked against real mainnet swaps (tests/fixtures/pumpswap)."""

import json
from pathlib import Path

from app.fills import LAMPORTS, PoolState, buy, compute_fills, curve_buy, sell, simulate_cell, state_at
from app.pumpswap import DISCRIMINATORS, Swap, event_discriminator, swaps_from_tx

FIX = Path(__file__).parent / "fixtures" / "pumpswap"


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
