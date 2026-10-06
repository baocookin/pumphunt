"""SwapFetcher: windows, states at decision times, the tokenTransfer filter, the fallback."""

import asyncio
import json
from pathlib import Path

import pytest
from fakechain import MINT, POOL, FakeChain, noise, real_swaps

from app.fills import state_at
from app.pumpswap import swaps_from_tx
from app.rpc import RpcError, gtfa_credits
from app.swaps import SwapFetcher, chain_breaks, encode_swaps, merge_swaps

CHAIN = Path(__file__).parent / "fixtures" / "pumpswap_chain"


def times_of(real):
    return sorted(tx["blockTime"] for tx in real.values())


def run(coro):
    return asyncio.run(coro)


def test_a_quiet_window_is_settled_by_one_page():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()))
    f = SwapFetcher(chain, token_filter=False)
    swaps, st = run(f.window(POOL, ts[0] - 10, ts[-1] + 10, max_tx=1000))
    assert f.gtfa is True and st["method"] == "gtfa" and st["complete"] and st["covered_to"] == ts[-1] + 10
    assert [s.side for s in swaps] == ["buy", "sell", "buy", "sell"] and st["fetched"] == 4
    assert [s.order for s in swaps] == sorted(s.order for s in swaps) and swaps[0].coin_creator
    assert st["credits"] == f.credits == 10 and len(chain.calls) == 1
    assert chain.calls[0]["limit"] == 100 and chain.calls[0]["bt"] == {"gte": ts[0] - 10, "lte": ts[-1] + 10}
    assert chain.tx_calls == []  # no getTransaction round trips


def test_noise_that_fits_is_counted_then_fetched_whole():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()) + noise(300, ts[0] - 5, ts[-1] + 5))
    f = SwapFetcher(chain, token_filter=False)
    swaps, st = run(f.window(POOL, ts[0] - 10, ts[-1] + 10, max_tx=1000))
    assert st["complete"] and st["fetched"] == 304 and len(swaps) == 4
    assert [c["full"] for c in chain.calls] == [True, False, True]  # first page, count, the rest
    assert st["counted"] >= 304 and st["credits"] == 10 + 10 + gtfa_credits(204)


def test_a_window_over_its_cap_stops_after_the_count():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()) + noise(2500, ts[0] - 5, ts[-1] + 5))
    f = SwapFetcher(chain, token_filter=False)
    swaps, st = run(f.window(POOL, ts[0] - 10, ts[-1] + 10, max_tx=1000))
    assert not st["complete"] and st["fetched"] == 100 and st["counted"] > 1000
    assert st["credits"] == 20 and [c["full"] for c in chain.calls] == [True, False]
    first_page_last = chain.txs[99]["blockTime"]
    assert st["covered_to"] == first_page_last - 1  # that second may continue on the next page


def test_the_token_filter_is_used_only_once_verified():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()) + noise(50, ts[0] - 5, ts[-1] + 5), token_filter="honour")
    f = SwapFetcher(chain)
    assert f.token_filter is None
    for _ in range(2):  # unverified: the window is read unfiltered and compared with a filtered page
        swaps, st = run(f.window(POOL, ts[0] - 10, ts[-1] + 10, 1000, mint=MINT))
        assert not st["filtered"] and st["fetched"] == 54 and len(swaps) == 4
    assert f.token_filter is True and f.filter_checks["reduced"] == 2 and "verified" in f.filter_note
    chain.calls.clear()
    swaps, st = run(f.window(POOL, ts[0] - 10, ts[-1] + 10, 1000, mint=MINT))
    assert st["filtered"] and st["fetched"] == 4 and len(swaps) == 4 and st["complete"]
    assert chain.calls[0]["filtered"]
    # the fixture swaps are a sample, not consecutive: their gaps are read again unfiltered, in vain
    assert st["repaired"] == 0 and all(not c["filtered"] for c in chain.calls[1:])
    # Helius serves the filter at finalized commitment only; unfiltered reads stay at confirmed
    assert chain.calls[0]["commitment"] == "finalized"
    chain.calls.clear()
    run(f.window(POOL, ts[0] - 10, ts[-1] + 10, 1000))  # no mint: no filter
    assert chain.calls[0]["commitment"] == "confirmed"


