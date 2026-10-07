"""Hypothesis G: a ticket bought once a curve stood at X SOL, sold right after the migration."""

import pytest
from test_sniper import DEV, A, B, path_row, ticket_value

from app.fills import LAMPORTS, sell_ex
from app.graduation import (
    G_MIN_N,
    G_SAMPLE_PER_10K,
    GS_MIN_TRIGGER_S,
    PREREG_G_TS,
    curve_phase,
    pool_after_migration,
    speed,
    summarize,
    ticket_net,
    verdict,
)
from app.sniper import CurvePath, sampled

GRAD = 85.005


def test_trigger_waits_one_slot_and_buys_behind_that_slot():
    steps = [(0, 0, DEV, 1.0), (10, 2, A, 55.0), (12, 3, B, 62.0), (13, 3, A, 64.0), (20, 5, B, GRAD)]
    p = CurvePath(path_row(steps, complete_slot=20))
    ph = curve_phase(p, 60.0)
    # the trade that crossed 60 SOL landed in slot +12; the ticket buys at the end of slot +13
    assert ph["why"] == "grad" and ph["entry_real"] == pytest.approx(64.0)
    # it landed 3 s after the create; the curve then took 8 more slots to complete
    assert (ph["trigger_s"], ph["trigger_slots"], ph["complete_slots"]) == (3, 12, 8)
    assert speed(ph) == "fast" and speed({"why": "grad"}) == "unknown"
    assert speed({**ph, "trigger_s": GS_MIN_TRIGGER_S}) == "slow"
    assert curve_phase(p, 50.0)["entry_real"] == pytest.approx(55.0)  # slot +11 is empty
    assert curve_phase(p, 86.0) is None  # never stood there


def test_a_curve_that_completes_before_the_ticket_lands_is_a_jump():
    steps = [(0, 0, DEV, 1.0), (5, 1, A, 40.0), (9, 2, B, GRAD)]  # 40 -> complete in one buy
    jump = {"why": "jump", "trigger_s": 2, "trigger_slots": 9}
    assert curve_phase(CurvePath(path_row(steps, complete_slot=9)), 60.0) == jump
    steps = [(0, 0, DEV, 1.0), (5, 1, A, 61.0), (6, 2, B, GRAD)]  # completed in the slot after the trigger
    jump = {"why": "jump", "trigger_s": 1, "trigger_slots": 5}
    assert curve_phase(CurvePath(path_row(steps, complete_slot=6)), 60.0) == jump


def test_a_curve_that_fails_is_sold_at_its_last_state():
    steps = [(0, 0, DEV, 1.0), (5, 1, A, 61.0), (8, 2, A, 3.0)]
    ph = curve_phase(CurvePath(path_row(steps)), 60.0)
    expected = (ticket_value(61.0, 3.0) - 0.002) / 0.5 - 1
    assert ph["why"] == "fail" and ph["net"] == pytest.approx(expected, abs=1e-5)
    assert ph["net"] < -0.5  # bought 1.6x above the floor and the curve fell back
    trunc = curve_phase(CurvePath(path_row(steps, truncated=True)), 60.0)
    assert trunc == {"why": "unresolved", "trigger_s": 1, "trigger_slots": 5}


def _survivor(mint="M", liq0=84.87, base0=207.2e6 * 1e6, liq3=86.0, with_base=False, d5=None):
    mark0 = liq0 * LAMPORTS / base0
    cell = {"liquidity_in_sol": liq3, "real_in_sol": liq3 - 17.58, "virtual_in_sol": 17.58}
    if with_base:
        cell["base_in"] = int(liq0 * base0 / liq3)
        cell["pool_fees_bps"] = [2, 93, 30]
    row = {
        "mint": mint,
        "decision": {"d0": {"liquidity_sol": liq0, "mark": mark0}},
        "fills": {"d0_h60": {"1": cell}},
    }
    if d5:
        row["decision"]["d5"] = d5
    return row


def test_the_exit_sells_into_the_pool_three_seconds_after_migration():
    row = _survivor()
    pool = pool_after_migration(row, "t3s")
    assert pool.effective == pytest.approx(86.0 * LAMPORTS, rel=1e-9)
    # constant product from the opening state: the price moved with (86 / 84.87)^2
    assert pool.mark / row["decision"]["d0"]["mark"] == pytest.approx((86.0 / 84.87) ** 2, rel=1e-6)
    exact = pool_after_migration(_survivor(with_base=True), "t3s")
    assert exact.base == pytest.approx(pool.base, rel=1e-6) and exact.fee_bps == 125
    steps = [(0, 0, DEV, 1.0), (10, 2, A, 62.0), (20, 5, B, GRAD)]
    ph = curve_phase(CurvePath(path_row(steps, complete_slot=20)), 60.0)
    recv, _, _, _ = sell_ex(pool, int(ph["dt"]))
    net = ticket_net(ph, row, "t3s")
    assert net == pytest.approx((recv / LAMPORTS - 0.002) / 0.5 - 1, abs=1e-9)
    # from 62 SOL to the graduation price is (115/92)^2 = 1.56x before fees and the pool's move
    assert 0.45 < net < 0.65
    assert ticket_net(ph, None, "t3s") is None  # its pool is harvested a day later
    assert ticket_net(ph, row, "t5m") is None  # no T+5 state in this row
    d5 = {"liquidity_sol": 60.0, "real_sol": 42.42, "mark": 60.0 * LAMPORTS / (295e6 * 1e6)}
    later = ticket_net(ph, _survivor(d5=d5), "t5m")
    assert later < net  # the pool fell over the first five minutes


