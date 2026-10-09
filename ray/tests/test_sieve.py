from helpers import Launch, pk, row_of

from app import sieve


def _score(la: Launch, D: int = 120, data=None, row=None):
    row = row or row_of(la)
    dslot = int(row["trades"][-1][0])
    return sieve.score_row(row, dslot, (la.vs, la.vt), D=D, age_s=D + 5, now=la.t0 + D + 5, data=data or {})


def _crowd(la: Launch, n: int, start_slot: int, sizes=(0.21, 0.33, 0.27, 0.38, 0.23, 0.41, 0.29)):
    """n distinct buyers, one per slot, sizes off the trading-terminal presets."""
    for i in range(n):
        la.buy(pk(1_000 + i), sizes[i % len(sizes)], start_slot + 3 * i, la.t0 + 10 + (3 * i) // 4)


def test_the_floor_is_minus_half_at_the_gate():
    assert abs(sieve.floor_net(11.66) + 0.5) < 0.001
    assert sieve.floor_net(5) > -0.5 > sieve.floor_net(20) > sieve.floor_net(60)


def test_a_dev_holding_three_percent_is_avoid():
    la = Launch(100)
    la.buy(la.dev, 5.0, la.s0, la.t0, in_create=True)
    _crowd(la, 30, la.s0 + 30)
    sc = _score(la)
    assert la.real > sieve.GATE_E
    assert sc["verdict"] == "TRANH" and "Dev + creator" in sc["summary"]
    dev = next(f for f in sc["active"] if f["id"] == "SH-DEV-1")
    assert dev["fired"] and dev["scored"] and dev["raw"] > 0.10
    assert sc["risk"]["pct"] >= 0.80 and sc["f0"]["ok"]
    assert sc["data"]["chain_ok"] and sc["frozen_ok"]


def test_a_same_size_wave_is_avoid():
    la = Launch(200)
    tok = la.buy(la.dev, 0.5, la.s0, la.t0, in_create=True)
    la.sell(la.dev, tok, la.s0 + 4, la.t0 + 2)
    for i in range(4):  # four wallets, one slot, the same 1 SOL
        la.buy(pk(500 + i), 1.0, la.s0 + 20, la.t0 + 6, idx=10 + i)
    _crowd(la, 35, la.s0 + 40)
    assert la.real > sieve.GATE_E
    sc = _score(la)
    wave = next(f for f in sc["active"] if f["id"] == "N-MMAAS-WAVE-STREAM")
    assert wave["fired"] and wave["raw"] == 4
    assert sc["verdict"] == "TRANH"


def test_no_flag_is_not_a_buy_signal():
    la = Launch(300)
    tok = la.buy(la.dev, 1.0, la.s0, la.t0, in_create=True)
    la.sell(la.dev, tok, la.s0 + 4, la.t0 + 2)
    _crowd(la, 45, la.s0 + 30)
    sc = _score(la)
    assert not any(f["fired"] for f in sc["active"] + sc["shadow"]), [f for f in sc["active"] + sc["shadow"]]
    assert sc["verdict"] == "KHONG_THAY_CO"
    assert "KHÔNG phải tín hiệu mua" in sc["summary"]
    assert sc["risk"]["pct"] == 33 / 47  # 13-30 SOL at 2 minutes on the founding pool


def test_a_gap_in_the_trades_leaves_the_dev_filter_unscored():
    la = Launch(400)
    la.buy(la.dev, 5.0, la.s0, la.t0, in_create=True)
    _crowd(la, 30, la.s0 + 30)
    row = row_of(la)
    row["trades"] = row["trades"][:10] + row["trades"][11:]
    sc = _score(la, row=row)
    dev = next(f for f in sc["active"] if f["id"] == "SH-DEV-1")
    assert not dev["scored"] and not dev["fired"]
    assert sc["verdict"] == "THIEU_DU_LIEU" and not sc["data"]["chain_ok"]


def test_below_the_gate_no_veto_applies():
    la = Launch(500)
    la.buy(la.dev, 2.0, la.s0, la.t0, in_create=True)
    _crowd(la, 15, la.s0 + 30)
    assert la.real < sieve.GATE_E
    sc = _score(la)
    assert sc["verdict"] == "DUOI_CONG" and sc["floor"] > -0.5
    light = sieve.light_score(row_of(la), la.real, 120, 125, la.t0 + 125, "DUOI_CONG")
    assert light["verdict_vi"] == "DƯỚI CỔNG" and light["risk"]["pct"] is None


def test_risk_takes_the_band_cell_or_the_fired_filter():
    r = sieve.risk(20.0, 125, [])
    assert (r["k"], r["n"]) == (33, 47) and "13-30" in r["basis"]
    r = sieve.risk(20.0, 125, ["N-MMAAS-WAVE-STREAM"])
    assert (r["k"], r["n"]) == (26, 29) and "N-MMAAS-WAVE-STREAM" in r["basis"]
    r = sieve.risk(40.0, 610, [])  # 30-70 at 10 minutes has 9 rows: the whole band is used
    assert (r["k"], r["n"]) == (21, 45)
    assert sieve.risk(80.0, 125, [])["pct"] is None


def test_the_filters_are_the_frozen_ones():
    assert sieve.FROZEN_PROBLEMS == []
    assert sieve.ACTIVE == ["SH-DEV-1", "N-MMAAS-WAVE-STREAM"]
    assert "N-WM-EXIT2-v2b" not in sieve.SHADOW  # memory filters need every launch's trades
    reg = sieve.registry()
    assert {f["id"] for f in reg} >= set(sieve.ACTIVE + sieve.SHADOW)
