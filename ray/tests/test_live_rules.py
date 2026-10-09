import asyncio

import pytest
from helpers import Cfg, FakeRpc, Launch, pk, row_of

from app import sieve
from app.engine import Engine, ScoreBook
from app.live_rules import LiveRules, filter_record

NOW = 1_800_000_000.0
IDS = sieve.ACTIVE + sieve.SHADOW + sieve.INFO
NETS = {"trap": -0.8, "winner": 1.5, "neutral": 0.0}  # the ticket's net by label, for these rows


def _rows(fid, on, on_traps, on_wins, off, off_traps, off_wins, band="13-30", D=120, tag="x"):
    """`on` rows where `fid` fired and `off` where it did not, each from its own launch."""
    out = []
    for i in range(on + off):
        fired = i < on
        j = i if fired else i - on
        traps, wins = (on_traps, on_wins) if fired else (off_traps, off_wins)
        label = "trap" if j < traps else "winner" if j < traps + wins else "neutral"
        out.append(
            {
                "mint": f"{tag}{fid}{i}",
                "key": f"D{D}",
                "D": D,
                "score_at": NOW - 1000 - i,
                "entry_at": NOW - 1000 - i,
                "band": band,
                "status": "ok",
                "label": label,
                "net": NETS[label],
                "fired": {"active": [fid] if fired else [], "shadow": [], "info": []},
                "unscored": [],
            }
        )
    return out


def test_a_filter_keeps_deciding_only_while_its_rows_lose_more_than_the_band():
    works = _rows("SH-SG-1", 40, 32, 2, 60, 36, 9)  # its rows: -0.565 on average, the band's -0.255
    rec = filter_record(works, "SH-SG-1")
    assert rec["status"] == "ok" and rec["saved"] == pytest.approx(0.31) and rec["saved_ci"][0] > 0
    reversed_ = _rows("N-MMAAS-SPLDIST", 40, 16, 12, 60, 36, 6)
    rec = filter_record(reversed_, "N-MMAAS-SPLDIST")
    assert rec["status"] == "suspended" and rec["trap_on"] == 0.4 and rec["trap_exp"] == pytest.approx(0.6)
    assert rec["net_on"] > rec["net_exp"]  # its rows did better: it blocks the winners
    more_winners = _rows("SH-DEV-1", 40, 32, 10, 60, 36, 6)  # traps fine, but the winners pay for them
    assert filter_record(more_winners, "SH-DEV-1")["status"] == "suspended"
    assert filter_record(_rows("SH-DEV-1", 20, 18, 0, 60, 36, 6), "SH-DEV-1")["status"] == "unproven"


def test_the_risk_comes_from_new_launches_once_there_are_enough():
    rules = LiveRules()
    rules.refresh(_rows("SH-DEV-1", 40, 16, 12, 60, 45, 6), NOW, IDS)
    assert not rules.allows("SH-DEV-1")  # suspended
    assert not rules.allows("SH-SG-1")  # never fired here: unproven, so silent
    n, k, basis, net = rules.base("13-30", 120)
    assert (n, k) == (100, 61) and "coin mới" in basis and net == pytest.approx((-48.8 + 27) / 100)
    assert [t["D"] for t in rules.by_time("13-30")] == [120]
    assert rules.base("13-30", 300)[0] == 100  # no 5-minute rows yet: the band
    assert rules.base("30-70", 120) is None  # nothing: the founding pool
    r = sieve.risk(20.0, 125, [], rules)
    assert r["live"] and r["pct"] == pytest.approx(0.61) and r["net_mean"] < 0 and r["by_time"][0]["n"] == 100
    assert not sieve.risk(40.0, 125, [], rules)["live"]
    assert rules.snapshot()["suspended"] == ["SH-DEV-1"]


