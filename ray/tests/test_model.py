import asyncio
import json
import random

import pytest
from helpers import Cfg, FakeRpc

from app import model as M
from app.candidates import scan
from app.engine import Engine, ScoreBook
from app.outcome import journal_line

DAY = 86_400
T0 = 1_791_590_400.0  # 2026-10-10 00:00 UTC
NETS = {"trap": -0.8, "winner": 1.5, "neutral": 0.0}


def _features(rng, crowd):
    f = {k: rng.random() for k in M.FEATURES}
    f.update(n120=rng.randint(5, 400), trades60=rng.randint(2, 200), n_early=rng.randint(1, 120))
    f.update(dev_prior=rng.randint(0, 3), dev_traps=-1.0, wallets120=crowd)
    return f


def _lines(n, start, seed=1, effect=True, span=DAY):
    """`n` settled decision-time rows over `span` seconds: with `effect`, a crowded curve (>= 100
    wallets in 2 minutes) is a trap 80% of the time and a quiet one 35%; without, 50% either way."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        crowd = rng.choice([rng.randint(100, 250), rng.randint(5, 60)])
        p = (0.80 if crowd >= 100 else 0.35) if effect else 0.5
        label = "trap" if rng.random() < p else "winner" if rng.random() < 0.2 else "neutral"
        at = start + span * i / n
        out.append(
            {
                "mint": f"m{seed}-{i}",
                "key": "D120",
                "D": 120,
                "score_at": at,
                "entry_at": at,
                "band": "13-30",
                "status": "ok",
                "label": label,
                "net": NETS[label],
                "features": _features(rng, crowd),
                "fired": {"active": [], "shadow": [], "info": []},
                "unscored": [],
            }
        )
    return out


def test_inputs_need_every_feature_and_a_band():
    f = {k: 1.0 for k in M.FEATURES} | {"dev_traps": -1.0}
    x = M.inputs(f, "13-30", 300)
    assert len(x) == len(M.names()) == 25
    i = M.names().index("dev_known")
    assert x[i] == 0.0 and x[i - 1] == 0.0  # an unknown dev: no value, flag off
    assert x[M.names().index("band_13-30")] == 1.0 and x[M.names().index("D300")] == 1.0
    assert M.inputs(f, None, 120) is None and M.inputs({"n120": 3}, "13-30", 120) is None


def test_too_few_rows_give_no_model():
    assert M.fit(_lines(200, T0), T0 + DAY) is None


def test_the_model_learns_what_marks_traps_and_is_calibrated():
    lines = _lines(1200, T0)
    m = M.fit(lines, T0 + DAY + 3600)
    assert m["n"] == 1200 and len(m["w"]) == 26
    base = dict(lines[0]["features"])
    hi = M.predict(m, base | {"wallets120": 180}, "13-30", 120)
    lo = M.predict(m, base | {"wallets120": 20}, "13-30", 120)
    assert hi > 0.65 and lo < 0.45
    preds = [M.predict(m, r["features"], r["band"], r["D"]) for r in lines]
    traps = sum(r["label"] == "trap" for r in lines)
    assert sum(preds) == pytest.approx(traps, rel=0.02)  # the intercept is free: calibrated in the mean
    assert M.factors(m)["up"][0]["name"] == "wallets120"


def _scored(lines, model_better):
    for r in lines:
        crowd = r["features"]["wallets120"] >= 100
        good = 0.8 if crowd else 0.35
        r["model_p"] = good if model_better else 1 - good
        r["base_risk"] = 0.55
    return lines


def test_the_switch_needs_two_full_days_where_the_model_did_better():
    one = _scored(_lines(400, T0, seed=2), True)
    two = _scored(_lines(400, T0 + DAY, seed=3), True)
    ev = M.held_out(one, T0 + DAY + 600)  # one full day so far
    assert ev["gain"] > 0 and ev["gain_ci"][0] > 0 and ev["qualified_days"] == 1 and not ev["active"]
    ev = M.held_out(one + two, T0 + 2 * DAY + 600)
    assert ev["qualified_days"] == 2 and ev["active"]
    assert [d["day"] for d in ev["days"]] == ["2026-10-10", "2026-10-11"]
    cal = {c["lo"]: c for c in ev["calibration"]}
    assert cal[0.8]["observed"] == pytest.approx(0.8, abs=0.08)
    worse = _scored(_lines(400, T0 + 2 * DAY, seed=4), False)
    ev = M.held_out(one + two + worse, T0 + 3 * DAY + 600)
    assert not ev["active"]  # the latest full day went the other way


def test_the_scan_finds_a_planted_rule_and_nothing_in_noise():
    res = scan(_lines(900, T0), T0 + DAY + 600, [])
    found = {(c["feature"], c["dir"]) for c in res["candidates"]}
    assert ("wallets120", ">=") in found
    crowd = next(c for c in res["candidates"] if c["feature"] == "wallets120")
    assert crowd["later"]["saved"] > 0.2 and crowd["measured_by"] == "RAY-CROWD-v1" and crowd["p"] < 0.01
    noise = scan(_lines(900, T0, seed=9, effect=False), T0 + DAY + 600, [])
    assert noise["candidates"] == [] and noise["rows"] == 900
    assert "chưa đủ dữ liệu" in scan(_lines(100, T0), T0 + DAY, [])["note"]


def test_the_scan_counts_rows_registered_filters_already_flag():
    lines = _lines(900, T0)
    for r in lines:
        if r["features"]["wallets120"] >= 100:
            r["fired"]["shadow"] = ["RAY-HOT-v1"]
    res = scan(lines, T0 + DAY + 600, ["RAY-HOT-v1"])
    crowd = next(c for c in res["candidates"] if c["feature"] == "wallets120")
    assert crowd["overlap"] == 1.0


def _score(p_band=0.73):
    return {
        "mint": "M1",
        "D": 120,
        "real_d": 20.0,
        "at": T0,
        "risk": {"pct": p_band, "n": 300, "basis": "coin mới"},
        "entry": {"at": T0},
    }


def test_the_engine_records_the_model_and_shows_it_only_once_switched(tmp_path):
    eng = Engine(Cfg(), FakeRpc(), ScoreBook(tmp_path), clock=lambda: T0 + DAY)
    feats = _lines(1, T0)[0]["features"] | {"wallets120": 200}
    sc = _score()
    eng._apply_model(sc, feats, 125)
    assert "model" not in sc and sc["risk"]["base_pct"] == 0.73  # no model yet
    eng.model = M.fit(_lines(1200, T0 - DAY), T0)
    sc = _score()
    eng._apply_model(sc, feats, 125)
    p = sc["model"]["p"]
    assert p > 0.65 and not sc["model"]["active"] and sc["risk"]["pct"] == 0.73
    line = journal_line(sc, {"status": "ok", "label": "trap", "net": -0.8})
    assert line["model_p"] == p and line["base_risk"] == 0.73 and line["risk"] == 0.73
    eng.model_eval = {"active": True, "qualified_days": 2}
    sc = _score()
    eng._apply_model(sc, feats, 125)
    assert sc["risk"]["pct"] == pytest.approx(p, abs=1e-4) and sc["risk"]["model"]
    assert sc["risk"]["base_pct"] == 0.73
    line = journal_line(sc, {"status": "ok", "label": "trap", "net": -0.8})
    assert line["base_risk"] == 0.73 and line["risk"] == pytest.approx(p, abs=1e-4)


def test_the_hourly_refit_saves_the_model_and_scans(tmp_path):
    book = ScoreBook(tmp_path)
    for r in _lines(900, T0):
        book.add_outcome(r)
    eng = Engine(Cfg(), FakeRpc(), book, clock=lambda: T0 + DAY + 600)
    m = asyncio.run(eng.refit_model())
    assert m["n"] == 900 and json.loads((book.dir / "model.json").read_text())["w"] == m["w"]
    assert eng.candidates["candidates"] and eng.model_eval["rows"] == 0  # no score carried model_p yet
    view = eng.model_view()
    assert view["n"] == 900 and not view["active"] and view["factors"]["up"]
    assert eng.status()["model"]["candidates"] == len(eng.candidates["candidates"])