def test_summary_counts_tickets_and_keeps_the_confirmatory_sample_apart():
    sigs, i = [], 0
    while len(sigs) < G_MIN_N + 2:
        if sampled(f"g{i}", G_SAMPLE_PER_10K):
            sigs.append(f"g{i}")
        i += 1
    # the graduates reached the level slowly, the failures within a minute of their create
    grad = {"why": "grad", "dt": 3.0e12, "entry_real": 61.0, "trigger_s": GS_MIN_TRIGGER_S + 30}
    fail = {"why": "fail", "net": -0.8, "entry_real": 61.0, "trigger_s": GS_MIN_TRIGGER_S - 30}
    results = []
    for n, sig in enumerate(sigs[:G_MIN_N]):
        ph = grad if n % 4 else fail  # 3 graduates for each failure
        results.append(
            {"mint": f"m{n}", "signature": sig, "t0": PREREG_G_TS + n, "g": {"50": ph, "60": ph, "70": ph}}
        )
    results.append({"mint": "early", "signature": sigs[-1], "t0": PREREG_G_TS - 5, "g": {"60": grad}})
    results.append(
        {"mint": "jumped", "signature": sigs[-2], "t0": PREREG_G_TS + 1, "g": {"60": {"why": "jump"}}}
    )
    results.append({"mint": "may", "signature": sigs[-2], "t0": PREREG_G_TS + 1, "mayhem": True, "g": None})
    survivor = [_survivor(mint=f"m{n}") for n in range(G_MIN_N) if n % 4] + [_survivor(mint="early")]
    out = summarize(results, survivor)
    lv = out["levels"]["60"]
    assert lv["reached"] == G_MIN_N + 2 and lv["jump"] == 1 and lv["fail"] == G_MIN_N // 4
    assert lv["p_grad_given_ticket"] == pytest.approx((G_MIN_N * 3 / 4 + 1) / (G_MIN_N + 1))
    pr = out["prereg"]
    assert pr["n"] == G_MIN_N  # the early launch is exploratory, the jump has no ticket
    assert pr["verdict"] in ("PASS", "INCONCLUSIVE", "KILL") and pr["mean"] > 0
    assert lv["cells"]["t3s"]["n"] == G_MIN_N + 1
    sp = lv["by_speed"]
    assert (sp["fast"]["reached"], sp["fast"]["fail"], sp["fast"]["grad"]) == (G_MIN_N // 4, G_MIN_N // 4, 0)
    assert (sp["slow"]["reached"], sp["slow"]["grad"]) == (G_MIN_N * 3 // 4 + 1, G_MIN_N * 3 // 4 + 1)
    assert sp["unknown"]["jump"] == 1 and sp["slow"]["t3s"]["n"] == G_MIN_N * 3 // 4 + 1
    gs = out["prereg_gs"]
    # GS keeps G's sample and criteria but only the slow triggers: 225 confirmatory graduates
    assert gs["n"] == G_MIN_N * 3 // 4 and gs["verdict"] == "WAIT" and gs["min_trigger_s"] == GS_MIN_TRIGGER_S
    assert gs["mean"] > pr["mean"]


def test_verdict_rules():
    base = {"n": G_MIN_N, "top1pct_share": 0.1}
    assert verdict({"n": 5}, [1, 1]) == "WAIT"
    assert verdict({**base, "mean_ci95": [-0.2, -0.01]}, [1, 1]) == "KILL"
    assert verdict({**base, "mean_ci95": [0.01, 0.3]}, [0.1, 0.05]) == "PASS"
    assert verdict({**base, "mean_ci95": [0.01, 0.3]}, [0.1, -0.05]) == "INCONCLUSIVE"


def test_gs_is_judged_once_on_its_first_tickets():
    sigs, i = [], 0
    while len(sigs) < G_MIN_N + 50:
        if sampled(f"s{i}", G_SAMPLE_PER_10K):
            sigs.append(f"s{i}")
        i += 1
    results = []
    for n, sig in enumerate(sigs):
        # the first 300 slow tickets win half their stake, the 50 after them lose everything
        ph = {"why": "fail", "net": 0.5 if n < G_MIN_N else -1.0, "trigger_s": GS_MIN_TRIGGER_S}
        g = {"50": ph, "60": ph, "70": ph}
        results.append({"mint": f"m{n}", "signature": sig, "t0": PREREG_G_TS + n, "g": g})
    out = summarize(results, [])
    gs = out["prereg_gs"]
    assert (gs["n"], gs["n_after"], gs["judged_until"]) == (G_MIN_N, 50, PREREG_G_TS + G_MIN_N - 1)
    assert gs["mean"] == pytest.approx(0.5) and gs["robust_means"] == [pytest.approx(0.5)] * 2
    assert gs["verdict"] == "PASS" and gs["exit_waiting"] == 0
    # G reads every ticket so far
    assert out["prereg"]["n"] == G_MIN_N + 50 and out["prereg"]["mean"] < 0.5
    # a graduate among the first 300 whose pool row is not in yet holds the verdict back
    pending = {"why": "grad", "dt": 3.0e12, "trigger_s": GS_MIN_TRIGGER_S}
    results[10]["g"] = {**results[10]["g"], "60": pending}
    gs = summarize(results, [])["prereg_gs"]
    assert (gs["verdict"], gs["exit_waiting"], gs["judged_until"]) == ("WAIT", 1, PREREG_G_TS + G_MIN_N - 1)
    assert gs["n"] == G_MIN_N - 1