def test_a_suspended_filter_is_shown_but_sets_no_verdict():
    la = Launch(100)
    la.buy(la.dev, 5.0, la.s0, la.t0, in_create=True)
    for i in range(30):
        la.buy(pk(1_000 + i), (0.21, 0.33, 0.27, 0.38)[i % 4], la.s0 + 30 + 3 * i, la.t0 + 10 + (3 * i) // 4)
    row = row_of(la)
    dslot = int(row["trades"][-1][0])

    def score(rules):
        entry = (la.vs, la.vt)
        return sieve.score_row(row, dslot, entry, D=120, age_s=125, now=la.t0 + 125, data={}, rules=rules)

    assert score(None)["verdict"] == "TRANH"
    rules = LiveRules()
    rules.refresh(_rows("SH-DEV-1", 40, 16, 12, 60, 45, 6), NOW, IDS)
    sc = score(rules)
    dev = next(f for f in sc["active"] if f["id"] == "SH-DEV-1")
    assert dev["fired"] and not dev["deciding"] and dev["live"]["status"] == "suspended"
    assert sc["verdict"] != "TRANH" and "chưa được coin mới xác nhận" in sc["summary"] and sc["risk"]["live"]


def test_the_engine_reads_the_rule_from_its_journal(tmp_path):
    book = ScoreBook(tmp_path)
    for r in _rows("SH-DEV-1", 40, 16, 12, 60, 45, 6):
        book.add_outcome(r)
    eng = Engine(Cfg(), FakeRpc(), book, clock=lambda: NOW)
    assert asyncio.run(eng.refresh_rules()) == 100
    assert eng.status()["rules"]["suspended"] == ["SH-DEV-1"]


def test_only_a_filter_new_launches_confirm_decides():
    rules = LiveRules()
    rules.refresh(_rows("SH-SG-1", 40, 32, 2, 60, 36, 9), NOW, IDS)
    assert rules.allows("SH-SG-1")
    assert not rules.allows("SH-DEV-1") and not LiveRules().allows("SH-SG-1")  # no record: silent


def test_entering_needs_evidence_and_leaving_needs_it_gone():
    weak = _rows("SH-SG-1", 40, 24, 2, 60, 36, 6)  # its rows 7.5 points worse than the band's
    assert filter_record(weak, "SH-SG-1")["saved"] == pytest.approx(0.075)
    assert filter_record(weak, "SH-SG-1")["status"] == "suspended"
    assert filter_record(weak, "SH-SG-1", was_ok=True)["status"] == "ok"
    thin = _rows("SH-SG-1", 30, 22, 2, 60, 36, 6)  # 15.7 points, but the interval reaches below zero
    rec = filter_record(thin, "SH-SG-1")
    assert rec["saved"] >= 0.10 and rec["saved_ci"][0] <= 0 and rec["status"] == "suspended"
    rules = LiveRules()
    rules.refresh(_rows("SH-SG-1", 40, 32, 2, 60, 36, 9), NOW, IDS)
    assert rules.allows("SH-SG-1")
    rules.refresh(weak, NOW, IDS)
    assert rules.allows("SH-SG-1")  # still above the keeping bar
    rules.refresh(_rows("SH-SG-1", 40, 20, 2, 60, 36, 6), NOW, IDS)  # as the band
    assert not rules.allows("SH-SG-1")


def _score_launch(la):
    row = row_of(la)
    dslot = int(row["trades"][-1][0])
    return sieve.score_row(row, dslot, (la.vs, la.vt), D=120, age_s=125, now=la.t0 + 125, data={})


def test_a_hot_curve_and_a_washed_one_fire_the_new_filters():
    assert {"RAY-HOT-v1", "RAY-WASH-v1"} <= set(sieve.SHADOW) and sieve.FROZEN_PROBLEMS == []
    hot = Launch(600)
    hot.buy(hot.dev, 2.0, hot.s0, hot.t0, in_create=True)
    for i in range(320):  # 320 trades in the last 320 slots (~86 s)
        hot.buy(pk(5_000 + i), 0.05, hot.s0 + 500 + i, hot.t0 + 135 + i // 4)
    flag = next(f for f in _score_launch(hot)["shadow"] if f["id"] == "RAY-HOT-v1")
    assert flag["fired"] and flag["raw"] == 320
    wash = Launch(700)
    wash.buy(wash.dev, 1.0, wash.s0, wash.t0, in_create=True)
    for i in range(40):
        wash.buy(pk(6_000 + i), 0.3, wash.s0 + 20 + i, wash.t0 + 6 + i // 4)
    slot = wash.s0 + 100
    for w in range(5):  # five wallets buying and selling back, again and again
        for _ in range(2):
            tok = wash.buy(pk(7_000 + w), 1.0, slot, wash.t0 + 30)
            wash.sell(pk(7_000 + w), tok, slot + 1, wash.t0 + 30)
            slot += 2
        wash.buy(pk(7_000 + w), 1.0, slot, wash.t0 + 31)
        slot += 1
    sc = _score_launch(wash)
    flag = next(f for f in sc["shadow"] if f["id"] == "RAY-WASH-v1")
    assert wash.real >= 11.73 and flag["fired"] and flag["raw"] >= 0.30
