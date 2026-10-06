"""Exploration tables: terciles with the mean and the rug share next to the median."""

import pytest

from app import prereg, sniper
from app.explore import RUG, explore_c, explore_s, feature_table, stats
from app.prereg import PREREG_TS, RULES, evaluate, rule_verdict

WSOL = "So11111111111111111111111111111111111111112"


def test_stats_show_what_a_median_hides():
    # nine small wins and one rug: the median is positive, the mean is not
    st = stats([0.03] * 9 + [-1.0])
    assert st["median"] == pytest.approx(0.03) and st["mean"] == pytest.approx(-0.073)
    assert st["win"] == pytest.approx(0.9) and st["rug"] == pytest.approx(0.1) and RUG == -0.9


def test_feature_table_terciles_and_halves():
    pts = [(float(i), (0.1 if i < 30 else -0.1), float(i % 2)) for i in range(90)]
    t = feature_table(pts)
    assert [b["n"] for b in t] == [30, 30, 30] and t[0]["range"] == [None, 30.0] and t[2]["range"][1] is None
    assert t[0]["mean"] == pytest.approx(0.1) and t[1]["mean"] == pytest.approx(-0.1)
    assert t[0]["mean_early"] == pytest.approx(0.1) and t[0]["mean_late"] == pytest.approx(0.1)
    flags = feature_table([(float(i % 2), 0.0, 0.0) for i in range(40)])  # a 0/1 feature: one bucket each
    assert [b["range"] for b in flags] == [[0.0, 0.0], [1.0, 1.0]]
    assert feature_table(pts[:10]) is None


def _row(mint, t, net, real=50.0, mark0=1.0, mark30=1.0, dev_buy=0.5):
    return {
        "mint": mint,
        "fills_t0": t,
        "quote_mint": WSOL,
        "fills_version": 2,
        "fills": {"d30_h60": {"1": {"net": net}}},
        "decision": {
            "d0": {"mark": mark0, "real_sol": 67.0},
            "d30": {"mark": mark30, "real_sol": real, "last_trade_age_s": 3},
        },
        "curve": {"found": True, "dev_buy_sol": dev_buy},
    }


def test_explore_c_splits_the_window_from_earlier_rows():
    rows = [
        _row(f"w{i}", PREREG_TS + i, -1.0 if i % 3 == 0 else 0.02, dev_buy=85.0 if i % 3 == 0 else 0.5)
        for i in range(60)
    ]
    rows += [_row(f"b{i}", PREREG_TS - 100 - i, 0.1) for i in range(40)]
    rows += [_row("thin", PREREG_TS + 5, 0.5, real=2.0)]  # not C2
    out = explore_c(rows)
    win, before = out["samples"]["window"], out["samples"]["before"]
    assert win["all"]["n"] == 60 and before["all"]["n"] == 40
    sg = {b["range"][0]: b for b in win["features"]["self_graduated"]["buckets"]}
    assert sg[1.0]["rug"] == 1.0 and sg[0.0]["rug"] == 0.0 and sg[0.0]["mean"] == pytest.approx(0.02)
    assert win["features"]["holders_top10"]["buckets"] is None  # no snapshot on these rows


def test_explore_s_uses_entry_features_of_classic_tickets():
    i = sniper.CELLS.index(sniper.PRIMARY_CELL)
    rows = []
    for k in range(45):
        nets = [None] * len(sniper.CELLS)
        nets[i] = 0.5 if k < 15 else -0.2
        rows.append(
            {
                "mint": f"m{k}",
                "t0": sniper.PREREG_S_TS + k,
                "sim_version": sniper.SIM_VERSION,
                "mayhem": k == 44,
                "nets": nets,
                "entry": {"price_x": 1.0 + k / 10, "dev_sold": k % 2 == 0},
            }
        )
    out = explore_s(rows)
    cell = out["samples"]["window"][sniper.PRIMARY_CELL]
    assert cell["all"]["n"] == 44  # the mayhem launch is left out
    px = cell["features"]["price_x"]["buckets"]
    assert px[0]["mean"] == pytest.approx(0.5) and px[-1]["mean"] == pytest.approx(-0.2)
    assert [b["range"] for b in cell["features"]["dev_sold"]["buckets"]] == [[0.0, 0.0], [1.0, 1.0]]


def test_rules_need_the_median_interval_above_zero(monkeypatch):
    base = {"n": 400, "median": 0.03, "win_rate": 0.6, "top2pct_share": 0.1}
    assert rule_verdict(base, (0.01, 0.05))["status"] == "PASS"
    assert rule_verdict(base, (-0.01, 0.05))["status"] == "INCONCLUSIVE"
    assert rule_verdict({**base, "median": -0.05}, (-0.1, 0.0))["status"] == "KILL"
    # 52% small wins, 48% losses: C's criteria say PASS, but the median's interval reaches below 0
    rows = [_row(f"r{i}", PREREG_TS + 3600 + i, 0.03 if i % 25 < 13 else -0.05) for i in range(310)]
    rule = {
        "name": "R-test",
        "desc": "test",
        "since": PREREG_TS + 3600,
        "member": lambda r: True,
        "rule": True,
    }
    monkeypatch.setattr(prereg, "RULES", [*RULES, rule])
    h = {x["name"]: x for x in evaluate(rows)["hypotheses"]}
    assert h["C*"]["verdict"]["status"] == "PASS" and h["C*"]["mean"] < 0.03
    assert h["R-test"]["verdict"]["status"] == "INCONCLUSIVE" and h["R-test"]["median_ci95"][0] < 0
    assert h["R-test"]["rug_share"] == 0 and h["C"]["n"] == 310
