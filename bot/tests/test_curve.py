from app import curve as bc


def fresh() -> bc.CurveState:
    return bc.CurveState(bc.INITIAL_V_SOL, bc.INITIAL_V_TOKENS)


def test_buy_moves_price_up_and_conserves_k():
    s0 = fresh()
    tokens, s1 = bc.buy(s0, 1.0, fee_bps=125)
    assert tokens > 0
    assert s1.price > s0.price
    assert abs(s0.v_sol * s0.v_tokens - s1.v_sol * s1.v_tokens) < 1e-3
    # 1 SOL minus 1.25% fee goes into the curve
    assert abs(s1.v_sol - (30 + 0.9875)) < 1e-9


def test_roundtrip_loses_exactly_fees():
    s0 = fresh()
    tokens, s1 = bc.buy(s0, 1.0, fee_bps=125)
    sol_back, s2 = bc.sell(s1, tokens, fee_bps=125)
    # buy fee 1.25% then sell fee 1.25% on the remainder
    assert abs(sol_back - 0.9875 * 0.9875) < 1e-9
    assert abs(s2.v_sol - s0.v_sol) < 1e-9


def test_zero_fee_roundtrip_is_lossless():
    s0 = fresh()
    tokens, s1 = bc.buy(s0, 2.0, fee_bps=0)
    sol_back, _ = bc.sell(s1, tokens, fee_bps=0)
    assert abs(sol_back - 2.0) < 1e-9


def test_initial_mcap_is_about_30_sol():
    assert 27 < fresh().market_cap_sol < 29  # 30 * 1e9 / 1.073e9 ≈ 27.96


def test_progress():
    assert fresh().progress_pct == 0
    assert bc.CurveState(bc.GRADUATION_V_SOL, 1).progress_pct == 100