@pytest.mark.parametrize(
    "mode, windows, note",
    [("ignore", 3, "ignored"), ("drop", 1, "dropped"), ("reject", 1, "rejected")],
)
def test_a_filter_the_provider_ignores_breaks_or_rejects_is_switched_off(mode, windows, note):
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()) + noise(50, ts[0] - 5, ts[-1] + 5), token_filter=mode)
    f = SwapFetcher(chain)
    for _ in range(windows):
        swaps, st = run(f.window(POOL, ts[0] - 10, ts[-1] + 10, 1000, mint=MINT))
        assert st["complete"] and len(swaps) == 4  # the window itself is always whole
    assert f.token_filter is False and note in f.filter_note


def test_a_verified_filter_is_audited_and_dropped_when_it_starts_losing_swaps():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()) + noise(50, ts[0] - 5, ts[-1] + 5))
    f = SwapFetcher(chain)
    f.token_filter = True
    chain.token_filter = "drop"
    for _ in range(19):
        run(f.window(POOL, ts[0] - 10, ts[-1] + 10, 1000, mint=MINT))
    assert f.token_filter is True and f.filter_checks["audits"] == 0
    run(f.window(POOL, ts[0] - 10, ts[-1] + 10, 1000, mint=MINT))  # the 20th filtered window
    assert f.filter_checks["audits"] == 1 and f.token_filter is False


def test_states_scan_past_noise_to_the_newest_swap():
    real = real_swaps()
    ts = times_of(real)  # buy +0, sell +280, buy +545, sell +553
    chain = FakeChain(list(real.values()) + noise(400, ts[0] - 100, ts[-1] + 100))
    f = SwapFetcher(chain, token_filter=False)
    times = [ts[1] + 1, ts[2] - 1, ts[-1] + 50]
    swaps, st = run(f.states(POOL, times, ts[0] - 100))
    assert st["resolved"] == 3 and st["unresolved"] == 0 and st["before_first"] == 0
    assert all(c["sort"] == "desc" and c["limit"] == 100 for c in chain.calls)
    assert st["pages"] == len(chain.calls) <= 4 and st["credits"] == 10 * st["pages"]
    every = sorted((s for tx in real.values() for s in swaps_from_tx(tx, pool=POOL)), key=lambda s: s.order)
    for t in times:
        want = max((s for s in every if s.ts <= t), key=lambda s: s.order)
        got = state_at(swaps, t)
        assert (got.base, got.quote) == (want.base_post, want.quote_post)


def test_states_give_up_within_the_scan_budget():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()) + noise(400, ts[0] - 100, ts[-1] + 100))
    f = SwapFetcher(chain, scan_page=10, scan_pages=1, token_filter=False)
    swaps, st = run(f.states(POOL, [ts[2] - 1], ts[0] - 100))
    assert st["unresolved"] == 1 and st["pages"] == 1 and swaps == []


def test_a_time_before_any_swap_takes_the_first_swaps_pre_state():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()) + noise(20, ts[0] - 50, ts[0] - 1))
    f = SwapFetcher(chain, token_filter=False)
    swaps, st = run(f.states(POOL, [ts[0] - 10], ts[0] - 60))
    assert st["before_first"] == 1 and st["resolved"] == 0
    first = min((s for tx in real.values() for s in swaps_from_tx(tx, pool=POOL)), key=lambda s: s.order)
    got = state_at(swaps, ts[0] - 10)
    assert (got.base, got.quote) == (first.base_pre, first.quote_pre)


def test_a_413_halves_the_page():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()), too_large_above=40)
    f = SwapFetcher(chain, token_filter=False)
    swaps, st = run(f.window(POOL, ts[0] - 10, ts[-1] + 10, max_tx=1000))
    assert st["complete"] and len(swaps) == 4
    assert [c["limit"] for c in chain.calls] == [100, 50, 25]


def test_without_helius_both_reads_fall_back_on_one_signature_listing():
    real = real_swaps()
    ts = times_of(real)
    chain = FakeChain(list(real.values()) + noise(30, ts[0] - 5, ts[-1] + 5), gtfa=False)
    f = SwapFetcher(chain, fallback_max_tx=10)
    swaps, st = run(f.window(POOL, ts[0] - 10, ts[-1] + 10, 1000, mint=MINT, floor_ts=ts[0] - 60))
    assert f.gtfa is False and "Method not found" in f.gtfa_error
    assert st["method"] == "signatures" and st["fetched"] == 10 and not st["complete"]
    pts, pst = run(f.states(POOL, [ts[-1] + 1], ts[0] - 60))
    assert pst["method"] == "signatures" and pst["resolved"] == 1
    assert len(chain.sig_calls) == 1  # the listing was cached for the pool
    assert len([c for c in chain.calls]) == 1  # the provider is not asked again for the run


def test_repeated_other_errors_end_gtfa_after_three():
    chain = FakeChain([], gtfa="internal error")
    f = SwapFetcher(chain, token_filter=False)
    for _ in range(2):
        with pytest.raises(RpcError):
            run(f.window(POOL, 0, 10, 100))
    assert f.gtfa is not False
    swaps, st = run(f.window(POOL, 0, 10, 100))
    assert f.gtfa is False and st["method"] == "signatures"


def test_chain_breaks_count_missing_swaps():
    pairs = []
    for p in sorted(CHAIN.glob("*.json")):
        fx = json.loads(p.read_text())
        (a,), (b,) = (swaps_from_tx(tx, pool=fx["pool"]) for tx in fx["txs"])
        assert chain_breaks([a, b]) == 0
        pairs.append((a, b))
    a, b = pairs[0]
    assert chain_breaks([a, a, b]) == 1


def test_merge_dedupes_and_encode_is_compact():
    real = real_swaps()
    every = [s for tx in real.values() for s in swaps_from_tx(tx, pool=POOL)]
    merged = merge_swaps(every, every[:2])
    assert len(merged) == len({(s.signature, s.ev_index) for s in every}) == 4
    enc = encode_swaps(merged)
    cols = enc["columns"]
    assert cols[0] == "slot" and len(enc["rows"]) == 4 and len(enc["users"]) <= 4
    row = enc["rows"][0]
    assert row[cols.index("side")] in (0, 1) and isinstance(row[cols.index("fee_bps")], list)
    s0 = merged[0]
    assert row[cols.index("vault_delta")] == s0.quote_post - s0.quote_pre and row[cols.index("ix")] in (0, 1)


def test_rpc_error_flags_unsupported_methods():
    assert RpcError(-32601, "Method not found").method_unsupported
    assert not RpcError(-32602, "Invalid params").method_unsupported


def test_a_swap_the_filter_missed_is_read_back_unfiltered():
    """Three consecutive real swaps; the filtered read lacks the middle one (as Helius' index
    once did for a routed version-1 buy). The token-side break gives it away and the slot range
    is read again without the filter."""
    ei = json.loads((CHAIN / "buy_exact_quote_in.json").read_text())
    se = json.loads((CHAIN / "sell.json").read_text())
    pool = ei["pool"]
    a, x = ei["txs"]
    x_again, b = se["txs"]
    assert se["pool"] == pool and x["transaction"]["signatures"] == x_again["transaction"]["signatures"]
    chain = FakeChain([a, x, b], pool=pool, missed={x["transaction"]["signatures"][0]})
    f = SwapFetcher(chain)
    f.token_filter = True
    swaps, st = run(f.window(pool, a["blockTime"] - 1, b["blockTime"] + 1, 1000, mint=MINT))
    assert st["filtered"] and st["fetched"] == 2 and st["repaired"] == 1
    assert len(swaps) == 3 and st["chain_breaks"] == 0 and f.filter_checks["repaired"] == 1
    assert [s.order for s in swaps] == sorted(s.order for s in swaps)
    repair = chain.calls[-1]
    assert not repair["filtered"] and repair["commitment"] == "confirmed"
    # an unfiltered window is never "repaired": a break there is not the filter's doing
    plain, st2 = run(SwapFetcher(FakeChain([a, b], pool=pool), token_filter=False).window(pool, 0, 2e9, 1000))
    assert st2["repaired"] == 0 and st2["chain_breaks"] == 1
